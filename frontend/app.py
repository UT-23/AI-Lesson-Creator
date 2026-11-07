"""Instructor UI (Streamlit). Stateless: every view reads from the FastAPI backend, which keeps all state in SQLite.

Run (from the repo root, backend already running on :8000):
    backend\\.venv\\Scripts\\streamlit run frontend\\app.py
"""

import os
import time

import httpx
import pandas as pd
import streamlit as st

API = os.environ.get("LESSON_API", "http://localhost:8000")
STATUS_ICON = {"pending": "⚪", "running": "🔵", "done": "🟢", "failed": "🔴", "skipped": "🟠"}
SEVERITY_ICON = {"critical": "🔴", "major": "🟠", "minor": "🟡"}
TIER_LABEL = {1: "Tier 1 · standard/official", 2: "Tier 2 · academic/publisher", 3: "Tier 3 · known site",
              4: "Tier 4 · blog/unknown"}

st.set_page_config(page_title="AI Lesson Creator", layout="wide")


def api(method: str, path: str, **kwargs):  # type: ignore[no-untyped-def]
    """Call the backend; show a readable error instead of a stack trace."""
    try:
        resp = httpx.request(method, f"{API}{path}", timeout=kwargs.pop("timeout", 180), **kwargs)
    except httpx.HTTPError as err:
        st.error(f"Cannot reach the backend at {API}: {err}")
        return None
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        st.error(f"{resp.status_code}: {detail}")
        return None
    return resp


# ---------------------------------------------------------------------------
# Sidebar: new lesson + lesson picker
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("New lesson")
    with st.form("new_lesson", clear_on_submit=False):
        title = st.text_input("Lesson title", placeholder="HTTP Requests and Responses")
        objective = st.text_area("Learning objective", placeholder="Explain GET and POST methods and ...")
        submitted = st.form_submit_button("Create and run")
    if submitted:
        problems = []
        if len(title.strip()) < 3:
            problems.append("Title is required (at least 3 characters).")
        if len(objective.strip()) < 15:
            problems.append("Learning objective is required (at least 15 characters).")
        for p in problems:
            st.error(p)
        if not problems:
            created = api("POST", "/lessons", json={"title": title, "objective": objective})
            if created is not None:
                lesson_id = created.json()["id"]
                if api("POST", f"/lessons/{lesson_id}/run") is not None:
                    st.session_state["lesson_id"] = lesson_id
                    st.success(f"Lesson {lesson_id} created; pipeline started.")

    st.header("Lessons")
    listed = api("GET", "/lessons")
    lessons = listed.json() if listed is not None else []
    if lessons:
        options = {f"#{l['id']} {l['title']} ({l['status']})": l["id"] for l in lessons}
        ids = list(options.values())
        current = st.session_state.get("lesson_id", ids[0])
        index = ids.index(current) if current in ids else 0
        choice = st.selectbox("Open lesson", list(options), index=index)
        st.session_state["lesson_id"] = options[choice]
    st.caption(f"Backend: {API}")

lesson_id = st.session_state.get("lesson_id")
if not lesson_id:
    st.title("AI Lesson Creator")
    st.info("Create a lesson in the sidebar to start.")
    st.stop()

data_resp = api("GET", f"/lessons/{lesson_id}")
if data_resp is None:
    st.stop()
data = data_resp.json()
lesson, version = data["lesson"], data["version"]
st.title(f"#{lesson['id']} {lesson['title']}")
st.caption(lesson["objective"])

tabs = st.tabs(["Pipeline", "Edit", "Sources", "QC1 · Factual", "QC2 · Instructional", "Preview", "Export"])

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

with tabs[0]:
    steps_resp = api("GET", f"/lessons/{lesson_id}/steps")
    steps = steps_resp.json() if steps_resp is not None else []
    running = any(s["status"] == "running" for s in steps) or lesson["status"] == "running"
    top = st.columns([1, 1, 4])
    if top[0].button("Run / resume", disabled=running):
        if api("POST", f"/lessons/{lesson_id}/run") is not None:
            st.rerun()
    if top[1].button("Refresh"):
        st.rerun()
    auto = top[2].toggle("Auto-refresh while running", value=running)
    st.write(f"Lesson status: **{lesson['status']}**")
    for s in steps:
        cols = st.columns([3, 2, 6, 1])
        cols[0].write(f"{STATUS_ICON.get(s['status'], '')} `{s['name']}`")
        cols[1].write(f"{s['status']} (attempt {s['attempt']})")
        if s["error"]:
            cols[2].error(s["error"])
        if s["status"] in ("failed", "skipped", "done") and cols[3].button("Retry", key=f"retry_{s['name']}",
                                                                           disabled=running):
            if api("POST", f"/lessons/{lesson_id}/steps/{s['name']}/retry") is not None:
                st.rerun()
    gen = data.get("generation") or {}
    if gen.get("model"):
        st.caption(f"Lesson generated by: {gen['model']}")
    for w in gen.get("warnings", []):
        st.warning(w)
    tb = data.get("time_budget")
    if tb:
        st.subheader("Time budget")
        st.progress(min(tb["total_computed_min"] / tb["budget_min"], 1.0),
                    text=f"{tb['total_computed_min']} of {tb['budget_min']} minutes (measured)")
        st.dataframe(pd.DataFrame([{"section": r["id"], "type": r["type"], "heading": r["heading"],
                                    "shown (min)": r["declared_min"], "measured (min)": r["computed_min"],
                                    "flags": "; ".join(r["flags"])} for r in tb["sections"]]),
                     hide_index=True, use_container_width=True)
    if auto and running:
        time.sleep(3)
        st.rerun()

# ---------------------------------------------------------------------------
# Edit (per-section, every save = new version) + version history
# ---------------------------------------------------------------------------

with tabs[1]:
    if not version:
        st.info("No lesson version yet — run the pipeline first.")
    else:
        versions = (api("GET", f"/lessons/{lesson_id}/versions") or httpx.Response(200, json=[])).json()
        labels = [f"v{v['version_no']} · {v['author']} · {v['note'] or ''}" for v in versions]
        st.write(f"Editing the latest version: **v{version['version_no']}** ({version['author']})")
        with st.expander("Version history"):
            pick = st.selectbox("Version", labels) if labels else None
            if pick:
                n = versions[labels.index(pick)]["version_no"]
                if st.button(f"Restore v{n} as a new version"):
                    restored = api("POST", f"/lessons/{lesson_id}/versions/{n}/restore")
                    if restored is not None:
                        st.success(restored.json()["message"])
                        st.rerun()
        for section in version["content"]["sections"]:
            with st.expander(f"{section['id']} · {section['type']} · {section['heading']} (~{section['minutes']} min)"):
                key = f"edit_{version['version_no']}_{section['id']}"
                text = st.text_area("Markdown (keep [S#] citations after facts)", section["content_md"],
                                    height=300, key=key)
                if st.button("Save section", key=f"save_{key}"):
                    saved = api("PUT", f"/lessons/{lesson_id}/content",
                                json={"sections": {section["id"]: {"content_md": text}}})
                    if saved is not None:
                        st.success(f"Saved ✓ — {saved.json()['message']}")
                        time.sleep(0.8)
                        st.rerun()

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

with tabs[2]:
    rows = []
    for s in data["sources"]:
        meta = s.get("metadata_json") or {}
        minutes = round(meta["duration_seconds"] / 60, 1) if meta.get("duration_seconds") else None
        rows.append({"id": s["sid"], "type": s["type"], "tier": TIER_LABEL.get(s["reliability_tier"]),
                     "title": s["title"], "link": s["url"], "publisher/author": s["publisher"],
                     "video min": minutes, "why this tier": s["reliability_reason"]})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                     column_config={"link": st.column_config.LinkColumn("link")})
        for s in data["sources"]:
            vid = (s.get("metadata_json") or {}).get("video_id")
            if vid:
                st.image(f"https://img.youtube.com/vi/{vid}/mqdefault.jpg", width=240,
                         caption=f"[{s['sid']}] {s['title']}")
    else:
        st.info("No sources yet.")


# ---------------------------------------------------------------------------
# QC reports + issue workflow
# ---------------------------------------------------------------------------


def issue_list(report: dict) -> None:  # type: ignore[type-arg]
    for issue in report["issues"]:
        icon = SEVERITY_ICON.get(issue["severity"], "")
        with st.expander(f"{icon} {issue['issue_id']} · {issue['severity']} · {issue['category']} · "
                         f"{issue.get('location') or '-'} · {issue['status']}"):
            st.write(f"**Text:** {issue['claim_or_text']}")
            if issue["evidence"]:
                st.write(f"**Evidence:** {issue['evidence']}")
            if issue["source_ids"]:
                st.write(f"**Sources:** {', '.join(issue['source_ids'])}")
            st.write(f"**Suggestion:** {issue['suggestion']}")
            if issue["status"] != "open":
                continue
            cols = st.columns(2)
            fix_key = f"fix_{issue['id']}"
            if cols[0].button("Preview fix", key=f"prev_{issue['id']}"):
                with st.spinner("Asking the model to rewrite this section…"):
                    fixed = api("POST", f"/qc/issues/{issue['id']}/preview-fix", timeout=300)
                if fixed is not None:
                    st.session_state[fix_key] = fixed.json()
            if cols[1].button("Dismiss", key=f"dis_{issue['id']}"):
                if api("POST", f"/qc/issues/{issue['id']}/dismiss") is not None:
                    st.rerun()
            fix = st.session_state.get(fix_key)
            if fix:
                st.caption(f"Proposed by {fix['model']} for {fix['section_id']}: {fix['change_summary']}")
                added = ", ".join(f"{s} (tier {t})" for s, t in fix.get("citations_added", {}).items()) or "none"
                removed = ", ".join(f"{s} (tier {t})" for s, t in fix.get("citations_removed", {}).items()) or "none"
                st.info(f"Checked against the evidence store — citations added: {added}; removed: {removed}.")
                if fix.get("unchanged"):
                    st.warning("The proposed text is identical to the current section.")
                before, after = st.columns(2)
                before.markdown("**Before**")
                before.code(fix["before"], language="markdown")
                after.markdown("**After**")
                after.code(fix["after"], language="markdown")
                a, b = st.columns(2)
                if a.button("Apply fix (new version)", key=f"apply_{issue['id']}"):
                    applied = api("POST", f"/qc/issues/{issue['id']}/apply",
                                  json={"section_id": fix["section_id"], "content_md": fix["after"]})
                    if applied is not None:
                        st.session_state.pop(fix_key, None)
                        st.success(applied.json()["message"])
                        st.rerun()
                if b.button("Discard proposal", key=f"discard_{issue['id']}"):
                    st.session_state.pop(fix_key, None)
                    st.rerun()


qc_resp = api("GET", f"/lessons/{lesson_id}/qc")
qc = qc_resp.json() if qc_resp is not None else {}

with tabs[3]:
    if st.button("Re-run QC1 on the latest version"):
        if api("POST", f"/lessons/{lesson_id}/qc/factual") is not None:
            st.info("QC1 started — see the Pipeline tab.")
    report = qc.get("factual")
    if not report:
        st.info("No QC1 report yet.")
    else:
        d = report["details"]
        st.metric("Claims supported", f"{report['score']}%")
        st.write(report["summary"])
        st.caption(f"Version v{report['lesson_version_no']} · judge {d.get('model')} · {d.get('method')}")
        st.subheader("Claim table")
        st.dataframe(pd.DataFrame([{"id": c["id"], "where": c["location"], "claim": c["text"],
                                    "cites": ", ".join(c.get("sids", [])), "verdict": c["verdict"],
                                    "evidence quote": c.get("evidence_quote"),
                                    "quote found in source": c.get("quote_verified")} for c in d["claims"]]),
                     hide_index=True, use_container_width=True)
        if d.get("numeric_checks"):
            st.subheader("Numeric checks (recomputed in Python)")
            st.dataframe(pd.DataFrame([{"ok": "✓" if n["ok"] else "✗", "where": n["location"],
                                        "expression": n["expression"], "detail": n["detail"]}
                                       for n in d["numeric_checks"]]), hide_index=True, use_container_width=True)
        st.subheader("Source audit")
        for line in d.get("source_audit", []):
            st.write(f"- {line}")
        st.subheader(f"Issues ({len(report['issues'])})")
        issue_list(report)

with tabs[4]:
    if st.button("Re-run QC2 on the latest version"):
        if api("POST", f"/lessons/{lesson_id}/qc/instructional") is not None:
            st.info("QC2 started — see the Pipeline tab.")
    report = qc.get("instructional")
    if not report:
        st.info("No QC2 report yet.")
    else:
        d = report["details"]
        st.metric("Rubric average", f"{d.get('rubric_average')}/5")
        st.write(report["summary"])
        st.caption(f"Version v{report['lesson_version_no']} · reviewer {d.get('model')}")
        st.subheader("Outcome coverage matrix")

        def cell(c: dict) -> str:  # type: ignore[type-arg]
            return ("✓ " if c["present"] else "✗ ") + ", ".join(c.get("sections", []))

        st.dataframe(pd.DataFrame([{"outcome": r["outcome"], "explanation": cell(r["explanation"]),
                                    "example": cell(r["example"]), "practice": cell(r["practice"]),
                                    "quiz": cell(r["quiz"])} for r in d["coverage_matrix"]]),
                     hide_index=True, use_container_width=True)
        st.subheader("Verb alignment (Bloom)")
        st.dataframe(pd.DataFrame(d.get("verb_alignment", [])), hide_index=True, use_container_width=True)
        st.subheader("Rubric")
        st.dataframe(pd.DataFrame(d.get("rubric", [])), hide_index=True, use_container_width=True)
        tb = d.get("time_budget") or {}
        if tb:
            st.progress(min(tb["total_computed_min"] / tb["budget_min"], 1.0),
                        text=f"Time budget: {tb['total_computed_min']} of {tb['budget_min']} min (measured)")
        st.subheader(f"Issues ({len(report['issues'])})")
        issue_list(report)

# ---------------------------------------------------------------------------
# Preview + export
# ---------------------------------------------------------------------------

with tabs[5]:
    if version:
        st.caption(f"Version v{version['version_no']} as a learner sees it")
        st.markdown(version["markdown"])
    else:
        st.info("No lesson yet.")

with tabs[6]:
    st.write("ZIP with lesson.md, lesson.json, references.md, and both QC reports (.md + .json).")
    if st.button("Build export"):
        exported = api("GET", f"/lessons/{lesson_id}/export")
        if exported is not None:
            st.success("Files: " + exported.headers.get("X-Export-Files", ""))
            st.download_button("Download ZIP", exported.content, file_name=f"lesson-{lesson_id}.zip",
                               mime="application/zip")
