"""Pipeline step status (for polling) and retry."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.deps import get_lesson_or_404, get_providers
from app.config import Settings, get_settings
from app.db import get_session
from app.models import Lesson, LessonStatus
from app.pipeline.orchestrator import STEP_FUNCS, RunRejected, get_steps, run_pipeline, start_run
from app.providers import Providers
from app.schemas import RunAccepted, StepOut

router = APIRouter(prefix="/lessons/{lesson_id}/steps", tags=["steps"])


@router.get("", response_model=list[StepOut])
def list_steps(
    lesson: Lesson = Depends(get_lesson_or_404),
    session: Session = Depends(get_session),
    include_output: bool = Query(False, description="Include each step's output_json (can be large)"),
) -> list[StepOut]:
    steps = [StepOut.model_validate(s) for s in get_steps(session, lesson.id)]  # type: ignore[arg-type]
    if not include_output:
        steps = [s.model_copy(update={"output_json": None}) for s in steps]
    return steps


@router.post("/{step_name}/retry", status_code=status.HTTP_202_ACCEPTED, response_model=RunAccepted)
def retry_step(
    step_name: str,
    background: BackgroundTasks,
    lesson: Lesson = Depends(get_lesson_or_404),
    session: Session = Depends(get_session),
    providers: Providers = Depends(get_providers),
    settings: Settings = Depends(get_settings),
) -> RunAccepted:
    """Re-run `step_name` and every step after it, reusing cached outputs of earlier steps."""
    if step_name not in STEP_FUNCS:
        raise HTTPException(status_code=404, detail=f"Unknown step '{step_name}'. Valid steps: {', '.join(STEP_FUNCS)}.")
    try:
        first = start_run(session, lesson.id, from_step=step_name)  # type: ignore[arg-type]
    except RunRejected as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    background.add_task(run_pipeline, lesson.id, providers, settings)
    return RunAccepted(lesson_id=lesson.id, status=LessonStatus.running, from_step=first,  # type: ignore[arg-type]
                       message=f"Retrying from '{first}'. Earlier steps reuse their saved outputs.")
