"""Unit tests for deterministic pieces: time budget, reliability tiers, retry policy."""

import pytest

from app.pipeline.orchestrator import with_dependents
from app.pipeline.sources import tier_for_channel, tier_for_url
from app.pipeline.timebudget import compute_time_budget, count_words, segment_minutes
from app.providers.errors import ErrorKind, ProviderError, with_retries
from app.schemas import LessonContent


def _lesson(**overrides) -> LessonContent:  # type: ignore[no-untyped-def]
    base = {
        "title": "T", "objective": "O", "outcomes": ["o1"], "total_minutes": 20,
        "sections": [
            {"id": "sec-1", "type": "concept", "heading": "C", "minutes": 1, "content_md": "word " * 200 + "[S1]"},
            {"id": "sec-2", "type": "video", "heading": "V", "minutes": 6, "content_md": "Watch [S2]."},
            {"id": "sec-3", "type": "activity", "heading": "A", "minutes": 8, "content_md": "Do it."},
            {"id": "sec-4", "type": "knowledge_check", "heading": "K", "minutes": 1, "content_md": "Answer."},
        ],
        "videos": [{"sid": "S2", "title": "v", "url": "u", "duration_min": 6, "why": "w"}],
        "knowledge_check": [
            {"q": f"q{i}", "options": ["a", "b"], "answer": "a", "explanation": "e", "outcome": "o1"} for i in range(4)
        ],
    }
    base.update(overrides)
    return LessonContent.model_validate(base)


def test_count_words_ignores_citations_and_link_urls() -> None:
    # "GET retrieves data See MDN" — the citation and the URL are not read by the learner.
    assert count_words("GET retrieves data [S1]. See [MDN](https://developer.mozilla.org/x).") == 5


@pytest.mark.parametrize(
    ("segment", "minutes"),
    [("02:00–07:30", 5.5), ("2:00-3:00", 1.0), ("1:00:00 - 1:10:00", 10.0), ("bad", None), ("05:00-01:00", None), (None, None)],
)
def test_segment_minutes(segment: str | None, minutes: float | None) -> None:
    assert segment_minutes(segment) == minutes


def test_time_budget_per_section_rules() -> None:
    tb = compute_time_budget(_lesson(), wpm=200, budget_min=45)
    rows = {r.id: r for r in tb.sections}
    assert rows["sec-1"].computed_min == 1.0  # 200 words @ 200 wpm
    assert rows["sec-2"].computed_min == pytest.approx(6.0, abs=0.1)  # real video duration
    assert rows["sec-3"].computed_min == 8.0  # declared activity time
    assert rows["sec-4"].computed_min >= 2.0  # 4 questions x 0.5 min
    assert any("1 min per 2 questions" in f for f in rows["sec-4"].flags)
    assert not tb.over_budget


def test_time_budget_uses_watch_segment_and_flags_over_budget() -> None:
    lesson = _lesson(videos=[{"sid": "S2", "title": "v", "url": "u", "duration_min": 60, "why": "w"}])
    tb = compute_time_budget(lesson, budget_min=45)
    assert tb.over_budget and "exceeds the 45-minute budget" in tb.flags[0]
    assert any("declared 6 min but computed" in f for f in tb.flags)

    trimmed = _lesson(videos=[{"sid": "S2", "title": "v", "url": "u", "duration_min": 60, "why": "w",
                               "watch_segment": "10:00-16:00"}])
    assert not compute_time_budget(trimmed, budget_min=45).over_budget


@pytest.mark.parametrize(
    ("url", "tier"),
    [
        ("https://www.rfc-editor.org/rfc/rfc9110", 1),
        ("https://developer.mozilla.org/en-US/docs/Web/HTTP", 1),
        ("https://www.investor.gov/compound-interest", 1),
        ("https://cs.stanford.edu/notes", 2),
        ("https://en.wikipedia.org/wiki/HTTP", 3),
        ("https://medium.com/@someone/http", 4),
        ("https://notmdn.org/http", 4),
        ("https://evil-developer.mozilla.org.attacker.com/", 4),
        (None, 4),
    ],
)
def test_reliability_tiers(url: str | None, tier: int) -> None:
    assert tier_for_url(url)[0] == tier


def test_channel_tiers() -> None:
    assert tier_for_channel("Khan Academy")[0] == 3
    assert tier_for_channel("Random Uploader")[0] == 4


def test_dependents_closure() -> None:
    assert with_dependents({"research_youtube"}) == [
        "research_youtube", "score_sources", "generate", "timebudget", "qc_factual", "qc_instructional"
    ]
    assert with_dependents({"qc_factual"}) == ["qc_factual"]
    assert with_dependents({"timebudget"}) == ["timebudget"]


def test_quiz_answer_must_be_an_option() -> None:
    with pytest.raises(ValueError, match="not one of the options"):
        _lesson(knowledge_check=[{"q": "q", "options": ["a", "b"], "answer": "c", "explanation": "e", "outcome": "o1"}])


def test_retry_policy_retries_transient_errors_only() -> None:
    calls = {"n": 0}

    @with_retries(max_attempts=3, min_wait=0, max_wait=0)
    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ProviderError("gemini", ErrorKind.rate_limited, "429")
        return "ok"

    assert flaky() == "ok" and calls["n"] == 3

    calls["n"] = 0

    @with_retries(max_attempts=3, min_wait=0, max_wait=0)
    def quota() -> None:
        calls["n"] += 1
        raise ProviderError("gemini", ErrorKind.quota_exhausted, "daily quota")

    with pytest.raises(ProviderError):
        quota()
    assert calls["n"] == 1  # not retried


def test_problem_result_check_catches_wrong_final_answer() -> None:
    from app.pipeline.numeric import check_problem_results

    text = ("**Problem:** £8,500 at 0.3% compound for 5 years.\n"
            "* **Step 1:** Here, P = 8500, r = 0.3% = 0.003, and t = 5 [S5].\n"
            "* **Final Answer:** £8,628.79.")
    found = check_problem_results(text, "sec-3")
    assert len(found) == 1 and found[0].stated == 8628.79
    assert "compound amount = 8,628.27" in found[0].detail


def test_problem_result_check_accepts_correct_and_rounded_answers() -> None:
    from app.pipeline.numeric import check_problem_results

    text = ("**Problem:** $10,000 at 5% compound for 3 years.\n"
            "* **Step 1:** P = 10000, r = 5% = 0.05, t = 3.\n"
            "* **Final Answer:** $11,576.25 (yielding $1,576.25 interest compared to $1,500 under simple interest).\n"
            "**Problem:** rounded factor.\n* P = 10000, r = 0.05, t = 3\n* **Final Answer:** $11,576.00")
    assert check_problem_results(text, "sec-3") == []


def test_rupee_amounts_and_indian_grouping() -> None:
    from app.pipeline.numeric import check_problem_results, check_text

    assert all(c.ok for c in check_text("A = 125000 × 1.05 = ₹1,31,250.00", "x"))
    assert not check_text("Rs. 1,00,000 × 0.05 × 2 = Rs. 11,000", "x")[0].ok  # should be 10,000
    found = check_problem_results("**Problem:** loan\n* P = 8500, r = 0.3% = 0.003, t = 5\n* **Final Answer:** ₹8,628.79", "s")
    assert len(found) == 1 and found[0].stated == 8628.79
