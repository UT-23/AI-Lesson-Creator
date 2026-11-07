"""Step `qc_factual` (QC1 — research & factual accuracy).

1. Claims are extracted IN CODE: every sentence / table row carrying a [S#]
   citation is a claim; factual-looking sentences without one are "uncited".
2. ONE QC_MODEL call judges all cited claims against their cited sources'
   excerpts (supported / partially_supported / unsupported / contradicted),
   quoting the evidence, and lists contradictions between sections and quiz answers.
3. Code verifies each quote really appears in the source excerpt; a "supported"
   verdict whose quote can't be found is downgraded to partially_supported.
4. Source audit in code: key claims resting only on tier-4 sources, over-reliance
   on one source, uncited factual sentences.
5. Gaps in code: outcomes with no supported claim in the sections covering them.
6. Numeric examples recomputed in Python (pipeline/numeric.py).
Score = % of claims (cited + uncited) judged "supported".
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlmodel import select

from app.models import QCLayer, Source, SourceType
from app.pipeline.context import StepContext
from app.pipeline.numeric import check_problem_results, check_text
from app.pipeline.passages import select_passages, topic_keywords
from app.pipeline.qc_store import model_used, qc_model_for, save_qc_report, write_report_files
from app.providers.llm import generate_structured
from app.schemas import CITATION_GROUP_RE, FactCheckResult, LessonContent, QCIssueDraft, extract_citations

MAX_JUDGED_CLAIMS = 90
SOURCE_PROMPT_CHARS = 3500
FACTUAL_SECTION_TYPES = {"hook", "concept", "example", "summary"}
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9`*_(\[])")
_ASSERTIVE = re.compile(
    r"\b(is|are|was|were|means|indicates?|returns?|uses?|must|cannot|can't|grows?|calculated|defined|"
    r"refers|represents?|requires?|always|never|only)\b", re.I)
_INSTRUCTION = re.compile(r"^(let'?s|imagine|try|watch|note|notice|consider|calculate|compare|complete|answer|"
                          r"remember|think|work|use|look|read|see|now|first|next|then|step)\b", re.I)

QC_FACTUAL_SYSTEM = (
    "You are a meticulous fact-checker. You judge each claim ONLY against the source excerpts provided, "
    "never against your own knowledge, and you quote the exact words of the source that decide your verdict."
)


@dataclass
class Claim:
    id: str
    location: str
    text: str
    sids: list[str] = field(default_factory=list)


def _plain(text: str) -> str:
    text = CITATION_GROUP_RE.sub("", text)
    text = re.sub(r"[*_`#>]|\$\$?", "", text)
    return re.sub(r"\s+", " ", text).strip(" -|")


def extract_claims(content: LessonContent) -> tuple[list[Claim], list[Claim]]:
    """Return (cited claims, uncited factual-looking sentences)."""
    cited: list[Claim] = []
    uncited: list[Claim] = []

    def add(location: str, raw: str, factual_section: bool) -> None:
        sids = list(dict.fromkeys(extract_citations(raw)))
        plain = _plain(raw)
        if len(plain.split()) < 4:
            return
        if sids:
            cited.append(Claim(f"C{len(cited) + 1}", location, plain, sids))
        elif (factual_section and len(plain.split()) >= 8 and "?" not in plain and "=" not in plain
              and _ASSERTIVE.search(plain) and not _INSTRUCTION.match(plain)):
            uncited.append(Claim(f"U{len(uncited) + 1}", location, plain))

    for section in content.sections:
        factual = section.type in FACTUAL_SECTION_TYPES
        for line in section.content_md.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or re.fullmatch(r"[|:\-\s]+", line) or line == "---":
                continue
            if line.startswith("|"):  # a table row is one claim
                add(section.id, line, factual)
                continue
            for sentence in _SENTENCE_SPLIT.split(line):
                add(section.id, sentence, factual)
    for n, item in enumerate(content.knowledge_check, start=1):
        add(f"quiz-Q{n}", f"Answer to '{item.q}': {item.answer}. {item.explanation}", True)
    return cited, uncited


def _normal(text: str) -> str:
    text = re.sub(r"[*_`#>\[\]()]", " ", text.lower())
    text = text.replace("’", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def quote_found(quote: str, excerpt: str) -> bool:
    q = _normal(quote).strip(" .\"'")
    return len(q) >= 8 and q in _normal(excerpt)


def build_prompt(claims: list[Claim], sources: dict[str, Source], quiz_text: str) -> str:
    by_source: dict[str, list[Claim]] = {}
    for claim in claims:
        for sid in claim.sids:
            by_source.setdefault(sid, []).append(claim)
    blocks = []
    for sid, its_claims in sorted(by_source.items(), key=lambda kv: int(kv[0][1:])):
        src = sources.get(sid)
        if src is None:
            blocks.append(f"[{sid}] (NOT IN THE EVIDENCE STORE)")
            continue
        keywords = topic_keywords([c.text for c in its_claims])
        excerpt, _ = select_passages(src.excerpt_text, keywords, SOURCE_PROMPT_CHARS)
        blocks.append(f"[{sid}] {src.type.value}, tier {src.reliability_tier}: {src.title}\n{excerpt.strip() or '(empty)'}")
    claim_lines = "\n".join(f"[{c.id}] ({c.location}) {c.text}   — cites: {', '.join(c.sids)}" for c in claims)
    return f"""Check every claim below against the excerpt(s) of the source(s) it cites.

CLAIMS:
{claim_lines}

SOURCE EXCERPTS (the only evidence you may use):

{chr(10).join(blocks)}

KNOWLEDGE CHECK (questions and keyed answers):
{quiz_text}

For EVERY claim id return one verdict:
- supported: the cited excerpt states it (paraphrase is fine).
- partially_supported: part of the claim is supported, part is not stated, or it overgeneralises.
- unsupported: the cited excerpt does not say this (even if you believe it is true).
- contradicted: the cited excerpt says something incompatible.
"evidence_quote" must be copied character-for-character from the excerpt of "source_id" (max ~40 words);
leave it empty if nothing in the excerpt bears on the claim. Worked arithmetic and the lesson's own
illustrative scenarios count as supported if the formula/rule they apply is supported.

Also list "contradictions": places where two sections disagree, or where a keyed quiz answer or its
explanation disagrees with the lesson text. Return an empty list if there are none."""


def _all_ids_present(ids: list[str]):  # type: ignore[no-untyped-def]
    def check(result: FactCheckResult) -> list[str]:
        got = {v.claim_id for v in result.verdicts}
        missing = [i for i in ids if i not in got]
        return [f"Missing verdicts for claim ids: {', '.join(missing[:30])}. Return one verdict per claim."] if missing else []
    return check


def run_qc_factual(ctx: StepContext) -> dict[str, Any]:
    version = ctx.require_latest_version()
    content = LessonContent.model_validate(version.content_json)
    sources = {s.sid: s for s in ctx.session.exec(select(Source).where(Source.lesson_id == ctx.lesson.id)).all()}

    cited, uncited = extract_claims(content)
    judged, not_checked = cited[:MAX_JUDGED_CLAIMS], cited[MAX_JUDGED_CLAIMS:]
    quiz_text = "\n".join(f"Q{n}. {q.q} → {q.answer} ({q.explanation})" for n, q in enumerate(content.knowledge_check, 1))

    llm = qc_model_for(ctx)
    result = generate_structured(
        llm, build_prompt(judged, sources, quiz_text), FactCheckResult, system=QC_FACTUAL_SYSTEM,
        max_repairs=ctx.settings.llm_max_repairs, check=_all_ids_present([c.id for c in judged]),
    )
    verdicts = {v.claim_id: v for v in result.verdicts}

    # --- claim table, with quotes verified in code ---
    table: list[dict[str, Any]] = []
    issues: list[QCIssueDraft] = []
    severity = {"contradicted": "critical", "unsupported": "major", "partially_supported": "minor"}
    for claim in judged:
        v = verdicts[claim.id]
        verdict, note = v.verdict, v.explanation
        src = sources.get(v.source_id or "") or sources.get(claim.sids[0])
        quote_ok = bool(v.evidence_quote) and src is not None and quote_found(v.evidence_quote, src.excerpt_text)
        if verdict == "supported" and not quote_ok:
            verdict = "partially_supported"
            note = f"Downgraded: the quoted evidence was not found verbatim in the source excerpt. {note}"
        table.append({**asdict(claim), "verdict": verdict, "source_id": v.source_id, "evidence_quote": v.evidence_quote,
                      "quote_verified": quote_ok, "explanation": note})
        if verdict in severity:
            issues.append(QCIssueDraft(
                severity=severity[verdict], category=f"claim_{verdict}", location=claim.location,  # type: ignore[arg-type]
                claim_or_text=claim.text, evidence=v.evidence_quote or note, source_ids=claim.sids,
                suggestion=("Rewrite the claim so it says only what the cited source states, cite a source that "
                            "supports it, or remove it." if verdict != "contradicted" else
                            "Correct the claim to match the source (see evidence) and re-check related quiz items."),
            ))
    for claim in not_checked:
        table.append({**asdict(claim), "verdict": "not_checked", "source_id": None, "evidence_quote": "",
                      "quote_verified": False, "explanation": f"Over the {MAX_JUDGED_CLAIMS}-claim limit for one QC call."})
    for claim in uncited:
        table.append({**asdict(claim), "verdict": "uncited", "source_id": None, "evidence_quote": "",
                      "quote_verified": False, "explanation": "Factual-looking sentence without a citation (detected in code)."})
        section_type = next((s.type for s in content.sections if s.id == claim.location), "")
        issues.append(QCIssueDraft(
            severity="major" if section_type in ("concept", "example") else "minor", category="uncited_claim",
            location=claim.location, claim_or_text=claim.text, evidence="",
            suggestion="Add a citation to a source that states this, or remove/soften the sentence."))

    # --- contradictions (from the same call) ---
    for c in result.contradictions:
        issues.append(QCIssueDraft(severity="critical", category="contradiction", location=c.location,
                                   claim_or_text=c.description, evidence="", suggestion=c.suggestion))

    # --- source audit (code) ---
    audit: list[str] = []
    cited_counts: dict[str, int] = {}
    for claim in cited:
        for sid in claim.sids:
            cited_counts[sid] = cited_counts.get(sid, 0) + 1
        tiers = [sources[s].reliability_tier for s in claim.sids if s in sources]
        section_type = next((s.type for s in content.sections if s.id == claim.location), "")
        if tiers and min(tiers) == 4 and section_type in ("concept", "example"):
            issues.append(QCIssueDraft(
                severity="major", category="low_tier_source", location=claim.location, claim_or_text=claim.text,
                evidence=f"Only tier-4 source(s): {', '.join(claim.sids)}", source_ids=claim.sids,
                suggestion="Support this key claim with a tier 1-2 source from the evidence store, or soften it."))
    if cited:
        top_sid, top_n = max(cited_counts.items(), key=lambda kv: kv[1])
        share = top_n / len(cited)
        audit.append(f"Most-cited source {top_sid} carries {top_n} of {len(cited)} cited claims ({share:.0%}).")
        if share > 0.4:
            issues.append(QCIssueDraft(
                severity="minor", category="over_reliance", location=None, claim_or_text=f"{top_sid} carries {share:.0%} of claims",
                evidence=sources[top_sid].title if top_sid in sources else "", source_ids=[top_sid],
                suggestion="Cross-check key claims against a second independent source."))
    for sid in cited_counts:
        src = sources.get(sid)
        if src is None:
            audit.append(f"{sid} is cited but not in the evidence store.")
        elif not src.excerpt_text.strip():
            audit.append(f"{sid} has no stored text, so its claims cannot be verified.")
        elif src.type == SourceType.book:
            audit.append(f"{sid} is a book (metadata only) but is cited.")

    # --- gaps: outcomes with no supported claim in their sections (code) ---
    gaps = []
    for outcome in content.outcomes:
        section_ids = {s.id for s in content.sections if outcome in s.outcomes_covered}
        supported = [r for r in table if r["location"] in section_ids and r["verdict"] == "supported"]
        if not supported:
            gaps.append(outcome)
            issues.append(QCIssueDraft(
                severity="major", category="evidence_gap", location=", ".join(sorted(section_ids)) or None,
                claim_or_text=outcome, evidence="No claim in the sections covering this outcome was verified as supported.",
                suggestion="Add or fix claims for this outcome so they rest on a cited source that states them."))

    # --- numeric recomputation (code) ---
    numeric = []
    for section in content.sections:
        numeric += check_text(section.content_md, section.id)
    for n, q in enumerate(content.knowledge_check, start=1):
        numeric += check_text(q.explanation, f"quiz-Q{n}")
    for check in numeric:
        if not check.ok:
            issues.append(QCIssueDraft(
                severity="critical", category="arithmetic_error", location=check.location,
                claim_or_text=check.expression, evidence=check.detail,
                suggestion="Recompute this step; the numbers in the text do not match."))

    # Whole-problem check: stated results vs the problem's own P, r, t (n), recomputed in Python.
    formula_checks = []
    for section in content.sections:
        formula_checks += check_problem_results(section.content_md, section.id)
    for n, q in enumerate(content.knowledge_check, start=1):
        formula_checks += check_problem_results(f"{q.q}\nAnswer: {q.answer}\n{q.explanation}", f"quiz-Q{n}")
    for f in formula_checks:
        compound = f.expected["compound amount"]
        issues.append(QCIssueDraft(
            severity="critical", category="wrong_result", location=f.location, claim_or_text=f.line,
            evidence=f.detail,
            suggestion=(f"Replace {f.stated:,.2f} with the value recomputed from the problem's own inputs: "
                        f"compound amount {compound:,.2f} (simple amount {f.expected['simple amount']:,.2f}); "
                        "fix any intermediate step that led to the wrong figure.")))

    counts: dict[str, int] = {}
    for row in table:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    total = len(judged) + len(uncited)
    score = 100 * counts.get("supported", 0) / total if total else 0.0
    model = model_used(llm)
    summary = (f"{counts.get('supported', 0)} of {total} claims supported ({score:.0f}%); "
               f"{counts.get('partially_supported', 0)} partial, {counts.get('unsupported', 0)} unsupported, "
               f"{counts.get('contradicted', 0)} contradicted, {len(uncited)} uncited. "
               f"{sum(c.ok for c in numeric)}/{len(numeric)} calculations recomputed correctly; "
               f"{len(formula_checks)} stated result(s) contradict their own inputs. "
               f"{len(result.contradictions)} contradiction(s), {len(gaps)} outcome gap(s). Judge: {model}.")
    details = {
        "method": "claims extracted in code; one batched LLM verdict call; quotes verified in code",
        "model": model,
        "counts": counts,
        "claims": table,
        "numeric_checks": [asdict(c) for c in numeric],
        "result_checks": [{"location": f.location, "line": f.line, "stated": f.stated, "detail": f.detail}
                          for f in formula_checks],
        "source_audit": audit,
        "outcome_gaps": gaps,
        "contradictions": [c.model_dump() for c in result.contradictions],
    }
    report = save_qc_report(ctx.session, lesson_id=ctx.lesson.id, layer=QCLayer.factual,  # type: ignore[arg-type]
                            version_no=version.version_no, summary=summary, score=score, details=details, issues=issues)
    files = write_report_files(ctx.session, report, ctx.settings.reports_dir)
    return {"report_id": report.id, "version_no": version.version_no, "score": report.score, "model": model,
            "issue_count": len(issues), "counts": counts, "files": files}
