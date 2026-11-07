# Decisions

One entry per non-obvious choice: **decision**, alternatives considered, why.

## Phase 1 — Scaffold

### D1. Step dependencies are an explicit map, not "everything after a failure is blocked"
- **Decision:** `orchestrator.DEPENDS_ON` lists each step's inputs. A step is `skipped` only if a *required* input isn't `done`. Retry re-runs the chosen step plus its transitive dependents only.
- **Alternatives:** strictly linear pipeline (failure skips every later step; retry re-runs everything after).
- **Why:** With a linear chain, a Tavily failure would also skip YouTube/Books research, and a QC1 failure would skip QC2. That contradicts the spec, which says the QC layers are independent and each research step can fail on its own. The map also makes retry cheaper: retrying `qc_factual` doesn't re-run QC2.

### D2. Optional steps are soft inputs
- **Decision:** `research_youtube` and `research_books` appear in `score_sources`'s inputs but never block it. If either fails, the lesson ends `completed_with_warnings`. Resuming the run later re-runs the failed step *and its dependents*, so the new videos/books actually reach the lesson (as a new version).
- **Why:** This follows the spec ("generation still runs") and makes a later fix actually show up in the lesson.

### D3. A step's writes are atomic with its status
- **Decision:** Step functions never commit. The orchestrator commits their writes together with `status=done`, or rolls everything back on exception before marking `failed`.
- **Alternatives:** commit inside steps.
- **Why:** No half-written Source rows or orphan versions after a crash. `output_json` keeps the last *successful* output, because the failure path never touches it.

### D4. Append-only versions, reports and sources; stable source ids
- **Decision:** `LessonVersion` and `QCReport` are insert-only. `Source` rows are never deleted. A URL keeps its `S#` across research re-runs (`Source.key` is the dedupe key). The `score_sources` output lists which sids belong to the *current* run, and `generate` only offers those to the model.
- **Why:** Older versions keep valid citations, and no instructor edit or earlier output is ever overwritten.
- **Schema additions beyond the spec:** `Source.key` (dedupe), `PipelineStep.position` (ordering), `QCReport.details_json` (QC1 claim table / QC2 coverage matrix need somewhere to live).

### D5. One run per lesson via an atomic claim
- **Decision:** `start_run` does `UPDATE lesson SET status='running' WHERE id=? AND status!='running'` and checks the rowcount. A second request gets HTTP 409.
- **Why:** A read-then-write check has a race (for example, a double-click on Run). This version avoids the race and needs no lock table.

### D6. Crash/restart recovery on startup
- **Decision:** On startup, steps left `running` become `failed` ("Interrupted… Retry it"), and the lesson status is recomputed from its steps.
- **Why:** FastAPI background tasks don't survive a restart. This makes the interruption visible and retryable instead of leaving the lesson stuck in "running" forever.

### D7. Background execution with FastAPI `BackgroundTasks`
- **Alternatives:** Celery/RQ, asyncio task queue.
- **Why:** This is a single-user, locally-run tool. A broker would add setup cost without benefit, and D5/D6 cover the failure modes that matter.

### D8. LLM output: schema validation + semantic checks share one repair loop
- **Decision:** `generate_structured(llm, prompt, Schema, check=...)` validates with Pydantic, then runs `check()` for rules Pydantic can't express (unknown `[S#]` citations, an outcome with no quiz question). Both kinds of problem are fed back to the model, up to `LLM_MAX_REPAIRS` (2) times. After that the step fails with a readable message.
- **Why:** This is the spec's "retry with error feedback". It also catches invented sources at generation time instead of hoping QC finds them.

### D9. Video title/URL/duration are copied from the Source row
- **Decision:** After generation, `normalize_videos` overwrites each video's title, URL and duration with the researched values.
- **Why:** The model can't invent or garble a URL, and the time budget uses the real YouTube duration.

### D10. Provider errors are typed (`ErrorKind`) and only transient kinds are retried
- **Decision:** `ProviderError(provider, kind, message)`. The `with_retries()` decorator (tenacity, exponential backoff) retries only `rate_limited`, `timeout` and `network`. `quota_exhausted`/`auth` fail immediately. Research loops also stop on those "fatal" kinds instead of trying every query.
- **Why:** Retrying a daily-quota error just burns time. One readable message per failure kind is what the instructor needs to see. API keys are scrubbed from every error message before it is stored.

### D11. Reliability tiers: deterministic domain rules first
- **Decision:** An ordered suffix table (`sources.DOMAIN_RULES`) plus a channel table. Matching is exact-domain-or-subdomain, so `developer.mozilla.org.attacker.com` does not match MDN. Unknown domains default to tier 4 with a stated reason. Books are tier 2 and labelled "metadata/description only".
- **Planned (Phase 2):** LLM-assisted classification for domains the table doesn't know.

### D12. Time budget rules
- **Decision:** Reading time is words ÷ WPM, with citations and link URLs excluded from the count. Videos count at their real duration or `watch_segment` length. Activities use their declared minutes (never less than the reading time). Quizzes get at least 0.5 min per question. A section is flagged when declared and computed minutes differ by more than max(2 min, 50%).
- **Why:** The rules are explicit, cheap, and explainable; a rubric you can read beats an LLM guess.

### D13. Fake providers are visibly fake
- **Decision:** Every fake title starts with `[FAKE]` and every fake URL is under `https://example.com/fake/`. Fakes load only when `DEMO_OFFLINE=1` or a test injects them. In real mode, Phase 1 refuses to run (HTTP 503 with an explanation) instead of falling back to fakes.
- **Why:** This follows the spec rule that research results are never faked in real mode, and fake output can't be mistaken for real research.

### D14. Python 3.13 locally
- **Decision:** The venv uses Python 3.13 (spec: 3.11+). The code uses only 3.11-compatible syntax.
- **Why:** The 3.11 on this machine is the Microsoft Store build, whose venvs can be quirky. 3.13 is a regular install with full wheel coverage.

### D15. Phase-1 QC steps are explicit skeletons
- **Decision:** `qc_factual` and `qc_instructional` currently make one QC_MODEL review pass each, labelled `method: phase1_single_pass` in `details_json`. They exist so the report/issue tables and the "QC1 failure doesn't block QC2" behaviour are exercised end to end.
- **Planned:** Phases 4 and 5 replace them with claim-level verification and the coverage matrix.

## Phase 2 — Real research

### D16. Response cache in SQLite, written on its own connection
- **Decision:** `ProviderCache(namespace, sha256(params))` stores every *successful* Tavily search, Tavily extract (per URL), YouTube search/details/relevance verdict, book search, and LLM vetting call. Cache writes use a separate session that commits immediately.
- **Alternatives:** cache inside the step's own transaction; an HTTP-level cache such as hishel.
- **Why:** A failed step rolls back its own transaction. If the cache lived in that transaction, three successful Tavily searches followed by one failure would be lost, and the retry would pay for them again. The cache is shared across lessons, so researching the same query twice costs nothing. Failures are never cached. There is no expiry; a stale cache is acceptable for a local authoring tool.

### D17. Extraction picks reliable, diverse pages
- **Decision:** Search results are ordered round-robin across queries, then stable-sorted by deterministic tier, with at most `WEB_MAX_PER_HOST` (2) pages per site. The top `WEB_MAX_EXTRACT` (8) are extracted. Social and video sites are excluded at search time.
- **Why:** Evidence quality is the main goal. Without this, one SEO-heavy site could supply most of the evidence, and an MDN or RFC page ranked 4th for its query might never be read.

### D18. Extracted pages are cleaned, and short pages rejected
- **Decision:** `clean_page_text` drops navigation-only lines and images and keeps link *text* but not URLs. Pages under 400 characters after cleaning are rejected and logged with a reason.
- **Why:** QC1 will quote evidence spans, so the excerpt must read like the page a human sees. Pages that are almost empty (paywalls, JS-only sites) are not evidence.

### D19. YouTube: hard duration window, then relevance by watching
- **Decision:** One `search.list` (100 units) plus one `videos.list` (1 unit) per lesson. Videos shorter than 2 min (Shorts) or longer than 15 min are dropped before any LLM cost. Known educational channels go first, then by views, with at most 6 relevance checks. Methods are tried in order: Gemini watches the URL (low media resolution), then the transcript, then metadata only.
- **Guardrail:** A metadata-only verdict never produces "key points", because nothing was actually verified. The method used is stored on the source and shown in the evidence store.
- **Why:** This is the order the spec asks for, with the token cost bounded. Key points from a video that was actually watched become that source's excerpt, so QC1 can later check claims attributed to the video.

### D20. Research judgements use QC_MODEL
- **Decision:** Video relevance, book vetting and unknown-domain tiering all call `QC_MODEL`. `GEN_MODEL` only plans and writes.
- **Why:** These are verification tasks. Keeping the writer out of source vetting means the same model never chooses evidence it then writes from.

### D21. LLM-assisted tiers are a fallback, never an override
- **Decision:** Deterministic domain and channel rules win. Only names they don't know go to the LLM, in one batched call. That call is told "when unsure, choose the higher number", and its reason is stored prefixed with "LLM-assessed by <model>". If the call fails, those sources stay at tier 4 and the step still succeeds.
- **Why:** The spec asks for "deterministic + LLM-assisted". The rules are easy to audit, and the LLM covers the long tail of sites the rules can't list, such as official project docs. Every LLM-assigned tier is labelled as such.

### D22. Books: Google Books → Open Library, then LLM vetting
- **Decision:** `FallbackBooksProvider` moves to Open Library when Google Books errors *or* returns nothing. Open Library descriptions come from the `/works/{id}.json` record. QC_MODEL then keeps only books genuinely about the topic, falling back to a keyword-overlap filter. Books with a description are listed first.
- **Why:** A raw title search returns many unrelated books that just share a word. Books remain metadata-only, and the tier reason says so.

### D23. Missing YouTube key = warning, missing Gemini/Tavily key = refuse to start
- **Decision:** `build_providers` refuses real mode, with a list of the missing variables, when `GEMINI_API_KEY`, `TAVILY_API_KEY`, `GEN_MODEL` or `QC_MODEL` is unset. A missing YouTube key produces a provider whose every call fails with a "set YOUTUBE_API_KEY" message, so that optional step warns and the lesson still completes.
- **Why:** This matches which research the spec treats as essential and which it treats as optional.

### D24. Gemini error mapping
- **Decision:** 429/RESOURCE_EXHAUSTED counts as **per-day** quota (not retried, "wait for reset or switch model") when the quota id contains `PerDay`. Otherwise it is a per-minute rate limit, retried with backoff. Missing models (404) and bad keys get their own messages naming the env var to fix.
- **Why:** The spec requires explicit, readable handling of 429/RESOURCE_EXHAUSTED and quota errors. Retrying a daily-quota error just wastes minutes.

### D25. Long pages are reduced to their most relevant passages, not truncated
- **Decision:** `pipeline/passages.py` removes site chrome before the page title. For pages over `WEB_EXCERPT_CHARS` (12k), it keeps the opening summary plus the paragraphs that best match the lesson keywords, each with its section heading, in original order with `[…]` marking skipped text. Keywords that are rare on the page weigh more, and keywords in the section heading count double.
- **Alternatives:** keep the first N characters; let an LLM summarise each page; embeddings.
- **Why:** On the first real run, Tavily returned the whole of RFC 9110 (447k characters). The first 20k were front matter and the table of contents, so none of the GET/POST/status-class definitions reached the evidence store. With selection, the excerpt contains §9.3.1 GET, §9.3.3 POST and §15.3/15.5/15.6 verbatim. An LLM summary would replace the source's own words, which QC1 needs to quote. The selection is deterministic, free, and testable.

### D26. Navigation filter keeps single-link lines
- **Decision:** Only bulleted link lines and lines with 2+ links are dropped as menus.
- **Why:** MDN writes each status-code name as a line holding a single link (`` `200 OK` ``). The first version of the filter deleted every such name.

### D27. Video language is checked twice, in code
- **Decision:** A video is dropped if `videos.list` declares a non-English `defaultAudioLanguage`. The relevance judgement must also report `spoken_language`, and code (not the prompt) marks non-English narration as not relevant.
- **Why:** A Hindi tutorial with an English title passed an "English only" rule written only in the prompt. On the next run, the declared-language check alone removed 3 Hindi videos.

### D28. Near-duplicate pages and self-declared outdated pages
- **Decision:** A page whose excerpt has Jaccard similarity ≥ 0.5 (8-word shingles) with an already-kept page is skipped. On real data, the two RFC 9110 mirrors scored 0.73 and every other pair scored ≤ 0.01. A page that calls itself "historic", "not accurate anymore" and so on near its top is demoted to tier 4, with the reason recorded.
- **Why:** A 1992 W3C page that says it is "not accurate anymore" was getting tier 1 because of its domain. Duplicate mirrors waste extraction slots and would make one document look like two independent sources to QC1's over-reliance check.

### D29. Prompt versions in cache keys
- **Decision:** Cached LLM judgements (video relevance, book selection) include a `prompt_version` in their cache key. Video details use a `.v2` namespace since a field was added.
- **Why:** Without this, improving a prompt would silently keep serving verdicts from the old one.

### D30. Books are rated against a rubric, not picked from a list
- **Decision:** QC_MODEL scores every candidate book 0–10 against an explicit rubric. Books scoring 7+ are kept, best first. The planner also writes 1–2 catalogue-style `book_queries` ("HTTP protocol"), so books aren't searched by the lesson title.
- **Alternatives:** ask for "the relevant ids"; a keyword filter only.
- **Why:** With the free-form keep list, flash-lite's choice changed between identical runs. One run kept 1905 interest tables and rejected *Mathematics for Finance*. Forcing a score per book made it consider each one, and the threshold is visible in the output ("9/10 — dedicated textbook"). Searching by the lesson title had returned conference proceedings. Catalogue queries found *HTTP: The Definitive Guide* and Kellison's *The Theory of Interest*.

### D31. Planner must aim at least two queries at authoritative sources
- **Decision:** The plan prompt requires two queries naming an authoritative source type for the subject (standard/official docs, regulator/.gov, university/open textbook). Search operators such as `site:edu` are stripped before keyword extraction.
- **Why:** Without this, the interest lesson's web evidence was all tier 3–4. With it, the same lesson found a Consumer Financial Protection Bureau page (tier 1) and two OpenStax chapters (tier 2). A planner-written `site:` operator had turned "site" into a topic keyword that matched cookie banners.

## Phase 3 — Generation + time budget

### D32. The model writes a `LessonDraft`; code produces the `LessonContent`
- **Decision:** The LLM schema (`LessonDraft`) contains only what the model should author. After validation, `finalize()` overwrites the title, objective and outcomes from the plan; video title, URL and duration from the Source rows; `references` from the citations actually present; and `further_reading` from the researched books. That last field exists only on `LessonContent`, so the model never sees it.
- **Why:** Anything a model can restate, it can get wrong. Stored data is the single source of truth for facts about sources.

### D33. Books are further reading, never evidence
- **Decision:** Book sources are not given to the generation model and cannot be cited. They are listed under "Further reading", with a note that only catalogue details and publisher descriptions were reviewed.
- **Why:** We only have a book's description, not its text. Citing it for a claim would imply we checked the claim against the book. This follows the spec ("never claim the tool read the full book").

### D34. Hard vs soft checks on the generated lesson
- **Hard** (fed back; the step fails if they persist): citations must be web/video sources from this research run; every outcome must be covered by a section *and* a quiz question; the required section types must be present; concept and example sections must cite something; `videos[]` must point at researched videos.
- **Soft** (fed back once, then stored as `warnings`): the measured time is outside 25–45 minutes, videos total more than 15 minutes, a question doesn't have 4 options, there are fewer than 4 or more than 8 questions, or there is no video section although videos exist.
- **Why:** A missing outcome makes a lesson wrong. A 23-minute lesson is only weaker. Failing the step on soft issues would throw away a usable lesson.
- **Cost guard:** Soft issues get at most one repair call (`max_soft_repairs=1`). Each repair is a full generation (~40k-character prompt), and on the free tier the daily quota for `gemini-3.6-flash` ran out after a handful of runs. On a real run, two soft rounds for "too short" moved the lesson from 20.1 to 22.7 minutes, which was not worth the quota.

### D35. Learners see measured minutes, not model-declared minutes
- **Decision:** After validation, each section's `minutes` is replaced with the deterministic estimate from `timebudget.py`, rounded up (minimum 1). The model's numbers are kept in the step output (`minutes_adjusted`).
- **Why:** On real runs, the model declared 40 minutes for a lesson that measures 22.7 (a 10-minute "concept" section was 2.3 minutes of reading). A learner-facing estimate must be honest. The `timebudget` step still flags disagreements, which matters once instructors edit sections (Phase 6).

### D36. Grouped citations are parsed and normalised
- **Decision:** `[S3, S5]` and `[S3; S5]` are recognised everywhere, and `finalize()` rewrites them as `[S3], [S5]`.
- **Why:** On a real run, the model mixed both styles. The single-id pattern missed grouped ones, so S5 was cited in the text but missing from the References list, and those ids were never checked. One normalised format keeps QC1's claim-to-source mapping simple.

### D37. Per-tier prompt budget, reusing passage selection
- **Decision:** Each source contributes its most relevant passages to the prompt, re-selected by `passages.py` against the outcomes, within a per-tier budget (tier 1: 6k characters, tier 2: 5k, tier 3: 3.5k, tier 4: 2k). The prompt asks for key definitions to rest on tier 1–2.
- **Why:** About 40k characters (~10k tokens) for 12+ sources leaves room in the context while giving the most trustworthy sources the most weight.

## Deadline build (QC, instructor features, UI)

### D38. Model fallback chain instead of retry loops
- **Decision:** `LLM_FALLBACK_MODELS` (comma-separated). Each LLM role (generation, QC) is a `FallbackLLM`: the preferred model first, then the chain. On 429, 503, 504, timeout or daily-quota errors the next model answers immediately, with one attempt per model and no backoff. The model that actually answered is stored: in the version note ("Generated by …"), the `generate` step output, and each QC report's `details.model`. Per-call timeout is 120 s.
- **Why:** On the free tier, single models failed for long stretches tonight. `gemini-3.6-flash` hit its daily quota; `gemini-3.8-flash` returned 504 even for "say ok" (VERIFIED with `scripts/check_models.py`). Retrying the same model wasted about 12 minutes in one run.

### D39. A failed repair call never discards a valid draft
- **Decision:** If an extra (repair) call raises a provider error after a draft has already passed every hard check, that draft is kept and its soft problems are stored as warnings. A soft repair is only attempted when the lesson measures under 25 minutes; 25–35 minutes is kept with a warning, and the prompt targets 35–45.
- **Why:** A live run lost a valid `gemini-3.8-flash` lesson because its optional "make it longer" call got a 503.

### D40. QC1 = claims in code + one batched judging call + verification in code
- **Decision:** Code extracts claims: each sentence or table row with a citation, plus factual-looking uncited sentences. One QC call judges all claims against excerpts of their cited sources and must quote evidence. Code then checks every quote appears verbatim in the source excerpt, and a "supported" verdict without a verifiable quote is downgraded to "partially_supported". The source-tier audit, over-reliance check, outcome-gap check and arithmetic recomputation (`pipeline/numeric.py`, which evaluates every `a op b = c` chain, LaTeX included) are all in code.
- **Alternatives:** one call per claim (too many calls on the free tier); "LLM, is this right?" (not a real check).
- **Observed (VERIFIED on lesson 7 v1):** the judge model marked all 84 claims "supported"; all 26 partial verdicts came from the code's quote verification, including the POST "suitable for sensitive data" overclaim. The verification layer is what makes QC1 meaningful with a lenient judge model; this is listed as a limitation.

### D41. QC2 is one call in a fresh context, with code-owned facts
- **Decision:** QC2 never sees QC1. The model fills the coverage matrix, Bloom verb alignment, a 6-criterion rubric and issues. Code overwrites the quiz column with the real quiz-to-outcome mapping, turns gaps and misalignments into issues, and adds time-budget findings from `timebudget.py`. QC uses the first model in the chain that differs from the generator.

### D42. Apply-fix rewrites one section; nothing is saved until the instructor accepts
- **Decision:** `preview-fix` returns before/after for the section named in the issue's location, with citations restricted to this lesson's web/video sources. `apply` saves the accepted text as a new version (author `qc_fix`) and marks the issue applied; `dismiss` marks it dismissed. Issues not tied to one section (e.g. over-reliance) return 422, "edit the lesson directly".

### D43. Streamlit instead of React
- **Decision:** The UI is a single Streamlit app (`frontend/app.py`) that only calls the FastAPI backend.
- **Why:** Streamlit was chosen over React because of the submission deadline. State lives in SQLite behind FastAPI, so the UI is stateless: refreshing or restarting it loses nothing.

### D44. QC2 no longer waits for the `timebudget` step
- **Decision:** QC2 and QC re-runs only need a lesson version to exist; a failed later re-generation no longer blocks QC on the existing version. QC2 computes the time budget itself with the same deterministic module.
- **Why:** After the failed regeneration attempts, QC on the still-valid v1 was blocked with "Step 'generate' must succeed before 'qc_factual' can run".
