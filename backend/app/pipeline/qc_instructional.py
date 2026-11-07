"""Step `qc_instructional` (QC2 — instructional quality).

ONE QC_MODEL call in a fresh context; it never sees QC1's output. It returns:
* an outcome coverage matrix (explanation / example / practice / quiz, with section refs),
* Bloom's verb alignment per outcome,
* a 1-5 rubric (clarity, structure/flow, jargon before use, example quality,
  practical relevance, outcome alignment) and issues.
Code then: replaces the quiz column with the true mapping from the lesson data,
turns coverage gaps and misalignments into issues, and adds the deterministic
time-budget findings from timebudget.py.
Score = rubric average, scaled to 0-100.
"""

from typing import Any

from app.models import QCLayer
from app.pipeline.context import StepContext
from app.pipeline.qc_store import model_used, qc_model_for, save_qc_report, write_report_files
from app.pipeline.timebudget import compute_time_budget
from app.providers.llm import generate_structured
from app.schemas import CoverageCell, InstructionalReview, LessonContent, QCIssueDraft

QC_INSTRUCTIONAL_SYSTEM = (
    "You are an experienced instructional designer reviewing a self-paced lesson for adult beginners. "
    "Judge what the lesson actually contains, cite section ids, and be specific and constructive."
)
CRITERIA = ["clarity", "structure_flow", "jargon_before_use", "example_quality", "practical_relevance",
            "outcome_alignment"]


def lesson_for_review(content: LessonContent) -> str:
    parts = []
    for s in content.sections:
        parts.append(f"### [{s.id}] ({s.type}) {s.heading}\n{s.content_md.strip()}")
    for n, q in enumerate(content.knowledge_check, start=1):
        parts.append(f"[quiz Q{n}] {q.q}\n  options: {q.options}\n  answer: {q.answer}\n  outcome: {q.outcome}")
    for v in content.videos:
        parts.append(f"[video {v.sid}] {v.title} ({v.duration_min} min): {v.why}")
    return "\n\n".join(parts)


def build_prompt(content: LessonContent) -> str:
    outcomes = "\n".join(f"- {o}" for o in content.outcomes)
    return f"""Review this lesson's instructional design.

OBJECTIVE: {content.objective}
OUTCOMES:
{outcomes}

LESSON (section ids in brackets):
{lesson_for_review(content)}

Return:
1. "coverage": one entry per outcome (copy the outcome text exactly). For each of explanation, example,
   practice (an activity where the learner actually performs the outcome's verb) and quiz: present
   true/false and the section ids / quiz numbers where it appears.
2. "verb_alignment": per outcome, its main verb, the Bloom level it demands, and whether the activity
   AND quiz make the learner perform that verb (e.g. "distinguish" needs classification/comparison
   tasks, not definitions; "calculate" needs the learner to compute). Give evidence and a suggestion.
3. "rubric": a 1-5 score with a one-line justification for each of: clarity, structure_flow,
   jargon_before_use (terms defined before they are used), example_quality, practical_relevance,
   outcome_alignment. 5 = excellent, 3 = adequate, 1 = poor.
4. "issues": concrete problems (severity critical/major/minor, category, location = section id,
   the problematic text, and a specific suggestion). Do not report factual accuracy; another reviewer does that.
5. "summary": two or three sentences."""


def _check(outcomes: list[str]):  # type: ignore[no-untyped-def]
    def check(review: InstructionalReview) -> list[str]:
        problems = []
        got = {c.outcome for c in review.coverage}
        missing = [o for o in outcomes if o not in got]
        if missing:
            problems.append(f"coverage must have one entry per outcome, copied exactly. Missing: {missing}")
        crit = {r.criterion for r in review.rubric}
        if set(CRITERIA) - crit:
            problems.append(f"rubric is missing criteria: {sorted(set(CRITERIA) - crit)}")
        return problems
    return check


def run_qc_instructional(ctx: StepContext) -> dict[str, Any]:
    version = ctx.require_latest_version()
    content = LessonContent.model_validate(version.content_json)
    llm = qc_model_for(ctx)
    review = generate_structured(llm, build_prompt(content), InstructionalReview, system=QC_INSTRUCTIONAL_SYSTEM,
                                 max_repairs=ctx.settings.llm_max_repairs, check=_check(content.outcomes))

    issues: list[QCIssueDraft] = list(review.issues)
    matrix = []
    for outcome in content.outcomes:
        cov = next((c for c in review.coverage if c.outcome == outcome), None)
        quiz_refs = [f"Q{n}" for n, q in enumerate(content.knowledge_check, start=1) if q.outcome == outcome]
        quiz = CoverageCell(present=bool(quiz_refs), sections=quiz_refs, note="from the lesson's quiz mapping (code)")
        row = {"outcome": outcome,
               "explanation": cov.explanation.model_dump() if cov else {"present": False, "sections": []},
               "example": cov.example.model_dump() if cov else {"present": False, "sections": []},
               "practice": cov.practice.model_dump() if cov else {"present": False, "sections": []},
               "quiz": quiz.model_dump()}
        matrix.append(row)
        for column, sev in (("explanation", "major"), ("practice", "major"), ("quiz", "major"), ("example", "minor")):
            if not row[column]["present"]:
                issues.append(QCIssueDraft(
                    severity=sev, category=f"coverage_missing_{column}", location=None, claim_or_text=outcome,  # type: ignore[arg-type]
                    evidence=f"No {column} found for this outcome.",
                    suggestion=f"Add a {column} that directly addresses: {outcome}"))
    for a in review.verb_alignment:
        if not a.aligned:
            issues.append(QCIssueDraft(
                severity="major", category="verb_misalignment", location=None, claim_or_text=f"{a.outcome} ({a.verb})",
                evidence=a.evidence, suggestion=a.suggestion or f"Add practice where the learner must {a.verb}."))

    budget = compute_time_budget(content, ctx.settings.reading_wpm, ctx.settings.lesson_minutes_budget)
    if budget.over_budget:
        issues.append(QCIssueDraft(severity="major", category="time_budget", location=None,
                                   claim_or_text=f"Measured {budget.total_computed_min} min",
                                   evidence=budget.flags[0], suggestion="Trim text or shorten/segment the videos."))
    for row in budget.sections:
        for flag in row.flags:
            issues.append(QCIssueDraft(severity="minor", category="time_budget", location=row.id,
                                       claim_or_text=row.heading, evidence=flag,
                                       suggestion="Make the section's stated minutes match its real length."))

    scores = {r.criterion: r.score for r in review.rubric}
    average = sum(scores.values()) / len(scores) if scores else 0
    model = model_used(llm)
    summary = (f"{review.summary} Rubric average {average:.1f}/5. Measured time {budget.total_computed_min} of "
               f"{budget.budget_min} min. Reviewer: {model}.")
    details = {
        "method": "one LLM review call (no access to QC1) + code: quiz mapping, coverage gaps, time budget",
        "model": model,
        "coverage_matrix": matrix,
        "verb_alignment": [a.model_dump() for a in review.verb_alignment],
        "rubric": [r.model_dump() for r in review.rubric],
        "rubric_average": round(average, 2),
        "time_budget": budget.model_dump(),
    }
    report = save_qc_report(ctx.session, lesson_id=ctx.lesson.id, layer=QCLayer.instructional,  # type: ignore[arg-type]
                            version_no=version.version_no, summary=summary, score=average / 5 * 100,
                            details=details, issues=issues)
    files = write_report_files(ctx.session, report, ctx.settings.reports_dir)
    return {"report_id": report.id, "version_no": version.version_no, "score": report.score, "model": model,
            "rubric_average": round(average, 2), "issue_count": len(issues), "files": files}
