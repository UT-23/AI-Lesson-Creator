"""Turn one QC issue into a rewrite of ONE section (preview), which the instructor can apply or dismiss.

The writer model gets the section, the issue, the outcomes, and excerpts of the
relevant sources (for factual fixes). Code checks the rewrite only cites
web/video sources of this lesson. Nothing is saved here: `preview_fix` returns
before/after; the API's apply endpoint creates the new version.
"""

import re
from typing import Any

from sqlmodel import Session

from app.config import Settings
from app.models import QCIssue, SourceType
from app.pipeline.passages import select_passages, topic_keywords
from app.providers.llm import LLMProvider, generate_structured
from app.schemas import LessonContent, SectionRewrite, extract_citations
from app.versions import latest_version, lesson_sources

FIX_SYSTEM = ("You are an expert instructional designer revising one section of a lesson. Change only what is "
              "needed to resolve the reviewer's issue; keep the rest of the section, its style and its citations.")


class FixNotPossible(Exception):
    """The issue cannot be fixed by rewriting a single section (message is user-facing)."""


def section_for_issue(issue: QCIssue, content: LessonContent) -> str:
    ids = re.findall(r"sec-\d+", issue.location or "")
    for sid in ids:
        if any(s.id == sid for s in content.sections):
            return sid
    raise FixNotPossible(
        f"Issue {issue.issue_id} is not tied to a single lesson section (location: {issue.location or 'none'}). "
        "Edit the lesson directly instead.")


def preview_fix(session: Session, issue: QCIssue, lesson_id: int, llm: LLMProvider,
                settings: Settings) -> dict[str, Any]:
    version = latest_version(session, lesson_id)
    if version is None:
        raise FixNotPossible("The lesson has no version yet.")
    content = LessonContent.model_validate(version.content_json)
    section_id = section_for_issue(issue, content)
    section = next(s for s in content.sections if s.id == section_id)

    sources = lesson_sources(session, lesson_id)
    citable = {sid: s for sid, s in sources.items() if s.type != SourceType.book}
    wanted = list(dict.fromkeys([*extract_citations(section.content_md), *(issue.source_ids or [])]))
    wanted += [sid for sid, s in sorted(citable.items(), key=lambda kv: kv[1].reliability_tier)
               if s.reliability_tier <= 2 and sid not in wanted][:3]  # strong sources for factual fixes
    keywords = topic_keywords([section.content_md, issue.claim_or_text, issue.suggestion])
    blocks = []
    for sid in wanted[:6]:
        src = citable.get(sid)
        if src:
            excerpt, _ = select_passages(src.excerpt_text, keywords, 2500)
            blocks.append(f"[{sid}] tier {src.reliability_tier}: {src.title}\n{excerpt}")
    outcomes = "\n".join(f"- {o}" for o in content.outcomes)
    prompt = f"""Rewrite ONE section of a lesson to resolve a reviewer's issue.

LESSON OUTCOMES:
{outcomes}

SECTION [{section.id}] ({section.type}) "{section.heading}":
{section.content_md}

ISSUE {issue.issue_id} ({issue.severity}, {issue.category}):
Text: {issue.claim_or_text}
Evidence: {issue.evidence}
Suggestion: {issue.suggestion}

SOURCES you may cite (cite as [S#] right after each factual claim; no other ids):
{chr(10).join(blocks) or '(none)'}

Return the complete new Markdown for this section only (no heading line) and a short change summary.
Keep every correct part and existing valid citation. Do not invent facts the sources do not state."""

    allowed = set(citable)

    def check(rewrite: SectionRewrite) -> list[str]:
        bad = sorted(set(extract_citations(rewrite.content_md)) - allowed)
        return [f"Unknown source ids cited: {', '.join(bad)}. Only cite: {', '.join(wanted)}."] if bad else []

    rewrite = generate_structured(llm, prompt, SectionRewrite, system=FIX_SYSTEM,
                                  max_repairs=settings.llm_max_repairs, check=check)

    def tiers(text: str) -> dict[str, int]:
        return {sid: citable[sid].reliability_tier for sid in dict.fromkeys(extract_citations(text)) if sid in citable}

    before_tiers, after_tiers = tiers(section.content_md), tiers(rewrite.content_md)
    # Facts from stored data, so the instructor never has to trust the model's own change summary.
    added = {sid: t for sid, t in after_tiers.items() if sid not in before_tiers}
    removed = {sid: t for sid, t in before_tiers.items() if sid not in after_tiers}
    return {
        "issue_id": issue.id,
        "section_id": section_id,
        "heading": section.heading,
        "base_version_no": version.version_no,
        "before": section.content_md,
        "after": rewrite.content_md,
        "change_summary": rewrite.change_summary,
        "citations_added": added,  # sid -> reliability tier (from the evidence store)
        "citations_removed": removed,
        "unchanged": rewrite.content_md.strip() == section.content_md.strip(),
        "model": getattr(llm, "last_model", None) or llm.model,
    }
