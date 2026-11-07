# AI Lesson Creation Tool

Give it a lesson title and a learning objective. It researches the topic (web, YouTube, books), writes a cited lesson that fits in 45 minutes, and runs two independent QC audits: QC1 for research and factual accuracy, QC2 for instructional quality. An instructor can then edit, apply QC fixes, preview and export.

- Spec: [`docs/SPEC.md`](docs/SPEC.md)
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
| `GROQ_API_KEY`, `GROQ_MODEL` | optional | last-resort LLM after every Gemini model fails (verified model: `openai/gpt-oss-120b`) |
| `DEMO_OFFLINE` | optional | `1` = fake providers, no keys needed (outputs marked `[FAKE]`) |
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

Start the **Lesson Studio** web frontend (`/web`) in terminal 2, then open http://localhost:5173:

```powershell
cd web
npm install
npm run dev
```

The web app connects to `http://localhost:8000` by default. To point it at a different backend URL, set `VITE_API_URL` before starting Vite (or in `web/.env`):

```powershell
$env:VITE_API_URL="http://localhost:8000"
npm run dev
```

(Legacy Streamlit UI: `backend\.venv\Scripts\streamlit run frontend\app.py` on http://localhost:8501.)

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

- **Libraries:** FastAPI, Pydantic, pydantic-settings, SQLModel/SQLAlchemy, httpx, tenacity, google-genai, youtube-transcript-api, git-filter-repo (maintenance only), Streamlit, pandas, Altair, Playwright (UI screenshots), pytest, uvicorn; web: React, Vite, TypeScript, Tailwind CSS, framer-motion, lucide-react, react-markdown, remark-gfm.
- **APIs:** Google Gemini API, Groq API, Tavily Search/Extract, YouTube Data API v3, Google Books API, Open Library.
- **AI assistance:** AI coding assistants were used for implementation support; design decisions are documented in DECISIONS.md.

---

## Manual fact verification of the samples

Re-checked on 2026-11-07 against the files in `samples/`. **VERIFIED** = recomputed in Python, or the exact wording was found in the stored text of the cited source. **ISSUE** = wrong, or not supported by the cited source's stored text.

### `samples/interest`: lesson v2 (generated by gemini-3.5-flash-lite; £ → ₹ by an instructor edit, figures unchanged; QC by gemini-3.1-flash-lite)

| Where | Lesson says | Independent check (Python) | Result |
| --- | --- | --- | --- |
| sec-3 simple, 1500 @ 5% × 4 y | 1,800 | 1500 × (1 + 0.05 × 4) = 1,800 | VERIFIED |
| sec-3 simple, 10,000 @ 2% × 1 y | interest 200, total 10,200 | 10000 × 0.02 × 1 = 200 | VERIFIED |
| sec-3 compound, ₹8,500 @ 0.3% × 5 y, step 4 | (1.003)^5 ≈ 1.50896 | 1.003^5 = 1.0150903 | **ISSUE** — QC1 F-1 (critical) |
| same example, step 5 | 8500 × 1.008985 = 8,628.79 | = 8,576.37 | **ISSUE** — QC1 F-2 (critical) |
| same example, final answer | ₹8,628.79 | 8500 × 1.003^5 = **₹8,628.27** | **ISSUE** — QC1 F-3 (critical, `wrong_result`) |
| sec-3 compound, 10,000 @ 5% × 3 y | 11,576.25 | 10000 × 1.05^3 = 11,576.25 | VERIFIED |
| sec-5 practice answers | 360 · 60 · 5,408 · 2,315.25 | 4500×0.04×2 · 2000×0.06×0.5 · 5000×1.04² · 2000×1.05³ | VERIFIED |
| Quiz Q1–Q3 | 300 · 100 · 11,576.25 | same | VERIFIED |
| Quiz Q4 keyed answer | ₹8,628.79 | ₹8,628.27 | **ISSUE** — QC1 F-4 (critical, `wrong_result`) |

QC1 now catches **all three** wrong figures in that example and the quiz answer. The whole-problem check (`numeric.check_problem_results`) recomputes each worked problem from its own P, r, t and also reads ₹ / Rs / INR amounts and Indian digit grouping. The error is deliberately left in the sample so it can be fixed live with **Preview fix → Apply**: sec-3 is rewritten as a lesson section and Q4 as a quiz item. A rehearsal on a copy turned ₹8,628.79 into ₹8,628.27 in the options, answer and explanation.

### `samples/http`: lesson v4 = restored v1 (generated by gemini-3.6-flash; QC by gemini-3.5-flash-lite)

Each key fact was searched for in the stored excerpt of the source(s) the lesson cites for it:

| Fact taught | Result | Evidence in cited source |
| --- | --- | --- |
| POST is not idempotent | VERIFIED | S1 (MDN POST): "Successive identical `POST` requests may have additional effects" |
| 2xx = "successfully received, understood, and accepted" | VERIFIED | S6 (RFC 7231 text) |
| 4xx = client error, 5xx = server error | VERIFIED | S6: "4xx (Client Error)…", "5xx (Server Error): The server failed to fulfill an apparently valid request" |
| 201 Created = new resource created | VERIFIED | S6 §6.3.2 |
| 404 Not Found | VERIFIED (weak) | only S15, the key points of a Codecademy video (tier 3) |
| GET is safe | **ISSUE** | true per RFC 9110 §9.2.1, but the stored excerpts of the cited S1/S2/S6 don't state it, so the citation doesn't support it |
| GET is idempotent | **ISSUE** | same: S2 only says methods "can be safe, idempotent, or cacheable" |
| Source quality | **ISSUE** | S6 is RFC 7231, obsoleted by RFC 9110 in 2022, served as a PDF from law.resource.org, yet tiered 1 by the `.gov`-style rule |
| References list | VERIFIED | every cited `[S#]` is listed; 0 grouped citations (`scripts/check_sample.py`) |

A first automated pass marked "GET is safe/idempotent" as VERIFIED. Re-checking showed the regex had matched "get" inside "tar**get**" in text about the QUERY method, so the verdict was corrected to ISSUE.

## More limitations found during the final runs (VERIFIED)
- **Non-deterministic judge.** Re-running QC1 on the *same* interest lesson moved its count from 37 to 29 supported claims. Treat the score as indicative; the issues list (with verified quotes and Python arithmetic) is the actionable part.
- **Fix summaries can be wrong.** A real `preview-fix` described swapping in "a Tier 1-2 citation" when the new source was tier 4. The preview now shows, from stored data, the tier of every citation added or removed, so the instructor doesn't have to trust the model's summary.
- **429 classification can be wrong.** A 429 was reported as a *daily* quota, yet the same model answered 200 OK two minutes later. Daily vs per-minute is inferred from the error text; the fallback chain handles both the same way.
- **Lessons run short.** Flash-Lite lessons measured 23–29 minutes despite the 35–45 target; this is recorded as a generation warning.
- **Groq fallback.** If every Gemini model fails, `GROQ_API_KEY` + `GROQ_MODEL` (verified: `openai/gpt-oss-120b`) answer instead. A Groq 413/token-limit error trims the lowest-ranked evidence once. Each output records `provider:model`.
