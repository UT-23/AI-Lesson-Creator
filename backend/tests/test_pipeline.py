"""End-to-end pipeline runs with fake providers: happy path, failures, retry, recovery."""

import json

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.models import (
    Lesson,
    LessonStatus,
    LessonVersion,
    PipelineStep,
    QCIssue,
    QCReport,
    Source,
    StepStatus,
)
from app.pipeline.orchestrator import STEP_NAMES, recover_interrupted
from app.providers import Providers
from app.providers.errors import ErrorKind, ProviderError
from app.schemas import LessonContent
from tests.conftest import create_lesson, step_map


def test_full_pipeline_with_fakes(client: TestClient, session: Session) -> None:
    lesson_id = create_lesson(client)
    resp = client.post(f"/lessons/{lesson_id}/run")
    assert resp.status_code == 202
    assert resp.json()["from_step"] == "plan"

    steps = step_map(client, lesson_id)
    assert {n: s["status"] for n, s in steps.items()} == {n: "done" for n in STEP_NAMES}
    assert all(s["attempt"] == 1 and s["error"] is None for s in steps.values())
    assert session.get(Lesson, lesson_id).status == LessonStatus.completed  # type: ignore[union-attr]

    # Plan keeps the objective's verbs and has 4-8 queries.
    plan = steps["plan"]["output_json"]
    assert plan["outcomes"][0].startswith("Explain GET and POST")
    assert 4 <= len(plan["queries"]) <= 8

    # Evidence store: sequential stable ids, every type present, irrelevant/long video dropped.
    sources = session.exec(select(Source).where(Source.lesson_id == lesson_id)).all()
    assert [s.sid for s in sources] == [f"S{i}" for i in range(1, len(sources) + 1)]
    assert {s.type.value for s in sources} == {"web", "book", "video"}
    assert "fakevid003" not in {s.metadata_json.get("video_id") for s in sources}
    assert all(1 <= s.reliability_tier <= 4 and s.reliability_reason for s in sources)

    # Version 1, authored by the AI, citations only to real sources, references from Source rows.
    versions = session.exec(select(LessonVersion).where(LessonVersion.lesson_id == lesson_id)).all()
    assert [(v.version_no, v.author.value) for v in versions] == [(1, "ai")]
    content = LessonContent.model_validate(versions[0].content_json)
    assert content.cited_sids() <= {s.sid for s in sources}
    assert "## References" in versions[0].content_md
    video_src = next(s for s in sources if s.type.value == "video")
    assert content.videos[0].url == video_src.url  # URL taken from the Source row

    # Time budget is computed, not guessed.
    tb = steps["timebudget"]["output_json"]
    assert tb["version_no"] == 1 and tb["total_computed_min"] > 0

    # Both QC layers wrote their own report on version 1.
    reports = session.exec(select(QCReport).where(QCReport.lesson_id == lesson_id)).all()
    assert sorted(r.layer.value for r in reports) == ["factual", "instructional"]
    assert all(r.lesson_version_no == 1 for r in reports)
    issues = session.exec(select(QCIssue)).all()
    assert {i.issue_id[0] for i in issues} == {"F", "I"}  # both layers produced issues
    assert all(r.details_json.get("model") for r in reports)  # reviewer model recorded


def test_web_failure_blocks_generation_but_not_other_research(
    client: TestClient, session: Session, providers: Providers
) -> None:
    providers.web.fail_with = ProviderError("tavily", ErrorKind.quota_exhausted, "Monthly credit limit reached.")  # type: ignore[attr-defined]
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")

    steps = step_map(client, lesson_id)
    assert steps["research_web"]["status"] == "failed"
    assert steps["research_web"]["error"] == "tavily: Monthly credit limit reached."
    assert steps["research_youtube"]["status"] == "done"  # independent of web research
    assert steps["research_books"]["status"] == "done"
    for name in ["score_sources", "generate", "timebudget", "qc_factual", "qc_instructional"]:
        assert steps[name]["status"] == "skipped", name
        assert "did not complete" in steps[name]["error"]
    assert session.get(Lesson, lesson_id).status == LessonStatus.failed  # type: ignore[union-attr]
    assert session.exec(select(LessonVersion)).all() == []


def test_retry_failed_step_reuses_cached_upstream(client: TestClient, session: Session, providers: Providers) -> None:
    providers.web.fail_with = ProviderError("tavily", ErrorKind.timeout, "Request timed out.")  # type: ignore[attr-defined]
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")
    plan_calls = sum(1 for name, _ in providers.gen_llm.calls if name == "ResearchPlan")  # type: ignore[attr-defined]
    youtube_calls = len(providers.youtube.calls)  # type: ignore[attr-defined]

    providers.web.fail_with = None  # type: ignore[attr-defined]
    resp = client.post(f"/lessons/{lesson_id}/steps/research_web/retry")
    assert resp.status_code == 202

    steps = step_map(client, lesson_id)
    assert all(s["status"] == "done" for s in steps.values())
    assert steps["plan"]["attempt"] == 1  # not re-run
    assert steps["research_youtube"]["attempt"] == 1  # not a dependent of research_web
    assert steps["research_web"]["attempt"] == 2
    assert sum(1 for name, _ in providers.gen_llm.calls if name == "ResearchPlan") == plan_calls  # type: ignore[attr-defined]
    assert len(providers.youtube.calls) == youtube_calls  # type: ignore[attr-defined]
    assert session.get(Lesson, lesson_id).status == LessonStatus.completed  # type: ignore[union-attr]


def test_optional_research_failure_gives_warning_not_failure(
    client: TestClient, session: Session, providers: Providers
) -> None:
    providers.youtube.fail_with = ProviderError("youtube", ErrorKind.quota_exhausted, "Daily quota exceeded.")  # type: ignore[attr-defined]
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")

    steps = step_map(client, lesson_id)
    assert steps["research_youtube"]["status"] == "failed"
    assert all(s["status"] == "done" for n, s in steps.items() if n != "research_youtube")
    assert session.get(Lesson, lesson_id).status == LessonStatus.completed_with_warnings  # type: ignore[union-attr]
    content = LessonContent.model_validate(session.exec(select(LessonVersion)).one().content_json)
    assert content.videos == []

    # Resuming after fixing YouTube re-runs it and everything that consumes it -> version 2.
    providers.youtube.fail_with = None  # type: ignore[attr-defined]
    assert client.post(f"/lessons/{lesson_id}/run").status_code == 202
    steps = step_map(client, lesson_id)
    assert all(s["status"] == "done" for s in steps.values())
    assert steps["research_books"]["attempt"] == 1
    assert steps["generate"]["attempt"] == 2
    versions = session.exec(select(LessonVersion).order_by(LessonVersion.version_no)).all()
    assert [v.version_no for v in versions] == [1, 2]  # v1 kept, v2 appended
    assert LessonContent.model_validate(versions[1].content_json).videos


def test_malformed_llm_json_is_repaired_with_feedback(client: TestClient, providers: Providers) -> None:
    providers.gen_llm.queue("ResearchPlan", "not json at all", '{"outcomes": [], "queries": []}')  # type: ignore[attr-defined]
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")

    steps = step_map(client, lesson_id)
    assert steps["plan"]["status"] == "done"
    plan_prompts = [p for name, p in providers.gen_llm.calls if name == "ResearchPlan"]  # type: ignore[attr-defined]
    assert len(plan_prompts) == 3
    assert "YOUR PREVIOUS RESPONSE WAS REJECTED" in plan_prompts[1]
    assert "outcomes" in plan_prompts[2]  # the validation error was fed back


def test_persistently_malformed_llm_json_fails_step_cleanly(client: TestClient, providers: Providers) -> None:
    providers.gen_llm.queue("LessonDraft", "{", "{", "{")  # type: ignore[attr-defined]
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")

    steps = step_map(client, lesson_id)
    assert steps["generate"]["status"] == "failed"
    assert "invalid LessonDraft output 3 times" in steps["generate"]["error"]
    assert steps["score_sources"]["status"] == "done"  # upstream output preserved
    assert steps["qc_factual"]["status"] == "skipped"


def test_invented_citation_is_fed_back_to_the_model(client: TestClient, providers: Providers, session: Session) -> None:
    lesson_id = create_lesson(client)
    # Run once to get a valid lesson, then replay it with a bogus citation injected.
    client.post(f"/lessons/{lesson_id}/run")
    good = session.exec(select(LessonVersion)).one().content_json
    bad = json.loads(json.dumps(good))
    bad["sections"][0]["content_md"] += " Invented fact [S99]."
    providers.gen_llm.queue("LessonDraft", json.dumps(bad), json.dumps(good))  # type: ignore[attr-defined]

    client.post(f"/lessons/{lesson_id}/steps/generate/retry")
    prompts = [p for name, p in providers.gen_llm.calls if name == "LessonDraft"]  # type: ignore[attr-defined]
    retry_prompts = prompts[-2:]  # the bad draft, then the repair request
    assert "Unknown source ids cited: S99" in retry_prompts[1]
    assert step_map(client, lesson_id)["generate"]["status"] == "done"
    assert step_map(client, lesson_id)["generate"]["output_json"]["warnings"] == []


def test_qc1_failure_does_not_block_qc2(client: TestClient, providers: Providers) -> None:
    providers.qc_llm.queue("FactCheckResult", "{", "{", "{")  # type: ignore[attr-defined]  # QC1 runs first
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")
    steps = step_map(client, lesson_id)
    assert steps["qc_factual"]["status"] == "failed"
    assert steps["qc_instructional"]["status"] == "done"


def test_retry_rejected_when_required_input_missing(client: TestClient, providers: Providers) -> None:
    providers.web.fail_with = ProviderError("tavily", ErrorKind.auth, "Invalid API key.")  # type: ignore[attr-defined]
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")
    resp = client.post(f"/lessons/{lesson_id}/steps/generate/retry")
    assert resp.status_code == 409
    assert "score_sources" in resp.json()["detail"]


def test_run_rejected_while_running_and_when_complete(client: TestClient, session: Session) -> None:
    lesson_id = create_lesson(client)
    lesson = session.get(Lesson, lesson_id)
    lesson.status = LessonStatus.running  # type: ignore[union-attr]
    session.add(lesson)
    session.commit()
    resp = client.post(f"/lessons/{lesson_id}/run")
    assert resp.status_code == 409 and "already running" in resp.json()["detail"]

    lesson.status = LessonStatus.created  # type: ignore[union-attr]
    session.add(lesson)
    session.commit()
    client.post(f"/lessons/{lesson_id}/run")
    resp = client.post(f"/lessons/{lesson_id}/run")
    assert resp.status_code == 409 and "already completed" in resp.json()["detail"]


def test_api_keys_are_scrubbed_from_errors(client: TestClient, providers: Providers, settings) -> None:  # type: ignore[no-untyped-def]
    from pydantic import SecretStr

    settings.tavily_api_key = SecretStr("tvly-SECRET123")
    providers.web.fail_with = ProviderError("tavily", ErrorKind.auth, "Key tvly-SECRET123 rejected.")  # type: ignore[attr-defined]
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")
    assert step_map(client, lesson_id)["research_web"]["error"] == "tavily: Key *** rejected."


def test_startup_recovers_interrupted_steps(client: TestClient, session: Session) -> None:
    lesson_id = create_lesson(client)
    lesson = session.get(Lesson, lesson_id)
    step = session.exec(select(PipelineStep).where(PipelineStep.name == "plan")).one()
    lesson.status = LessonStatus.running  # type: ignore[union-attr]
    step.status = StepStatus.running
    session.add_all([lesson, step])
    session.commit()

    assert recover_interrupted(session) == 1
    session.refresh(step)
    session.refresh(lesson)
    assert step.status == StepStatus.failed and "Interrupted" in (step.error or "")
    assert lesson.status == LessonStatus.failed  # type: ignore[union-attr]
    # ...and it can be resumed.
    assert client.post(f"/lessons/{lesson_id}/run").status_code == 202
    assert all(s["status"] == "done" for s in step_map(client, lesson_id).values())
