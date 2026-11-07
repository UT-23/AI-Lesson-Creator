"""Shared FastAPI dependencies (overridable in tests via app.dependency_overrides)."""

from fastapi import Depends, HTTPException
from sqlmodel import Session

from app.config import Settings, get_settings
from app.db import get_session
from app.models import Lesson
from app.providers import Providers, build_providers
from app.providers.errors import ProviderError


def get_providers(settings: Settings = Depends(get_settings)) -> Providers:
    try:
        return build_providers(settings)
    except ProviderError as err:
        raise HTTPException(status_code=503, detail=err.message) from err


def get_lesson_or_404(lesson_id: int, session: Session = Depends(get_session)) -> Lesson:
    lesson = session.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail=f"Lesson {lesson_id} not found.")
    return lesson
