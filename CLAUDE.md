# CLAUDE.md — AI Lesson Creation Tool

## What we're building

A locally-running tool that takes a Lesson Title + Learning Objective and:

1. Researches the topic from websites, books, and YouTube videos
2. Generates a structured lesson designed to be completed in ≤ 45 minutes
3. Runs two independent QC layers, each producing its own audit report:
   * QC1 — Research & Factual Accuracy
   * QC2 — Instructional Quality
4. Lets an instructor review, edit, save, apply QC fixes, preview, and export (lesson + references + both QC reports)
5. Handles errors gracefully: empty inputs, research/AI failures, retry of failed steps, never losing saved work or edits

This is a hiring assignment. Evaluation = workflow functionality, research quality/factual accuracy, QC effectiveness, instructional quality, and technical decisions. Functionality and research quality matter more than visual design. The author must be able to explain every part, so keep code readable and log decisions in `DECISIONS.md`.

## Stack (do not change without asking)

* Backend: Python 3.11+, FastAPI, Pydantic v2, SQLite via SQLModel (or SQLAlchemy), `httpx`, `tenacity` for retries
* LLM: Google Gemini via the `google-genai` SDK. Model names come from env vars (`GEN_MODEL`, `QC_MODEL`) — check the current Gemini docs for valid free-tier Flash / Flash-Lite model IDs; do not hardcode. Generation and QC should be able to use different models (independence).
* Web research: Tavily API (search + extract)
* YouTube: YouTube Data API v3 (`search.list` = 100 quota units, `videos.list` = 1 unit). Relevance check via Gemini with the YouTube URL passed as `file_data`, falling back to `youtube-transcript-api` (works locally).
* Books: Google Books API (with key) → fallback to Open Library search API. Books provide metadata + descriptions only; never claim the tool read the full book.
* Frontend: React + Vite + TypeScript, a markdown editor (e.g. `@uiw/react-md-editor`), a diff viewer (e.g. `react-diff-viewer-continued`). Plain, clean UI — no time spent on fancy styling.
* Export: Markdown always; PDF and DOCX via `pandoc` if installed, else `python-docx` / `markdown-pdf` fallbacks. Bundle as a ZIP.
* Tests: pytest with mocked providers. All external calls go through provider interfaces so they can be faked.

## Repo layout

```
/backend
  app/main.py                 FastAPI app, CORS for localhost
  app/config.py               env loading (.env), settings
  app/db.py                   SQLite engine + session
  app/models.py               DB tables
  app/schemas.py              Pydantic request/response + LLM output schemas
  app/providers/
    llm.py                    LLMProvider interface + GeminiProvider (JSON-mode, schema-validated output)
    web.py                    WebSearchProvider + TavilyProvider
    youtube.py                YouTubeProvider (search, durations, relevance check)
    books.py                  BooksProvider (Google Books → Open Library fallback)
    fakes.py                  Fake providers for tests / offline demo
  app/pipeline/
    orchestrator.py           step state machine, resume/retry from failed step
    plan.py                   research planner
    research.py               runs providers, caches results
    sources.py                reliability scoring + evidence store
    generate.py               lesson generation
    timebudget.py             deterministic 45-min calculator (no LLM)
    qc_factual.py             QC1
    qc_instructional.py       QC2
    apply_fix.py              turn a QC suggestion into a section patch
  app/export/exporter.py
  app/api/                    routers: lessons, steps, qc, versions, export
  tests/
/frontend
  src/pages/NewLesson.tsx     inputs + validation
  src/pages/LessonWorkspace.tsx  pipeline status, editor, sources, QC panels, preview, export
  src/components/...
/samples                      exported outputs for the 2 test lessons (committed for reviewers)
README.md  DECISIONS.md  .env.example
```

## Data model (SQLite)

* `Lesson(id, title, objective, status, created_at, updated_at)`
* `PipelineStep(id, lesson_id, name, status[pending|running|done|failed|skipped], attempt, error, output_json, started_at, finished_at)` Steps in order: `plan → research_web → research_youtube → research_books → score_sources → generate → timebudget → qc_factual → qc_instructional`
* `Source(id, lesson_id, sid["S1".."Sn"], type[web|book|video], title, url, publisher/author, reliability_tier[1-4], reliability_reason, excerpt_text, metadata_json)`
* `LessonVersion(id, lesson_id, version_no, content_json, content_md, author[ai|instructor|qc_fix], note, created_at)` — never overwrite; always append a new version
* `QCReport(id, lesson_id, layer[factual|instructional], lesson_version_no, summary, score, created_at)`
* `QCIssue(id, report_id, issue_id, severity[critical|major|minor], category, location(section_id), claim_or_text, evidence, source_ids, suggestion, status[open|applied|dismissed])`

## Lesson schema (LLM structured output, validated by Pydantic)

```json
{
  "title": "...",
  "objective": "...",
  "outcomes": ["atomic outcome 1", "..."],
  "total_minutes": 45,
  "sections": [
    {
      "id": "sec-1",
      "type": "hook|concept|example|activity|video|knowledge_check|summary",
      "heading": "...",
      "minutes": 5,
      "content_md": "Text with inline citations like [S2] after each factual claim.",
      "outcomes_covered": ["outcome 1"]
    }
  ],
  "videos": [{"sid": "S7", "title": "...", "url": "...", "duration_min": 6, "why": "...", "watch_segment": "optional mm:ss–mm:ss"}],
  "knowledge_check": [{"q": "...", "options": ["..."], "answer": "...", "explanation": "...", "outcome": "..."}],
  "references": ["S1", "S2"]
}
```

Rules for generation:

* Every factual claim gets a `[S#]` citation pointing to a real source in the evidence store. No invented sources, no invented URLs.
* Include explanations, worked examples, a practical application/activity, supplementary YouTube videos, and a knowledge check covering every outcome.
* Reference list at the end is rendered from stored `Source` rows, not from LLM text.

## Pipeline details

### plan
LLM decomposes the objective into atomic outcomes (keep the objective's verbs, e.g. "explain", "distinguish") and 4–8 research sub-queries. Store both.

### research_*
* Web: Tavily search per sub-query, then extract full text for the top results. Cache everything in DB so retries don't re-spend credits.
* YouTube: 1–2 `search.list` calls max per lesson, then `videos.list` for durations/channel/stats. Keep 2–4 candidates; prefer < 15 min, educational channels. Verify relevance to the outcomes via Gemini (YouTube URL) or transcript; drop irrelevant ones.
* Books: 2–5 relevant books (title, authors, year, description, link).
* Each research step can fail independently. If YouTube or Books fail, mark step `failed`, continue, and surface a warning; generation still runs. Web research failing = block generation (not enough evidence) and offer retry.

### score_sources
Deterministic + LLM-assisted reliability tiers:
* Tier 1: standards/specs/official docs (e.g. RFCs, MDN, .gov, official project docs)
* Tier 2: universities, established publishers, reputable textbooks
* Tier 3: well-known tech/education sites
* Tier 4: blogs/forums/unknown

Store a short reason. Assign stable IDs S1..Sn.

### generate
Gemini with structured JSON output + Pydantic validation. On invalid JSON: retry with the validation error fed back (max 2). Save as `LessonVersion` v1 (author=ai).

### timebudget (pure Python, no LLM)
* Reading: words / 200 wpm (configurable)
* Videos: actual durations from YouTube API (or watch_segment length)
* Activities / knowledge check: section `minutes` (sanity-check: ≥ 1 min per 2 quiz questions)

Output per-section and total. Flag if total > 45 or if section `minutes` disagree badly with computed time.

### qc_factual (QC1) — must be a real check, not "LLM, is this right?"
1. Extract atomic factual claims from the lesson (with section id).
2. For each claim: look up the cited source excerpt(s) and have `QC_MODEL` judge `supported | partially_supported | unsupported | contradicted | uncited`, quoting the evidence span.
3. Source audit: flag low-tier sources carrying key claims, broken/irrelevant sources, over-reliance on one source.
4. Consistency: detect contradictions between sections and between the lesson and the knowledge-check answers.
5. Gaps: outcomes or subtopics with no supporting evidence.
6. For numeric/worked examples, recompute in Python where possible (e.g. interest calculations) and flag mismatches.

Output: QCReport(layer=factual) + QCIssues with suggestion text. Score = % claims supported.

### qc_instructional (QC2) — separate prompt, separate context, does not see QC1 output
1. Outcome coverage matrix: for each atomic outcome → has explanation? example? practice/activity? knowledge-check item? (✓/✗ with section refs)
2. Verb alignment (Bloom's): e.g. "distinguish" requires a classification/compare activity, not just definitions.
3. Clarity, structure/flow, jargon introduced before use, example quality, practical application relevance.
4. Time-budget findings from `timebudget`.

Output: QCReport(layer=instructional) + QCIssues + the coverage matrix. Score = rubric average.

### apply_fix
Given a QCIssue, LLM rewrites only the affected section (with sources available for factual fixes). Return old vs new for a diff. Instructor accepts → new LessonVersion (author=qc_fix), issue status=applied; or dismisses. After fixes, instructor can re-run either QC layer on the latest version.

## API (sketch)

* `POST /lessons` {title, objective} → 422 on empty/whitespace/too-short input with a clear message
* `POST /lessons/{id}/run` → runs pipeline (background task); `GET /lessons/{id}/steps` → step statuses for polling
* `POST /lessons/{id}/steps/{name}/retry` → re-run from that step using cached upstream outputs
* `GET /lessons/{id}` → latest version + sources
* `PUT /lessons/{id}/content` → instructor edit → new version (autosave from UI, debounced)
* `GET /lessons/{id}/versions`, `GET /lessons/{id}/versions/{n}`, `POST .../restore`
* `POST /lessons/{id}/qc/{layer}` → run/re-run one QC layer on latest version
* `GET /lessons/{id}/qc` → both reports + issues
* `POST /qc/issues/{issue_id}/preview-fix` → returns proposed patch (diff)
* `POST /qc/issues/{issue_id}/apply` / `/dismiss`
* `GET /lessons/{id}/preview` → rendered final lesson
* `GET /lessons/{id}/export?formats=md,pdf,docx` → ZIP: `lesson.*`, `references.md`, `qc1_factual_report.md/.json`, `qc2_instructional_report.md/.json`

## Frontend

* New Lesson: two inputs, client-side validation, submit.
* Workspace: left = pipeline step list with status badges, error messages, and Retry buttons; center = markdown editor per section (autosave, "saved" indicator, version history dropdown); right tabs = Sources (tier badges, links, video thumbnails/durations), QC1 report, QC2 report (coverage matrix table), Time budget bar.
* QC issues: severity badge, evidence, suggestion, "Preview fix" → diff modal → Apply / Dismiss. "Re-run QC" buttons.
* Preview tab: final rendered lesson as a learner would see it, with embedded video links and references.
* Export button.

## Error handling rules (non-negotiable)

* Empty/invalid inputs rejected on both client and server with clear messages.
* All provider calls wrapped with `tenacity` exponential backoff; handle Gemini 429 / RESOURCE_EXHAUSTED, timeouts, and quota errors explicitly with readable messages.
* A failed step never deletes previous outputs or instructor edits. Retry resumes from the failed step.
* Instructor edits are saved as versions immediately; refresh/restart of the server loses nothing.
* Malformed LLM JSON → validate, retry with error feedback, then fail the step cleanly.
* Log every step (start/end/error) to console and DB.

## Secrets

`.env` with `GEMINI_API_KEY, TAVILY_API_KEY, YOUTUBE_API_KEY, GOOGLE_BOOKS_API_KEY, GEN_MODEL, QC_MODEL`. Commit `.env.example` only. Never log keys.

## Build phases — complete ONE phase, run tests, summarize, then STOP and wait

1. Scaffold: repo layout, config, DB models, provider interfaces + fakes, orchestrator with step state machine, `POST /lessons` + run + steps endpoints. Pipeline runs end-to-end with fake providers. Tests pass.
2. Real research: Tavily, YouTube, Books providers; caching; source scoring. Script `scripts/try_research.py "HTTP Requests and Responses"` prints the evidence store.
3. Generation + time budget: structured lesson with citations, Pydantic validation, version v1.
4. QC1 (factual) with claim table.
5. QC2 (instructional) with coverage matrix.
6. Edit / versions / apply-fix / re-run QC endpoints.
7. Frontend (all pages above).
8. Export + error-handling polish (retry buttons, 429 messages, empty-input handling).
9. Samples + docs: run both test lessons, save exports in `/samples`, write README (setup, architecture diagram, how QC works, limitations, acknowledgments of libraries/APIs/AI assistance) and finish DECISIONS.md.

## Test lessons

* Title: HTTP Requests and Responses — Objective: Explain GET and POST methods and distinguish between 2xx, 4xx, and 5xx response status categories.
* Title: Simple vs Compound Interest — Objective: Calculate simple and compound interest for a given principal, rate, and time, and explain why compound interest grows faster.

## Working rules for Claude Code

* Explain non-obvious choices in `DECISIONS.md` (one short entry each: decision, alternatives, why).
* Prefer simple, readable code over clever abstractions. Type hints everywhere.
* Never fake research results, sources, or URLs in real mode. Fakes live only in `providers/fakes.py` and are used only in tests or when `DEMO_OFFLINE=1`.
* Don't add features outside this spec without asking.
* After each phase: list files changed, how to run/test it, and any open questions.

## Anti-hallucination rules (apply to every task)
- Never say something ran, passed, or works unless you ran it in this session. Show the exact command and its raw output.
- Never invent numbers, quota figures, URLs, file contents, model names, or API behaviour. If you don't know, say "unknown" and check (run it, read the file, or read the installed library/docs).
- When I ask to see output (a lesson, a report, a table), print it from the actual file. Don't summarise or rewrite it from memory.
- Label every claim in your summaries as VERIFIED (you ran or read it) or ASSUMED (not checked).
- When something fails, paste the real error message verbatim. Don't paraphrase it or guess the cause without evidence.
- Read a file before describing or editing it. Never describe code you haven't opened this session.
- For library or API usage, check the installed version (pip show / package.json) instead of relying on memory.
- If a result looks too good or contradicts an earlier run, say so and re-check it before reporting.
