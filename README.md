# AI Lesson Creation Tool

Give it a lesson title and a learning objective. It researches the topic (web, YouTube, books), writes a cited lesson that fits in 45 minutes, and runs two independent QC audits: QC1 for research and factual accuracy, QC2 for instructional quality. An instructor can then edit, apply QC fixes, preview and export.

- Spec: [`CLAUDE.md`](CLAUDE.md)
- Design decisions, each with alternatives and reasons: [`DECISIONS.md`](DECISIONS.md)
- Sample outputs for both test lessons: [`samples/`](samples/)

---

## Setup (Windows, PowerShell)

Requires Python 3.11+ (developed on 3.13). Run from the repo root.

```powershell
py -3.13 -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt -r frontend\requirements.txt
copy .env.example .env
```

Then edit `.env`:

| Variable | Required | Notes |
| --- | --- | --- |
| `GEMINI_API_KEY` | yes | https://aistudio.google.com/apikey |
| `TAVILY_API_KEY` | yes | https://app.tavily.com (free: 1,000 credits/month) |
| `GEN_MODEL`, `QC_MODEL` | yes | Gemini model ids; QC should differ from generation |
| `LLM_FALLBACK_MODELS` | recommended | e.g. `gemini-3.5-flash-lite,gemini-3.1-flash-lite`; check yours with `scripts\check_models.py` |
| `YOUTUBE_API_KEY` | optional | without it the YouTube step warns and the lesson still completes |
| `GOOGLE_BOOKS_API_KEY` | optional | Google Books works keyless; Open Library is the fallback |

Check which models currently answer for your key (one tiny request each):

```powershell
cd backend; .venv\Scripts\python scripts\check_models.py gemini-3.5-flash-lite gemini-3.1-flash-lite; cd ..
```

## Run

Start the backend in terminal 1:

```powershell
cd backend; .venv\Scripts\python -m uvicorn app.main:app --port 8000
```

Start the UI in terminal 2, then open http://localhost:8501:

```powershell
backend\.venv\Scripts\streamlit run frontend\app.py
```

API docs: http://localhost:8000/docs. Offline demo with no keys: set `DEMO_OFFLINE=1` (every fake output is marked `[FAKE]`).

Tests (no network; all providers are faked):

```powershell
cd backend; .venv\Scripts\python -m pytest
```

---

## Architecture

```
 Streamlit UI (frontend/app.py) — stateless, only calls the API
        │ HTTP
        ▼
 FastAPI (app/main.py, app/api/*) ── SQLite (lessons, steps, sources, versions, QC reports/issues, response cache)
        │ BackgroundTasks
        ▼
 Orchestrator (pipeline/orchestrator.py) — step state machine with explicit dependencies
   plan ─► research_web ──────┐
       ├─► research_youtube ──┼─► score_sources ─► generate ─► timebudget
       └─► research_books ────┘                        ├─► qc_factual        (QC1)
                                                       └─► qc_instructional  (QC2, never sees QC1)
        │
        ▼
 Providers (app/providers/*) — every external call goes through an interface (fakes for tests)
   Gemini (FallbackLLM chain) · Tavily search/extract · YouTube Data API v3 + transcripts · Google Books → Open Library
```

## How it works

**Plan.** Gemini splits the objective into atomic outcomes, keeping the objective's verbs ("explain", "distinguish", "calculate"). It also writes 4–8 web queries (at least two aimed at authoritative sources) and 1–2 book-catalogue queries.

**Research.**
- **Web:** a Tavily search per query, results ordered round-robin across queries, then reliable sites preferred (at most 2 pages per site) and the top 8 extracted. Pages are cleaned of navigation and images. Long pages (RFC 9110 is ~450k characters) are reduced in code to their most relevant passages, with section headings and `[…]` gap markers. Near-duplicate pages and pages that call themselves outdated are filtered or demoted.
- **YouTube:** one `search.list` and one `videos.list` per lesson. Videos under 2 or over 15 minutes, or in a language other than English, are dropped. Relevance is checked by Gemini watching the video, falling back to the transcript, then to metadata only.
- **Books:** Google Books, falling back to Open Library; the QC model rates each candidate 0–10 and keeps 7+.
- **Cache:** every successful API response is cached in SQLite, so retries never re-spend credits.

**Source scoring.** Tiers 1–4 come from domain and channel rules (RFC/MDN/.gov = 1, universities/publishers = 2, well-known education sites = 3, blogs/forums = 4). Unknown sites are tiered by the QC model, labelled "LLM-assessed". Source ids S1..Sn stay stable across re-runs.

**Citations.**
- The model may only cite web/video sources from this research run. Unknown ids are fed back to it until fixed, and the step fails if they persist.
- Grouped citations like `[S3, S5]` are normalised to `[S3], [S5]`.
- The References list is rendered from stored Source rows, never from model text.
- Books are never cited, because only their descriptions were read; they appear under "Further reading" with that disclaimer.
- Video titles, URLs and durations are copied from the YouTube API data, not from the model.

**Time budget (no LLM).** Reading time is words ÷ 200 wpm. Videos count at their real duration (or `watch_segment` length). Activities count at their stated minutes; quizzes at least 0.5 min per question. Learners see these measured minutes, not the model's guesses. Generation targets 35–45 minutes, and a lesson under 25 minutes gets one repair call.

**QC1 (factual).**
1. Claims are extracted in code: each sentence or table row with a citation, plus factual-looking uncited sentences.
2. One call to the QC model judges all claims against their cited excerpts (supported / partially / unsupported / contradicted) with a quoted evidence span, and lists contradictions between sections and quiz answers.
3. Code verifies each quote really appears in the source; a "supported" verdict with an unverifiable quote is downgraded to partially_supported.
4. Code then audits sources (tier-4-only key claims, over-reliance on one source), finds outcomes with no supported evidence, and **recomputes every calculation in Python** (`pipeline/numeric.py`).

Score = % of claims supported.

**QC2 (instructional).** One separate call that never sees QC1's output produces:
- an outcome × {explanation, example, practice, quiz} coverage matrix with section references,
- Bloom verb alignment ("distinguish" needs a classification task, not definitions),
- a 6-criterion rubric (1–5) and issues.

Code replaces the quiz column with the real quiz-to-outcome mapping and adds the time-budget findings. Score = rubric average × 20. QC uses a different model from the generator when the chain allows it, and each report records which model judged it.

**Instructor workflow.**
- **Edit:** edit a section; every save is a new version.
- **History:** browse versions and restore any of them.
- **Fixes:** on a QC issue, **Preview fix** rewrites only that section and shows before/after; **Apply** saves it as a new version (author `qc_fix`), **Dismiss** marks the issue dismissed.
- **QC:** re-run either QC layer on the latest version.
- **Export:** a ZIP containing `lesson.md`, `lesson.json`, `references.md`, `qc1_factual_report.md/.json` and `qc2_instructional_report.md/.json`, plus PDF/DOCX if `pandoc` is installed.

## Error handling

- **Empty or invalid input** is rejected in the UI and by the API (422 with readable messages, e.g. "Title is required.").
- **Gemini failures** (429 / 503 / 504 / timeout / daily quota) move to the next model in `LLM_FALLBACK_MODELS` immediately. The per-call timeout is 120 s. Errors are typed and readable, for example "Daily Gemini quota for model 'gemini-3.6-flash' is used up (429 RESOURCE_EXHAUSTED)…", and API keys are scrubbed from messages.
- **Research failures:** each step can fail independently. YouTube or Books failing gives a warning, and the lesson still completes. Web research failing blocks generation, and the UI offers Retry.
- **Malformed LLM JSON** is validated, then retried with the validation error fed back (max 2 repairs), then the step fails cleanly. If a repair call itself fails after a valid draft exists, the valid draft is kept.
- **Nothing is lost:**
  - A failed step keeps its previous output.
  - Every edit, fix and regeneration is a new version.
  - Each step's writes are committed atomically.
  - A server restart marks interrupted steps as failed so they can be retried.

## Manual fact verification

See [Manual fact verification of the samples](#manual-fact-verification-of-the-samples) at the end.

## Limitations

- **Books are metadata only.** Only catalogue details and publisher descriptions are read, so books are never cited as evidence.
- **Free-tier limits.** Daily quotas ran out and `gemini-3.8-flash` timed out on 2026-11-07, so samples were produced with the Flash-Lite fallback chain. Lower-tier models write shorter lessons and judge more leniently.
- **QC1's judge is lenient.** On a real run, the judge model marked every claim "supported"; the code-side verbatim-quote check produced all the partial verdicts. Claim extraction is heuristic (sentence-level), and only the first 90 claims are judged per call.
- **Arithmetic checking** covers explicit `a op b = c` chains. It can't recompute values written only in prose.
- **YouTube relevance by watching** costs many tokens; transcripts work locally but are often blocked from cloud IPs.
- **No PDF/DOCX export** on this machine, because pandoc isn't installed (Markdown always works).
- **Local tool:** the UI is Streamlit rather than React (deadline), and the API has no authentication.

## Acknowledgments

- **Libraries:** FastAPI, Pydantic, pydantic-settings, SQLModel/SQLAlchemy, httpx, tenacity, google-genai, youtube-transcript-api, Streamlit, pandas, pytest, uvicorn.
- **APIs:** Google Gemini API, Tavily Search/Extract, YouTube Data API v3, Google Books API, Open Library.
- **AI assistance:** this project was designed and written with Claude Code (Anthropic) under the author's direction and review; architecture decisions and the reasons for them are in `DECISIONS.md`.

---

## Manual fact verification of the samples

Checked by hand on 2026-11-07 against the exported files in `samples/`. **VERIFIED** = recomputed in Python or compared against source text retrieved in this project. **ASSUMED** = checked from general knowledge only.

### `samples/interest` (generated by gemini-3.5-flash-lite, QC by gemini-3.1-flash-lite)

| Where | Lesson says | Independent check (Python) | Result |
| --- | --- | --- | --- |
| sec-3 simple, £1,500 @ 5% × 4 y | £1,800 | 1500 × (1 + 0.05 × 4) = 1,800 | ✓ VERIFIED |
| sec-3 simple, $10,000 @ 2% × 1 y | interest $200, total $10,200 | 10000 × 0.02 × 1 = 200 | ✓ VERIFIED |
| sec-3 compound, £8,500 @ 0.3% × 5 y, step 4 | (1.003)^5 ≈ 1.50896 | 1.003^5 = 1.0150903 | ✗ **wrong** — QC1 flagged (critical) |
| sec-3 same example, step 5 | 8500 × 1.008985 = 8,628.79 | 8500 × 1.008985 = 8,576.37 | ✗ **wrong** — QC1 flagged (critical) |
| sec-3 same example, final answer | £8,628.79 | 8500 × 1.003^5 = **£8,628.27** | ✗ **wrong** (prose, not caught by QC1) |
| sec-3 compound, $10,000 @ 5% × 3 y | $11,576.25 | 10000 × 1.05^3 = 11,576.25 | ✓ VERIFIED |
| sec-5 practice: 4500 × 0.04 × 2 | $360 | 360 | ✓ VERIFIED |
| sec-5 practice: 2000 × 0.06 × 0.5 | $60 | 60 | ✓ VERIFIED |
| sec-5 practice: 5000 × 1.0816 | $5,408 | 5000 × 1.04^2 = 5,408 | ✓ VERIFIED |
| sec-5 practice: 2000 × 1.157625 | $2,315.25 | 2000 × 1.05^3 = 2,315.25 | ✓ VERIFIED |
| Quiz Q1 / Q2 / Q3 | $300 / $100 / $11,576.25 | 300 / 100 / 11,576.25 | ✓ VERIFIED |
| Quiz Q4 (keyed answer) | £8,628.79 | £8,628.27 | ✗ **wrong** (same error; prose) |

**Result:** 11 of 12 calculations are right; one worked example and its quiz question carry a wrong figure. QC1's Python recomputation caught two of the three wrong numbers, both raised as critical issues. An instructor would fix the third from the same issue via "Preview fix" or a direct edit. This is exactly why the arithmetic is checked in code rather than trusted.

### `samples/http` (generated by gemini-3.6-flash, QC by gemini-3.5-flash-lite)

| Claim in lesson.md | Check | Result |
| --- | --- | --- |
| GET is *safe* and *idempotent*; POST is *not idempotent* | RFC 9110 §9.2.1/§9.2.2 and §9.3.3 text retrieved in research (§9.3.3 POST excerpt seen in the evidence store) | ✓ VERIFIED (excerpt) |
| "Status codes starting with 2 (2xx) indicate that the request was successfully received, understood, and accepted" | RFC 9110 §15.3 wording | ✓ ASSUMED (from knowledge of the RFC) |
| 4xx = client error; 5xx = server error ("the server is aware that it has erred…") | RFC 9110 §15.6 excerpt retrieved in this project | ✓ VERIFIED (excerpt) |
| `201 Created`, `404 Not Found` meanings | MDN status page excerpt in the evidence store (`200 OK` … `404 Not Found` entries present) | ✓ VERIFIED (excerpt) |
| "Requests using GET … should not contain request content" | RFC 9110 says GET content has *no generally defined semantics* — the lesson states it more strongly | ~ overstated (ASSUMED) |
| References list | every `[S#]` cited in the text appears in References; 0 grouped citations left (`scripts/check_sample.py`) | ✓ VERIFIED |

### What the QC layers reported (from the sample files)
- **HTTP:** QC1 found 72 of 91 claims supported (79%), 18 partial, 1 uncited, 0 contradicted. QC2's rubric average was 4.8/5, with every outcome covered by explanation, example, practice and quiz. Measured time is 28.8 of 45 minutes.
- **Interest (after re-running QC1):** QC1 found 29 of 68 claims supported (43%), 27 partial, 5 unsupported, 7 uncited, with 21/23 calculations correct and 2 flagged critical. QC2's rubric average was 4.8/5 with full coverage. Measured time is 23.3 of 45 minutes, below the 35–45 target, stored as a warning.

## More limitations found during the final runs (VERIFIED)
- **Non-deterministic judge.** Re-running QC1 on the *same* interest lesson moved its count from 37 to 29 supported claims. Treat the score as indicative; the issues list (with verified quotes and Python arithmetic) is the actionable part.
- **Fix summaries can be wrong.** A real `preview-fix` described swapping in "a Tier 1-2 citation" when the new source was tier 4. The preview now shows, from stored data, the tier of every citation added or removed, so the instructor doesn't have to trust the model's summary.
- **429 classification can be wrong.** A 429 was reported as a *daily* quota, yet the same model answered 200 OK two minutes later. Daily vs per-minute is inferred from the error text; the fallback chain handles both the same way.
- **Lessons run short.** Flash-Lite lessons measured 23–29 minutes despite the 35–45 target; this is recorded as a generation warning.
- **Not under version control yet.** This folder is not a git repository. `.env` is in `.gitignore`, and a scan for `AIza…`/`tvly-…` patterns outside `.env` found nothing.
