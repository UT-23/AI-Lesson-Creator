"""Generation rules: hard/soft checks, finalisation, rendering, and the step with fakes."""

import json
from typing import Any

from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import Settings
from app.models import LessonVersion, Source, SourceType
from app.pipeline.generate import build_generate_prompt, finalize, hard_checks, soft_checks
from app.pipeline.render import render_markdown
from app.providers import Providers
from app.providers.fakes import FakeLLM
from app.providers.llm import generate_structured
from app.schemas import LessonDraft
from tests.conftest import create_lesson, step_map

OUTCOMES = ["Explain the GET method", "Distinguish 2xx, 4xx and 5xx status codes"]


def src(sid: str, type_: SourceType = SourceType.web, tier: int = 1, **meta: Any) -> Source:
    return Source(lesson_id=1, sid=sid, key=sid, type=type_, title=f"title {sid}", url=f"https://x.org/{sid}",
                  publisher="pub", reliability_tier=tier, reliability_reason="r",
                  excerpt_text=f"GET retrieves a representation. Status codes 2xx 4xx 5xx. ({sid})",
                  metadata_json=meta)


ALLOWED = {"S1": src("S1"), "S2": src("S2", tier=3), "S3": src("S3", SourceType.video, tier=3, duration_seconds=360)}


def draft(**overrides: Any) -> LessonDraft:
    base: dict[str, Any] = {
        "title": "T", "objective": "O", "outcomes": OUTCOMES, "total_minutes": 30,
        "sections": [
            {"id": "sec-1", "type": "hook", "heading": "H", "minutes": 1, "content_md": "Imagine a browser."},
            {"id": "sec-2", "type": "concept", "heading": "C", "minutes": 5, "content_md": "GET reads [S1].",
             "outcomes_covered": OUTCOMES},
            {"id": "sec-3", "type": "example", "heading": "E", "minutes": 4, "content_md": "A 404 example [S2]."},
            {"id": "sec-4", "type": "activity", "heading": "A", "minutes": 26, "content_md": "Sort these codes."},
            {"id": "sec-5", "type": "video", "heading": "V", "minutes": 7, "content_md": "Watch [S3]."},
            {"id": "sec-6", "type": "knowledge_check", "heading": "K", "minutes": 4, "content_md": "Answer."},
            {"id": "sec-7", "type": "summary", "heading": "S", "minutes": 1, "content_md": "Recap."},
        ],
        "videos": [{"sid": "S3", "title": "made-up title", "url": "https://made.up/video", "duration_min": 2,
                    "why": "shows it"}],
        "knowledge_check": [
            {"q": f"q{i}", "options": ["a", "b", "c", "d"], "answer": "a", "explanation": "because [S1]", "outcome": o}
            for i, o in enumerate(OUTCOMES * 2)
        ],
        "references": ["S1"],
    }
    base.update(overrides)
    return LessonDraft.model_validate(base)


def test_valid_draft_passes_hard_and_soft_checks() -> None:
    assert hard_checks(OUTCOMES, ALLOWED)(draft()) == []
    assert soft_checks(OUTCOMES, ALLOWED, Settings(_env_file=None))(draft()) == []  # type: ignore[call-arg]


def test_hard_checks_catch_each_rule() -> None:
    d = draft()
    sections = [s.model_dump() for s in d.sections]
    sections[1]["outcomes_covered"] = OUTCOMES[:1]  # outcome 2 no longer covered by a section
    sections[2]["content_md"] = "An example with no citation."  # example section uncited
    sections = [s for s in sections if s["type"] != "summary"]  # required type missing
    sections[0]["content_md"] += " Invented [S9]."  # unknown source
    bad = draft(sections=sections,
                knowledge_check=[q.model_dump() for q in d.knowledge_check if q.outcome == OUTCOMES[0]],
                videos=[{"sid": "S1", "title": "x", "url": "u", "duration_min": 1, "why": "w"}])
    problems = "\n".join(hard_checks(OUTCOMES, ALLOWED)(bad))
    assert "Unknown source ids cited: S9" in problems
    assert "videos[].sid S1 is a web source" in problems
    assert f"No section lists the outcome {OUTCOMES[1]!r}" in problems
    assert f"No knowledge_check question for the outcome {OUTCOMES[1]!r}" in problems
    assert "Missing required section type(s): summary" in problems
    assert "Section sec-3 (example) has no [S#] citation" in problems


def test_soft_checks_use_real_video_duration_and_time_budget() -> None:
    long_video = {**ALLOWED, "S3": src("S3", SourceType.video, tier=3, duration_seconds=14 * 60)}
    sections = [s.model_dump() for s in draft().sections]
    sections[3]["minutes"] = 30  # activity
    problems = soft_checks(OUTCOMES, long_video, Settings(_env_file=None))(draft(sections=sections))  # type: ignore[call-arg]
    assert any("The lesson takes" in p and "limit is 45" in p for p in problems)


def test_soft_problem_is_fed_back_but_draft_still_returned() -> None:
    class Small(BaseModel):
        n: int

    llm = FakeLLM()
    llm.queue("Small", '{"n": 1}', '{"n": 2}', '{"n": 3}')
    result = generate_structured(llm, "p", Small, max_repairs=2, soft_check=lambda s: ["too small"])
    # One soft repair round only (each round is a full paid generation), then the draft is accepted.
    assert result.n == 2 and len(llm.calls) == 2
    assert "too small" in llm.calls[1][1]


def test_hard_problems_still_get_all_repair_rounds_after_soft_round() -> None:
    class Small(BaseModel):
        n: int

    llm = FakeLLM()
    llm.queue("Small", '{"n": 1}', "not json", '{"n": 3}')
    result = generate_structured(llm, "p", Small, max_repairs=2, soft_check=lambda s: ["too small"] if s.n == 1 else [])
    # soft round (n=1) → malformed reply still gets a repair round → clean draft n=3 wins
    assert result.n == 3 and len(llm.calls) == 3


def test_finalize_overwrites_model_supplied_facts() -> None:
    books = ["S7"]
    content = finalize(draft(outcomes=["rephrased outcome"]), "Real title", "Real objective", OUTCOMES, ALLOWED, books)
    assert (content.title, content.objective, content.outcomes) == ("Real title", "Real objective", OUTCOMES)
    video = content.videos[0]
    assert (video.title, video.url, video.duration_min) == ("title S3", "https://x.org/S3", 6.0)
    assert content.references == ["S1", "S2", "S3"]  # from actual citations, not the model's list
    assert content.further_reading == books
    assert content.total_minutes == 48


def test_grouped_citations_are_checked_and_normalised() -> None:
    sections = [s.model_dump() for s in draft().sections]
    sections[1]["content_md"] = "GET reads [S1, S2]. Also [S1; S9]."
    grouped = draft(sections=sections)
    assert "Unknown source ids cited: S9" in "\n".join(hard_checks(OUTCOMES, ALLOWED)(grouped))
    sections[1]["content_md"] = "GET reads [S1, S2]."
    content = finalize(draft(sections=sections), "T", "O", OUTCOMES, ALLOWED, [])
    assert content.sections[1].content_md == "GET reads [S1], [S2]."
    assert "S2" in content.references


def test_measured_minutes_replace_declared_ones() -> None:
    from app.pipeline.generate import set_measured_minutes

    sections = [s.model_dump() for s in draft().sections]
    sections[1]["minutes"] = 10  # concept claims 10 min for 3 words
    content = finalize(draft(sections=sections), "T", "O", OUTCOMES, ALLOWED, [])
    adjusted, changes = set_measured_minutes(content, Settings(_env_file=None))  # type: ignore[call-arg]
    by_id = {s.id: s.minutes for s in adjusted.sections}
    assert by_id["sec-2"] == 1 and by_id["sec-4"] == 26 and by_id["sec-5"] == 6  # the real 6-min video
    assert {"section": "sec-2", "declared": 10.0, "measured": 1} in changes
    assert adjusted.total_minutes == sum(by_id.values())


def test_render_lists_books_as_further_reading_not_references() -> None:
    book = src("S7", SourceType.book, tier=2, year=2002)
    content = finalize(draft(), "T", "O", OUTCOMES, ALLOWED, ["S7"])
    md = render_markdown(content, {**ALLOWED, "S7": book})
    references, further = md.split("## Further reading")
    assert "[S7]" not in references
    assert "title S7 — pub (2002)" in further and "not used as evidence" in further


def test_prompt_contains_tiers_videos_and_no_books() -> None:
    sources = [*ALLOWED.values()]
    prompt = build_generate_prompt("HTTP", "Explain GET", OUTCOMES, sources, Settings(_env_file=None))  # type: ignore[call-arg]
    assert "[S1] type=web | tier=1" in prompt and "[S3] type=video | tier=3" in prompt and "duration_min=6.0" in prompt
    assert "type=book" not in prompt
    assert "Target 35-45 minutes" in prompt


def test_generate_step_records_books_and_never_cites_them(client: TestClient, session: Session) -> None:
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")
    out = step_map(client, lesson_id)["generate"]["output_json"]
    books = {s.sid for s in session.exec(select(Source).where(Source.type == SourceType.book)).all()}
    assert set(out["further_reading"]) == books and not books & set(out["cited_sids"])
    assert out["warnings"] == [] and out["citations_by_tier"]
    version = session.exec(select(LessonVersion)).one()
    assert "## Further reading" in version.content_md
    assert json.loads(json.dumps(version.content_json))["further_reading"] == out["further_reading"]


def test_generation_warnings_are_stored_when_soft_problems_persist(client: TestClient, providers: Providers) -> None:
    providers.youtube.fail_with = RuntimeError("no videos")  # type: ignore[attr-defined]  # shorter lesson
    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")
    out = step_map(client, lesson_id)["generate"]
    assert out["status"] == "done"
    assert any("below the 35-45 minute target" in w for w in out["output_json"]["warnings"])


def test_quiz_issue_can_be_previewed_and_applied(client: TestClient, session: Session) -> None:
    from app.models import QCIssue, QCReport

    lesson_id = create_lesson(client)
    client.post(f"/lessons/{lesson_id}/run")
    report = session.exec(select(QCReport).where(QCReport.layer == "factual")).first()
    issue = QCIssue(report_id=report.id, issue_id="F-99", severity="critical", category="wrong_result",  # type: ignore[arg-type]
                    location="quiz-Q1", claim_or_text="wrong answer", suggestion="recompute")
    session.add(issue)
    session.commit()

    preview = client.post(f"/qc/issues/{issue.id}/preview-fix").json()
    assert preview["kind"] == "quiz" and preview["quiz_index"] == 0 and "Corrected question" in preview["after"]
    applied = client.post(f"/qc/issues/{issue.id}/apply",
                          json={"quiz_index": 0, "quiz_item": preview["after_item"]}).json()
    version = session.exec(select(LessonVersion).where(LessonVersion.version_no == applied["version_no"])).one()
    assert version.author.value == "qc_fix" and version.content_json["knowledge_check"][0]["answer"] == "Right"
    # quiz edit through the normal edit path
    edit = client.put(f"/lessons/{lesson_id}/content", json={"quiz": {"1": preview["after_item"]}})
    assert edit.status_code == 200
