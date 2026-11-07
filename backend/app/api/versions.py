"""Version history: list, read, restore (restore = a new version copying an old one)."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.api.deps import get_lesson_or_404
from app.db import get_session
from app.models import Lesson, LessonVersion, VersionAuthor
from app.schemas import LessonContent
from app.versions import append_version

router = APIRouter(prefix="/lessons/{lesson_id}/versions", tags=["versions"])


def _get(session: Session, lesson_id: int, n: int) -> LessonVersion:
    version = session.exec(select(LessonVersion).where(LessonVersion.lesson_id == lesson_id,
                                                       LessonVersion.version_no == n)).first()
    if version is None:
        raise HTTPException(404, f"Version {n} not found.")
    return version


@router.get("")
def list_versions(lesson: Lesson = Depends(get_lesson_or_404), session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = session.exec(select(LessonVersion).where(LessonVersion.lesson_id == lesson.id)
                        .order_by(col(LessonVersion.version_no).desc())).all()
    return [{"version_no": v.version_no, "author": v.author.value, "note": v.note, "created_at": v.created_at}
            for v in rows]


@router.get("/{n}")
def get_version(n: int, lesson: Lesson = Depends(get_lesson_or_404), session: Session = Depends(get_session)) -> dict[str, Any]:
    v = _get(session, lesson.id, n)  # type: ignore[arg-type]
    return {"version_no": v.version_no, "author": v.author.value, "note": v.note, "content": v.content_json,
            "markdown": v.content_md}


@router.post("/{n}/restore")
def restore(n: int, lesson: Lesson = Depends(get_lesson_or_404), session: Session = Depends(get_session)) -> dict[str, Any]:
    old = _get(session, lesson.id, n)  # type: ignore[arg-type]
    new = append_version(session, lesson.id, LessonContent.model_validate(old.content_json),  # type: ignore[arg-type]
                         VersionAuthor.instructor, f"Restored from version {n}")
    session.commit()
    return {"version_no": new.version_no, "message": f"Version {n} restored as version {new.version_no}."}
