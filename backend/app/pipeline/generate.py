"""Step `generate`: outcomes + evidence store → structured lesson → LessonVersion.

The model writes a `LessonDraft` (JSON, schema-validated). Code then enforces
what a prompt can only ask for:

Hard checks (fed back to the model; the step fails if they persist):
* every [S#] citation is a web/video source from the current research run
  (books are metadata-only, so they are never offered for citation),
* every outcome is covered by a section AND by at least one quiz question,
* the lesson has concept, example, activity, knowledge_check and summary sections,
* every concept and example section cites at least one source,
* `videos[]` only point at researched videos.

Soft checks (fed back, but the lesson is kept and the warnings stored):
* the deterministic time budget (pipeline/timebudget.py) is within range,
* each quiz question has 4 options, a video section exists if videos were found.

After validation, code overwrites everything the model must not invent:
title/objective/outcomes from the plan, video title/URL/duration from the
Source rows, `references` from the actual citations, `further_reading` from
the researched books.
"""

import math
from collections.abc import Callable
from typing import Any

from sqlmodel import col, select

from app.config import Settings
from app.models import LessonVersion, Source, SourceType, VersionAuthor
from app.pipeline.context import StepContext, StepError
from app.pipeline.passages import select_passages, topic_keywords
from app.pipeline.render import render_markdown
from app.pipeline.timebudget import compute_time_budget
from app.providers.llm import generate_structured
from app.schemas import LessonContent, LessonDraft, extract_citations, normalize_citations

GENERATE_SYSTEM = (
    "You are an expert instructional designer and subject-matter writer. You write accurate, engaging, "
    "self-paced lessons for adult beginners. You only state facts that the provided sources support, "
    "and you cite them."
)

REQUIRED_SECTION_TYPES = ["concept", "example", "activity", "knowledge_check", "summary"]
MIN_LESSON_MINUTES = 25  # below this, one repair call asks for more teaching
TARGET_MIN_MINUTES = 35  # the prompt aims for 35-45; 25-35 is kept with a warning
SHORT_LESSON_PREFIX = "The lesson takes only"
MAX_VIDEO_MINUTES = 15


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


def _clean(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ").strip()


def source_block(src: Source, keywords: set[str], settings: Settings) -> str:
    """One source as the model sees it: a parseable header line + the most relevant passages."""
    header = (f"[{src.sid}] type={src.type.value} | tier={src.reliability_tier} | "
              f"title={_clean(src.title)} | url={src.url or 'n/a'}")
    if src.type == SourceType.video and src.metadata_json.get("duration_seconds"):
        header += f" | duration_min={src.metadata_json['duration_seconds'] / 60:.1f}"
    budget = settings.prompt_chars_by_tier.get(src.reliability_tier, 2000)
    excerpt, _ = select_passages(src.excerpt_text, keywords, budget)
    return f"{header}\n{excerpt.strip() or '(no excerpt available)'}"


def build_generate_prompt(title: str, objective: str, outcomes: list[str], sources: list[Source],
                          settings: Settings) -> str:
    keywords = topic_keywords([title, objective, *outcomes])
    outcome_lines = "\n".join(f"- {o}" for o in outcomes)
    text_sources = [s for s in sources if s.type == SourceType.web]
    videos = [s for s in sources if s.type == SourceType.video]
    text_blocks = "\n\n".join(source_block(s, keywords, settings) for s in text_sources)
    video_blocks = "\n\n".join(source_block(s, keywords, settings) for s in videos) or "(none found)"
    budget = settings.lesson_minutes_budget
    wpm = settings.reading_wpm
    max_words = int((budget - 15) * wpm)
    target_words = int((TARGET_MIN_MINUTES - 15) * wpm)
    return f"""Write a complete self-paced lesson as JSON.

TITLE: {title}
OBJECTIVE: {objective}
LEARNER: an adult beginner with no prior knowledge of the topic.
TIME BUDGET: at most {budget} minutes in total = reading time (about {wpm} words per minute)
+ time for the videos you recommend + time for the activity + time for the knowledge check.
OUTCOMES:
{outcome_lines}

SOURCES — the only evidence you may use. Tier 1 is the most trustworthy, tier 4 the least.
[…] inside an excerpt marks skipped text.

{text_blocks}

VIDEOS you may recommend (durations are real; each was checked to be relevant):

{video_blocks}

REQUIREMENTS

Structure — section ids "sec-1", "sec-2", ... in reading order:
1. hook (1-2 min): a concrete, relatable situation or question that motivates the topic.
2. concept: explain each outcome in plain language. Define every technical term before or where it is
   first used. Short paragraphs; use a bullet list or a small table where it makes a comparison clearer.
3. example: at least one fully worked example. For calculations show the formula, the substitution, every
   arithmetic step and the final answer with units, and double-check the arithmetic.
4. activity: something the learner DOES, matched to the outcome verbs, with the answer key or a model
   answer in the same section:
   "calculate" → 2-4 practice problems with worked answers; "distinguish"/"classify"/"compare" → a sorting
   or classification task with real cases; "explain" → explain-in-your-own-words prompt with a model answer.
5. video (only if videos are listed): recommend 1-2 videos, at most {MAX_VIDEO_MINUTES} minutes in total,
   saying what to watch for. Cite the video's [S#] and add it to "videos".
6. knowledge_check: one or two sentences of instructions; the questions themselves go in "knowledge_check".
7. summary: 3-5 key takeaways.

Citations:
- Put a citation like [S2] right after every factual claim: definitions, rules, formulas, standards, numbers.
  Your own worked arithmetic and the activity instructions need no citation.
- Only cite ids listed above. Never invent sources, URLs, statistics or quotes.
- Rest key definitions on tier 1-2 sources where available; use tier 3-4 only for supporting detail.
- If sources disagree, follow the higher tier. If no source supports a claim, leave the claim out.

Knowledge check ("knowledge_check"):
- 4-8 questions, at least one per outcome; copy the outcome text exactly into "outcome".
- Each question has exactly 4 distinct options and one correct answer; "answer" equals that option exactly.
- Test the outcome's verb (apply, classify, calculate), not just recall. Distractors should reflect
  common misconceptions. Each explanation says why the answer is right and cites a source.

Time:
- "minutes" per section must be realistic: text ≈ words / {wpm}; video section = recommended video minutes
  + 1; activity and knowledge check = time to actually do them (≥ 1 minute per 2 questions).
- Target {TARGET_MIN_MINUTES}-{budget} minutes in total, MEASURED as above (declared minutes do not count).
  Most lessons fall short, so be generous with teaching: at least two fully worked examples per outcome
  (for calculations: different numbers each time), 4-6 practice tasks with worked answers, and a short
  "common mistakes" subsection. Aim for roughly {target_words}-{max_words} words of lesson text.

Other fields:
- "outcomes" and every "outcomes_covered" entry: copy outcome texts exactly as listed above.
- "references": every id you cited. "total_minutes": the sum of section minutes."""


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def hard_checks(outcomes: list[str], allowed: dict[str, Source]) -> Callable[[LessonDraft], list[str]]:
    def check(draft: LessonDraft) -> list[str]:
        problems: list[str] = []
        unknown = sorted(draft.cited_sids() - set(allowed), key=lambda s: (len(s), s))
        if unknown:
            problems.append(f"Unknown source ids cited: {', '.join(unknown)}. Only cite: {', '.join(allowed)}.")
        for video in draft.videos:
            src = allowed.get(video.sid)
            if src is not None and src.type != SourceType.video:
                problems.append(f"videos[].sid {video.sid} is a {src.type.value} source, not a video.")

        covered = {o for s in draft.sections for o in s.outcomes_covered}
        quizzed = {q.outcome for q in draft.knowledge_check}
        for outcome in outcomes:
            if outcome not in covered:
                problems.append(f"No section lists the outcome {outcome!r} in outcomes_covered (copy the text exactly).")
            if outcome not in quizzed:
                problems.append(f"No knowledge_check question for the outcome {outcome!r} (copy the text exactly).")

        types = {s.type for s in draft.sections}
        missing = [t for t in REQUIRED_SECTION_TYPES if t not in types]
        if missing:
            problems.append(f"Missing required section type(s): {', '.join(missing)}.")
        for section in draft.sections:
            if section.type in ("concept", "example") and not extract_citations(section.content_md):
                problems.append(f"Section {section.id} ({section.type}) has no [S#] citation for its facts.")
        return problems

    return check


def soft_checks(outcomes: list[str], allowed: dict[str, Source], settings: Settings) -> Callable[[LessonDraft], list[str]]:
    has_videos = any(s.type == SourceType.video for s in allowed.values())

    def check(draft: LessonDraft) -> list[str]:
        problems: list[str] = []
        content = finalize(draft, draft.title, draft.objective, outcomes, allowed, [])
        budget = compute_time_budget(content, settings.reading_wpm, settings.lesson_minutes_budget)
        total = budget.total_computed_min
        if total > settings.lesson_minutes_budget:
            longest = sorted(budget.sections, key=lambda r: -r.computed_min)[:3]
            detail = ", ".join(f"{r.id} {r.computed_min:g} min" for r in longest)
            problems.append(
                f"The lesson takes {total:g} minutes (reading at {settings.reading_wpm} wpm + real video length + "
                f"activity/quiz time); the limit is {settings.lesson_minutes_budget}. Longest sections: {detail}. "
                "Shorten text or recommend a shorter video / a watch_segment.")
        elif total < MIN_LESSON_MINUTES:
            extra_words = int((TARGET_MIN_MINUTES - total) * settings.reading_wpm)
            problems.append(
                f"{SHORT_LESSON_PREFIX} {total:g} minutes when measured (reading at {settings.reading_wpm} wpm + "
                f"real video length + activity/quiz time); it must take {TARGET_MIN_MINUTES}-"
                f"{settings.lesson_minutes_budget}. Declared 'minutes' do not count — add about {extra_words} words "
                "of real teaching: e.g. a second worked example per outcome, 2-3 more practice problems with worked "
                "answers, and a 'common mistakes' subsection.")
        elif total < TARGET_MIN_MINUTES:
            problems.append(f"The lesson measures {total:g} minutes, below the {TARGET_MIN_MINUTES}-"
                            f"{settings.lesson_minutes_budget} minute target.")
        video_minutes = sum(v.duration_min for v in content.videos)
        if video_minutes > MAX_VIDEO_MINUTES:
            problems.append(f"Recommended videos total {video_minutes:g} minutes; keep it under {MAX_VIDEO_MINUTES}.")
        if has_videos and not any(s.type == "video" for s in draft.sections):
            problems.append("Videos were found but there is no video section recommending one.")
        for n, q in enumerate(draft.knowledge_check, start=1):
            if len(q.options) != 4:
                problems.append(f"Question {n} has {len(q.options)} options; use exactly 4.")
        if not 4 <= len(draft.knowledge_check) <= 8:
            problems.append(f"There are {len(draft.knowledge_check)} quiz questions; use 4-8.")
        return problems

    return check


# ---------------------------------------------------------------------------
# Finalise + save
# ---------------------------------------------------------------------------


def finalize(draft: LessonDraft, title: str, objective: str, outcomes: list[str],
             allowed: dict[str, Source], book_sids: list[str]) -> LessonContent:
    """Overwrite everything the model must not invent, from stored data, and normalise citations."""
    videos = []
    for video in draft.videos:
        src = allowed.get(video.sid)
        if src is None:
            continue
        seconds = src.metadata_json.get("duration_seconds")
        videos.append(video.model_copy(update={
            "title": src.title,
            "url": src.url or video.url,
            "duration_min": round(seconds / 60, 1) if seconds else video.duration_min,
            "why": normalize_citations(video.why),
        }))
    sections = [s.model_copy(update={"content_md": normalize_citations(s.content_md)}) for s in draft.sections]
    quiz = [q.model_copy(update={"explanation": normalize_citations(q.explanation)}) for q in draft.knowledge_check]
    content = LessonContent(**{
        **draft.model_dump(),
        "title": title,
        "objective": objective,
        "outcomes": outcomes,
        "sections": [s.model_dump() for s in sections],
        "knowledge_check": [q.model_dump() for q in quiz],
        "videos": [v.model_dump() for v in videos],
        "further_reading": book_sids,
    })
    return content.model_copy(update={
        "references": sorted(content.cited_sids(), key=lambda s: int(s[1:])),
        "total_minutes": round(sum(s.minutes for s in content.sections), 1),
    })


def set_measured_minutes(content: LessonContent, settings: Settings) -> tuple[LessonContent, list[dict[str, Any]]]:
    """Replace each section's model-declared minutes with the deterministic estimate (rounded up).

    Learners see honest times. The model's numbers are returned so the
    difference stays visible in the step output.
    """
    budget = compute_time_budget(content, settings.reading_wpm, settings.lesson_minutes_budget)
    measured = {row.id: max(1, math.ceil(row.computed_min - 0.05)) for row in budget.sections}
    changes = []
    sections = []
    for section in content.sections:
        minutes = measured.get(section.id, section.minutes)
        if minutes != section.minutes:
            changes.append({"section": section.id, "declared": section.minutes, "measured": minutes})
        sections.append(section.model_copy(update={"minutes": minutes}))
    updated = content.model_copy(update={"sections": sections, "total_minutes": sum(s.minutes for s in sections)})
    return updated, changes


def save_version(ctx: StepContext, content: LessonContent, author: VersionAuthor, note: str) -> LessonVersion:
    """Append a new LessonVersion (never overwrites)."""
    from app.versions import append_version

    return append_version(ctx.session, ctx.lesson.id, content, author, note)  # type: ignore[arg-type]


def run_generate(ctx: StepContext) -> dict[str, Any]:
    outcomes: list[str] = ctx.require("plan")["outcomes"]
    current_sids: list[str] = ctx.require("score_sources")["sids"]
    rows = ctx.session.exec(
        select(Source).where(Source.lesson_id == ctx.lesson.id, col(Source.sid).in_(current_sids))
    ).all()
    ordered = sorted(rows, key=lambda s: (s.reliability_tier, int(s.sid[1:])))
    citable = {s.sid: s for s in ordered if s.type != SourceType.book}
    book_sids = [s.sid for s in ordered if s.type == SourceType.book]
    if not any(s.type == SourceType.web for s in citable.values()):
        raise StepError("The evidence store has no web sources — re-run research first.")

    llm = ctx.providers.gen_llm
    s = ctx.settings
    prompt = build_generate_prompt(ctx.lesson.title, ctx.lesson.objective, outcomes, list(citable.values()), s)
    soft = soft_checks(outcomes, citable, s)
    # Only a too-short lesson (< 25 measured minutes) earns a repair call; other soft issues are warnings.
    repair_if_short = lambda d: [p for p in soft(d) if p.startswith(SHORT_LESSON_PREFIX)]  # noqa: E731
    draft = generate_structured(
        llm, prompt, LessonDraft, system=GENERATE_SYSTEM, max_repairs=s.llm_max_repairs,
        check=hard_checks(outcomes, citable), soft_check=repair_if_short, max_soft_repairs=1,
    )
    warnings = soft(draft)
    content = finalize(draft, ctx.lesson.title, ctx.lesson.objective, outcomes, citable, book_sids)
    content, minute_changes = set_measured_minutes(content, s)

    model = getattr(llm, "last_model", None) or llm.model or llm.name  # the model that actually answered
    version = save_version(ctx, content, VersionAuthor.ai, note=f"Generated by {model}")
    tiers = [citable[sid].reliability_tier for sid in content.references if sid in citable]
    return {
        "version_no": version.version_no,
        "model": model,
        "section_count": len(content.sections),
        "cited_sids": content.references,
        "citations_by_tier": {str(t): tiers.count(t) for t in sorted(set(tiers))},
        "further_reading": book_sids,
        "warnings": warnings,
        "minutes_adjusted": minute_changes,
        "prompt_chars": len(prompt),
    }
