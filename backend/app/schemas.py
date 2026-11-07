"""Pydantic schemas: API request/response bodies and LLM structured outputs.

LLM output schemas double as the JSON schema we send to the model, so field
descriptions here are part of the prompt.
"""

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import LessonStatus, StepStatus

# ---------------------------------------------------------------------------
# API: lessons
# ---------------------------------------------------------------------------

TITLE_MIN, TITLE_MAX = 3, 200
OBJECTIVE_MIN, OBJECTIVE_MAX = 15, 1000


def _clean_text(value: Any, field: str, min_len: int, max_len: int) -> str:
    if value is None or not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required.")
    cleaned = re.sub(r"\s+", " ", value).strip()
    if len(cleaned) < min_len:
        raise ValueError(f"{field} is too short (minimum {min_len} characters).")
    if len(cleaned) > max_len:
        raise ValueError(f"{field} is too long (maximum {max_len} characters).")
    if not re.search(r"[A-Za-z0-9]", cleaned):
        raise ValueError(f"{field} must contain letters or numbers.")
    return cleaned


class LessonCreate(BaseModel):
    title: str = Field(description="Lesson title", examples=["HTTP Requests and Responses"])
    objective: str = Field(description="Learning objective, ideally starting with an action verb")

    @field_validator("title", mode="before")
    @classmethod
    def _title(cls, v: Any) -> str:
        return _clean_text(v, "Title", TITLE_MIN, TITLE_MAX)

    @field_validator("objective", mode="before")
    @classmethod
    def _objective(cls, v: Any) -> str:
        return _clean_text(v, "Learning objective", OBJECTIVE_MIN, OBJECTIVE_MAX)


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    position: int
    status: StepStatus
    attempt: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    output_json: dict[str, Any] | None = None


class LessonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    objective: str
    status: LessonStatus
    created_at: datetime
    updated_at: datetime


class LessonCreatedOut(LessonOut):
    steps: list[StepOut]


class RunAccepted(BaseModel):
    lesson_id: int
    status: LessonStatus
    from_step: str
    message: str


# ---------------------------------------------------------------------------
# LLM output: plan
# ---------------------------------------------------------------------------


class ResearchPlan(BaseModel):
    outcomes: list[str] = Field(
        min_length=1,
        max_length=8,
        description="Atomic, measurable learning outcomes. Keep the objective's own verbs (explain, distinguish, calculate...).",
    )
    queries: list[str] = Field(
        min_length=4,
        max_length=8,
        description="4-8 focused web research sub-queries that together cover every outcome.",
    )
    book_queries: list[str] = Field(
        default_factory=list,
        max_length=2,
        description='1-2 short library-catalogue queries naming the subject, e.g. "HTTP protocol".',
    )


# ---------------------------------------------------------------------------
# LLM output: lesson
# ---------------------------------------------------------------------------

SectionType = Literal["hook", "concept", "example", "activity", "video", "knowledge_check", "summary"]
CITATION_RE = re.compile(r"\[(S\d+)\]")
# Models also write grouped citations like "[S3, S5]" or "[S3; S5]".
CITATION_GROUP_RE = re.compile(r"\[(S\d+(?:\s*[,;]\s*S\d+)*)\]")


def extract_citations(text: str) -> list[str]:
    """All cited sids in order, from single and grouped citations."""
    return [sid for group in CITATION_GROUP_RE.findall(text) for sid in re.findall(r"S\d+", group)]


def normalize_citations(text: str) -> str:
    """'[S3, S5]' → '[S3], [S5]' so every later step sees one citation format."""
    return CITATION_GROUP_RE.sub(lambda m: ", ".join(f"[{s}]" for s in re.findall(r"S\d+", m.group(1))), text)


class LessonSection(BaseModel):
    id: str = Field(description='Stable section id like "sec-1"')
    type: SectionType
    heading: str
    minutes: float = Field(ge=0, description="Planned learner minutes for this section")
    content_md: str = Field(description="Markdown body. Put a [S#] citation after every factual claim.")
    outcomes_covered: list[str] = Field(default_factory=list)


class LessonVideo(BaseModel):
    sid: str
    title: str
    url: str
    duration_min: float = Field(ge=0)
    why: str = Field(description="Why this video helps with the outcomes")
    watch_segment: str | None = Field(default=None, description='Optional "mm:ss-mm:ss" segment to watch')


class QuizItem(BaseModel):
    q: str
    options: list[str] = Field(min_length=2)
    answer: str = Field(description="Must exactly equal one of the options")
    explanation: str
    outcome: str = Field(description="The outcome this question assesses")

    @model_validator(mode="after")
    def _answer_in_options(self) -> "QuizItem":
        if self.answer not in self.options:
            raise ValueError(f"answer {self.answer!r} is not one of the options {self.options!r}")
        if len(set(self.options)) != len(self.options):
            raise ValueError(f"options must be distinct: {self.options!r}")
        return self


class LessonDraft(BaseModel):
    """The lesson exactly as the generation model must return it."""

    title: str
    objective: str
    outcomes: list[str] = Field(min_length=1)
    total_minutes: float = Field(ge=0)
    sections: list[LessonSection] = Field(min_length=1)
    videos: list[LessonVideo] = Field(default_factory=list)
    knowledge_check: list[QuizItem] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list, description="sids cited in the lesson")

    @model_validator(mode="after")
    def _unique_section_ids(self) -> "LessonDraft":
        ids = [s.id for s in self.sections]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate section ids: {sorted(dupes)}")
        return self

    def cited_sids(self) -> set[str]:
        """Every [S#] that appears anywhere in the lesson text."""
        texts = [s.content_md for s in self.sections]
        texts += [q.explanation for q in self.knowledge_check]
        found: set[str] = set()
        for text in texts:
            found.update(extract_citations(text))
        found.update(v.sid for v in self.videos)
        return found


class LessonContent(LessonDraft):
    """What a LessonVersion stores: the draft plus fields only code fills in."""

    # Book sids shown as "Further reading". Books are metadata-only, so they are
    # never cited for claims; code lists them instead of the model.
    further_reading: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM output: research judgements
# ---------------------------------------------------------------------------


class VideoRelevanceJudgement(BaseModel):
    spoken_language: str = Field(description='Main language of the narration as an ISO 639-1 code, e.g. "en", "hi", "es"')
    relevant: bool = Field(description="True only if a substantial part of the video directly teaches at least one outcome")
    reason: str = Field(description="One or two sentences explaining the decision")
    outcomes_matched: list[str] = Field(default_factory=list, description="Exact outcome texts the video teaches")
    key_points: list[str] = Field(
        default_factory=list,
        description="3-6 factual statements the video itself makes. Never add facts the video does not state.",
    )
    suggested_segment: str | None = Field(default=None, description='Most useful part as "mm:ss-mm:ss", or null')


class BookRating(BaseModel):
    id: int = Field(description="The candidate number in brackets")
    score: int = Field(ge=0, le=10, description="Suitability as further reading, using the rubric")
    reason: str


class BookSelection(BaseModel):
    ratings: list[BookRating] = Field(description="One rating per candidate")


class DomainTier(BaseModel):
    name: str = Field(description="The host or channel name exactly as given")
    tier: int = Field(ge=1, le=4)
    reason: str


class DomainTiers(BaseModel):
    items: list[DomainTier]


# ---------------------------------------------------------------------------
# LLM output: QC (Phase 1 skeleton — replaced by claim-level QC in Phases 4/5)
# ---------------------------------------------------------------------------


class QCIssueDraft(BaseModel):
    severity: Literal["critical", "major", "minor"]
    category: str
    location: str | None = Field(default=None, description="Section id, e.g. sec-2")
    claim_or_text: str
    evidence: str = ""
    source_ids: list[str] = Field(default_factory=list)
    suggestion: str


class QCReviewDraft(BaseModel):
    summary: str
    score: float = Field(ge=0, le=100)
    issues: list[QCIssueDraft] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM output: QC1 (batched claim verification) and QC2 (instructional review)
# ---------------------------------------------------------------------------

ClaimVerdictLabel = Literal["supported", "partially_supported", "unsupported", "contradicted"]


class ClaimVerdict(BaseModel):
    claim_id: str = Field(description='The claim id, e.g. "C3"')
    verdict: ClaimVerdictLabel
    source_id: str | None = Field(default=None, description="The cited source id the verdict is based on")
    evidence_quote: str = Field(
        default="",
        description="A span copied VERBATIM from that source's excerpt that decides the verdict; empty if none exists",
    )
    explanation: str = Field(description="One sentence: why this verdict")


class Contradiction(BaseModel):
    location: str = Field(description='Where, e.g. "sec-2 vs quiz Q3"')
    description: str
    suggestion: str


class FactCheckResult(BaseModel):
    verdicts: list[ClaimVerdict]
    contradictions: list[Contradiction] = Field(default_factory=list)


class CoverageCell(BaseModel):
    present: bool
    sections: list[str] = Field(default_factory=list, description="Section ids where it appears")
    note: str = ""


class OutcomeCoverage(BaseModel):
    outcome: str = Field(description="Copy the outcome text exactly")
    explanation: CoverageCell
    example: CoverageCell
    practice: CoverageCell = Field(description="An activity where the learner does the outcome's verb")
    quiz: CoverageCell


class VerbAlignment(BaseModel):
    outcome: str
    verb: str
    bloom_level: Literal["remember", "understand", "apply", "analyze", "evaluate", "create"]
    aligned: bool = Field(description="Do the activity and quiz actually make the learner perform this verb?")
    evidence: str
    suggestion: str = ""


RubricCriterion = Literal["clarity", "structure_flow", "jargon_before_use", "example_quality",
                          "practical_relevance", "outcome_alignment"]


class RubricScore(BaseModel):
    criterion: RubricCriterion
    score: int = Field(ge=1, le=5)
    justification: str


class InstructionalReview(BaseModel):
    summary: str
    coverage: list[OutcomeCoverage]
    verb_alignment: list[VerbAlignment]
    rubric: list[RubricScore]
    issues: list[QCIssueDraft] = Field(default_factory=list)


class SectionRewrite(BaseModel):
    content_md: str = Field(description="The full replacement Markdown for this one section")
    change_summary: str = Field(description="One or two sentences describing what changed and why")
