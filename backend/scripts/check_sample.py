"""Print checks for an exported sample, read ONLY from the sample's files.

Usage (from backend/):  .venv/Scripts/python scripts/check_sample.py ../samples/http
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline.timebudget import compute_time_budget  # noqa: E402
from app.schemas import CITATION_GROUP_RE, LessonContent, extract_citations  # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    folder = Path(sys.argv[1])
    md = (folder / "lesson.md").read_text(encoding="utf-8")
    meta = json.loads((folder / "lesson.json").read_text(encoding="utf-8"))
    content = LessonContent.model_validate(meta["content"])
    qc1 = json.loads((folder / "qc1_factual_report.json").read_text(encoding="utf-8"))
    qc2 = json.loads((folder / "qc2_instructional_report.json").read_text(encoding="utf-8"))
    print(f"=== {folder}  (version v{meta['version_no']}, {meta['note']})")

    tb = compute_time_budget(content)
    print("\n--- TIME BUDGET (measured from lesson.json with timebudget.py)")
    for r in tb.sections:
        print(f"  {r.id:6} {r.type:16} shown {r.declared_min:>4g} min  measured {r.computed_min:>5g} min  {r.heading[:50]}")
    print(f"  TOTAL shown {content.total_minutes:g} min, measured {tb.total_computed_min} of {tb.budget_min} min;"
          f" flags: {tb.flags or 'none'}")

    body, _, rest = md.partition("## References")
    refs = rest.partition("## Further reading")[0]
    cited = set(extract_citations(body))
    listed = re.findall(r"\*\*\[(S\d+)\]\*\*", refs)
    grouped = [g for g in CITATION_GROUP_RE.findall(md) if "," in g or ";" in g]
    print("\n--- REFERENCES (from lesson.md)")
    print(refs.strip())
    print(f"\n  cited in text: {', '.join(sorted(cited, key=lambda s: int(s[1:])))}")
    print(f"  listed:        {', '.join(listed)}")
    print(f"  cited but not listed: {sorted(cited - set(listed)) or 'none'};"
          f" listed but not cited: {sorted(set(listed) - cited) or 'none'}; grouped citations left: {len(grouped)}")

    print("\n--- OUTCOME COVERAGE (from lesson.json)")
    code = {o: f"O{i}" for i, o in enumerate(content.outcomes, start=1)}
    for o, c in code.items():
        print(f"  {c}: {o}")
    for s in content.sections:
        print(f"  {s.id:6} {s.type:16} covers {', '.join(code.get(o, '?') for o in s.outcomes_covered) or '-':10} {s.heading[:55]}")
    for n, q in enumerate(content.knowledge_check, start=1):
        print(f"  Q{n} -> {code.get(q.outcome, '?')}  {q.q[:90]}")

    print("\n--- QC1:", qc1["summary"])
    print("--- QC2:", qc2["summary"])
    for row in qc2["details"]["coverage_matrix"]:
        cells = ["✓" if row[k]["present"] else "✗" for k in ("explanation", "example", "practice", "quiz")]
        print(f"  {code.get(row['outcome'], '?')}: explanation {cells[0]} example {cells[1]} practice {cells[2]} quiz {cells[3]}")
    sev: dict[str, int] = {}
    for i in qc1["issues"] + qc2["issues"]:
        sev[i["severity"]] = sev.get(i["severity"], 0) + 1
    print(f"--- issues by severity (QC1+QC2): {sev}")


if __name__ == "__main__":
    main()
