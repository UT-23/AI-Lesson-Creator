"""Shared QC plumbing: persist reports, write .md/.json files, pick the QC model.

The two QC layers never share context; they only share this storage code.
"""

import json
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from app.models import QCIssue, QCLayer, QCReport, Severity
from app.pipeline.context import StepContext
from app.providers.llm import LLMProvider
from app.schemas import QCIssueDraft

FILE_NAMES = {QCLayer.factual: "qc1_factual_report", QCLayer.instructional: "qc2_instructional_report"}


def qc_model_for(ctx: StepContext) -> LLMProvider:
    """QC prefers a model other than the one that generated the lesson (independent judge)."""
    llm = ctx.providers.qc_llm
    generator = (ctx.output_of("generate") or {}).get("model")
    preferring_not = getattr(llm, "preferring_not", None)
    return preferring_not(generator) if preferring_not else llm


def model_used(llm: LLMProvider) -> str:
    return getattr(llm, "last_model", None) or llm.model or llm.name


def save_qc_report(
    session: Session,
    *,
    lesson_id: int,
    layer: QCLayer,
    version_no: int,
    summary: str,
    score: float,
    details: dict[str, Any],
    issues: list[QCIssueDraft],
) -> QCReport:
    """Append a new report + its issues (reports are never updated)."""
    report = QCReport(lesson_id=lesson_id, layer=layer, lesson_version_no=version_no,
                      summary=summary, score=round(score, 1), details_json=details)
    session.add(report)
    session.flush()

    prefix = "F" if layer == QCLayer.factual else "I"
    order = {"critical": 0, "major": 1, "minor": 2}
    for n, issue in enumerate(sorted(issues, key=lambda i: order[i.severity]), start=1):
        session.add(QCIssue(
            report_id=report.id,  # type: ignore[arg-type]
            issue_id=f"{prefix}-{n}",
            severity=Severity(issue.severity),
            category=issue.category,
            location=issue.location,
            claim_or_text=issue.claim_or_text,
            evidence=issue.evidence,
            source_ids=issue.source_ids,
            suggestion=issue.suggestion,
        ))
    session.flush()
    return report


def report_payload(session: Session, report: QCReport) -> dict[str, Any]:
    issues = session.exec(select(QCIssue).where(QCIssue.report_id == report.id)).all()
    return {
        "report_id": report.id,
        "layer": report.layer.value,
        "lesson_id": report.lesson_id,
        "lesson_version_no": report.lesson_version_no,
        "score": report.score,
        "summary": report.summary,
        "created_at": report.created_at.isoformat(),
        "details": report.details_json,
        "issues": [i.model_dump(exclude={"report_id"}) | {"severity": i.severity.value, "status": i.status.value}
                   for i in issues],
    }


def write_report_files(session: Session, report: QCReport, reports_dir: str) -> dict[str, str]:
    """Write <reports_dir>/lesson-<id>/qc{1,2}_..._report.{md,json}; returns the paths."""
    from app.export.reports import render_report_md  # local import: export depends on pipeline, not vice versa

    payload = report_payload(session, report)
    folder = Path(reports_dir) / f"lesson-{report.lesson_id}"
    folder.mkdir(parents=True, exist_ok=True)
    stem = FILE_NAMES[report.layer]
    md_path, json_path = folder / f"{stem}.md", folder / f"{stem}.json"
    md_path.write_text(render_report_md(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return {"md": str(md_path), "json": str(json_path)}
