"""Pipeline state machine.

Steps run in a fixed order. Each step:
  pending → running → done | failed
and a step whose required input failed becomes `skipped`.

Rules:
* `DEPENDS_ON` lists each step's inputs. A step is skipped only when one of its
  *required* inputs isn't done, so a web-research failure doesn't stop the
  YouTube/Books research, and a QC1 failure doesn't stop QC2.
* `research_youtube` and `research_books` are optional inputs: if they fail
  the pipeline continues and the lesson ends `completed_with_warnings`.
* A step's DB writes are committed together with its `done` status, or rolled
  back if it raises — no half-written sources or versions.
* `output_json` keeps the last *successful* output; a failed re-run doesn't erase it.
* Resume (`start_run` with no step) re-runs every step that isn't `done`, plus
  everything that depends on it. Retry (`start_run` with a step) re-runs that
  step plus everything that depends on it, reusing all other cached outputs.
"""

import logging
import time
from collections.abc import Callable
from typing import Any

from sqlalchemy import update
from sqlmodel import Session, col, select

from app.config import Settings
from app.db import get_engine
from app.models import Lesson, LessonStatus, LessonVersion, PipelineStep, StepStatus, utcnow
from app.pipeline.context import StepContext, StepError
from app.pipeline.generate import run_generate
from app.pipeline.plan import run_plan
from app.pipeline.qc_factual import run_qc_factual
from app.pipeline.qc_instructional import run_qc_instructional
from app.pipeline.research import run_research_books, run_research_web, run_research_youtube
from app.pipeline.sources import run_score_sources
from app.pipeline.timebudget import run_timebudget
from app.providers import Providers
from app.providers.errors import ProviderError
from app.providers.llm import LLMOutputError

log = logging.getLogger("pipeline")

StepFunc = Callable[[StepContext], dict[str, Any]]

STEPS: list[tuple[str, StepFunc]] = [
    ("plan", run_plan),
    ("research_web", run_research_web),
    ("research_youtube", run_research_youtube),
    ("research_books", run_research_books),
    ("score_sources", run_score_sources),
    ("generate", run_generate),
    ("timebudget", run_timebudget),
    ("qc_factual", run_qc_factual),
    ("qc_instructional", run_qc_instructional),
]
STEP_NAMES = [name for name, _ in STEPS]
STEP_FUNCS: dict[str, StepFunc] = dict(STEPS)
OPTIONAL_STEPS = frozenset({"research_youtube", "research_books"})

# Inputs of each step. Optional steps are soft inputs: used if done, never blocking.
DEPENDS_ON: dict[str, list[str]] = {
    "plan": [],
    "research_web": ["plan"],
    "research_youtube": ["plan"],
    "research_books": ["plan"],
    "score_sources": ["research_web", "research_youtube", "research_books"],
    "generate": ["plan", "score_sources"],
    "timebudget": ["generate"],
    "qc_factual": ["generate"],
    "qc_instructional": ["generate"],  # computes the time budget itself (deterministic)
}


def input_satisfied(session: Session, lesson_id: int, dep: PipelineStep) -> bool:
    """A required input is satisfied when its step is done — or, for `generate`, when any
    lesson version exists (a failed re-generation must not block QC on the existing version)."""
    if dep.status == StepStatus.done:
        return True
    if dep.name == "generate":
        return session.exec(select(LessonVersion).where(LessonVersion.lesson_id == lesson_id)).first() is not None
    return False


def required_inputs(step_name: str) -> list[str]:
    return [d for d in DEPENDS_ON[step_name] if d not in OPTIONAL_STEPS]


def with_dependents(names: set[str]) -> list[str]:
    """`names` plus every step that (transitively) consumes their output, in pipeline order."""
    affected = set(names)
    for name in STEP_NAMES:  # pipeline order is a valid topological order
        if any(dep in affected for dep in DEPENDS_ON[name]):
            affected.add(name)
    return [n for n in STEP_NAMES if n in affected]


class RunRejected(Exception):
    """A run/retry request that can't be accepted right now (message is user-facing)."""


# ---------------------------------------------------------------------------
# Step rows
# ---------------------------------------------------------------------------


def create_steps(session: Session, lesson_id: int) -> list[PipelineStep]:
    steps = [PipelineStep(lesson_id=lesson_id, name=name, position=i) for i, name in enumerate(STEP_NAMES)]
    session.add_all(steps)
    return steps


def get_steps(session: Session, lesson_id: int) -> list[PipelineStep]:
    return list(session.exec(
        select(PipelineStep).where(PipelineStep.lesson_id == lesson_id).order_by(col(PipelineStep.position))
    ).all())


def summarize_status(steps: list[PipelineStep]) -> LessonStatus:
    """Lesson status implied by its step statuses (when nothing is running)."""
    required_broken = any(
        s.status in (StepStatus.failed, StepStatus.skipped) and s.name not in OPTIONAL_STEPS for s in steps
    )
    if required_broken:
        return LessonStatus.failed
    if any(s.status in (StepStatus.pending, StepStatus.running) for s in steps):
        return LessonStatus.created  # incomplete, never failed
    if any(s.status == StepStatus.failed for s in steps):
        return LessonStatus.completed_with_warnings
    return LessonStatus.completed


# ---------------------------------------------------------------------------
# Starting a run (called by the API, synchronously)
# ---------------------------------------------------------------------------


def start_run(session: Session, lesson_id: int, from_step: str | None = None) -> str:
    """Claim the lesson for a run and reset the steps that will execute.

    Returns the name of the first step that will run. Raises RunRejected.
    """
    # Atomic claim: only one run per lesson at a time.
    claimed = session.execute(
        update(Lesson)
        .where(col(Lesson.id) == lesson_id, col(Lesson.status) != LessonStatus.running)
        .values(status=LessonStatus.running, updated_at=utcnow())
    )
    if claimed.rowcount != 1:  # type: ignore[attr-defined]
        session.rollback()
        raise RunRejected("The pipeline is already running for this lesson. Wait for it to finish.")

    steps = {s.name: s for s in get_steps(session, lesson_id)}
    if from_step is None:
        not_done = {name for name, s in steps.items() if s.status != StepStatus.done}
        if not not_done:
            session.rollback()
            raise RunRejected("Every step has already completed. Use Retry on a step to re-run it.")
        to_run = with_dependents(not_done)
    else:
        if from_step not in STEP_FUNCS:
            session.rollback()
            raise RunRejected(f"Unknown step '{from_step}'. Valid steps: {', '.join(STEP_NAMES)}.")
        missing = [d for d in required_inputs(from_step) if not input_satisfied(session, lesson_id, steps[d])]
        if missing:
            session.rollback()
            raise RunRejected(f"Step '{missing[0]}' must succeed before '{from_step}' can run. Retry '{missing[0]}' instead.")
        to_run = with_dependents({from_step})

    for name in to_run:
        steps[name].status = StepStatus.pending
        steps[name].error = None
        session.add(steps[name])
    session.commit()
    return to_run[0]


# ---------------------------------------------------------------------------
# Running (called in a background thread)
# ---------------------------------------------------------------------------


def describe_error(exc: Exception, settings: Settings) -> str:
    """A readable one-paragraph message, with any API keys scrubbed."""
    if isinstance(exc, ProviderError):
        message = f"{exc.provider}: {exc.message}"
    elif isinstance(exc, (StepError, LLMOutputError)):
        message = str(exc)
    else:
        message = f"Unexpected error ({type(exc).__name__}): {exc}"
    for secret in settings.secret_values():
        message = message.replace(secret, "***")
    return message[:2000]


def _execute_step(ctx: StepContext, step: PipelineStep) -> bool:
    session = ctx.session
    step.status = StepStatus.running
    step.attempt += 1
    step.started_at = utcnow()
    step.finished_at = None
    step.error = None
    session.add(step)
    session.commit()
    log.info("lesson=%s step=%s attempt=%d: started", ctx.lesson.id, step.name, step.attempt)
    began = time.monotonic()

    try:
        output = STEP_FUNCS[step.name](ctx)
    except Exception as exc:
        session.rollback()  # discard this step's partial writes
        step.status = StepStatus.failed
        step.error = describe_error(exc, ctx.settings)
        step.finished_at = utcnow()
        session.add(step)
        session.commit()
        expected = isinstance(exc, (ProviderError, StepError, LLMOutputError))
        log.error("lesson=%s step=%s: FAILED: %s", ctx.lesson.id, step.name, step.error, exc_info=not expected)
        return False

    step.output_json = output
    step.status = StepStatus.done
    step.finished_at = utcnow()
    session.add(step)
    session.commit()
    log.info("lesson=%s step=%s: done in %.1fs", ctx.lesson.id, step.name, time.monotonic() - began)
    return True


def run_pipeline(lesson_id: int, providers: Providers, settings: Settings, stop_after: str | None = None) -> None:
    """Run every `pending` step in order. Assumes `start_run` was called first.

    `stop_after` (used by scripts/try_research.py) leaves later steps `pending`.
    """
    last = STEP_NAMES.index(stop_after) if stop_after else len(STEP_NAMES) - 1
    with Session(get_engine()) as session:
        lesson = session.get(Lesson, lesson_id)
        if lesson is None:
            log.error("lesson=%s: not found, nothing to run", lesson_id)
            return
        ctx = StepContext(session=session, lesson=lesson, providers=providers, settings=settings)
        try:
            steps = get_steps(session, lesson_id)
            status_of = {s.name: s for s in steps}
            for step in steps:
                if step.position > last:
                    break
                if step.status != StepStatus.pending:
                    continue  # done steps keep their cached output
                blockers = [d for d in required_inputs(step.name)
                            if not input_satisfied(session, lesson_id, status_of[d])]
                if blockers:
                    step.status = StepStatus.skipped
                    step.error = f"Skipped because the required step '{blockers[0]}' did not complete."
                    session.add(step)
                    session.commit()
                    log.info("lesson=%s step=%s: skipped (needs %s)", lesson_id, step.name, blockers[0])
                    continue
                _execute_step(ctx, step)
        except Exception:  # never leave a lesson stuck in "running"
            log.exception("lesson=%s: orchestrator crashed", lesson_id)
            session.rollback()
        finally:
            steps = get_steps(session, lesson_id)
            for step in steps:  # only possible after a crash
                if step.status == StepStatus.running:
                    step.status = StepStatus.failed
                    step.error = "The orchestrator stopped unexpectedly while this step was running. Retry it."
                    session.add(step)
            lesson.status = summarize_status(steps)
            lesson.updated_at = utcnow()
            session.add(lesson)
            session.commit()
            log.info("lesson=%s: pipeline finished with status %s", lesson_id, lesson.status.value)


def recover_interrupted(session: Session) -> int:
    """On startup: steps left `running` by a crash/restart become `failed` (retryable)."""
    stuck = session.exec(select(PipelineStep).where(PipelineStep.status == StepStatus.running)).all()
    for step in stuck:
        step.status = StepStatus.failed
        step.error = "Interrupted: the server stopped while this step was running. Retry it."
        step.finished_at = utcnow()
        session.add(step)

    running = session.exec(select(Lesson).where(Lesson.status == LessonStatus.running)).all()
    for lesson in running:
        session.flush()
        lesson.status = summarize_status(get_steps(session, lesson.id))  # type: ignore[arg-type]
        lesson.updated_at = utcnow()
        session.add(lesson)
    session.commit()
    if stuck or running:
        log.warning("Recovered %d interrupted step(s) across %d lesson(s)", len(stuck), len(running))
    return len(stuck)
