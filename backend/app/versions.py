"""Append-only lesson versions: every AI generation, instructor edit, QC fix or restore is a new row."""

from sqlmodel import Session, col, select

from app.models import LessonVersion, Source, VersionAuthor
from app.pipeline.render import render_markdown
from app.schemas import LessonContent, normalize_citations


def latest_version(session: Session, lesson_id: int) -> LessonVersion | None:
    return session.exec(
        select(LessonVersion).where(LessonVersion.lesson_id == lesson_id).order_by(col(LessonVersion.version_no).desc())
    ).first()


def lesson_sources(session: Session, lesson_id: int) -> dict[str, Source]:
    return {s.sid: s for s in session.exec(select(Source).where(Source.lesson_id == lesson_id)).all()}


def append_version(session: Session, lesson_id: int, content: LessonContent, author: VersionAuthor,
                   note: str) -> LessonVersion:
    sources = lesson_sources(session, lesson_id)
    content = content.model_copy(update={
        "references": sorted(content.cited_sids(), key=lambda s: int(s[1:])),
        "total_minutes": round(sum(s.minutes for s in content.sections), 1),
    })
    latest = latest_version(session, lesson_id)
    version = LessonVersion(
        lesson_id=lesson_id,
        version_no=(latest.version_no if latest else 0) + 1,
        content_json=content.model_dump(),
        content_md=render_markdown(content, sources),
        author=author,
        note=note,
    )
    session.add(version)
    session.flush()
    return version


def with_section_text(content: LessonContent, section_id: str, content_md: str,
                      heading: str | None = None) -> LessonContent:
    if not any(s.id == section_id for s in content.sections):
        raise KeyError(section_id)
    sections = [
        s.model_copy(update={"content_md": normalize_citations(content_md), "heading": heading or s.heading})
        if s.id == section_id else s
        for s in content.sections
    ]
    return content.model_copy(update={"sections": sections})
