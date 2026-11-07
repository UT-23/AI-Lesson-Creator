"""QC reports, re-running a layer, and the issue workflow: preview fix → apply / dismiss."""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import get_lesson_or_404, get_providers
from app.config import Settings, get_settings
from app.db import get_session
from app.export.exporter import latest_report
from app.models import IssueStatus, Lesson, QCIssue, QCLayer, QCReport, VersionAuthor
from app.pipeline.apply_fix import FixNotPossible, preview_fix
from app.pipeline.orchestrator import RunRejected, run_pipeline, start_run
from app.pipeline.qc_store import report_payload
from app.providers import Providers
from app.providers.errors import ProviderError
from app.providers.llm import LLMOutputError
from app.schemas import LessonContent, QuizItem
from app.versions import append_version, latest_version, with_quiz_item, with_section_text

router = APIRouter(tags=["qc"])
STEP_FOR_LAYER = {"factual": "qc_factual", "instructional": "qc_instructional"}


@router.get("/lessons/{lesson_id}/qc")
def get_qc(lesson: Lesson = Depends(get_lesson_or_404), session: Session = Depends(get_session)) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for layer in (QCLayer.factual, QCLayer.instructional):
        report = latest_report(session, lesson.id, layer)  # type: ignore[arg-type]
        out[layer.value] = report_payload(session, report) if report else None
    return out


@router.post("/lessons/{lesson_id}/qc/{layer}", status_code=202)
def rerun_qc(layer: str, background: BackgroundTasks, lesson: Lesson = Depends(get_lesson_or_404),
             session: Session = Depends(get_session), providers: Providers = Depends(get_providers),
             settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Re-run one QC layer on the latest version (runs in the background; poll the steps)."""
    step = STEP_FOR_LAYER.get(layer)
    if step is None:
        raise HTTPException(404, "Layer must be 'factual' or 'instructional'.")
    try:
        start_run(session, lesson.id, from_step=step)  # type: ignore[arg-type]
    except RunRejected as err:
        raise HTTPException(409, str(err)) from err
    background.add_task(run_pipeline, lesson.id, providers, settings)
    return {"message": f"Re-running {step} on the latest version."}


def _issue(session: Session, issue_id: int) -> tuple[QCIssue, QCReport]:
    issue = session.get(QCIssue, issue_id)
    if issue is None:
        raise HTTPException(404, f"Issue {issue_id} not found.")
    report = session.get(QCReport, issue.report_id)
    return issue, report  # type: ignore[return-value]


@router.post("/qc/issues/{issue_id}/preview-fix")
def preview(issue_id: int, session: Session = Depends(get_session), providers: Providers = Depends(get_providers),
            settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    issue, report = _issue(session, issue_id)
    try:
        return preview_fix(session, issue, report.lesson_id, providers.gen_llm, settings)
    except FixNotPossible as err:
        raise HTTPException(422, str(err)) from err
    except (ProviderError, LLMOutputError) as err:
        raise HTTPException(503, f"Could not generate a fix: {err}") from err


class ApplyFix(BaseModel):
    section_id: str | None = None
    content_md: str | None = None
    quiz_index: int | None = None  # 0-based; with quiz_item, replaces one knowledge-check question
    quiz_item: QuizItem | None = None


@router.post("/qc/issues/{issue_id}/apply")
def apply(issue_id: int, body: ApplyFix, session: Session = Depends(get_session)) -> dict[str, Any]:
    issue, report = _issue(session, issue_id)
    version = latest_version(session, report.lesson_id)
    if version is None:
        raise HTTPException(409, "No lesson version to fix.")
    content = LessonContent.model_validate(version.content_json)
    if body.quiz_index is not None and body.quiz_item is not None:
        try:
            content = with_quiz_item(content, body.quiz_index, body.quiz_item)
        except IndexError:
            raise HTTPException(404, f"Quiz question Q{body.quiz_index + 1} does not exist.") from None
        where = f"quiz Q{body.quiz_index + 1}"
    elif body.section_id and body.content_md and body.content_md.strip():
        try:
            content = with_section_text(content, body.section_id, body.content_md)
        except KeyError:
            raise HTTPException(404, f"Section {body.section_id} does not exist.") from None
        where = body.section_id
    else:
        raise HTTPException(422, "Send section_id + content_md, or quiz_index + quiz_item.")
    new = append_version(session, report.lesson_id, content, VersionAuthor.qc_fix,
                         f"QC fix for {issue.issue_id} ({issue.category}) in {where}")
    issue.status = IssueStatus.applied
    session.add(issue)
    session.commit()
    return {"version_no": new.version_no, "message": f"Fix applied as version {new.version_no}."}


@router.post("/qc/issues/{issue_id}/dismiss")
def dismiss(issue_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    issue, _ = _issue(session, issue_id)
    issue.status = IssueStatus.dismissed
    session.add(issue)
    session.commit()
    return {"message": f"Issue {issue.issue_id} dismissed."}
