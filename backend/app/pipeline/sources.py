"""Step `score_sources`: research findings → `Source` rows (the evidence store).

* Reliability tiers come from deterministic domain/channel rules first; sites and
  channels the rules don't know are tiered by QC_MODEL in one cached call (the
  reason says "LLM-assessed"). If that call fails they stay tier 4.
* Source ids (S1..Sn) are stable: a URL that was S3 stays S3 across re-runs,
  so citations in older lesson versions keep pointing at the right source.
* Rows are never deleted. The step output lists which sids belong to the
  current research run; `generate` only uses those.
"""

import logging
from typing import Any
from urllib.parse import urlparse

from sqlmodel import select

from app.models import Source, SourceType
from app.pipeline.cache import cached_call
from app.pipeline.context import StepContext, StepError
from app.providers.errors import ProviderError
from app.providers.llm import LLMOutputError, generate_structured
from app.schemas import DomainTiers

log = logging.getLogger(__name__)

# (domain suffix, tier, reason). The first matching rule wins, so order matters.
DOMAIN_RULES: list[tuple[str, int, str]] = [
    # Tier 1 — standards bodies, specs, official documentation, government
    ("rfc-editor.org", 1, "IETF RFC (official standard)"),
    ("ietf.org", 1, "IETF (standards body)"),
    ("w3.org", 1, "W3C (standards body)"),
    ("whatwg.org", 1, "WHATWG (living standard)"),
    ("developer.mozilla.org", 1, "MDN Web Docs (official web platform documentation)"),
    ("docs.python.org", 1, "Official Python documentation"),
    ("iso.org", 1, "ISO (standards body)"),
    ("rbi.org.in", 1, "Reserve Bank of India (official regulator)"),
    ("sec.gov", 1, "US SEC (official regulator)"),
    (".gov", 1, "Government website"),
    (".gov.in", 1, "Government website"),
    (".gov.uk", 1, "Government website"),
    # Tier 2 — universities, established publishers, reputable textbooks
    (".edu", 2, "University website"),
    (".ac.uk", 2, "University website"),
    (".ac.in", 2, "University website"),
    ("openstax.org", 2, "OpenStax (peer-reviewed open textbooks)"),
    ("britannica.com", 2, "Encyclopaedia Britannica (established publisher)"),
    ("oreilly.com", 2, "O'Reilly Media (established technical publisher)"),
    ("springer.com", 2, "Springer (academic publisher)"),
    ("cambridge.org", 2, "Cambridge University Press"),
    ("oup.com", 2, "Oxford University Press"),
    # Tier 3 — well-known tech/education sites
    ("wikipedia.org", 3, "Wikipedia (well-known, community-edited reference)"),
    ("khanacademy.org", 3, "Khan Academy (well-known education site)"),
    ("investopedia.com", 3, "Investopedia (well-known finance education site)"),
    ("freecodecamp.org", 3, "freeCodeCamp (well-known tech education site)"),
    ("geeksforgeeks.org", 3, "GeeksforGeeks (well-known tech education site)"),
    ("w3schools.com", 3, "W3Schools (well-known tech education site)"),
    ("digitalocean.com", 3, "DigitalOcean tutorials (well-known tech site)"),
    ("cloudflare.com", 3, "Cloudflare Learning Center (well-known tech site)"),
    ("ibm.com", 3, "IBM documentation/articles (well-known tech site)"),
    ("learn.microsoft.com", 3, "Microsoft Learn (well-known tech site)"),
    # Tier 4 — explicitly community / blog platforms
    ("stackoverflow.com", 4, "Q&A forum"),
    ("reddit.com", 4, "Forum"),
    ("medium.com", 4, "Blog platform"),
    ("dev.to", 4, "Blog platform"),
    ("quora.com", 4, "Q&A forum"),
]

# YouTube channels with a strong educational track record.
CHANNEL_RULES: dict[str, tuple[int, str]] = {
    "mit opencourseware": (2, "MIT OpenCourseWare (university channel)"),
    "cs50": (2, "Harvard CS50 (university channel)"),
    "khan academy": (3, "Khan Academy (well-known education channel)"),
    "crashcourse": (3, "CrashCourse (well-known education channel)"),
    "freecodecamp.org": (3, "freeCodeCamp (well-known tech education channel)"),
}


def host_of(url: str | None) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.") if url else ""


def _host_matches(host: str, rule: str) -> bool:
    if rule.startswith("."):  # TLD-style rule, e.g. ".edu"
        return host.endswith(rule)
    return host == rule or host.endswith("." + rule)  # domain and its subdomains


def rule_for_host(host: str) -> tuple[int, str] | None:
    for rule, tier, reason in DOMAIN_RULES:
        if _host_matches(host, rule):
            return tier, reason
    return None


def tier_for_url(url: str | None) -> tuple[int, str]:
    host = host_of(url)
    return rule_for_host(host) or (4, f"Unknown site ({host or 'no URL'}); not on the reviewed list")


def rule_for_channel(channel: str) -> tuple[int, str] | None:
    return CHANNEL_RULES.get(channel.strip().lower())


def tier_for_channel(channel: str) -> tuple[int, str]:
    return rule_for_channel(channel) or (4, f"YouTube channel '{channel or 'unknown'}' is not on the reviewed list")


# Phrases a page uses about ITSELF when it is out of date. Checked only near the top of the page.
# (Not plain "obsolete": RFC 9110's abstract says it "obsoletes RFCs 2818, 7231...".)
OUTDATED_PHRASES = [
    "historic document", "not accurate anymore", "no longer accurate", "no longer maintained",
    "this page is obsolete", "this document is obsolete", "this page is deprecated", "this page is outdated",
]


def self_declared_outdated(text: str) -> str | None:
    head = text[:800].lower()
    return next((p for p in OUTDATED_PHRASES if p in head), None)


def book_key(title: str, authors: list[str]) -> str:
    return f"book:{title.strip().lower()}|{','.join(a.strip().lower() for a in authors)}"


# ---------------------------------------------------------------------------
# LLM-assisted tiers for sites/channels the rules don't know
# ---------------------------------------------------------------------------

TIER_SYSTEM = "You assess how trustworthy information sources are for school and university teaching material."
CHANNEL_PREFIX = "YouTube channel: "


def _tier_prompt(topic: str, names: list[str], examples: dict[str, str]) -> str:
    lines = "\n".join(f"- {n} (page: {examples[n]!r})" if examples.get(n) else f"- {n}" for n in names)
    return f"""Assign a reliability tier to each source used for a lesson on "{topic}".

Tiers:
1 = standards bodies, specifications, the official documentation of the technology or organisation itself,
    government and regulator websites
2 = universities, established publishers, reputable textbooks and encyclopaedias
3 = well-known, generally reliable technology / education / finance sites and channels
4 = personal blogs, forums, content farms, marketing pages, anything you do not recognise
When unsure, choose the higher number (less trusted). Do not reward a site for its name alone.

NAMES:
{lines}

Return one item per name, with "name" copied exactly (without the "(page: ...)" part)."""


def llm_tiers(ctx: StepContext, names: list[str], examples: dict[str, str]) -> dict[str, tuple[int, str]]:
    """Ask QC_MODEL to tier unknown hosts/channels. Never fails the step: returns {} on error."""
    if not names or not ctx.settings.llm_domain_tiering:
        return {}
    llm = ctx.providers.qc_llm
    names = sorted(set(names))
    try:
        result = cached_call(
            f"{llm.name}.{llm.model}.tiers", {"names": names},
            lambda: generate_structured(llm, _tier_prompt(ctx.lesson.title, names, examples), DomainTiers,
                                        system=TIER_SYSTEM, max_repairs=ctx.settings.llm_max_repairs),
            DomainTiers, enabled=ctx.settings.cache_enabled,
        )
    except (ProviderError, LLMOutputError) as err:
        log.warning("LLM tiering failed (%s); unknown sources stay tier 4", err)
        return {}
    wanted = set(names)
    model = llm.model or llm.name
    return {i.name: (i.tier, f"LLM-assessed by {model}: {i.reason}") for i in result.items if i.name in wanted}


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------


def _video_excerpt(video: dict[str, Any]) -> str:
    """Evidence text for a video: what it was verified to say, then transcript, then description."""
    relevance = video.get("relevance", {})
    parts = []
    if relevance.get("key_points"):
        points = "\n".join(f"- {p}" for p in relevance["key_points"])
        parts.append(f"Key points stated in the video (checked via {relevance.get('method')}):\n{points}")
    if relevance.get("transcript_excerpt"):
        parts.append(f"Transcript excerpt:\n{relevance['transcript_excerpt']}")
    if video.get("description"):
        parts.append(f"Channel's description:\n{video['description']}")
    return "\n\n".join(parts)


def run_score_sources(ctx: StepContext) -> dict[str, Any]:
    web = ctx.require("research_web")
    youtube = ctx.output_of("research_youtube") or {}  # optional step
    books = ctx.output_of("research_books") or {}  # optional step
    max_chars = ctx.settings.excerpt_chars_stored
    pages = web.get("pages", [])
    videos = youtube.get("kept", [])

    # 1. Tiers. The LLM call happens before any DB writes (the cache writes on its own connection).
    unknown_hosts = {host_of(p["url"]): p.get("title", "") for p in pages if rule_for_host(host_of(p["url"])) is None}
    unknown_channels = {CHANNEL_PREFIX + v.get("channel_title", ""): v["title"] for v in videos
                        if rule_for_channel(v.get("channel_title", "")) is None}
    assessed = llm_tiers(ctx, [*unknown_hosts, *unknown_channels], {**unknown_hosts, **unknown_channels})

    def web_tier(url: str) -> tuple[int, str]:
        return assessed.get(host_of(url)) or tier_for_url(url)

    def channel_tier(channel: str) -> tuple[int, str]:
        return assessed.get(CHANNEL_PREFIX + channel) or tier_for_channel(channel)

    # 2. Upsert Source rows with stable sids.
    existing = {
        s.key: s for s in ctx.session.exec(select(Source).where(Source.lesson_id == ctx.lesson.id)).all()
    }
    next_no = max((int(s.sid[1:]) for s in existing.values()), default=0) + 1
    current: dict[str, Source] = {}  # key -> source, in insertion order

    def upsert(key: str, **fields: Any) -> None:
        nonlocal next_no
        source = existing.get(key)
        if source is None:
            source = Source(lesson_id=ctx.lesson.id, sid=f"S{next_no}", key=key, **fields)
            next_no += 1
            existing[key] = source
        else:
            for name, value in fields.items():
                setattr(source, name, value)
        ctx.session.add(source)
        current[key] = source

    # --- web pages (only pages with extracted text count as evidence) ---
    results_by_url = {r["url"]: r for r in web.get("results", [])}
    for page in pages:
        result = results_by_url.get(page["url"], {})
        tier, reason = web_tier(page["url"])
        outdated = self_declared_outdated(page["content"])
        if outdated:
            tier, reason = 4, f"The page says it is out of date (\"{outdated}\"); normally: {reason}"
        upsert(
            page["url"],
            type=SourceType.web,
            title=page.get("title") or result.get("title") or page["url"],
            url=page["url"],
            publisher=host_of(page["url"]),
            reliability_tier=tier,
            reliability_reason=reason,
            excerpt_text=page["content"][:max_chars],
            metadata_json={"query": result.get("query"), "search_snippet": result.get("snippet"),
                           "published_date": result.get("published_date"),
                           "page_chars": page.get("full_chars"),
                           "excerpt_method": page.get("excerpt_method", "whole")},
        )

    # --- books (metadata + publisher description only) ---
    for book in books.get("books", []):
        upsert(
            book.get("url") or book_key(book["title"], book.get("authors", [])),
            type=SourceType.book,
            title=book["title"],
            url=book.get("url"),
            publisher=", ".join(book.get("authors", [])) or book.get("publisher"),
            reliability_tier=2,
            reliability_reason="Published book — only metadata and the publisher description were used, not the full text",
            excerpt_text=(book.get("description") or "")[:max_chars],
            metadata_json={k: book.get(k) for k in ("year", "publisher", "isbn", "source_api")},
        )

    # --- videos ---
    for video in videos:
        tier, reason = channel_tier(video.get("channel_title", ""))
        upsert(
            video["url"],
            type=SourceType.video,
            title=video["title"],
            url=video["url"],
            publisher=video.get("channel_title"),
            reliability_tier=tier,
            reliability_reason=reason,
            excerpt_text=_video_excerpt(video)[:max_chars],
            metadata_json={
                "video_id": video["video_id"],
                "duration_seconds": video.get("duration_seconds"),
                "view_count": video.get("view_count"),
                "relevance": video.get("relevance", {}),
            },
        )

    used = list(current.values())
    if not any(s.type == SourceType.web for s in used):
        raise StepError("No usable web sources with extracted text — cannot build an evidence store.")

    ctx.session.flush()
    return {
        "sids": [s.sid for s in used],
        "counts": {t.value: sum(1 for s in used if s.type == t) for t in SourceType},
        "tiers": {s.sid: s.reliability_tier for s in used},
        "llm_assessed": sorted(assessed),
    }
