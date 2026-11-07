"""Fake providers for tests and the DEMO_OFFLINE=1 mode.

Everything here is obviously fake: titles start with "[FAKE]" and every URL
lives under https://example.com/fake/. These classes are never used unless
DEMO_OFFLINE=1 or a test injects them.

Each fake supports:
* `fail_with` — set to an exception to make every call raise it
* `calls`     — a log of calls, so tests can assert on caching/retries
FakeLLM additionally supports `queue(schema_name, *raw_responses)` to script
exact (possibly malformed) responses.
"""

import json
import re
from typing import Any

from pydantic import BaseModel

from app.providers import Providers
from app.providers.books import BookResult, BooksProvider
from app.providers.llm import LLMProvider
from app.providers.web import WebPage, WebSearchProvider, WebSearchResult
from app.providers.youtube import RelevanceVerdict, VideoCandidate, YouTubeProvider

FAKE_BASE = "https://example.com/fake"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


# ---------------------------------------------------------------------------
# Prompt parsing helpers (prompts use "NAME: value" lines and "- item" lists)
# ---------------------------------------------------------------------------


def _field(prompt: str, name: str, default: str = "") -> str:
    match = re.search(rf"^{name}: (.+)$", prompt, re.MULTILINE)
    return match.group(1).strip() if match else default


def _list_block(prompt: str, name: str) -> list[str]:
    match = re.search(rf"^{name}:\n((?:- .*\n?)+)", prompt, re.MULTILINE)
    if not match:
        return []
    return [line[2:].strip() for line in match.group(1).splitlines() if line.startswith("- ")]


def _source_headers(prompt: str) -> list[dict[str, str]]:
    """Parse lines like: [S3] type=video | tier=3 | title=... | url=... | duration_min=6.0"""
    headers = []
    for match in re.finditer(r"^\[(S\d+)\] (.+)$", prompt, re.MULTILINE):
        fields: dict[str, str] = {"sid": match.group(1)}
        for part in match.group(2).split(" | "):
            if "=" in part:
                key, _, value = part.partition("=")
                fields[key.strip()] = value.strip()
        headers.append(fields)
    return headers


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------


class FakeLLM(LLMProvider):
    def __init__(self, name: str = "fake-llm", model: str = "fake-model") -> None:
        self.name = name
        self.model = model
        self.calls: list[tuple[str, str]] = []  # (schema name, prompt)
        self.fail_with: Exception | None = None
        self._scripted: dict[str, list[str]] = {}

    def queue(self, schema_name: str, *responses: str) -> None:
        self._scripted.setdefault(schema_name, []).extend(responses)

    def complete_json(
        self, prompt: str, schema: type[BaseModel], system: str | None = None, video_url: str | None = None
    ) -> str:
        name = schema.__name__
        self.calls.append((name, prompt))
        if self.fail_with:
            raise self.fail_with
        if self._scripted.get(name):
            return self._scripted[name].pop(0)
        builder = getattr(self, f"_build_{name}", None)
        if builder is None:
            raise NotImplementedError(f"FakeLLM has no canned response for {name}")
        return json.dumps(builder(prompt))

    # --- canned responses -------------------------------------------------

    def _build_ResearchPlan(self, prompt: str) -> dict[str, Any]:
        title = _field(prompt, "TITLE", "the topic")
        objective = _field(prompt, "OBJECTIVE", "Explain the topic").rstrip(".")
        return {
            "outcomes": [objective, f"Apply the ideas of {title} to a worked example"],
            "queries": [title, f"{title} explained", f"{title} examples", f"{title} common misconceptions"],
            "book_queries": [title],
        }

    def _build_LessonDraft(self, prompt: str) -> dict[str, Any]:
        title = _field(prompt, "TITLE", "Fake lesson")
        objective = _field(prompt, "OBJECTIVE", "Fake objective")
        outcomes = _list_block(prompt, "OUTCOMES") or [objective]
        sources = _source_headers(prompt)
        text_sids = [s["sid"] for s in sources if s.get("type") != "video"] or ["S1"]
        videos = [s for s in sources if s.get("type") == "video"]
        cite = f"[{text_sids[0]}]"
        cite2 = f"[{text_sids[-1]}]"

        sections = [
            {"id": "sec-1", "type": "hook", "heading": "Why this matters", "minutes": 3,
             "content_md": f"[FAKE] A short motivating scenario about {title} {cite}.", "outcomes_covered": []},
            {"id": "sec-2", "type": "concept", "heading": "Core ideas", "minutes": 10,
             "content_md": f"[FAKE] Explanation of the core ideas {cite}. More detail {cite2}.",
             "outcomes_covered": [outcomes[0]]},
            {"id": "sec-3", "type": "example", "heading": "Worked example", "minutes": 8,
             "content_md": f"[FAKE] Step-by-step worked example {cite}.", "outcomes_covered": outcomes[-1:]},
            {"id": "sec-4", "type": "activity", "heading": "Try it", "minutes": 26,
             "content_md": "[FAKE] Practice activity for the learner.", "outcomes_covered": outcomes},
        ]
        lesson_videos = []
        if videos:
            v = videos[0]
            minutes = float(v.get("duration_min", "5"))
            lesson_videos.append({"sid": v["sid"], "title": v.get("title", "video"), "url": v.get("url", ""),
                                  "duration_min": minutes, "why": "[FAKE] Shows the idea visually."})
            sections.append({"id": "sec-5", "type": "video", "heading": "Watch", "minutes": minutes,
                             "content_md": f"[FAKE] Watch the video [{v['sid']}].", "outcomes_covered": [outcomes[0]]})
        sections += [
            {"id": "sec-6", "type": "knowledge_check", "heading": "Check your understanding", "minutes": 4,
             "content_md": "[FAKE] Answer the questions below.", "outcomes_covered": outcomes},
            {"id": "sec-7", "type": "summary", "heading": "Summary", "minutes": 2,
             "content_md": f"[FAKE] Recap of the key points {cite}.", "outcomes_covered": []},
        ]
        quiz = [
            {"q": f"[FAKE] Question {n} about: {o}", "options": ["Correct", "Wrong A", "Wrong B", "Wrong C"],
             "answer": "Correct", "explanation": f"[FAKE] Because of the source {cite}.", "outcome": o}
            for o in outcomes for n in (1, 2)  # two per outcome: 4-8 questions for 2-4 outcomes
        ]
        return {
            "title": title,
            "objective": objective,
            "outcomes": outcomes,
            "total_minutes": sum(s["minutes"] for s in sections),
            "sections": sections,
            "videos": lesson_videos,
            "knowledge_check": quiz,
            "references": sorted({*text_sids, *(v["sid"] for v in videos[:1])}),
        }

    def _build_BookSelection(self, prompt: str) -> dict[str, Any]:
        ids = [int(m) for m in re.findall(r"^\[(\d+)\] ", prompt, re.MULTILINE)]
        return {"ratings": [{"id": i, "score": 8, "reason": "[FAKE] on topic"} for i in ids]}

    def _build_FactCheckResult(self, prompt: str) -> dict[str, Any]:
        ids = re.findall(r"^\[(C\d+)\] ", prompt, re.MULTILINE)
        return {"verdicts": [{"claim_id": i, "verdict": "supported", "source_id": None, "evidence_quote": "",
                              "explanation": "[FAKE] looks fine"} for i in ids],
                "contradictions": []}

    def _build_InstructionalReview(self, prompt: str) -> dict[str, Any]:
        outcomes = _list_block(prompt, "OUTCOMES")
        cell = {"present": True, "sections": ["sec-2"], "note": "[FAKE]"}
        return {
            "summary": "[FAKE] instructional review.",
            "coverage": [{"outcome": o, "explanation": cell, "example": cell, "practice": cell, "quiz": cell}
                         for o in outcomes],
            "verb_alignment": [{"outcome": o, "verb": o.split()[0].lower(), "bloom_level": "understand",
                                "aligned": True, "evidence": "[FAKE]", "suggestion": ""} for o in outcomes],
            "rubric": [{"criterion": c, "score": 4, "justification": "[FAKE]"} for c in
                       ["clarity", "structure_flow", "jargon_before_use", "example_quality", "practical_relevance",
                        "outcome_alignment"]],
            "issues": [{"severity": "minor", "category": "fake", "location": "sec-2", "claim_or_text": "[FAKE]",
                        "evidence": "", "source_ids": [], "suggestion": "[FAKE] Example suggestion."}],
        }

    def _build_SectionRewrite(self, prompt: str) -> dict[str, Any]:
        cited = re.findall(r"\[S\d+\]", prompt)
        return {"content_md": f"[FAKE] Rewritten section {cited[0] if cited else ''}.",
                "change_summary": "[FAKE] rewrote the section."}

    def _build_QuizItem(self, prompt: str) -> dict[str, Any]:
        outcome = re.search(r'keep it exactly: "([^"]*)"', prompt)
        return {"q": "[FAKE] Corrected question?", "options": ["Right", "Wrong A", "Wrong B", "Wrong C"],
                "answer": "Right", "explanation": "[FAKE] corrected.", "outcome": outcome.group(1) if outcome else ""}

    def _build_DomainTiers(self, prompt: str) -> dict[str, Any]:
        names = _list_block(prompt, "NAMES")
        return {"items": [{"name": n.split(" (page:")[0], "tier": 3, "reason": "[FAKE] assessed"} for n in names]}

    def _build_VideoRelevanceJudgement(self, prompt: str) -> dict[str, Any]:
        return {"spoken_language": "en", "relevant": True, "reason": "[FAKE] relevant", "outcomes_matched": _list_block(prompt, "OUTCOMES")[:1],
                "key_points": ["[FAKE] key point"], "suggested_segment": None}

    def _build_QCReviewDraft(self, prompt: str) -> dict[str, Any]:
        layer = _field(prompt, "QC_LAYER", "unknown")
        return {
            "summary": f"[FAKE] {layer} review: no real checks were performed.",
            "score": 80,
            "issues": [{
                "severity": "minor", "category": "fake", "location": "sec-2",
                "claim_or_text": "[FAKE] Example issue", "evidence": "", "source_ids": [],
                "suggestion": "[FAKE] Example suggestion.",
            }],
        }


# ---------------------------------------------------------------------------
# Web
# ---------------------------------------------------------------------------


class FakeWebSearch(WebSearchProvider):
    name = "fake-web"

    def __init__(self, results_per_query: int = 3) -> None:
        self.results_per_query = results_per_query
        self.calls: list[tuple[str, Any]] = []
        self.fail_with: Exception | None = None

    def search(self, query: str, max_results: int = 5) -> list[WebSearchResult]:
        self.calls.append(("search", query))
        if self.fail_with:
            raise self.fail_with
        n = min(max_results, self.results_per_query)
        return [
            WebSearchResult(
                query=query,
                url=f"{FAKE_BASE}/web/{_slug(query)}/{i}",
                title=f"[FAKE] {query} — result {i}",
                snippet=f"[FAKE] Snippet about {query}.",
                score=1.0 - i / 10,
            )
            for i in range(1, n + 1)
        ]

    def extract(self, urls: list[str]) -> list[WebPage]:
        self.calls.append(("extract", list(urls)))
        if self.fail_with:
            raise self.fail_with
        return [WebPage(url=u, title=f"[FAKE] page {u.rsplit('/', 2)[-2]}",
                        content=f"[FAKE] Full extracted text for {u}. " * 20) for u in urls]


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------

_FAKE_VIDEOS = [  # (id, minutes, relevant)
    ("fakevid001", 6, True),
    ("fakevid002", 11, True),
    ("fakevid003", 25, False),
]


class FakeYouTube(YouTubeProvider):
    name = "fake-youtube"

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.fail_with: Exception | None = None

    def _check(self) -> None:
        if self.fail_with:
            raise self.fail_with

    def search(self, query: str, max_results: int = 8) -> list[VideoCandidate]:
        self.calls.append(("search", query))
        self._check()
        return [
            VideoCandidate(video_id=vid, url=f"{FAKE_BASE}/watch/{vid}", title=f"[FAKE] {query} video {i}",
                           channel_title="[FAKE] Channel", description=f"[FAKE] A video about {query}.")
            for i, (vid, _, _) in enumerate(_FAKE_VIDEOS[:max_results], start=1)
        ]

    def get_details(self, video_ids: list[str]) -> list[VideoCandidate]:
        self.calls.append(("get_details", list(video_ids)))
        self._check()
        minutes = {vid: m for vid, m, _ in _FAKE_VIDEOS}
        return [
            VideoCandidate(video_id=vid, url=f"{FAKE_BASE}/watch/{vid}", title=f"[FAKE] video {vid}",
                           channel_title="[FAKE] Channel", duration_seconds=minutes.get(vid, 5) * 60,
                           view_count=1000)
            for vid in video_ids
        ]

    def check_relevance(self, video: VideoCandidate, lesson_title: str, outcomes: list[str]) -> RelevanceVerdict:
        self.calls.append(("check_relevance", video.video_id))
        self._check()
        relevant = {vid: r for vid, _, r in _FAKE_VIDEOS}.get(video.video_id, True)
        return RelevanceVerdict(
            relevant=relevant,
            reason="[FAKE] matches outcomes" if relevant else "[FAKE] off-topic",
            outcomes_matched=outcomes[:1] if relevant else [],
            method="fake",
        )


# ---------------------------------------------------------------------------
# Books
# ---------------------------------------------------------------------------


class FakeBooks(BooksProvider):
    name = "fake-books"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_with: Exception | None = None

    def search(self, query: str, max_results: int = 5) -> list[BookResult]:
        self.calls.append(query)
        if self.fail_with:
            raise self.fail_with
        return [
            BookResult(title=f"[FAKE] {query}: A Textbook", authors=["A. Author"], year=2020,
                       publisher="[FAKE] Press", description=f"[FAKE] Publisher description of a book on {query}.",
                       url=f"{FAKE_BASE}/books/1", source_api="fake"),
            BookResult(title=f"[FAKE] Practical {query}", authors=["B. Writer", "C. Coauthor"], year=2018,
                       description="[FAKE] Another description.", url=None, source_api="fake"),
        ][:max_results]


def make_fake_providers() -> Providers:
    return Providers(
        gen_llm=FakeLLM(name="fake-gen", model="fake-gen-model"),
        qc_llm=FakeLLM(name="fake-qc", model="fake-qc-model"),
        web=FakeWebSearch(),
        youtube=FakeYouTube(),
        books=FakeBooks(),
    )
