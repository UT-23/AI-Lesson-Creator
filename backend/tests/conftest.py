"""Test fixtures: a temp SQLite DB, fake providers, and a TestClient.

Starlette's TestClient runs BackgroundTasks before the request returns, so a
POST /run in a test has finished the whole pipeline by the time it returns.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from app import db
from app.api.deps import get_providers
from app.config import Settings, get_settings
from app.main import create_app
from app.providers import Providers
from app.providers.fakes import make_fake_providers

HTTP_LESSON = {
    "title": "HTTP Requests and Responses",
    "objective": "Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.",
}


@pytest.fixture
def settings(tmp_path) -> Settings:  # type: ignore[no-untyped-def]
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        demo_offline=True,
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        reports_dir=str(tmp_path / "reports"),
    )


@pytest.fixture
def engine(settings: Settings) -> Engine:
    return db.init_engine(settings.database_url)


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


@pytest.fixture
def providers() -> Providers:
    return make_fake_providers()


@pytest.fixture
def client(engine: Engine, settings: Settings, providers: Providers) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_providers] = lambda: providers
    with TestClient(app) as c:
        yield c


def create_lesson(client: TestClient, **overrides: str) -> int:
    resp = client.post("/lessons", json={**HTTP_LESSON, **overrides})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def step_map(client: TestClient, lesson_id: int) -> dict[str, dict]:
    resp = client.get(f"/lessons/{lesson_id}/steps", params={"include_output": True})
    assert resp.status_code == 200, resp.text
    return {s["name"]: s for s in resp.json()}
