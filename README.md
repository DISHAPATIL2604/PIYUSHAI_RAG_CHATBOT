# PiyushAI RAG Chatbot (MVP)

A course-aware educational chatbot for PiyushAI and GATE Data Science & AI (GATE DA).
FastAPI + ChromaDB + local Sentence Transformers + Groq LLM, with a minimal React test UI.

```
question -> query processing -> embedding -> retrieval (threshold) -> context assembly -> LLM -> source attribution
         -> course/video recommendation (from structured catalogs only) -> response
```

Key guarantees: recommendations come only from real indexed catalog records and their URLs are re-validated;
the LLM never writes recommendation links; any URL in a generated answer that is not in the retrieved sources or catalog is removed;
retrieved text is treated as untrusted data; ingestion endpoints require an `X-Admin-Key`.

## 1. Prerequisites (Windows PowerShell)

```powershell
python --version    # 3.11 or newer
node --version      # 18 or newer
git --version
```

## 2. Backend setup

```powershell
cd piyushai-rag-chatbot\backend
python -m venv .venv
# If activation is blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend\.env`:

| Variable | Where to get it |
|---|---|
| `GROQ_API_KEY` | https://console.groq.com/keys |
| `YOUTUBE_API_KEY` | Google Cloud Console -> enable **YouTube Data API v3** -> Credentials -> API key |
| `ADMIN_API_KEY` | any long random string, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `FIREBASE_PROJECT_ID` | Firebase Console -> Project Settings -> Project ID |
| `FIREBASE_AUTH_REQUIRED` | Set `true` to require Firebase auth tokens on `/api/v1/chat` (default: `true`) |

**First run downloads the embedding model** (`all-MiniLM-L6-v2`, about 90 MB) from Hugging Face into `%USERPROFILE%\.cache\huggingface`.
It needs internet once. Pre-download it with:

```powershell
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

Optional (only for JavaScript-rendered pages): `pip install -r requirements-optional.txt; playwright install chromium`, then set `ENABLE_PLAYWRIGHT=true`.

## 3. Inspect the sites, then ingest

```powershell
python -m scripts.inspect_sites     # writes docs\crawl_findings.md (robots.txt, sitemap, static vs JS-rendered)
python -m scripts.ingest_all        # websites + YouTube (YouTube is skipped with a warning if no key)
python -m scripts.ingest_all --websites-only --max-pages 30
python -m scripts.ingest_all --youtube-only --only-new
```

Or via the API (the server must be running):

```powershell
$h = @{ "X-Admin-Key" = "<your ADMIN_API_KEY>" }
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/ingestion/websites -Headers $h -ContentType "application/json" -Body '{"max_pages": 30}'
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/ingestion/youtube  -Headers $h
```

Re-running ingestion is safe: chunk IDs are deterministic, unchanged pages/videos are skipped, changed ones replace their old chunks.

## 4. Run the backend

```powershell
uvicorn app.main:app --reload --port 8000
# http://localhost:8000/api/v1/health      http://localhost:8000/docs
```

## 5. Run the React test UI

```powershell
cd ..\frontend
npm install
Copy-Item .env.example .env
# Fill in frontend/.env with Firebase Web App credentials (API Key, Project ID, etc.)
npm run dev          # http://localhost:5173
```

## 6. Tests

```powershell
cd backend
pytest -q
```

All external services are mocked (Groq, YouTube, website HTTP, embeddings use a deterministic fake). Sample data lives in `data\sample\` and is always flagged
`is_sample: true`; it is excluded from recommendations unless `ALLOW_SAMPLE_DATA=true`.

Offline demo without any keys or downloads (mock embedder + mock LLM + SAMPLE data, canned answers):
`uvicorn tests.dev_server:app --port 8000`

## 7. How it decides things

**Answer modes** (always returned as `answer_mode`):
- `grounded`: at least one chunk scored >= `RELEVANCE_THRESHOLD`.
- `not_found`: nothing relevant AND the question is about PiyushAI itself (courses, price, enrollment...). Fixed reply, no LLM call, no recommendations.
- `general_knowledge`: nothing relevant, general GATE DA question. Answered by the LLM with a visible "not from PiyushAI sources" note and no sources.

**Retrieval:** similarity = `1 - cosine distance` (Chroma cosine space). Fetch `RETRIEVAL_FETCH_K`, drop below `RELEVANCE_THRESHOLD`, prefer chunks tagged with the
selected subject/course (soft preference, never exclusion), de-duplicate, keep `RETRIEVAL_TOP_K` within `MAX_CONTEXT_CHARS`.
A short follow-up ("and why?") that finds nothing on its own is retried with the previous question added.

**Recommendation score:** `0.60*semantic + 0.20*subject match + 0.15*topic match + 0.05*selected-course match (+ 0.03*recency for videos)`.
Weights are `REC_W_*` in `.env`. A record is returned only if `score >= RECOMMENDATION_MIN_SCORE` **and** its URL equals the catalog URL, belongs to an official domain
(courses) or is `https://www.youtube.com/watch?v=<stored id>` (videos). Otherwise the field is `null`.

**Tuning:** the defaults (`RELEVANCE_THRESHOLD=0.35`, `RECOMMENDATION_MIN_SCORE=0.45`) are starting points for MiniLM and have NOT been tuned on real PiyushAI data.
After ingesting, try 10-20 real questions; if good answers fall to `general_knowledge`, lower `RELEVANCE_THRESHOLD` (e.g. 0.28); if unrelated chunks sneak in, raise it.

**Switching embedding model:** set `EMBEDDING_MODEL` (e.g. `BAAI/bge-small-en-v1.5`), point `CHROMA_PERSIST_DIRECTORY` at a NEW folder (or delete `data\chroma` and `data\catalog`),
and re-ingest. Opening an index built with a different model fails with a clear `embedding_model_mismatch` error instead of mixing vectors.

**Growing later:** `SessionStore` (swap in SQLite/Postgres for Google login + persistent history), `VectorStore`, `EmbeddingProvider` and `LLMClient` are interfaces in `app/services/`.

## 8. API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/health` | status, counts, embedding model, key-configured booleans |
| POST | `/api/v1/chat` | body: `session_id?`, `message`, `selected_course?`, `selected_subject?`, `selected_topic?` |
| GET | `/api/v1/courses` | exams (dropdown) + catalog courses |
| GET | `/api/v1/subjects?course=` | subjects and topics from the taxonomy |
| GET / DELETE | `/api/v1/sessions/{id}/history` , `/api/v1/sessions/{id}` | history / reset |
| POST | `/api/v1/ingestion/websites` , `/youtube` | **admin**, header `X-Admin-Key` |

Errors are always `{"error": {"code", "message"}}` (401/403 admin key, 422 validation, 429 rate limit, 503 missing key, 502/504 provider problems).

## 9. Troubleshooting

- **Activation blocked:** `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.
- **Port in use:** `uvicorn app.main:app --port 8001` and set `VITE_API_BASE_URL` accordingly; add the UI origin to `BACKEND_CORS_ORIGINS`.
- **CORS error in browser:** `BACKEND_CORS_ORIGINS` must include the exact UI origin (`http://localhost:5173`); restart the backend after editing `.env`.
- **Chroma path problems on Windows:** use short paths without OneDrive-synced folders; relative paths in `.env` resolve from `backend\`.
- **Model download fails / slow first run:** needs internet once; check proxy/VPN; pre-download with the command in section 2.
- **Groq 401:** wrong key. **429:** rate limit (response includes `retry_after`). **model not found:** change `GROQ_MODEL`.
- **Empty/short answers with gpt-oss:** it is a reasoning model; raise `LLM_MAX_TOKENS`.
- **YouTube 429 `youtube_quota_exceeded`:** daily quota reached; retry tomorrow or use `--only-new`. **502 `youtube_key_rejected`:** enable YouTube Data API v3 for the key.
- **Ingestion indexed nothing / many `skipped_no_content`:** the site is JavaScript-rendered. Run `python -m scripts.inspect_sites`, then enable Playwright (section 2).
- **`embedding_model_mismatch`:** see "Switching embedding model".
