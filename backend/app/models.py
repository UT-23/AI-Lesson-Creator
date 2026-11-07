"""Database tables (SQLModel on SQLite).

Append-only rules:
* LessonVersion rows are never updated — every edit / regeneration / fix is a new row.
* QCReport rows are never updated — re-running QC creates a new report.
* Source rows are never deleted — sids stay stable so older versions keep valid citations.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import JSON, Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LessonStatus(str, Enum):
    created = "created"
    running = "running"
    completed = "completed"
    completed_with_warnings = "completed_with_warnings"  # an optional research step failed
    failed = "failed"


class StepStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    skipped = "skipped"  # not run because a required upstream step failed


class SourceType(str, Enum):
    web = "web"
    book = "book"
    video = "video"


class VersionAuthor(str, Enum):
    ai = "ai"
    instructor = "instructor"
    qc_fix = "qc_fix"


class QCLayer(str, Enum):
    factual = "factual"
    instructional = "instructional"


class Severity(str, Enum):
    critical = "critical"
    major = "major"
    minor = "minor"


class IssueStatus(str, Enum):
    open = "open"
    applied = "applied"
    dismissed = "dismissed"


class Lesson(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    objective: str = Field(sa_column=Column(Text, nullable=False))
    status: LessonStatus = Field(default=LessonStatus.created)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PipelineStep(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("lesson_id", "name"),)

    id: int | None = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    name: str
    position: int  # order within the pipeline
    status: StepStatus = Field(default=StepStatus.pending)
    attempt: int = 0
    error: str | None = Field(default=None, sa_column=Column(Text))
    # Last *successful* output. Kept when a later re-run fails.
    output_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    started_at: datetime | None = None
    finished_at: datetime | None = None


class Source(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("lesson_id", "sid"), UniqueConstraint("lesson_id", "key"))

    id: int | None = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    sid: str  # "S1".."Sn", stable for the lifetime of the lesson
    key: str  # dedupe key: URL, or "book:<title>|<authors>" when a book has no link
    type: SourceType
    title: str
    url: str | None = None
    publisher: str | None = None  # site / channel / publisher, or book authors
    reliability_tier: int = Field(ge=1, le=4)
    reliability_reason: str
    excerpt_text: str = Field(default="", sa_column=Column(Text, nullable=False))
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class LessonVersion(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("lesson_id", "version_no"),)

    id: int | None = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    version_no: int
    content_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    content_md: str = Field(sa_column=Column(Text, nullable=False))
    author: VersionAuthor
    note: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class QCReport(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    lesson_id: int = Field(foreign_key="lesson.id", index=True)
    layer: QCLayer
    lesson_version_no: int
    summary: str = Field(sa_column=Column(Text, nullable=False))
    score: float
    # Layer-specific detail: QC1 claim table, QC2 coverage matrix, etc.
    details_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class ProviderCache(SQLModel, table=True):
    """Successful external-API responses, so retries never re-spend credits/quota.

    Keyed by (namespace, sha256 of the request params). Failures are never cached.
    Shared across lessons: the same Tavily query in two lessons is paid for once.
    """

    __table_args__ = (UniqueConstraint("namespace", "key"),)

    id: int | None = Field(default=None, primary_key=True)
    namespace: str = Field(index=True)  # "<provider name>.<operation>", e.g. "tavily.search"
    key: str
    params_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    response_json: Any = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class QCIssue(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    report_id: int = Field(foreign_key="qcreport.id", index=True)
    issue_id: str  # human-readable, e.g. "F-3" or "I-2"
    severity: Severity
    category: str
    location: str | None = None  # section id, e.g. "sec-2"
    claim_or_text: str = Field(default="", sa_column=Column(Text, nullable=False))
    evidence: str = Field(default="", sa_column=Column(Text, nullable=False))
    source_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    suggestion: str = Field(default="", sa_column=Column(Text, nullable=False))
    status: IssueStatus = Field(default=IssueStatus.open)
