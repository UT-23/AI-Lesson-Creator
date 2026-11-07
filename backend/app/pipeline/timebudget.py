"""Step `timebudget`: deterministic learner-time estimate (no LLM).

Per section:
* reading time  = words / WPM (default 200)
* video section = reading + real video durations (or watch_segment length)
* activity      = the declared minutes (at least the reading time)
* knowledge check = declared minutes, at least reading + 0.5 min per question
                    (flagged if declared < 1 min per 2 questions)
Flags: total over budget, or declared minutes far from the computed minutes.
"""

import re
from typing import Any

from pydantic import BaseModel

from app.pipeline.context import StepContext
from app.schemas import CITATION_GROUP_RE, LessonContent, LessonVideo, extract_citations

MIN_PER_QUESTION = 0.5
MISMATCH_ABS_MIN = 2.0  # declared vs computed may differ by this many minutes...
MISMATCH_REL = 0.5  # ...or by this fraction of the computed time, whichever is larger

_SEGMENT_RE = re.compile(r"^\s*((?:\d+:)?\d{1,2}:\d{2})\s*[-–—]\s*((?:\d+:)?\d{1,2}:\d{2})\s*$")
_LINK_URL_RE = re.compile(r"\]\([^)]*\)")
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’.-][A-Za-z0-9]+)*")


class SectionTime(BaseModel):
    id: str
    type: str
    heading: str
    declared_min: float
    computed_min: float
    basis: str
    flags: list[str] = []


class TimeBudget(BaseModel):
    budget_min: int
    wpm: int
    total_declared_min: float
    total_computed_min: float
    over_budget: bool
    sections: list[SectionTime]
    flags: list[str]


def count_words(markdown: str) -> int:
    text = CITATION_GROUP_RE.sub(" ", markdown)
    text = _LINK_URL_RE.sub("]", text)  # don't count URLs inside [text](url)
    return len(_WORD_RE.findall(text))


def _seconds(stamp: str) -> int:
    parts = [int(p) for p in stamp.split(":")]
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def segment_minutes(segment: str | None) -> float | None:
    """'02:10–07:40' → 5.5. None if missing or unparseable."""
    if not segment:
        return None
    match = _SEGMENT_RE.match(segment)
    if not match:
        return None
    start, end = _seconds(match.group(1)), _seconds(match.group(2))
    return (end - start) / 60 if end > start else None


def video_minutes(video: LessonVideo) -> float:
    seg = segment_minutes(video.watch_segment)
    return seg if seg is not None else video.duration_min


def _mismatch(declared: float, computed: float) -> bool:
    return abs(declared - computed) > max(MISMATCH_ABS_MIN, MISMATCH_REL * computed)


def compute_time_budget(content: LessonContent, wpm: int = 200, budget_min: int = 45) -> TimeBudget:
    videos_by_sid = {v.sid: v for v in content.videos}
    n_questions = len(content.knowledge_check)
    quiz_words = sum(
        count_words(" ".join([q.q, *q.options, q.explanation])) for q in content.knowledge_check
    )
    rows: list[SectionTime] = []

    for s in content.sections:
        reading = count_words(s.content_md) / wpm
        flags: list[str] = []

        if s.type == "video":
            cited = [videos_by_sid[sid] for sid in extract_citations(s.content_md) if sid in videos_by_sid]
            shown = list({v.sid: v for v in cited}.values()) or content.videos
            computed = reading + sum(video_minutes(v) for v in shown)
            basis = f"reading + {len(shown)} video(s) at real duration"
        elif s.type == "activity":
            computed = max(s.minutes, reading)
            basis = "declared activity time (at least the reading time)"
        elif s.type == "knowledge_check":
            minimum = reading + quiz_words / wpm + n_questions * MIN_PER_QUESTION
            computed = max(s.minutes, minimum)
            basis = f"declared time, at least reading + {MIN_PER_QUESTION} min x {n_questions} question(s)"
            if s.minutes < n_questions / 2:
                flags.append(f"{s.minutes:g} min is under the 1 min per 2 questions minimum for {n_questions} questions")
        else:
            computed = reading
            basis = f"{count_words(s.content_md)} words at {wpm} wpm"

        if _mismatch(s.minutes, computed):
            flags.append(f"declared {s.minutes:g} min but computed {computed:.1f} min")
        rows.append(SectionTime(id=s.id, type=s.type, heading=s.heading, declared_min=s.minutes,
                                computed_min=round(computed, 1), basis=basis, flags=flags))

    if n_questions and not any(s.type == "knowledge_check" for s in content.sections):
        quiz_min = quiz_words / wpm + n_questions * MIN_PER_QUESTION
        rows.append(SectionTime(id="quiz", type="knowledge_check", heading="Knowledge check (no section)",
                                declared_min=0, computed_min=round(quiz_min, 1),
                                basis=f"{n_questions} question(s) without a knowledge_check section"))

    total_declared = round(sum(r.declared_min for r in rows), 1)
    total_computed = round(sum(r.computed_min for r in rows), 1)
    flags = [f"{r.id}: {f}" for r in rows for f in r.flags]
    over = total_computed > budget_min
    if over:
        flags.insert(0, f"Total computed time {total_computed:g} min exceeds the {budget_min}-minute budget")

    return TimeBudget(budget_min=budget_min, wpm=wpm, total_declared_min=total_declared,
                      total_computed_min=total_computed, over_budget=over, sections=rows, flags=flags)


def run_timebudget(ctx: StepContext) -> dict[str, Any]:
    version = ctx.require_latest_version()
    content = LessonContent.model_validate(version.content_json)
    budget = compute_time_budget(content, ctx.settings.reading_wpm, ctx.settings.lesson_minutes_budget)
    return {"version_no": version.version_no, **budget.model_dump()}
