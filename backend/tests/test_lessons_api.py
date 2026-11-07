"""POST /lessons input validation and basic endpoint behaviour."""

import pytest
from fastapi.testclient import TestClient

from app.pipeline.orchestrator import STEP_NAMES
from tests.conftest import HTTP_LESSON


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"title": "", "objective": HTTP_LESSON["objective"]}, "Title is required."),
        ({"title": "   ", "objective": HTTP_LESSON["objective"]}, "Title is required."),
        ({"title": HTTP_LESSON["title"], "objective": "\n\t "}, "Learning objective is required."),
        ({"title": "Hi", "objective": HTTP_LESSON["objective"]}, "Title is too short"),
        ({"title": HTTP_LESSON["title"], "objective": "Explain it"}, "Learning objective is too short"),
        ({"title": "!!!???", "objective": HTTP_LESSON["objective"]}, "Title must contain letters or numbers."),
        ({"title": "x" * 201, "objective": HTTP_LESSON["objective"]}, "Title is too long"),
        ({"objective": HTTP_LESSON["objective"]}, "Title is required."),
        ({"title": HTTP_LESSON["title"], "objective": None}, "Learning objective is required."),
    ],
)
def test_create_lesson_rejects_bad_input(client: TestClient, payload: dict, expected: str) -> None:
    resp = client.post("/lessons", json=payload)
    assert resp.status_code == 422
    body = resp.json()
    assert expected in body["detail"]
    assert body["errors"] and all({"field", "message"} <= e.keys() for e in body["errors"])


def test_create_lesson_normalizes_whitespace_and_creates_steps(client: TestClient) -> None:
    resp = client.post("/lessons", json={"title": "  HTTP   Requests ", "objective": HTTP_LESSON["objective"] + "  "})
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "HTTP Requests"
    assert body["objective"] == HTTP_LESSON["objective"]
    assert body["status"] == "created"
    assert [s["name"] for s in body["steps"]] == STEP_NAMES
    assert all(s["status"] == "pending" and s["attempt"] == 0 for s in body["steps"])


def test_unknown_lesson_returns_404(client: TestClient) -> None:
    assert client.post("/lessons/999/run").status_code == 404
    assert client.get("/lessons/999/steps").status_code == 404


def test_unknown_step_retry_returns_404(client: TestClient) -> None:
    lesson_id = client.post("/lessons", json=HTTP_LESSON).json()["id"]
    resp = client.post(f"/lessons/{lesson_id}/steps/not_a_step/retry")
    assert resp.status_code == 404
    assert "Unknown step" in resp.json()["detail"]


def test_steps_hide_output_by_default(client: TestClient) -> None:
    lesson_id = client.post("/lessons", json=HTTP_LESSON).json()["id"]
    client.post(f"/lessons/{lesson_id}/run")
    steps = client.get(f"/lessons/{lesson_id}/steps").json()
    assert all(s["output_json"] is None for s in steps)
