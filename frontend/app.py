"""Instructor UI (Streamlit). Stateless: every view reads from the FastAPI backend; all state lives in SQLite.

Run (from the repo root, backend already running on :8000):
    backend\\.venv\\Scripts\\streamlit run frontend\\app.py
Open a specific lesson: http://localhost:8501/?lesson=2
"""

import os
import time

import altair as alt
import httpx
import pandas as pd
import streamlit as st

API = os.environ.get("LESSON_API", "http://localhost:8000")
STEP_ICON = {"done": "✅", "failed": "❌", "running": "⏳", "pending": "⚪", "skipped": "⏭️"}
SEVERITY_ICON = {"critical": "🔴", "major": "🟠", "minor": "🟡"}
TIER = {1: "1 · standard/official", 2: "2 · academic/publisher", 3: "3 · known site", 4: "4 · blog/unknown"}

st.set_page_config(page_title="AI Lesson Creator", layout="wide")


def api(method: str, path: str, quiet: bool = False, **kwargs):  # type: ignore[no-untyped-def]
    """Call the backend; show a readable error (never a stack trace)."""
    try:
        resp = httpx.request(method, f"{API}{path}", timeout=kwargs.pop("timeout", 180), **kwargs)
    except httpx.HTTPError as err:
        st.error(f"Cannot reach the backend at {API} ({type(err).__name__}). Is it running?")
        return None
    if resp.status_code >= 400:
        if not quiet:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            st.error(f"{resp.status_code}: {detail}")
        return None
    return resp


def get_json(path: str, default):  # type: ignore[no-untyped-def]
    resp = api("GET", path)
    return resp.json() if resp is not None else default


# ---------------------------------------------------------------------------
# Sidebar: new lesson + lesson list (auto-selects the latest)
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("➕ New lesson")
    with st.form("new_lesson"):
        title = st.text_input("Lesson title", placeholder="HTTP Requests and Responses")
        objective = st.text_area("Learning objective", placeholder="Explain GET and POST methods and …")
        submitted = st.form_submit_button("Create and run", type="primary")
    if submitted:
        problems = []
        if len(title.strip()) < 3:
            problems.append("Title is required (at least 3 characters).")
        if len(objective.strip()) < 15:
            problems.append("Learning objective is required (at least 15 characters).")
        for problem in problems:
            st.error(problem)
        if not problems:
            created = api("POST", "/lessons", json={"title": title, "objective": objective})
            if created is not None:
                new_id = created.json()["id"]
                api("POST", f"/lessons/{new_id}/run")
                st.query_params["lesson"] = str(new_id)
                st.rerun()

    st.header("📚 Lessons")
    lessons = get_json("/lessons", [])
    if not lessons:
        st.info("No lessons yet — create one above.")
        st.stop()
    ids = [l["id"] for l in lessons]
    wanted = st.query_params.get("lesson")
    current = int(wanted) if wanted and wanted.isdigit() and int(wanted) in ids else ids[0]  # latest by default
    labels = {l["id"]: f"#{l['id']} {l['title']} · {l['status']}" for l in lessons}
    picked = st.radio("Open lesson", ids, index=ids.index(current), format_func=lambda i: labels[i])
    if picked != current or wanted != str(picked):
        st.query_params["lesson"] = str(picked)
    lesson_id = picked
    st.caption(f"Backend: {API}")

data = get_json(f"/lessons/{lesson_id}", None)
if data is None:
    st.stop()
lesson, version = data["lesson"], data["version"]
qc = get_json(f"/lessons/{lesson_id}/qc", {}) or {}
qc1, qc2 = qc.get("factual"), qc.get("instructional")
steps = get_json(f"/lessons/{lesson_id}/steps", [])
running = lesson["status"] == "running" or any(s["status"] == "running" for s in steps)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title(f"#{lesson['id']} {lesson['title']}")
st.caption(f"🎯 {lesson['objective']}")
measured = (data.get("measured_time") or {}).get("total_computed_min")
cols = st.columns([1, 1, 3])
cols[0].metric("Version", f"v{version['version_no']}" if version else "—", version["author"] if version else None,
               delta_color="off")
cols[1].metric("Measured time (max 45)", f"{measured:g} min" if measured is not None else "—",
               ("over budget" if measured and measured > 45 else "within budget") if measured else None,
               delta_color="inverse" if measured and measured > 45 else "normal")
cols[2].markdown(
    f"**Generator:** `{(data.get('generation') or {}).get('model') or '—'}`  \n"
    f"**QC1 judge:** `{(qc1 or {}).get('details', {}).get('model') or '—'}`  \n"
    f"**QC2 reviewer:** `{(qc2 or {}).get('details', {}).get('model') or '—'}`")
if running:
    st.info("⏳ The pipeline is running — this page refreshes every few seconds.")

tabs = st.tabs(["Pipeline", "Lesson", "Sources", "QC1", "QC2", "Edit", "Preview", "Export"])

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

with tabs[0]:
    top = st.columns([1, 1, 5])
    if top[0].button("▶ Run / resume", disabled=running):
        if api("POST", f"/lessons/{lesson_id}/run") is not None:
            st.rerun()
    if top[1].button("🔄 Refresh"):
        st.rerun()
    for s in steps:
        row = st.columns([3, 2, 7, 1])
        row[0].markdown(f"{STEP_ICON.get(s['status'], '')} **{s['name']}**")
        row[1].write(f"{s['status']} · attempt {s['attempt']}")
        if s["error"]:
            row[2].error(s["error"])
        if s["status"] in ("failed", "skipped") or (s["status"] == "done" and not running):
            if row[3].button("Retry", key=f"retry_{s['name']}", disabled=running):
                if api("POST", f"/lessons/{lesson_id}/steps/{s['name']}/retry") is not None:
                    st.rerun()
    for warning in (data.get("generation") or {}).get("warnings", []):
        st.warning(f"Generation: {warning}")

# ---------------------------------------------------------------------------
# Lesson (structured view)
# ---------------------------------------------------------------------------

with tabs[1]:
    if not version:
        st.info("No lesson yet — the pipeline has not generated one.")
    else:
        content = version["content"]
        st.markdown("**Outcomes:** " + " · ".join(f"`O{i}` {o}" for i, o in enumerate(content["outcomes"], 1)))
        videos = {v["sid"]: v for v in content.get("videos", [])}
        for sec in content["sections"]:
            with st.container(border=True):
                st.markdown(f"#### {sec['heading']}")
                st.caption(f"{sec['id']} · {sec['type']} · ~{sec['minutes']:g} min")
                st.markdown(sec["content_md"])
                if sec["type"] == "video" and videos:
                    vcols = st.columns(len(videos))
                    for vcol, v in zip(vcols, videos.values()):
                        with vcol:
                            vid = v["url"].split("v=")[-1]
                            st.image(f"https://img.youtube.com/vi/{vid}/mqdefault.jpg", use_container_width=True)
                            st.markdown(f"**[{v['title']}]({v['url']})**  \n⏱ {v['duration_min']:g} min · [{v['sid']}]")
                            st.caption(v["why"])
        with st.container(border=True):
            st.markdown("#### Knowledge check")
            for n, q in enumerate(content.get("knowledge_check", []), start=1):
                st.markdown(f"**Q{n}. {q['q']}**")
                st.markdown("\n".join(f"- {'✅' if o == q['answer'] else '▫️'} {o}" for o in q["options"]))
                st.caption(f"{q['explanation']} — assesses: {q['outcome']}")

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

with tabs[2]:
    if not data["sources"]:
        st.info("No sources yet — research has not finished.")
    else:
        rows = []
        for s in data["sources"]:
            meta = s.get("metadata_json") or {}
            minutes = round(meta["duration_seconds"] / 60, 1) if meta.get("duration_seconds") else None
            rows.append({"ID": s["sid"], "Type": s["type"], "Tier": TIER.get(s["reliability_tier"]),
                         "Title": s["title"], "Link": s["url"], "Video min": minutes,
                         "Why this tier": s["reliability_reason"]})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                     column_config={"Link": st.column_config.LinkColumn("Link")})


# ---------------------------------------------------------------------------
# QC issue workflow (shared by QC1 and QC2)
# ---------------------------------------------------------------------------


def issue_list(report: dict) -> None:  # type: ignore[type-arg]
    if not report["issues"]:
        st.success("No issues found.")
        return
    for severity in ("critical", "major", "minor"):
        group = [i for i in report["issues"] if i["severity"] == severity]
        if not group:
            continue
        st.markdown(f"##### {SEVERITY_ICON[severity]} {severity.title()} ({len(group)})")
        for issue in group:
            with st.expander(f"{issue['issue_id']} · {issue['category']} · {issue.get('location') or 'lesson'}"
                             f" · {issue['status']}"):
                st.markdown(f"**Text:** {issue['claim_or_text']}")
                if issue["evidence"]:
                    st.markdown(f"**Evidence:** {issue['evidence']}")
                st.markdown(f"**Suggestion:** {issue['suggestion']}")
                if issue["status"] != "open":
                    continue
                key = f"fix_{issue['id']}"
                b1, b2 = st.columns(2)
                if b1.button("🔧 Preview fix", key=f"prev_{issue['id']}"):
                    with st.spinner("Rewriting only the affected part…"):
                        fixed = api("POST", f"/qc/issues/{issue['id']}/preview-fix", timeout=300)
                    if fixed is not None:
                        st.session_state[key] = fixed.json()
                if b2.button("Dismiss", key=f"dis_{issue['id']}"):
                    if api("POST", f"/qc/issues/{issue['id']}/dismiss") is not None:
                        st.rerun()
                fix = st.session_state.get(key)
                if fix:
                    st.caption(f"Proposed by {fix['model']} for {fix['heading']}: {fix['change_summary']}")
                    added = ", ".join(f"{s} (tier {t})" for s, t in fix.get("citations_added", {}).items()) or "none"
                    removed = ", ".join(f"{s} (tier {t})" for s, t in fix.get("citations_removed", {}).items()) or "none"
                    st.info(f"Citations added: {added} · removed: {removed} (tiers from the evidence store)")
                    left, right = st.columns(2)
                    left.markdown("**Before**")
                    left.code(fix["before"], language="markdown")
                    right.markdown("**After**")
                    right.code(fix["after"], language="markdown")
                    a1, a2 = st.columns(2)
                    if a1.button("✅ Apply (new version)", key=f"apply_{issue['id']}", type="primary"):
                        body = ({"quiz_index": fix["quiz_index"], "quiz_item": fix["after_item"]}
                                if fix.get("kind") == "quiz" else
                                {"section_id": fix["section_id"], "content_md": fix["after"]})
                        applied = api("POST", f"/qc/issues/{issue['id']}/apply", json=body)
                        if applied is not None:
                            st.session_state.pop(key, None)
                            st.success(applied.json()["message"] + " Re-run QC to re-check it.")
                            time.sleep(1)
                            st.rerun()
                    if a2.button("Discard", key=f"discard_{issue['id']}"):
                        st.session_state.pop(key, None)
                        st.rerun()


def rerun_button(layer: str, label: str) -> None:
    if st.button(f"🔁 Re-run {label} on the latest version", disabled=running, key=f"rerun_{layer}"):
        if api("POST", f"/lessons/{lesson_id}/qc/{layer}") is not None:
            st.success(f"{label} started — progress shows in the Pipeline tab.")
            time.sleep(1)
            st.rerun()


# ---------------------------------------------------------------------------
# QC1
# ---------------------------------------------------------------------------

with tabs[3]:
    rerun_button("factual", "QC1")
    if not qc1:
        st.info("No QC1 report yet — it runs after the lesson is generated.")
    else:
        d = qc1["details"]
        counts = d.get("counts", {})
        m = st.columns(5)
        m[0].metric("Claims supported", f"{qc1['score']:g}%")
        m[1].metric("Partial", counts.get("partially_supported", 0))
        m[2].metric("Unsupported / contradicted", counts.get("unsupported", 0) + counts.get("contradicted", 0))
        m[3].metric("Uncited", counts.get("uncited", 0))
        checks = d.get("numeric_checks", [])
        m[4].metric("Calculations correct", f"{sum(c['ok'] for c in checks)}/{len(checks)}")
        st.caption(f"Checked version v{qc1['lesson_version_no']} · judge {d.get('model')} · {d.get('method')}")
        st.markdown(qc1["summary"])
        st.markdown("##### Claim verdicts")
        st.dataframe(pd.DataFrame([{"Claim": c["id"], "Where": c["location"], "Text": c["text"],
                                    "Cites": ", ".join(c.get("sids", [])), "Verdict": c["verdict"],
                                    "Evidence quote": c.get("evidence_quote"),
                                    "Quote found in source": "✓" if c.get("quote_verified") else ""}
                                   for c in d["claims"]]), hide_index=True, use_container_width=True, height=320)
        wrong = [c for c in checks if not c["ok"]] + [{"location": r["location"], "expression": r["line"],
                                                      "detail": r["detail"]} for r in d.get("result_checks", [])]
        if wrong:
            st.markdown("##### ❌ Calculation errors (recomputed in Python)")
            st.dataframe(pd.DataFrame([{"Where": w["location"], "Text": w["expression"], "Recomputed": w["detail"]}
                                       for w in wrong]), hide_index=True, use_container_width=True)
        st.markdown("##### Issues")
        issue_list(qc1)

# ---------------------------------------------------------------------------
# QC2
# ---------------------------------------------------------------------------

with tabs[4]:
    rerun_button("instructional", "QC2")
    if not qc2:
        st.info("No QC2 report yet — it runs after the lesson is generated.")
    else:
        d = qc2["details"]
        tb = d.get("time_budget") or {}
        m = st.columns(3)
        m[0].metric("Rubric average", f"{d.get('rubric_average')}/5")
        m[1].metric("Measured time", f"{tb.get('total_computed_min', 0):g} / {tb.get('budget_min', 45)} min")
        m[2].metric("Issues", len(qc2["issues"]))
        st.caption(f"Checked version v{qc2['lesson_version_no']} · reviewer {d.get('model')}")
        st.markdown(qc2["summary"])
        st.markdown("##### Outcome coverage")
        mark = lambda c: ("✓ " if c["present"] else "✗ ") + ", ".join(c.get("sections", []))  # noqa: E731
        st.dataframe(pd.DataFrame([{"Outcome": r["outcome"], "Explanation": mark(r["explanation"]),
                                    "Example": mark(r["example"]), "Practice": mark(r["practice"]),
                                    "Quiz": mark(r["quiz"])} for r in d["coverage_matrix"]]),
                     hide_index=True, use_container_width=True)
        if tb.get("sections"):
            st.markdown("##### Time budget (measured)")
            frame = pd.DataFrame([{"Section": f"{r['id']} {r['type']}", "Minutes": r["computed_min"],
                                   "Order": i} for i, r in enumerate(tb["sections"])])
            frame["Lesson"] = "lesson"
            bars = alt.Chart(frame).mark_bar(size=34).encode(
                x=alt.X("sum(Minutes):Q", title="Cumulative minutes", scale=alt.Scale(domain=[0, 50])),
                y=alt.Y("Lesson:N", title=None, axis=None),
                color=alt.Color("Section:N", sort=alt.SortField("Order"), legend=alt.Legend(orient="right", title=None)),
                order=alt.Order("Order:Q"), tooltip=["Section", "Minutes"])
            limit = alt.Chart(pd.DataFrame({"x": [45], "Lesson": ["lesson"]})).mark_tick(
                color="red", thickness=3, size=46).encode(x=alt.X("x:Q", scale=alt.Scale(domain=[0, 50])),
                                                          y=alt.Y("Lesson:N", axis=None))
            st.altair_chart((bars + limit).properties(height=150), use_container_width=True)
            st.caption("Red dashed line = 45-minute budget.")
        st.markdown("##### Verb alignment (Bloom)")
        st.dataframe(pd.DataFrame([{"Outcome": a["outcome"], "Verb": a["verb"], "Level": a["bloom_level"],
                                    "Aligned": "✓" if a["aligned"] else "✗", "Evidence": a["evidence"]}
                                   for a in d.get("verb_alignment", [])]), hide_index=True, use_container_width=True)
        st.markdown("##### Rubric")
        st.dataframe(pd.DataFrame([{"Criterion": r["criterion"].replace("_", " "), "Score": f"{r['score']}/5",
                                    "Why": r["justification"]} for r in d.get("rubric", [])]),
                     hide_index=True, use_container_width=True)
        st.markdown("##### Issues")
        issue_list(qc2)

# ---------------------------------------------------------------------------
# Edit (sections + quiz) and version history
# ---------------------------------------------------------------------------

with tabs[5]:
    if not version:
        st.info("Nothing to edit yet — run the pipeline first.")
    else:
        content = version["content"]
        st.caption(f"Editing v{version['version_no']}. Every save creates a new version; nothing is overwritten.")
        for sec in content["sections"]:
            with st.expander(f"{sec['id']} · {sec['type']} · {sec['heading']}"):
                key = f"sec_{version['version_no']}_{sec['id']}"
                text = st.text_area("Markdown (keep [S#] citations after facts)", sec["content_md"], height=260, key=key)
                if st.button("💾 Save section", key=f"save_{key}"):
                    saved = api("PUT", f"/lessons/{lesson_id}/content",
                                json={"sections": {sec["id"]: {"content_md": text}}})
                    if saved is not None:
                        st.success(f"Saved ✓ — {saved.json()['message']}")
                        time.sleep(1)
                        st.rerun()
        st.markdown("##### Knowledge check")
        for n, q in enumerate(content.get("knowledge_check", [])):
            with st.expander(f"Q{n + 1}. {q['q'][:90]}"):
                key = f"quiz_{version['version_no']}_{n}"
                question = st.text_area("Question", q["q"], key=f"{key}_q")
                options = [st.text_input(f"Option {i + 1}", opt, key=f"{key}_o{i}") for i, opt in enumerate(q["options"])]
                answer_index = q["options"].index(q["answer"]) if q["answer"] in q["options"] else 0
                answer = st.selectbox("Correct answer", options, index=answer_index, key=f"{key}_a")
                explanation = st.text_area("Explanation (cite [S#])", q["explanation"], key=f"{key}_e")
                if st.button("💾 Save question", key=f"{key}_save"):
                    item = {"q": question, "options": options, "answer": answer, "explanation": explanation,
                            "outcome": q["outcome"]}
                    saved = api("PUT", f"/lessons/{lesson_id}/content", json={"quiz": {str(n): item}})
                    if saved is not None:
                        st.success(f"Saved ✓ — {saved.json()['message']}")
                        time.sleep(1)
                        st.rerun()
        st.markdown("##### Version history")
        versions = get_json(f"/lessons/{lesson_id}/versions", [])
        st.dataframe(pd.DataFrame([{"Version": f"v{v['version_no']}", "Author": v["author"], "Note": v["note"],
                                    "Created": v["created_at"]} for v in versions]),
                     hide_index=True, use_container_width=True)
        older = [v["version_no"] for v in versions[1:]]
        if older:
            n = st.selectbox("Restore an older version", older, format_func=lambda x: f"v{x}")
            if st.button(f"Restore v{n} as a new version"):
                restored = api("POST", f"/lessons/{lesson_id}/versions/{n}/restore")
                if restored is not None:
                    st.success(restored.json()["message"])
                    time.sleep(1)
                    st.rerun()

# ---------------------------------------------------------------------------
# Preview + Export
# ---------------------------------------------------------------------------

with tabs[6]:
    if not version:
        st.info("No lesson to preview yet.")
    else:
        st.caption(f"v{version['version_no']} as a learner sees it, with references.")
        st.markdown(version["markdown"])

with tabs[7]:
    if not version:
        st.info("Nothing to export yet.")
    else:
        st.write("ZIP with lesson.md, lesson.json, references.md, qc1_factual_report.md/.json, "
                 "qc2_instructional_report.md/.json.")
        exported = api("GET", f"/lessons/{lesson_id}/export", quiet=True)
        if exported is not None:
            st.download_button("⬇ Download ZIP", exported.content, file_name=f"lesson-{lesson_id}.zip",
                               mime="application/zip", type="primary")
            st.caption("Files: " + exported.headers.get("X-Export-Files", "").replace(",", ", "))
        else:
            st.error("Export failed — check that the backend is running.")

if running:
    time.sleep(3)
    st.rerun()
