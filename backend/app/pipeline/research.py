"""Steps `research_web`, `research_youtube`, `research_books`.

Each step stores its raw findings in its own `output_json`; `score_sources`
later turns them into `Source` rows. Every provider call goes through the
DB cache (pipeline/cache.py), so a retry never re-spends Tavily credits,
YouTube quota or Gemini tokens on work that already succeeded.
"""

import logging
import re
from typing import Any

from app.pipeline.cache import cached_batch, cached_call
from app.pipeline.context import StepContext, StepError
from app.pipeline.passages import select_passages, topic_keywords
from app.pipeline.sources import host_of, tier_for_channel, tier_for_url
from app.providers.books import BookResult
from app.providers.errors import ErrorKind, ProviderError
from app.providers.llm import LLMOutputError, generate_structured
from app.providers.web import WebPage, WebSearchResult
from app.providers.youtube import RELEVANCE_PROMPT_VERSION, RelevanceVerdict, VideoCandidate
from app.schemas import BookSelection

log = logging.getLogger(__name__)

# Failures where trying the next query is pointless.
_FATAL_KINDS = {ErrorKind.auth, ErrorKind.not_configured, ErrorKind.quota_exhausted}


# ---------------------------------------------------------------------------
# Web (required: generation is blocked without it)
# ---------------------------------------------------------------------------


def _round_robin(per_query: list[list[WebSearchResult]]) -> list[WebSearchResult]:
    """Best result of each query, then the second best, ... (deduplicated by URL)."""
    ordered: list[WebSearchResult] = []
    seen: set[str] = set()
    depth = max((len(r) for r in per_query), default=0)
    for rank in range(depth):
        for results in per_query:
            if rank < len(results) and results[rank].url not in seen:
                ordered.append(results[rank])
                seen.add(results[rank].url)
    return ordered


def select_for_extraction(results: list[WebSearchResult], limit: int, max_per_host: int) -> list[WebSearchResult]:
    """Prefer more reliable sites, keep query diversity, and cap pages per site.

    `results` arrive in round-robin order; a stable sort by deterministic tier
    keeps that order within each tier.
    """
    picked: list[WebSearchResult] = []
    per_host: dict[str, int] = {}
    for result in sorted(results, key=lambda r: tier_for_url(r.url)[0]):
        host = host_of(result.url)
        if per_host.get(host, 0) >= max_per_host:
            continue
        picked.append(result)
        per_host[host] = per_host.get(host, 0) + 1
        if len(picked) >= limit:
            break
    return picked


_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
# Menus/breadcrumbs: a bulleted line that is only a link, or a line of 2+ links.
# A single bare link on its own line is kept: definition lists use it for the
# term (e.g. MDN's "`200 OK`" heading for each status code).
_LINK = r"\[[^\]]*\]\([^)]*\)"
_ONLY_LINKS_LINE = re.compile(
    rf"^\s*(?:(?:[*\-+]|\d+\.)\s*{_LINK}\s*|(?:{_LINK}\s*[|·•,]?\s*){{2,}})$"
)


def clean_page_text(markdown: str) -> str:
    """Strip images, navigation-only lines and link URLs from extracted markdown.

    Link text is kept (it is often part of a sentence); URLs are dropped so the
    excerpt is readable and quotes in QC match what a human sees.
    """
    lines = []
    for line in markdown.splitlines():
        if _ONLY_LINKS_LINE.match(line):
            continue  # menus, breadcrumbs, "related articles" lists
        line = _MD_IMAGE.sub("", line)
        line = _MD_LINK.sub(r"\1", line)
        line = line.replace("¶", "")  # paragraph anchors (RFCs, Sphinx docs)
        lines.append(line.rstrip())
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


DUPLICATE_THRESHOLD = 0.5
_SHINGLE = 8


def similarity(a: str, b: str) -> float:
    """Jaccard similarity of 8-word shingles: ~1.0 for the same text, ~0 for unrelated pages."""
    def shingles(text: str) -> set[tuple[str, ...]]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        return {tuple(words[i:i + _SHINGLE]) for i in range(max(0, len(words) - _SHINGLE + 1))}

    sa, sb = shingles(a), shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def run_research_web(ctx: StepContext) -> dict[str, Any]:
    plan = ctx.require("plan")
    queries: list[str] = plan["queries"]
    keywords = topic_keywords([ctx.lesson.title, *plan["outcomes"], *queries])
    web = ctx.providers.web
    s = ctx.settings

    per_query: list[list[WebSearchResult]] = []
    failed_queries: list[dict[str, str]] = []
    for query in queries:
        try:
            per_query.append(cached_call(
                f"{web.name}.search", {"query": query, "max_results": s.web_results_per_query},
                lambda q=query: web.search(q, max_results=s.web_results_per_query),  # type: ignore[misc]
                list[WebSearchResult], enabled=s.cache_enabled,
            ))
        except ProviderError as err:
            if err.kind in _FATAL_KINDS:
                raise
            log.warning("web search failed for %r: %s", query, err)
            failed_queries.append({"query": query, "error": err.message})

    all_results = _round_robin(per_query)
    if not all_results:
        detail = f" ({len(failed_queries)} of {len(queries)} queries failed)" if failed_queries else ""
        raise StepError(f"Web research returned no results{detail}. Not enough evidence to write a lesson.")

    to_extract = select_for_extraction(all_results, s.web_max_extract, s.web_max_per_host)
    extracted = cached_batch(
        f"{web.name}.extract", [r.url for r in to_extract],
        lambda urls: {p.url: p for p in web.extract(urls)},
        WebPage, enabled=s.cache_enabled,
    )

    pages: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for result in to_extract:
        page = extracted.get(result.url)
        if page is None:
            rejected.append({"url": result.url, "reason": "extraction failed"})
            continue
        text = clean_page_text(page.content)
        if len(text) < s.web_min_page_chars:
            rejected.append({"url": result.url, "reason": f"only {len(text)} characters of text after cleaning"})
            continue
        excerpt, method = select_passages(text, keywords, s.web_excerpt_chars)
        duplicate_of = next((p["url"] for p in pages if similarity(p["content"], excerpt) >= DUPLICATE_THRESHOLD), None)
        if duplicate_of:  # e.g. the same RFC served by rfc-editor.org and httpwg.org
            rejected.append({"url": result.url, "reason": f"near-duplicate of {duplicate_of}"})
            continue
        pages.append({"url": result.url, "title": page.title or result.title, "content": excerpt,
                      "full_chars": len(text), "excerpt_method": method})

    if not pages:
        raise StepError("Could not extract usable text from any web result. Not enough evidence to write a lesson.")

    return {
        "queries": queries,
        "results": [r.model_dump() for r in all_results],
        "pages": pages,
        "rejected_pages": rejected,
        "failed_queries": failed_queries,
    }


# ---------------------------------------------------------------------------
# YouTube (optional: failure produces a warning, pipeline continues)
# ---------------------------------------------------------------------------


def run_research_youtube(ctx: StepContext) -> dict[str, Any]:
    plan = ctx.require("plan")
    outcomes: list[str] = plan["outcomes"]
    yt = ctx.providers.youtube
    s = ctx.settings

    search_queries = [ctx.lesson.title, *plan["queries"]][: max(1, s.youtube_max_searches)]
    candidates: dict[str, VideoCandidate] = {}
    for query in search_queries:
        found = cached_call(
            f"{yt.name}.search", {"query": query, "max_results": s.youtube_max_candidates},
            lambda q=query: yt.search(q, max_results=s.youtube_max_candidates),  # type: ignore[misc]
            list[VideoCandidate], enabled=s.cache_enabled,
        )
        for video in found:
            candidates.setdefault(video.video_id, video)
    if not candidates:
        raise StepError("YouTube search returned no videos.")

    ids = sorted(candidates)
    details = {d.video_id: d for d in cached_call(
        # ".v2": details now include audio_language; older cache entries lack it.
        f"{yt.name}.details.v2", {"ids": ids}, lambda: yt.get_details(ids), list[VideoCandidate], enabled=s.cache_enabled,
    )}
    videos = [details.get(vid, candidates[vid]) for vid in candidates]  # details carry duration + full description

    min_s, max_s = s.youtube_min_seconds, s.youtube_preferred_max_minutes * 60
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    eligible: list[VideoCandidate] = []
    for video in videos:
        if video.duration_seconds is None:
            dropped.append({**video.model_dump(), "reason": "unknown duration"})
        elif video.audio_language and not video.audio_language.lower().startswith("en"):
            dropped.append({**video.model_dump(), "reason": f"audio language is '{video.audio_language}', not English"})
        elif video.duration_seconds < min_s:
            dropped.append({**video.model_dump(), "reason": f"shorter than {min_s} s (likely a Short or trailer)"})
        elif video.duration_seconds > max_s:
            dropped.append({**video.model_dump(), "reason": f"longer than {s.youtube_preferred_max_minutes} min"})
        else:
            eligible.append(video)

    # Known educational channels first, then the most watched.
    eligible.sort(key=lambda v: (tier_for_channel(v.channel_title)[0], -(v.view_count or 0)))

    checks = 0
    for video in eligible:
        if len(kept) >= s.youtube_keep_max or checks >= s.youtube_max_relevance_checks:
            dropped.append({**video.model_dump(), "reason": "not checked (enough videos already kept)"})
            continue
        checks += 1
        try:
            verdict = cached_call(
                f"{yt.name}.relevance",
                {"video_id": video.video_id, "title": ctx.lesson.title, "outcomes": outcomes,
                 "order": s.youtube_relevance_order, "prompt_version": RELEVANCE_PROMPT_VERSION},
                lambda v=video: yt.check_relevance(v, ctx.lesson.title, outcomes),  # type: ignore[misc]
                RelevanceVerdict, enabled=s.cache_enabled,
            )
        except ProviderError as err:
            if err.kind in _FATAL_KINDS and err.provider == "youtube":
                raise
            dropped.append({**video.model_dump(), "reason": f"relevance could not be verified: {err.message}"})
            continue
        record = {**video.model_dump(), "relevance": verdict.model_dump()}
        if verdict.relevant:
            kept.append(record)
        else:
            dropped.append({**record, "reason": verdict.reason})

    if not kept:
        reasons = "; ".join(f"{d['video_id']}: {d['reason']}" for d in dropped[:5])
        raise StepError(f"No suitable YouTube video found among {len(videos)} candidates ({reasons}).")
    return {"search_queries": search_queries, "kept": kept, "dropped": dropped}


# ---------------------------------------------------------------------------
# Books (optional)
# ---------------------------------------------------------------------------

_STOPWORDS = {"and", "the", "for", "with", "from", "into", "what", "how", "why", "your", "between", "versus"}


def _keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 4 and w not in _STOPWORDS}


def keyword_filter(books: list[BookResult], topic: str) -> list[BookResult]:
    """Fallback when the LLM vetting fails: keep books sharing a topic keyword."""
    words = _keywords(topic)
    return [b for b in books if words & _keywords(f"{b.title} {b.description or ''}")]


def _book_prompt(title: str, outcomes: list[str], books: list[BookResult]) -> str:
    lines = []
    for i, b in enumerate(books):
        desc = (b.description or "(no description)")[:400]
        lines.append(f"[{i}] {b.title} — {', '.join(b.authors) or 'unknown author'} ({b.year or 'n.d.'})\n    {desc}")
    outcome_lines = "\n".join(f"- {o}" for o in outcomes)
    candidates = "\n".join(lines)
    return f"""Rate every candidate book as further reading for a learner who has just finished this lesson.

LESSON: {title}
OUTCOMES:
{outcome_lines}

CANDIDATES:
{candidates}

Rubric (0-10):
 9-10  a current textbook, guide or reference whose main subject is this topic, at a level a learner can use
 7-8   a well-regarded textbook or reference that teaches this topic in depth among others
       (e.g. a mathematics-of-finance textbook for an interest lesson, a networking text for HTTP)
 4-6   tangential, too specialised/advanced, popular-audience with little teaching, or mostly reference tables
 0-3   unrelated, fiction, conference proceedings, historical works whose methods are no longer taught
Rate each candidate independently by its number in brackets, with a one-line reason."""


BOOK_PROMPT_VERSION = 4  # bump when _book_prompt changes so cached selections are not reused
BOOK_MIN_SCORE = 7


def run_research_books(ctx: StepContext) -> dict[str, Any]:
    s = ctx.settings
    books_provider = ctx.providers.books
    plan = ctx.require("plan")
    outcomes: list[str] = plan["outcomes"]
    title = ctx.lesson.title
    queries: list[str] = plan.get("book_queries") or [title]

    candidates: list[BookResult] = []
    seen: set[str] = set()
    failures: list[str] = []
    for query in queries:
        try:
            found = cached_call(
                f"{books_provider.name}.search", {"query": query, "max_results": s.books_candidates},
                lambda q=query: books_provider.search(q, max_results=s.books_candidates),  # type: ignore[misc]
                list[BookResult], enabled=s.cache_enabled,
            )
        except ProviderError as err:
            failures.append(f"{query}: {err.message}")
            continue
        for book in found:
            if book.title.lower() not in seen:
                seen.add(book.title.lower())
                candidates.append(book)
    if not candidates:
        detail = f" ({'; '.join(failures)})" if failures else ""
        raise StepError(f"No books found for {queries}{detail}.")

    llm = ctx.providers.qc_llm
    try:
        selection = cached_call(
            f"{llm.name}.{llm.model}.book_selection",
            {"title": title, "outcomes": outcomes, "candidates": [b.title for b in candidates],
             "prompt_version": BOOK_PROMPT_VERSION},
            lambda: generate_structured(llm, _book_prompt(title, outcomes, candidates), BookSelection,
                                        max_repairs=s.llm_max_repairs),
            BookSelection, enabled=s.cache_enabled,
        )
        valid = [r for r in selection.ratings if 0 <= r.id < len(candidates)]
        # Best score first; among equals, books with a description (they give evidence text) first.
        valid.sort(key=lambda r: (-r.score, candidates[r.id].description is None))
        chosen = [candidates[r.id] for r in valid if r.score >= BOOK_MIN_SCORE]
        method = "llm"
        reasons = {candidates[r.id].title: f"{r.score}/10 — {r.reason}" for r in valid}
    except (ProviderError, LLMOutputError) as err:
        log.warning("book vetting via LLM failed (%s); using keyword filter", err)
        chosen, method, reasons = keyword_filter(candidates, f"{title} {' '.join(outcomes)}"), "keywords", {}
        chosen = sorted(chosen, key=lambda b: b.description is None)  # described books first

    chosen = chosen[: s.books_max]
    if not chosen:
        raise StepError(f"None of the {len(candidates)} books found for {queries} were relevant to the topic.")
    return {
        "queries": queries,
        "selection_method": method,
        "books": [b.model_dump() for b in chosen],
        "rejected": [b.title for b in candidates if b not in chosen],
        "reasons": reasons,
    }
