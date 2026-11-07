"""Run plan → research → score_sources for one lesson and print the evidence store.

Usage (from backend/):
    .venv/Scripts/python scripts/try_research.py "HTTP Requests and Responses"
    .venv/Scripts/python scripts/try_research.py "Photosynthesis" --objective "Explain how plants make glucose"
    .venv/Scripts/python scripts/try_research.py "HTTP Requests and Responses" --offline   # fake providers

Uses its own database (data/try_research.db) so the response cache persists
between runs: running the same title twice costs no extra API credits.
"""

import argparse
import logging
import sys
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from sqlmodel import Session, col, select  # noqa: E402

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import Lesson, Source  # noqa: E402
from app.pipeline.orchestrator import create_steps, get_steps, run_pipeline, start_run  # noqa: E402
from app.providers import build_providers  # noqa: E402
from app.providers.errors import ProviderError  # noqa: E402

KNOWN_OBJECTIVES = {
    "http requests and responses": "Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx "
                                   "response status categories.",
    "simple vs compound interest": "Calculate simple and compound interest for a given principal, rate, and time, "
                                   "and explain why compound interest grows faster.",
}


def one_line(text: str, width: int) -> str:
    return textwrap.shorten(" ".join(text.split()), width=width, placeholder=" …")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("title")
    parser.add_argument("--objective", help="learning objective (required unless the title is a known test lesson)")
    parser.add_argument("--offline", action="store_true", help="use fake providers (DEMO_OFFLINE)")
    parser.add_argument("--db", default=str(BACKEND / "data" / "try_research.db"))
    parser.add_argument("-v", "--verbose", action="store_true", help="show provider/step logs")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]  (log messages)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)-7s %(name)s: %(message)s")

    objective = args.objective or KNOWN_OBJECTIVES.get(args.title.strip().lower())
    if not objective:
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
        lesson = Lesson(title=args.title.strip(), objective=objective)
        session.add(lesson)
        session.flush()
        create_steps(session, lesson.id)  # type: ignore[arg-type]
        session.commit()
        lesson_id = lesson.id
        start_run(session, lesson_id)  # type: ignore[arg-type]

    print(f"Researching lesson {lesson_id}: {args.title!r} (offline={settings.demo_offline}) …\n")
    run_pipeline(lesson_id, providers, settings, stop_after="score_sources")  # type: ignore[arg-type]

    with Session(db.get_engine()) as session:
        steps = {s.name: s for s in get_steps(session, lesson_id)}  # type: ignore[arg-type]
        plan = steps["plan"].output_json or {}
        print("PLAN")
        for outcome in plan.get("outcomes", []):
            print(f"  outcome: {outcome}")
        for query in plan.get("queries", []):
            print(f"  query:   {query}")

        print("\nSTEPS")
        for name in ["plan", "research_web", "research_youtube", "research_books", "score_sources"]:
            step = steps[name]
            print(f"  {name:17} {step.status.value:8} {one_line(step.error, 110) if step.error else ''}")

        web = steps["research_web"].output_json or {}
        for rejected in web.get("rejected_pages", []):
            print(f"  - web page skipped: {rejected['url']} ({rejected['reason']})")
        youtube = steps["research_youtube"].output_json or {}
        for dropped in youtube.get("dropped", []):
            print(f"  - video dropped: {one_line(dropped['title'], 60)} ({one_line(dropped['reason'], 80)})")
        books = steps["research_books"].output_json or {}
        if books.get("rejected"):
            print(f"  - books rejected ({books.get('selection_method')}): {', '.join(one_line(t, 50) for t in books['rejected'])}")

        sids = (steps["score_sources"].output_json or {}).get("sids", [])
        sources = session.exec(
            select(Source).where(Source.lesson_id == lesson_id, col(Source.sid).in_(sids))
        ).all()
        print(f"\nEVIDENCE STORE ({len(sources)} sources)")
        for src in sorted(sources, key=lambda s: int(s.sid[1:])):
            extra = ""
            if src.type.value == "video":
                seconds = src.metadata_json.get("duration_seconds") or 0
                method = src.metadata_json.get("relevance", {}).get("method")
                extra = f" | {seconds / 60:.1f} min | relevance via {method}"
            print(f"\n[{src.sid}] {src.type.value.upper():5} tier {src.reliability_tier} | {src.title}{extra}")
            print(f"     {src.url or '(no link)'}  — {src.publisher or ''}")
            print(f"     why tier {src.reliability_tier}: {one_line(src.reliability_reason, 120)}")
            print(f"     excerpt ({len(src.excerpt_text)} chars): {one_line(src.excerpt_text, 220) or '(none)'}")

    ok = steps["score_sources"].status.value == "done"
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
