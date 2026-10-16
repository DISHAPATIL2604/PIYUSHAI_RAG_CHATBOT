# Verification report

Everything below was measured by running commands in the build sandbox. Items that could not be verified are listed explicitly.

## 1. Environment
- Sandbox: Ubuntu Linux, Python 3.12.3, Node v22.22.2, npm 10.9.7. **Not run on Windows or Python 3.11** (target platform is unverified).
- Embedding model in tests: deterministic fake bag-of-words (config default for real use: `all-MiniLM-L6-v2`).
- Installed: fastapi 0.143, pydantic 2.14, chromadb 1.5.9.

## 2. Commands run
- `pytest -q` -> **47 passed, 0 failed, 0 skipped** (about 2.7 s).
- Backend started with `uvicorn tests.dev_server:app` (real FastAPI + real persistent ChromaDB; mocked embedder and LLM; SAMPLE data). `/api/v1/health`, `/courses`, `/subjects`, `/chat`, `/sessions/.../history` returned correct responses over HTTP; CORS preflight from `http://localhost:5173` returned `access-control-allow-origin`.
- Server restart on the same data directory: index counts read back from disk (1 chunk, 2 courses, 2 videos) -> **persistence works**.
- Frontend: `npm install`, `npm run build` -> built successfully (32 modules). **The UI was not opened in a browser**, so the UI behaviour itself is untested.

## 3. Crawl findings
**Not performed.** The sandbox cannot reach piyushai.com, piyushwairale.com, youtube.com/googleapis.com, huggingface.co or api.groq.com (connection fails for all). robots.txt, sitemap and static-vs-JS status of the real sites are unknown.
`backend/docs/crawl_findings.md` says so; run `python -m scripts.inspect_sites` locally to fill it in. Crawler logic (robots.txt incl. 5xx, sitemap, per-domain rate limit, navigation removal, embedded-JSON fallback, optional Playwright fallback, `skipped_no_content`) was verified against **simulated** sites only.

## 4. Ingestion results
- **Real ingestion: 0 pages, 0 videos** (no network). No real course or video was ever indexed.
- Simulated-source run (fake site + fake YouTube API), measured:
  - Run 1: websites fetched 5, new 3, chunks 6, skipped {robots_disallowed: 2, skipped_no_content: 1, http_404: 1}; YouTube fetched 2, new 2, chunks 3, playlists 1, skipped {unavailable_video: 2}. Totals: 9 chunks, 1 course, 2 videos.
  - The one course record had price, enrollment URL and exam extracted; a later run with the price removed stored `null` (never guessed).

## 5. Duplicate-ingestion check (simulated sources)
Run 1 -> run 2: chunks 9 -> 9, courses 1 -> 1, videos 2 -> 2; run 2 reported new=0, chunks_created=0, unchanged=3 (web) / 2 (YouTube). A changed page replaced its old chunks (asserted in tests).

## 6. Threshold tuning
**Not tuned on real data.** Defaults `RELEVANCE_THRESHOLD=0.35`, `RECOMMENDATION_MIN_SCORE=0.45` are untested against MiniLM on real PiyushAI content (tests use 0.20 retrieval threshold with the fake embedder). With the fake embedder the recommender scored a sample ML course 0.80 and a sample video 0.84 for "Explain linear regression" with subject and topic selected, and returned `null` for "capital of France". Those numbers say nothing about MiniLM. Tune after real ingestion (README section 7).

## 7. End-to-end checks (mock LLM, SAMPLE data)
- "Explain linear regression" (+ course/subject/topic): `grounded`, 1 source, sample course + sample video recommended (flagged `is_sample`), follow-ups returned.
- "Explain the French revolution" in the same session: `general_knowledge`, no sources, no recommendations (this caught a real bug - history was polluting retrieval - which is fixed and covered by a test).
- "What is the price of the PiyushAI course?" with no matching data: `not_found`, LLM not called, no recommendations.
- Session history: 6 messages after 3 turns; GET history 404 for unknown session; DELETE resets.

## 8. Security checks
- `X-Admin-Key`: missing -> 401, wrong -> 403, correct -> passes, unconfigured server key -> 503 (fails closed). Verified in tests and over HTTP.
- Health output and error bodies contain no API keys (asserted; a provider error echoing the key is not forwarded).
- Prompt injection (poisoned chunk + obedient mock LLM): context is wrapped in `<retrieved_document>` blocks with a forged closing tag escaped; evil URL removed from answer, follow-ups **and source snippets** (the snippet leak was found by this test and fixed); recommendations come only from the catalog; leaked system-prompt lines are replaced.

## 9. Real vs mocked
| Service | Tests | HTTP E2E run |
|---|---|---|
| Groq LLM | mocked (HTTP layer faked for error paths; real client code exercised) | mocked |
| YouTube API | mocked | not called |
| Website fetching | mocked (simulated site) | not called |
| Embedding model | fake | fake |
| FastAPI, ChromaDB persistence, catalog, sessions | real | real |

## 10. Known limitations / needs your action
- Never run against the real sites, real YouTube API, real Groq, or the real MiniLM model. First real run may surface site-specific extraction problems.
- Course price/enrollment extraction is heuristic (first currency match, first "Enroll"-like link); verify on real pages.
- Subject/topic tagging is keyword-based from `app/data/gate_da_taxonomy.json`; extend aliases for real titles.
- Transcripts are not indexed (title, description, playlist context only).
- Sessions are in memory (lost on restart). Groq `LLM_MAX_TOKENS` default is 1500, not 800, because gpt-oss spends tokens on hidden reasoning (unverified against the live API).
- Windows/Python 3.11 not tested; React UI not exercised in a browser.

## 11. Next steps
Run `inspect_sites` and `ingest_all` locally; tune thresholds on 10-20 real questions; persistent session store (Google login + history); compare embedding models (e.g. bge-small); hybrid retrieval and reranking.
