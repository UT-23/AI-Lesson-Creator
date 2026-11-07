"""Export bundle: lesson.md (+ lesson.json, PDF/DOCX if pandoc exists), references.md, both QC reports."""

import io
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from sqlmodel import Session, col, select

from app.export.reports import render_report_md
from app.models import QCLayer, QCReport, SourceType
from app.pipeline.qc_store import FILE_NAMES, report_payload
from app.pipeline.render import render_reference
from app.schemas import LessonContent
from app.versions import latest_version, lesson_sources


def references_md(content: LessonContent, sources: dict) -> str:  # type: ignore[type-arg]
    lines = [f"# References — {content.title}", ""]
    for sid in sorted(content.cited_sids(), key=lambda s: int(s[1:])):
        if sid in sources:
            src = sources[sid]
            lines.append(render_reference(src))
            lines.append(f"  - Why this tier: {src.reliability_reason}")
    books = [sources[s] for s in content.further_reading if s in sources and sources[s].type == SourceType.book]
    if books:
        lines += ["", "## Further reading (catalogue details and publisher descriptions only; not used as evidence)", ""]
        lines += [f"- {b.title} — {b.publisher or ''} <{b.url or ''}>" for b in books]
    return "\n".join(lines) + "\n"


def latest_report(session: Session, lesson_id: int, layer: QCLayer) -> QCReport | None:
    return session.exec(select(QCReport).where(QCReport.lesson_id == lesson_id, QCReport.layer == layer)
                        .order_by(col(QCReport.id).desc())).first()


def _pandoc(markdown: str, fmt: str) -> bytes | None:
    if not shutil.which("pandoc"):
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp) / "lesson.md", Path(tmp) / f"lesson.{fmt}"
        src.write_text(markdown, encoding="utf-8")
        result = subprocess.run(["pandoc", str(src), "-o", str(out)], capture_output=True, timeout=120)
        return out.read_bytes() if result.returncode == 0 and out.exists() else None


def build_export(session: Session, lesson_id: int) -> tuple[bytes, list[str]]:
    """Return (zip bytes, list of file names inside)."""
    version = latest_version(session, lesson_id)
    if version is None:
        raise LookupError("This lesson has no version to export yet.")
    content = LessonContent.model_validate(version.content_json)
    sources = lesson_sources(session, lesson_id)
    files: dict[str, bytes] = {
        "lesson.md": version.content_md.encode("utf-8"),
        "lesson.json": json.dumps({"version_no": version.version_no, "author": version.author.value,
                                   "note": version.note, "content": version.content_json}, indent=2).encode("utf-8"),
        "references.md": references_md(content, sources).encode("utf-8"),
    }
    for layer in (QCLayer.factual, QCLayer.instructional):
        report = latest_report(session, lesson_id, layer)
        if report is not None:
            payload = report_payload(session, report)
            files[f"{FILE_NAMES[layer]}.md"] = render_report_md(payload).encode("utf-8")
            files[f"{FILE_NAMES[layer]}.json"] = json.dumps(payload, indent=2, default=str).encode("utf-8")
    for fmt in ("pdf", "docx"):
        data = _pandoc(version.content_md, fmt)
        if data:
            files[f"lesson.{fmt}"] = data

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buffer.getvalue(), list(files)
