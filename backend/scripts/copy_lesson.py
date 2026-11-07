"""Copy a lesson (steps, sources, versions, QC reports + issues) to a new lesson id — for rehearsals.

Usage (from backend/):  .venv/Scripts/python scripts/copy_lesson.py 2   [--db data/lessons.db]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app import db  # noqa: E402
from app.models import Lesson, LessonVersion, PipelineStep, QCIssue, QCReport, Source  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("lesson_id", type=int)
    parser.add_argument("--db", default=str(Path(__file__).resolve().parent.parent / "data" / "lessons.db"))
    args = parser.parse_args()
    db.init_engine(f"sqlite:///{Path(args.db).as_posix()}")
    with Session(db.get_engine()) as s:
        old = s.get(Lesson, args.lesson_id)
        if old is None:
            raise SystemExit(f"No lesson {args.lesson_id}")
        new = Lesson(title=f"{old.title} (copy)", objective=old.objective, status=old.status)
        s.add(new)
        s.flush()

        def clone(rows, **overrides):  # type: ignore[no-untyped-def]
            out = []
            for row in rows:
                data = row.model_dump(exclude={"id"})
                data.update(overrides)
                out.append(type(row)(**data))
            s.add_all(out)
            return out

        for model in (PipelineStep, Source, LessonVersion):
            clone(s.exec(select(model).where(model.lesson_id == old.id)).all(), lesson_id=new.id)
        for report in s.exec(select(QCReport).where(QCReport.lesson_id == old.id)).all():
            [copy] = clone([report], lesson_id=new.id)
            s.flush()
            clone(s.exec(select(QCIssue).where(QCIssue.report_id == report.id)).all(), report_id=copy.id)
        s.commit()
        print(f"Copied lesson {old.id} -> {new.id} ({new.title})")


if __name__ == "__main__":
    main()
