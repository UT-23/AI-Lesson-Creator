"""Render a QC report payload (see qc_store.report_payload) as readable Markdown."""

from typing import Any

MARK = {True: "✓", False: "✗"}


def _issues_md(issues: list[dict[str, Any]]) -> list[str]:
    if not issues:
        return ["_No issues._", ""]
    lines = ["| ID | Severity | Category | Where | Text | Evidence | Suggestion | Status |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]

    def cell(text: Any) -> str:
        return str(text or "").replace("|", "/").replace("\n", " ")[:300]

    for i in issues:
        lines.append(f"| {i['issue_id']} | {i['severity']} | {cell(i['category'])} | {cell(i.get('location'))} | "
                     f"{cell(i['claim_or_text'])} | {cell(i['evidence'])} | {cell(i['suggestion'])} | {i['status']} |")
    return lines + [""]


def render_report_md(payload: dict[str, Any]) -> str:
    d = payload["details"]
    factual = payload["layer"] == "factual"
    title = "QC1 — Research & Factual Accuracy" if factual else "QC2 — Instructional Quality"
    lines = [f"# {title}", "",
             f"- Lesson {payload['lesson_id']}, version {payload['lesson_version_no']}",
             f"- Score: **{payload['score']}** ({'% of claims supported' if factual else 'rubric average × 20'})",
             f"- Reviewer model: {d.get('model')}",
             f"- Method: {d.get('method')}", "", "## Summary", "", payload["summary"], ""]

    if factual:
        lines += ["## Claim table", "", "| Claim | Where | Cites | Verdict | Evidence quote (verified?) |",
                  "| --- | --- | --- | --- | --- |"]
        for c in d.get("claims", []):
            quote = (c.get("evidence_quote") or "").replace("|", "/").replace("\n", " ")[:200]
            text = c["text"].replace("|", "/")[:180]
            lines.append(f"| {c['id']}: {text} | {c['location']} | {', '.join(c.get('sids', []))} | "
                         f"**{c['verdict']}** | {quote} {'(✓ found)' if c.get('quote_verified') else ''} |")
        lines += ["", "## Numeric checks (recomputed in Python)", ""]
        checks = d.get("numeric_checks", [])
        if not checks:
            lines.append("_No arithmetic found._")
        for n in checks:
            lines.append(f"- {MARK[n['ok']]} `{n['expression']}` ({n['location']}) — {n['detail']}")
        audit = [f"- {a}" for a in d.get("source_audit", [])] or ["_None._"]
        gaps = [f"- {g}" for g in d.get("outcome_gaps", [])] or ["_None._"]
        lines += ["", "## Source audit", "", *audit, "", "## Outcome evidence gaps", "", *gaps, ""]
    else:
        lines += ["## Outcome coverage matrix", "",
                  "| Outcome | Explanation | Example | Practice | Quiz |", "| --- | --- | --- | --- | --- |"]
        for row in d.get("coverage_matrix", []):
            cells = [f"{MARK[row[k]['present']]} {', '.join(row[k].get('sections', []))}"
                     for k in ("explanation", "example", "practice", "quiz")]
            lines.append(f"| {row['outcome']} | " + " | ".join(cells) + " |")
        lines += ["", "## Verb alignment (Bloom)", "", "| Outcome | Verb | Level | Aligned | Evidence |",
                  "| --- | --- | --- | --- | --- |"]
        for a in d.get("verb_alignment", []):
            lines.append(f"| {a['outcome']} | {a['verb']} | {a['bloom_level']} | {MARK[a['aligned']]} | "
                         f"{a['evidence'].replace('|', '/')[:200]} |")
        lines += ["", f"## Rubric (average {d.get('rubric_average')}/5)", "", "| Criterion | Score | Justification |",
                  "| --- | --- | --- |"]
        for r in d.get("rubric", []):
            lines.append(f"| {r['criterion']} | {r['score']}/5 | {r['justification'].replace('|', '/')} |")
        tb = d.get("time_budget", {})
        if tb:
            lines += ["", f"## Time budget (measured {tb['total_computed_min']} of {tb['budget_min']} min)", "",
                      "| Section | Type | Shown | Measured | Flags |", "| --- | --- | --- | --- | --- |"]
            for r in tb.get("sections", []):
                lines.append(f"| {r['id']} {r['heading'][:40]} | {r['type']} | {r['declared_min']:g} | "
                             f"{r['computed_min']:g} | {'; '.join(r['flags'])} |")
        lines.append("")

    lines += ["## Issues", "", *_issues_md(payload["issues"])]
    return "\n".join(lines)
