# 📊 PiyushAI RAG Chatbot — Comprehensive Project Report

**Date:** October 14, 2026  
**Project:** PiyushAI Educational RAG Chatbot (GATE Data Science & AI)  
**Status:** In Production / Offline Ready  

---

## 1. Executive Summary

The **PiyushAI RAG Chatbot** is a full-stack, enterprise-grade, retrieval-augmented educational assistant specifically engineered for **GATE Data Science and Artificial Intelligence (GATE DA)** students. 

The chatbot combines:
1. **Official Curriculum & Portal Grounding:** Scraped website data, course details, and YouTube video playlists.
2. **Offline-First Local Inference:** Native integration with **Ollama** (`llama3.2`) for 100% private, free, and local inference without data leaking to third-party cloud APIs.
3. **Cloud Fallback Capability:** Support for **Groq** ultra-fast cloud LPU inference.
4. **Secure User Identity:** Authentication powered by **Firebase Auth** guarding conversational endpoints.
5. **In-Process Semantic Search:** Embedded **ChromaDB** with **Sentence-Transformers** for fast vector search.

---

## 2. Component Architecture & Tech Stack

| Component | Technology / Library | Purpose & Responsibilities |
| :--- | :--- | :--- |
| **Frontend UI** | React 18, Vite, Vanilla CSS, Lucide Icons | Responsive modern chat interface, course/subject/topic filters, source citation badges, interactive follow-up question pills, session history, and Firebase authentication modal. |
| **Backend REST API** | FastAPI, Uvicorn, Pydantic v2 | High-performance asynchronous API, dependency injection container, route security guards, and chat session orchestration. |
| **Authentication** | Firebase Authentication (`firebase` client + `firebase-admin` server) | User login/signup, bearer token verification, and user-isolated session protection. |
| **Vector Database** | ChromaDB (`chromadb`) | In-process embedded vector database persisted on disk (`../data/chroma`) with cosine and L2 distance metrics. |
| **Embeddings** | HuggingFace `sentence-transformers` (`all-MiniLM-L6-v2`) | Generates dense 384-dimensional vector representations of document chunks and incoming user queries. |
| **LLM Inference** | **Ollama** (Local/Offline) / **Groq** (Cloud fallback) | Generates structured JSON responses (`answer` + `follow_up_questions`) adhering to strict context grounding rules. |
| **Web & Media Crawler** | `crawl4ai`, Playwright, BeautifulSoup4, YouTube Data API v3 | Ingests website pages, curriculum details, and YouTube video metadata into structured text documents. |

---

## 3. End-to-End RAG Pipeline Workflow

```
[ User Input + Course/Subject Filters ]
                  │
                  ▼
[ Firebase Auth Verification (Bearer Token Validation) ]
                  │
                  ▼
[ Query Embedding: sentence-transformers/all-MiniLM-L6-v2 (384-dim) ]
                  │
                  ▼
[ ChromaDB Semantic Search: Fetch top 15 chunks -> Filter top 5 ]
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
(Relevance <= 0.35)   (Relevance > 0.35 / Empty)
Grounding Mode        General Fallback Mode
        │                   │
        ▼                   ▼
Construct Prompt with  Construct Prompt with
<retrieved_document>   Explicit Refusal to Guess
        │                   │
        └─────────┬─────────┘
                  │
                  ▼
[ LLM Generation (Ollama llama3.2 / Groq llama3) ]
                  │
                  ▼
[ JSON Parsing & Fallback Validator ]
                  │
                  ▼
[ Curriculum Recommendation Engine (gate_da_taxonomy.json) ]
                  │
                  ▼
[ HTTP 200 Response: Answer + Citations + Recommendations + Follow-ups ]
```

### Key RAG Pipeline Hyperparameters
* **Chunk Size:** 800 characters
* **Chunk Overlap:** 120 characters
* **Retrieval Fetch-K:** 15 candidates
* **Retrieval Top-K:** 5 final chunks
* **Relevance Distance Threshold:** 0.35 (cosine distance threshold to strictly prevent hallucinations)
* **Max Context Characters:** 6,000 characters
* **Prompt Injection Defense:** Untrusted retrieved documents are stripped of escape sequences and wrapped in `<retrieved_document id="..." source="..." title="...">` blocks.

---

## 4. Models Used, Latency & Response Profiles

| Stage | Model Name | Host Environment | Average Latency | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Text Embedding** | `all-MiniLM-L6-v2` | Local (PyTorch / CPU) | **15ms – 40ms** | 384-dimensional embeddings; small memory footprint (~80 MB RAM). |
| **Primary LLM (Offline)** | `llama3.2:latest` | Local via Ollama daemon (`localhost:11434`) | **1.5s – 4.5s** (GPU) / **4s – 12s** (CPU) | 100% offline, zero API costs, strict JSON schema output. |
| **Cloud LLM (Optional)** | `llama3-8b-8192` or `openai/gpt-oss-20b` | Groq Cloud LPU | **250ms – 650ms** | Ultra-high throughput cloud inference (>300 tokens/sec). |

---

## 5. API Keys & Costing Breakdown

| Service | Key / Variable | Function | Cost / Pricing Tier |
| :--- | :--- | :--- | :--- |
| **Ollama Local LLM** | *None required* | Offline chat inference | **$0.00 / Free** (Open-source, self-hosted on user hardware) |
| **Sentence-Transformers** | *None required* | Local text embeddings | **$0.00 / Free** (Open-source, runs locally) |
| **ChromaDB** | *None required* | Local vector database | **$0.00 / Free** (Embedded database file, no cloud hosting fees) |
| **Firebase Auth** | `VITE_FIREBASE_API_KEY` | User sign-up & login | **$0.00 / Free** (Firebase Spark Free Tier up to 50k monthly active users) |
| **YouTube Data API v3** | `YOUTUBE_API_KEY` | Playlist and video metadata crawler | **$0.00 / Free** (Google Cloud Free Tier: 10,000 quota units/day) |
| **Groq Cloud API** *(Optional)* | `GROQ_API_KEY` | Cloud inference fallback | **Free Tier** available; paid tier is ~$0.05 to $0.15 per 1M tokens |
| **Admin Protection** | `ADMIN_API_KEY` | Crawler protection (`X-Admin-Key`) | **$0.00 / Free** (Application-level secret key) |

> **Total Ongoing Operating Cost:** **$0.00 / month** in the default offline configuration.

---

## 6. Token Usage & Context Budget

| Component | Token Allocation | Purpose |
| :--- | :--- | :--- |
| **System Grounding Prompt** | ~180 – 250 tokens | Grounding instructions, JSON schema formatting, injection safeguards |
| **Retrieved Context (Top-5 Chunks)**| ~800 – 1,500 tokens | 5 relevant document snippets (capped at 6,000 characters) |
| **Conversation History (6 Turns)** | ~200 – 600 tokens | Rolling context window of previous exchanges (`SESSION_MAX_TURNS=6`) |
| **User Question + Filters** | ~15 – 50 tokens | Current query + course/subject/topic filters |
| **Total Prompt Input** | **~1,200 – 2,400 tokens** | Sent to the LLM per turn |
| **LLM Output (Completion)** | **~200 – 450 tokens** | Parsed JSON object containing `answer` and 2–4 `follow_up_questions` |

---

## 7. Test Suite & Verification Results

The backend contains a test suite executed via `pytest`:

* **Total Test Cases:** **55 passed** (0 failures, 100% pass rate)
* **Execution Time:** ~13.30s

### Validated Test Modules:
1. **Ollama Integration (`tests/test_core.py`):**
   * Successful completion and JSON extraction.
   * `llm_unreachable` exception when Ollama service is stopped.
   * `llm_model_rejected` when specified model is not downloaded.
   * `llm_bad_response` for malformed LLM outputs.
   * Dynamic container dependency injection (`ollama` vs `groq`).
2. **Authentication Security (`app/core/auth.py`):**
   * Missing `Authorization: Bearer <token>` returns `401 Unauthorized`.
   * Invalid or expired tokens return `401 Unauthorized`.
   * Protection on `/api/v1/chat` and `/api/v1/sessions/*`.
3. **Admin Endpoints:**
   * Ingestion routes protected by `X-Admin-Key` header (401/403).
   * Safe 503 response if admin key is unconfigured.
4. **Vector Database & Retrieval:**
   * Detection and graceful degradation on embedding model version mismatch.
   * Distance threshold filtering for unrelated queries.
   * Multi-turn session expiration and memory TTL management.

---

## 8. Current System Environment (`backend/.env`)

```ini
# Provider: "ollama" (offline/local) or "groq" (cloud)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:latest

# Embeddings & Vector Storage
EMBEDDING_MODEL=all-MiniLM-L6-v2
CHROMA_PERSIST_DIRECTORY=../data/chroma

# RAG Hyperparameters
CHUNK_SIZE=800
CHUNK_OVERLAP=120
RETRIEVAL_TOP_K=5
RETRIEVAL_FETCH_K=15
RELEVANCE_THRESHOLD=0.35
MAX_CONTEXT_CHARS=6000

# Timeouts & Sessions
LLM_TIMEOUT_SECONDS=120
SESSION_MAX_TURNS=6

# Authentication
FIREBASE_AUTH_REQUIRED=true
```
