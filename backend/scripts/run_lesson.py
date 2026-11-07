"""Run the pipeline for one lesson up to a step (default: timebudget) and save the lesson Markdown.

Usage (from backend/):
    .venv/Scripts/python scripts/run_lesson.py "HTTP Requests and Responses"
    .venv/Scripts/python scripts/run_lesson.py "Simple vs Compound Interest" --until generate
    .venv/Scripts/python scripts/run_lesson.py "Photosynthesis" --objective "Explain how plants make glucose" --offline

Shares data/try_research.db with try_research.py, so research already done for
a title is served from the cache. Output: data/out/<title-slug>-lesson<id>-v<n>.md
"""

import argparse
import logging
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from sqlmodel import Session, col, select  # noqa: E402

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import Lesson, LessonVersion  # noqa: E402
from app.pipeline.orchestrator import STEP_NAMES, create_steps, get_steps, run_pipeline, start_run  # noqa: E402
from app.providers import build_providers  # noqa: E402
from app.providers.errors import ProviderError  # noqa: E402

KNOWN_OBJECTIVES = {
    "http requests and responses": "Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx "
                                   "response status categories.",
    "simple vs compound interest": "Calculate simple and compound interest for a given principal, rate, and time, "
                                   "and explain why compound interest grows faster.",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("title", nargs="?", help="omit when using --lesson")
    parser.add_argument("--objective")
    parser.add_argument("--lesson", type=int, help="re-run an existing lesson instead of creating one")
    parser.add_argument("--from", dest="from_step", default="generate", choices=STEP_NAMES,
                        help="with --lesson: step to retry from (earlier steps reuse saved outputs)")
    parser.add_argument("--until", default="timebudget", choices=STEP_NAMES, help="last step to run")
    parser.add_argument("--offline", action="store_true", help="use fake providers (DEMO_OFFLINE)")
    parser.add_argument("--db", default=str(BACKEND / "data" / "try_research.db"))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)-7s %(name)s: %(message)s")

    if args.lesson is None and not args.title:
        parser.error("give a title, or --lesson ID")
    objective = args.objective or KNOWN_OBJECTIVES.get((args.title or "").strip().lower())
    if args.lesson is None and not objective:
        parser.error("--objective is required for this title")
    settings = get_settings()
    if args.offline:
        settings = settings.model_copy(update={"demo_offline": True})
    try:
        providers = build_providers(settings)
    except ProviderError as err:
        print(f"Cannot start: {err.message}")
        return 2

    db.init_engine(f"sqlite:///{Path(args.db).as_posix()}")
    with Session(db.get_engine()) as session:
        if args.lesson is not None:
            existing = session.get(Lesson, args.lesson)
            if existing is None:
                print(f"No lesson {args.lesson} in {args.db}")
                return 2
            lesson_id: int = args.lesson
            args.title = existing.title
            start_run(session, lesson_id, from_step=args.from_step)
        else:
            lesson = Lesson(title=args.title.strip(), objective=objective)
            session.add(lesson)
            session.flush()
            create_steps(session, lesson.id)  # type: ignore[arg-type]
            session.commit()
            lesson_id = lesson.id  # type: ignore[assignment]
            start_run(session, lesson_id)

    print(f"Lesson {lesson_id}: {args.title!r} — running up to '{args.until}' (offline={settings.demo_offline}) …\n")
    run_pipeline(lesson_id, providers, settings, stop_after=args.until)

    with Session(db.get_engine()) as session:
        steps = {s.name: s for s in get_steps(session, lesson_id)}
        print("STEPS")
        for name in STEP_NAMES[: STEP_NAMES.index(args.until) + 1]:
            step = steps[name]
            print(f"  {name:17} {step.status.value:8} {(step.error or '')[:150]}")

        gen = steps["generate"].output_json or {}
        if gen and steps["generate"].status.value != "done":
            print("\n(generate failed this run — showing its last SUCCESSFUL output and version below)")
        if gen:
            for change in gen.get("minutes_adjusted", []):
                print(f"  minutes: {change['section']} declared {change['declared']:g} -> measured {change['measured']}")
            print(f"\nGENERATION  model={gen.get('model')}  sections={gen.get('section_count')}  "
                  f"prompt={gen.get('prompt_chars')} chars")
            print(f"  cited: {', '.join(gen.get('cited_sids', []))}   by tier: {gen.get('citations_by_tier')}")
            print(f"  further reading (books): {', '.join(gen.get('further_reading', [])) or '-'}")
            for warning in gen.get("warnings", []):
                print(f"  WARNING: {warning}")

        tb = steps["timebudget"].output_json or {}
        if tb:
            print(f"\nTIME BUDGET  computed {tb['total_computed_min']} min (declared {tb['total_declared_min']}) "
                  f"of {tb['budget_min']}  {'OVER BUDGET' if tb['over_budget'] else 'ok'}")
            for row in tb["sections"]:
                flags = f"  ! {'; '.join(row['flags'])}" if row["flags"] else ""
                print(f"  {row['id']:7} {row['type']:16} declared {row['declared_min']:>5g}  "
                      f"computed {row['computed_min']:>5g}  {row['heading'][:40]}{flags}")

        version = session.exec(
            select(LessonVersion).where(LessonVersion.lesson_id == lesson_id)
            .order_by(col(LessonVersion.version_no).desc())
        ).first()
        if version:
            slug = re.sub(r"[^a-z0-9]+", "-", args.title.lower()).strip("-")
            out = BACKEND / "data" / "out" / f"{slug}-lesson{lesson_id}-v{version.version_no}.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(version.content_md, encoding="utf-8")
            words = len(re.findall(r"\w+", version.content_md))
            print(f"\nSaved {out}  ({words} words)")

    return 0 if steps[args.until].status.value == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
