# PROJECT_CONTEXT — AI Lesson Creation Tool

Handoff file: everything needed to continue this project without the original chat.
Every status line is marked **VERIFIED** (checked by a command/test/file read on 2026-11-07) or **ASSUMED** / **UNKNOWN**.
Full original spec: [`docs/SPEC.md`](docs/SPEC.md). Design decisions with reasons: [`DECISIONS.md`](DECISIONS.md). User-facing docs: [`README.md`](README.md).

---

## 1. Assignment

**What:** an AI Lesson Creation Tool, for an **AI Research Intern** hiring task. Input: lesson title + learning objective. Output: a researched, cited lesson that takes ≤ 45 minutes, plus two independent QC audits.

**Requirements**
- **Research** from **websites, books and YouTube videos**.
- **A lesson** completable in **≤ 45 min**, with explanations, worked examples, practice, a knowledge check, **supplementary videos** and a **reference list**.
- **Two separate QC reports:**
  - **QC1** — research & factual accuracy.
  - **QC2** — instructional quality.
- **Instructor workflow:** **review / edit / save**, **apply QC fixes**, **preview**, **export** (lesson + references + both QC reports).
- **Error handling:** empty/invalid inputs, research/AI failures, **retry** of failed steps, **never losing saved work or edits**.
- **Test lessons:**
  - *HTTP Requests and Responses*: explain GET and POST, distinguish 2xx/4xx/5xx.
  - *Simple vs Compound Interest*: calculate both, explain why compound grows faster.

**Evaluation:** workflow functionality · research quality / factual accuracy · QC effectiveness · instructional quality · technical decisions. Functionality and research quality matter more than visual design.

**Submission:**
- A public GitHub repo (https://github.com/UT-23/AI-Lesson-Creator) and a **demo video**.
- The form can be submitted **ONCE**.
- **Deadline:** tonight, **7 Nov 2026 (IST)**; the user's target is ~23:30 IST.

---

## 2. Current status

| Requirement | Status | V/A | Evidence |
| --- | --- | --- | --- |
| Inputs + empty-input validation | DONE | VERIFIED | `POST /lessons` with blank fields → 422 `"Title is required. Learning objective is required."`; `backend/app/schemas.py` (`LessonCreate`) |
| Web research (Tavily) | DONE | VERIFIED | `samples/http/references.md`: 5 web sources; `backend/app/pipeline/research.py` |
| YouTube research | DONE | VERIFIED | 3 videos (HTTP) / 2 videos (interest) in the samples' references |
| Books (Google Books → Open Library) | DONE | VERIFIED | 5 books under "Further reading" in each sample |
| Lesson with citations, videos, references, ≤45 min | DONE | VERIFIED | `scripts/check_sample.py`: every cited `[S#]` listed, 0 grouped citations; measured 28.8 min (HTTP), 23.3 min (interest) |
| QC1 factual report (separate) | DONE | VERIFIED | `samples/*/qc1_factual_report.md/.json` |
| QC2 instructional report (separate) | DONE | VERIFIED | `samples/*/qc2_instructional_report.md/.json`; QC2 prompt never includes QC1 output |
| Edit + save (new version), survives restart | DONE | VERIFIED | `PUT /lessons/{id}/content` → "Saved as version N"; versions persist in `backend/data/lessons.db` across backend restarts |
| Apply QC fix (section **and** quiz item) | DONE | VERIFIED | Lesson 1 v2 (`qc_fix`, section); copy lesson 3 v2 (`qc_fix`, quiz Q4: ₹8,628.79 → ₹8,628.27) |
| Re-run QC on the latest version | DONE | VERIFIED | `POST /lessons/2/qc/factual` → QC1 re-checked v2 |
| Preview | DONE | VERIFIED | `GET /lessons/1/preview` returned the latest version |
| Export ZIP | DONE | VERIFIED | both samples were unpacked from `GET /lessons/{id}/export` (7 files each) |
| Retry of a failed step | DONE | VERIFIED (tests + script path) / ASSUMED (UI button click) | `pytest -k "retry or recovers"` → 6 passed |
| Second test lesson | DONE | VERIFIED | `samples/interest/` |
| Groq fallback after Gemini | DONE | VERIFIED | `"say ok"` to `openai/gpt-oss-120b` → HTTP 200; mocked routing test in `tests/test_reliability.py` |
| Streamlit UI on :8501 | DONE | VERIFIED | `curl localhost:8501/` → 200; Playwright screenshots of all 8 tabs |
| React UI (`web/`) | IN PROGRESS (other tool) | VERIFIED (files exist) / UNKNOWN (runs?) | see §12 |
| Demo video | NOT DONE | ASSUMED | not recorded in this session |
| **Tests** | **124 passed** | VERIFIED | `cd backend; .venv\Scripts\python -m pytest` → `124 passed in 22.87s` |
| **Commit** | `c6ef38c` (before this file was added) | VERIFIED | `git log --oneline -1` |

---

## 3. Architecture

```
 Streamlit UI (frontend/app.py)      React UI (web/, in progress)
            └──────────── HTTP ────────────┘
                           ▼
 FastAPI (backend/app/main.py, app/api/*) ── SQLite backend/data/lessons.db
                           │ BackgroundTasks
                           ▼
 plan ─► research_web ─────┐
     ├─► research_youtube ─┼─► score_sources ─► generate ─► timebudget
     └─► research_books ───┘                        ├─► qc_factual (QC1)
                                                    └─► qc_instructional (QC2, never sees QC1)
                           ▼
 instructor: edit (new version) · preview-fix → apply / dismiss · re-run QC · restore · export ZIP
```

**Stack:**
- **Backend:** Python 3.13 venv (spec allows 3.11+), FastAPI, Pydantic v2, SQLModel/SQLite, httpx, tenacity.
- **LLMs and data sources:** google-genai, Groq HTTP API, Tavily, YouTube Data API v3, youtube-transcript-api, Google Books, Open Library.
- **Front ends:** Streamlit + pandas + Altair; React/Vite/Tailwind (`web/`).
- **Tests:** pytest.

| Path | Purpose |
| --- | --- |
| `backend/app/main.py` | FastAPI app, CORS, readable 422s, restart recovery |
| `backend/app/config.py` | settings from `.env` (keys as SecretStr) |
| `backend/app/models.py` | SQLite tables |
| `backend/app/schemas.py` | API + LLM output schemas (LessonDraft/LessonContent, QC schemas) |
| `backend/app/versions.py` | append-only versions, section/quiz replacement |
| `backend/app/api/{lessons,steps,versions,qc}.py` | routers |
| `backend/app/providers/llm.py` | LLM interface, Gemini, `FallbackLLM`, `generate_structured` (validate + repair) |
| `backend/app/providers/groq.py` | Groq provider (last resort, 413 trim-once) |
| `backend/app/providers/{web,youtube,books}.py` | Tavily / YouTube / Books providers |
| `backend/app/providers/fakes.py` | fakes for tests and `DEMO_OFFLINE=1` |
| `backend/app/pipeline/orchestrator.py` | step state machine, dependencies, retry/resume |
| `backend/app/pipeline/{plan,research,passages,sources}.py` | planning, research, passage selection, tiers |
| `backend/app/pipeline/{generate,render,timebudget}.py` | lesson generation, Markdown, 45-min calculator |
| `backend/app/pipeline/{qc_factual,qc_instructional,numeric,qc_store}.py` | QC1, QC2, Python recomputation, report storage |
| `backend/app/pipeline/apply_fix.py` | one-section / one-quiz-item rewrite previews |
| `backend/app/export/{exporter,reports}.py` | ZIP bundle, QC report Markdown |
| `backend/scripts/` | `check_models.py`, `run_lesson.py`, `try_research.py`, `make_samples.py`, `check_sample.py`, `copy_lesson.py` |
| `frontend/app.py` | Streamlit instructor UI |
| `samples/{http,interest}/` | exported outputs of both test lessons |

---

## 4. How to run (Windows PowerShell, repo root)

```powershell
py -3.13 -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt -r frontend\requirements.txt
copy .env.example .env      # then fill in the values
```

Start the backend in terminal 1, on :8000:

```powershell
cd backend; .venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Start the Streamlit UI in terminal 2, on :8501 (open http://localhost:8501/?lesson=2):

```powershell
backend\.venv\Scripts\streamlit run frontend\app.py
```

React UI (`web/`): UNKNOWN whether it runs. `web/package.json` defines `npm install` then `npm run dev` (port 5173), and `node_modules` is not installed (VERIFIED).

Tests (no network; all providers are faked):

```powershell
cd backend; .venv\Scripts\python -m pytest
```

Check which models answer for your key (one tiny call each):

```powershell
cd backend; .venv\Scripts\python scripts\check_models.py gemini-3.5-flash-lite gemini-3.1-flash-lite
```

| Env var (`.env.example`) | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Gemini (generation, QC, research judgements) — required |
| `TAVILY_API_KEY` | web search + extract — required |
| `YOUTUBE_API_KEY` | YouTube Data API v3 — optional (step warns without it) |
| `GOOGLE_BOOKS_API_KEY` | Google Books — optional (keyless works; Open Library fallback) |
| `GEN_MODEL` / `QC_MODEL` | preferred Gemini models for generation / QC |
| `LLM_FALLBACK_MODELS` | comma-separated Gemini models tried next |
| `GROQ_API_KEY` / `GROQ_MODEL` | Groq last resort (verified model: `openai/gpt-oss-120b`) |
| `DEMO_OFFLINE` | `1` = fake providers, no keys needed |

> VERIFIED: the user's `.env` has `GEN_MODEL=gemini-3.6-flash` and `QC_MODEL=gemini-3.5-flash-lite`. `GROQ_API_KEY` is set, but `GROQ_MODEL` and `LLM_FALLBACK_MODELS` are **not** in `.env`. The running backend gets them as process env vars, started with:
> `LLM_FALLBACK_MODELS=gemini-3.5-flash-lite,gemini-3.1-flash-lite GROQ_MODEL=openai/gpt-oss-120b`.

---

## 5. API (VERIFIED from `/openapi.json`)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | liveness + offline flag |
| GET | `/lessons` | list lessons (newest first) |
| POST | `/lessons` | create lesson (422 on empty/short input) |
| GET | `/lessons/{id}` | latest version, sources, generation info, time budget, live measured time |
| POST | `/lessons/{id}/run` | run / resume the pipeline (background) |
| GET | `/lessons/{id}/steps` | step statuses (`?include_output=true` for outputs) |
| POST | `/lessons/{id}/steps/{name}/retry` | re-run a step + its dependents |
| PUT | `/lessons/{id}/content` | instructor edit of sections and/or quiz items → new version |
| GET | `/lessons/{id}/preview` | rendered Markdown of the latest version |
| GET | `/lessons/{id}/export` | ZIP: lesson.md/json, references.md, QC1 + QC2 .md/.json |
| GET | `/lessons/{id}/versions` | version history |
| GET | `/lessons/{id}/versions/{n}` | one version |
| POST | `/lessons/{id}/versions/{n}/restore` | restore as a new version |
| GET | `/lessons/{id}/qc` | latest QC1 + QC2 reports with issues |
| POST | `/lessons/{id}/qc/{factual\|instructional}` | re-run one QC layer on the latest version |
| POST | `/qc/issues/{issue_id}/preview-fix` | propose a rewrite of one section or quiz item (before/after) |
| POST | `/qc/issues/{issue_id}/apply` | accept → new version (`qc_fix`), issue → applied |
| POST | `/qc/issues/{issue_id}/dismiss` | mark issue dismissed |

---

## 6. LLM routing (as implemented, `backend/app/providers/__init__.py`)

- **Chains:** each role is a `FallbackLLM`: the preferred Gemini model, then each model in `LLM_FALLBACK_MODELS` (deduplicated), then **Groq** if `GROQ_API_KEY` and `GROQ_MODEL` are set.
  - **Generation and apply-fix:** chain starts at `GEN_MODEL`.
  - **QC1, QC2 and research judgements** (video relevance, book rating, domain tiers): chain starts at `QC_MODEL`. QC moves the generator's model to the end of its chain, so a different model judges.
- **Failover:** on **429 / RESOURCE_EXHAUSTED / 503 / 504 / timeout / 404 model / too-large**, the next model is tried **immediately**, with one attempt per model when a fallback list is set. No backoff loops.
- **Groq 413 / context length:** the prompt is trimmed once (head 70% + tail 30% of ~24k characters; the best evidence comes first) and retried once.
- **Recorded:** every output stores `provider:model` (e.g. `gemini:gemini-3.1-flash-lite`) in the version note, the generate step output, and QC `details.model`. The UI header shows the generator, QC1 and QC2 models.
- **Model checks on 2026-11-07 (VERIFIED):**

  | Model | Result |
  | --- | --- |
  | `gemini-3.5-flash-lite` | OK |
  | `gemini-3.1-flash-lite` | OK |
  | `gemini-3.8-flash` | 504 even for "say ok" |
  | `gemini-3.6-flash` | intermittent 429 |
  | Groq `openai/gpt-oss-120b` | OK |

- **Per-call timeout:** 120 s (`GEMINI_TIMEOUT_S`).

---

## 7. QC design

**QC1 — factual (`pipeline/qc_factual.py`)**
1. **Claims extracted in code:** every sentence or table row carrying `[S#]`, plus factual-looking uncited sentences ("uncited").
2. **One batched judging call:** each claim is judged against the passages of its cited sources (supported / partial / unsupported / contradicted) with an evidence quote. The same call lists contradictions between sections and quiz answers.
3. **Quotes verified in code:** a "supported" verdict whose quote isn't found verbatim in the source is downgraded to partial.
4. **Source audit in code:** key claims resting only on tier-4 sources, over-reliance on one source, outcomes with no supported evidence.
5. **Numbers recomputed in Python (`pipeline/numeric.py`):**
   - every `a op b = c` chain (LaTeX, `≈`, implicit multiplication), and
   - every worked problem as a whole: P, r, t, n are bound, simple and compound results recomputed, and any stated money result that matches none is flagged.
   - ₹ / Rs / INR, £, $ and € are parsed, as is Indian digit grouping (`1,23,456.50`).
6. **Score:** % of claims supported.

**QC2 — instructional (`pipeline/qc_instructional.py`)**
- **One call in a fresh context** produces:
  - an **outcome × explanation/example/practice/quiz coverage matrix**,
  - **Bloom verb alignment**,
  - a 6-criterion rubric (1–5),
  - issues.
- **Code-owned facts:** code overwrites the quiz column with the real quiz-to-outcome mapping and adds **time-budget** findings (`timebudget.py`).
- **Score:** rubric average × 20.

**Why independent:** separate prompts and calls; QC2 never receives QC1 output; and QC prefers a different model from the generator.

---

## 8. Data model (`backend/app/models.py`)

| Table | Holds |
| --- | --- |
| `Lesson` | title, objective, status |
| `PipelineStep` | per step: status, attempt, error, last **successful** output |
| `Source` | S1..Sn per lesson, type, tier + reason, excerpt, metadata |
| `LessonVersion` | content_json + content_md, author (`ai` / `instructor` / `qc_fix`), note |
| `QCReport` / `QCIssue` | report per layer + issues (status open / applied / dismissed) |
| `ProviderCache` | successful API responses (retries cost no credits) |

**Guarantees:**
- Versions, QC reports and sources are **append-only**: an edit, fix, regeneration or restore is always a new version.
- Source ids stay stable across re-runs.
- A step's writes commit atomically with its status.
- A failed step keeps its previous output.
- On restart, interrupted steps become retryable.

---

## 9. Key decisions (`DECISIONS.md`)

| ID | Decision |
| --- | --- |
| D1 | Explicit step dependency map instead of a linear block |
| D2 | YouTube/Books are optional (soft) inputs |
| D3 | A step's DB writes are atomic with its status |
| D4 | Append-only versions/reports/sources; stable source ids |
| D5 | One run per lesson via an atomic claim |
| D6 | Crash/restart recovery on startup |
| D7 | FastAPI BackgroundTasks, no broker |
| D8 | Schema + semantic checks share one repair loop |
| D9 | Video title/URL/duration copied from Source rows |
| D10 | Typed provider errors; only transient kinds retried |
| D11 | Deterministic domain rules for tiers first |
| D12 | Time budget rules |
| D13 | Fakes are visibly fake |
| D14 | Python 3.13 venv |
| D15 | Phase-1 QC skeletons (since replaced) |
| D16 | SQLite response cache on its own connection |
| D17 | Extraction prefers reliable, diverse pages |
| D18 | Cleaned pages; short pages rejected |
| D19 | YouTube duration window; relevance by watching |
| D20 | Research judgements use QC_MODEL |
| D21 | LLM tiers only for unknown domains |
| D22 | Books: Google Books → Open Library → LLM rating |
| D23 | Missing YouTube key = warning; Gemini/Tavily required |
| D24 | Gemini error mapping |
| D25 | Long pages → most relevant passages, not truncation |
| D26 | Navigation filter keeps single-link lines |
| D27 | Video language checked twice in code |
| D28 | Near-duplicate / self-declared outdated pages handled |
| D29 | Prompt versions in cache keys |
| D30 | Books rated against a rubric |
| D31 | Planner must target authoritative sources |
| D32 | Model writes LessonDraft; code builds LessonContent |
| D33 | Books are further reading, never evidence |
| D34 | Hard vs soft checks on the lesson |
| D35 | Learners see measured minutes |
| D36 | Grouped citations parsed and normalised |
| D37 | Per-tier prompt budget |
| D38 | Model fallback chain instead of retry loops |
| D39 | A failed repair call never discards a valid draft |
| D40 | QC1 = claims in code + one judging call + verification in code |
| D41 | QC2 one call, fresh context, code-owned facts |
| D42 | Apply-fix rewrites one section; saved only on accept |
| D43 | Streamlit instead of React (deadline) |
| D44 | QC2 doesn't wait for the timebudget step |

Later changes, not yet in DECISIONS.md: Groq last-resort provider, quiz-item fixes, the whole-problem numeric check, and rupee parsing.

---

## 10. Known issues and limitations

- **Books are metadata only:** they are never cited, only listed under "Further reading".
- **Free-tier rate limits:**
  - `gemini-3.6-flash` gave intermittent 429s and `gemini-3.8-flash` gave 504s. Once, a 429 was reported as a *daily* quota but the model recovered 2 minutes later.
  - Video relevance checks by watching cost many tokens.
- **No PDF/DOCX export:** pandoc is not installed (VERIFIED: `which pandoc` → not found). Markdown/JSON export works.
- **Lessons run short:** measured 23–29 min, below the 35–45 target (stored as a warning).
- **QC1's judge model is lenient and non-deterministic:** one run marked every claim supported, and re-runs changed the supported count (37 → 29 → 35 → 39). Quote verification and the Python arithmetic are the reliable parts.
- **HTTP sample citation and source quality:**
  - "GET is safe/idempotent" is not stated in its cited excerpts.
  - Cited S6 is the obsolete RFC 7231 (hosted on law.resource.org) yet tiered 1.
- **Fix summaries can be wrong:** a model's summary claimed a tier-1 source when it was tier 4. The UI shows real tiers from the evidence store.
- **No authentication;** the API is for local use only.

---

## 11. Demo plan

**The deliberate error (keep it until the video is recorded):**
- **Where:** lesson **#2** (interest), latest version **v2** (₹).
- **What:** the 0.3% compound example states **₹8,628.79**; the correct value is 8500 × 1.003⁵ = **₹8,628.27**.
- **QC1 issues** (VERIFIED open):

  | Issue | Location | What it flags |
  | --- | --- | --- |
  | **F-3** | `sec-3` | the final answer |
  | **F-4** | `quiz-Q4` | the keyed quiz answer |
  | F-1 | `sec-3` | (1.003)^5 ≈ 1.50896 |
  | F-2 | `sec-3` | 8500 × 1.008985 = 8,628.79 |

**Fix it live:**
1. Open http://localhost:8501/?lesson=2 and go to the **QC1** tab. Show the "Calculation errors" table.
2. Expand **F-3** → **Preview fix** → check the before/after → **Apply (new version)**.
3. Expand **F-4** → **Preview fix** (rewrites only quiz Q4) → **Apply**.
4. Click **Re-run QC1 on the latest version** and wait for the Pipeline tab to show done. F-3 and F-4 should be gone (ASSUMED until run).
5. **Preview** tab: show ₹8,628.27. **Export** tab: download the ZIP.

**Demo video outline:**
1. New lesson "HTTP Requests and Responses", with live pipeline statuses.
2. Sources tab (tiers, links, video durations).
3. Lesson tab (citations, video cards).
4. QC1: claim verdicts, then switch to lesson 2 to show the calculation catch.
5. QC2: coverage matrix and time-budget chart.
6. Apply the fix and re-run QC.
7. Edit a section (saved as a new version) and restore from history.
8. Preview, then Export.
9. Error handling: an empty-input 422, a Retry button, Groq/Gemini fallback (explained).
10. Second lesson (interest).
11. Stack and DECISIONS.md.

---

## 12. Frontend status

- **Streamlit (`frontend/app.py`): complete — the demo fallback.** VERIFIED by Playwright screenshots of every tab.
  - **Header:** version, measured time, and generator/QC1/QC2 `provider:model`.
  - **Tabs:** Pipeline, Lesson, Sources, QC1, QC2, Edit (sections + quiz + version history), Preview, Export.
- **`web/` (React + Vite + Tailwind, "lesson-studio-web"): being built in another tool.** Read-only snapshot, VERIFIED with `find web -type f` at 22:32 IST:
  - **Root files:** `index.html`, `package.json`, `vite.config.ts`, `tailwind.config.js`, `postcss.config.js`, `tsconfig.json`.
  - **`src/`:** `App.tsx`, `main.tsx`, `api/client.ts`, `types/api.ts`, `utils/diff.ts`, `utils/zipInspect.ts`, and components `HomeScreen`, `CoursePlayerScreen`, `DottedGlobeScreen`, `ExportModal`, `FixDiffModal`, `MarkdownWithCitations`, `QualityReviewDrawer`.
  - **Not verified:** `node_modules` is absent, so it has not been installed or run here. Whether it builds or matches the API is UNKNOWN.
  - **Git:** part of `web/` was committed in `7204fb6`; newer files (e.g. `web/src/components/`) were untracked at the time of writing.

---

## 13. Rules for any AI working on this repo

1. **Anti-hallucination:**
   - Write only what you verified in your own session, from code, git, the DB, tests or running servers, and show the commands.
   - Mark claims VERIFIED / ASSUMED / UNKNOWN.
   - Paste errors verbatim.
   - Read a file before editing or describing it.
   - Never print key values; env var **names** only.
2. **Never commit keys.** Before every commit, run `git grep --cached -nE "AIza[0-9A-Za-z_-]{20,}|tvly-[0-9A-Za-z_-]{10,}|gsk_[0-9A-Za-z]{20,}"`; it must print nothing. `.env`, `backend/.venv/` and `backend/data/` are git-ignored.
3. **Don't break the backend API contract** (§5): the Streamlit UI and `web/` both depend on it.
4. **Keep the lesson #2 demo error** (₹8,628.79; F-3 / F-4) until the demo video is recorded. Rehearse on a copy (`backend/scripts/copy_lesson.py 2`).
5. **Don't touch `web/`** unless you are the tool building it. Stage explicit paths, never `git add -A`.
6. **Commit and push after each change.** Commit messages carry no tool attribution lines.

---

## 14. Next steps (priority order)

1. **Record the demo video** using §11; fix F-3/F-4 live.
2. **Submit the form (once only):** repo URL + video link.
3. **Optional** (only if time allows, after the video): add `GROQ_MODEL` and `LLM_FALLBACK_MODELS` to your own `.env`, so a fresh backend start doesn't depend on process env vars.
4. **Optional:** add D45+ to DECISIONS.md (Groq fallback, quiz fixes, whole-problem numeric check, rupee parsing).
5. **Optional:** finish/verify `web/` against the API (`npm install`, `npm run dev`, point it at :8000).

---

## 15. Last updated

2026-11-07 22:32 IST, at commit `c6ef38c` (before this file's own commit; see `git log` for the latest).
