"""FastAPI application.

Run locally:  uvicorn app.main:app --reload   (from the backend/ folder)
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.api import lessons, qc, steps, versions
from app.config import get_settings
from app.db import get_engine
from app.pipeline.orchestrator import recover_interrupted

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    with Session(get_engine()) as session:  # creates tables on first use
        recover_interrupted(session)
    yield


def _friendly_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Turn Pydantic's error list into short, human-readable messages."""
    errors = []
    for err in exc.errors():
        field = next((str(p) for p in reversed(err["loc"]) if p not in ("body", "query", "path")), "request")
        message = str(err.get("msg", "Invalid value")).removeprefix("Value error, ")
        if err.get("type") == "missing":
            message = f"{field.capitalize()} is required."
        errors.append({"field": field, "message": message})
    detail = " ".join(e["message"] for e in errors) or "Invalid request."
    return JSONResponse(status_code=422, content={"detail": detail, "errors": errors})


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AI Lesson Creation Tool", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(RequestValidationError, _friendly_validation_error)  # type: ignore[arg-type]
    app.include_router(lessons.router)
    app.include_router(steps.router)
    app.include_router(versions.router)
    app.include_router(qc.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, object]:
        return {"ok": True, "demo_offline": settings.demo_offline}

    return app


app = create_app()
