"""Lessons: create, run, read, edit, preview, export."""

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlmodel import Session, col, select

from app.api.deps import get_lesson_or_404, get_providers
from app.config import Settings, get_settings
from app.db import get_session
from app.export.exporter import build_export
from app.pipeline.timebudget import compute_time_budget
from app.models import Lesson, LessonStatus, VersionAuthor
from app.pipeline.orchestrator import RunRejected, create_steps, get_steps, run_pipeline, start_run
from app.providers import Providers
from app.schemas import LessonContent, LessonCreate, QuizItem, LessonCreatedOut, RunAccepted, StepOut, extract_citations
from app.versions import append_version, latest_version, lesson_sources, with_quiz_item, with_section_text

router = APIRouter(prefix="/lessons", tags=["lessons"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=LessonCreatedOut)
def create_lesson(body: LessonCreate, session: Session = Depends(get_session)) -> LessonCreatedOut:
    lesson = Lesson(title=body.title, objective=body.objective)
    session.add(lesson)
    session.flush()
    steps = create_steps(session, lesson.id)  # type: ignore[arg-type]
    session.commit()
    session.refresh(lesson)
    return LessonCreatedOut(
        id=lesson.id,  # type: ignore[arg-type]
        title=lesson.title,
        objective=lesson.objective,
        status=lesson.status,
        created_at=lesson.created_at,
        updated_at=lesson.updated_at,
        steps=[StepOut.model_validate(s) for s in steps],
    )


@router.post("/{lesson_id}/run", status_code=status.HTTP_202_ACCEPTED, response_model=RunAccepted)
def run_lesson(
    background: BackgroundTasks,
    lesson: Lesson = Depends(get_lesson_or_404),
    session: Session = Depends(get_session),
    providers: Providers = Depends(get_providers),
    settings: Settings = Depends(get_settings),
) -> RunAccepted:
    """Run (or resume) the pipeline: every step that isn't `done` is (re-)run in the background."""
    try:
        first = start_run(session, lesson.id)  # type: ignore[arg-type]
    except RunRejected as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    background.add_task(run_pipeline, lesson.id, providers, settings)
    return RunAccepted(lesson_id=lesson.id, status=LessonStatus.running, from_step=first,  # type: ignore[arg-type]
                       message=f"Pipeline started from '{first}'. Poll GET /lessons/{lesson.id}/steps for progress.")


# ---------------------------------------------------------------------------
# Read / edit / preview / export
# ---------------------------------------------------------------------------


@router.get("")
def list_lessons(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    lessons = session.exec(select(Lesson).order_by(col(Lesson.id).desc())).all()
    return [{"id": l.id, "title": l.title, "status": l.status.value, "updated_at": l.updated_at} for l in lessons]


@router.get("/{lesson_id}")
def get_lesson(lesson: Lesson = Depends(get_lesson_or_404), session: Session = Depends(get_session)) -> dict[str, Any]:
    """Latest version + the sources of the current research run + step statuses."""
    version = latest_version(session, lesson.id)  # type: ignore[arg-type]
    steps = {s.name: s for s in get_steps(session, lesson.id)}  # type: ignore[arg-type]
    current = (steps["score_sources"].output_json or {}).get("sids", [])
    sources = lesson_sources(session, lesson.id)  # type: ignore[arg-type]
    gen = steps["generate"].output_json or {}
    return {
        "lesson": {"id": lesson.id, "title": lesson.title, "objective": lesson.objective,
                   "status": lesson.status.value},
        "version": None if version is None else {
            "version_no": version.version_no, "author": version.author.value, "note": version.note,
            "created_at": version.created_at, "content": version.content_json, "markdown": version.content_md},
        "generation": {"model": gen.get("model"), "warnings": gen.get("warnings", []),
                       "minutes_adjusted": gen.get("minutes_adjusted", [])},
        "time_budget": steps["timebudget"].output_json,
        # Measured on the latest version right now (the timebudget step output can predate edits).
        "measured_time": None if version is None else compute_time_budget(
            LessonContent.model_validate(version.content_json)).model_dump(),
        "sources": [s.model_dump(exclude={"key", "lesson_id"}) | {"type": s.type.value}
                    for sid, s in sorted(sources.items(), key=lambda kv: int(kv[0][1:])) if sid in current],
    }


class SectionEdit(BaseModel):
    content_md: str
    heading: str | None = None


class ContentEdit(BaseModel):
    sections: dict[str, SectionEdit] = {}
    quiz: dict[int, QuizItem] = {}  # 0-based index -> full replacement question
    note: str | None = None


@router.put("/{lesson_id}/content")
def edit_content(body: ContentEdit, lesson: Lesson = Depends(get_lesson_or_404),
                 session: Session = Depends(get_session)) -> dict[str, Any]:
    """Instructor edit of one or more sections → a new version (author=instructor). Nothing is overwritten."""
    version = latest_version(session, lesson.id)  # type: ignore[arg-type]
    if version is None:
        raise HTTPException(409, "There is no lesson version to edit yet — run the pipeline first.")
    if not body.sections and not body.quiz:
        raise HTTPException(422, "Nothing to save.")
    content = LessonContent.model_validate(version.content_json)
    known = set(lesson_sources(session, lesson.id))  # type: ignore[arg-type]
    for section_id, edit in body.sections.items():
        if not edit.content_md.strip():
            raise HTTPException(422, f"Section {section_id} cannot be empty.")
        unknown = sorted(set(extract_citations(edit.content_md)) - known)
        if unknown:
            raise HTTPException(422, f"Section {section_id} cites unknown source ids: {', '.join(unknown)}.")
        try:
            content = with_section_text(content, section_id, edit.content_md, edit.heading)
        except KeyError:
            raise HTTPException(404, f"Section {section_id} does not exist.") from None
    for index, item in body.quiz.items():
        unknown = sorted(set(extract_citations(item.explanation)) - known)
        if unknown:
            raise HTTPException(422, f"Quiz Q{index + 1} cites unknown source ids: {', '.join(unknown)}.")
        try:
            content = with_quiz_item(content, index, item)
        except IndexError:
            raise HTTPException(404, f"Quiz question Q{index + 1} does not exist.") from None
    edited = [*body.sections, *(f"quiz Q{i + 1}" for i in body.quiz)]
    new = append_version(session, lesson.id, content, VersionAuthor.instructor,  # type: ignore[arg-type]
                         body.note or f"Instructor edited {', '.join(edited)}")
    session.commit()
    return {"version_no": new.version_no, "message": f"Saved as version {new.version_no}."}


@router.get("/{lesson_id}/preview")
def preview(lesson: Lesson = Depends(get_lesson_or_404), session: Session = Depends(get_session)) -> dict[str, Any]:
    version = latest_version(session, lesson.id)  # type: ignore[arg-type]
    if version is None:
        raise HTTPException(404, "No lesson version yet.")
    return {"version_no": version.version_no, "markdown": version.content_md}


@router.get("/{lesson_id}/export")
def export(lesson: Lesson = Depends(get_lesson_or_404), session: Session = Depends(get_session)) -> Response:
    try:
        data, names = build_export(session, lesson.id)  # type: ignore[arg-type]
    except LookupError as err:
        raise HTTPException(404, str(err)) from err
    filename = f"lesson-{lesson.id}.zip"
    return Response(content=data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "X-Export-Files": ",".join(names)})
