"""What every pipeline step function receives, plus the step error type.

Step functions have the signature `(ctx: StepContext) -> dict` and must NOT
commit: the orchestrator commits the step's writes together with its `done`
status, or rolls them all back if the step raises.
"""

from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, col, select

from app.config import Settings
from app.models import Lesson, LessonVersion, PipelineStep, StepStatus
from app.providers import Providers


class StepError(Exception):
    """A step failed for a reason we can explain to the instructor."""


@dataclass
class StepContext:
    session: Session
    lesson: Lesson
    providers: Providers
    settings: Settings

    def output_of(self, step_name: str) -> dict[str, Any] | None:
        """Last successful output of an upstream step (None if it never succeeded)."""
        step = self.session.exec(
            select(PipelineStep).where(PipelineStep.lesson_id == self.lesson.id, PipelineStep.name == step_name)
        ).one()
        return step.output_json if step.status == StepStatus.done else None

    def require(self, step_name: str) -> dict[str, Any]:
        output = self.output_of(step_name)
        if output is None:
            raise StepError(f"Step '{step_name}' has not completed successfully, so this step cannot run.")
        return output

    def latest_version(self) -> LessonVersion | None:
        return self.session.exec(
            select(LessonVersion)
            .where(LessonVersion.lesson_id == self.lesson.id)
            .order_by(col(LessonVersion.version_no).desc())
        ).first()

    def require_latest_version(self) -> LessonVersion:
        version = self.latest_version()
        if version is None:
            raise StepError("No lesson version exists yet — the 'generate' step must succeed first.")
        return version
