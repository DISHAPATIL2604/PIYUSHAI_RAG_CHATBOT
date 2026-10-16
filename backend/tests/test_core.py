"""Health, admin key, validation, sessions, embedding mismatch."""
import pytest
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.main import create_app
from app.services.session_service import InMemorySessionStore
from app.services.vector_store import ChromaVectorStore
from tests.conftest import FakeEmbedder, make_settings


def test_health_has_no_secrets(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["embedding_model"] == "all-MiniLM-L6-v2"
    assert body["groq_configured"] is True and body["youtube_configured"] is True
    assert {"indexed_chunks", "indexed_courses", "indexed_videos"} <= body.keys()
    assert "test-groq-key" not in r.text and "admin-secret" not in r.text and "test-yt-key" not in r.text


@pytest.mark.parametrize("headers,status", [({}, 401), ({"X-Admin-Key": "wrong"}, 403)])
def test_admin_missing_or_wrong_key(client, headers, status):
    assert client.post("/api/v1/ingestion/websites", headers=headers).status_code == status
    assert client.post("/api/v1/ingestion/youtube", headers=headers).status_code == status


def test_admin_unconfigured_server_key_fails_closed(build):
    c = TestClient(create_app(build(admin_api_key="")))
    r = c.post("/api/v1/ingestion/websites", headers={"X-Admin-Key": "anything"})
    assert r.status_code == 503 and "ADMIN_API_KEY" in r.json()["error"]["message"]


def test_admin_correct_key_passes_guard(build):
    c = TestClient(create_app(build(youtube_api_key="")))
    r = c.post("/api/v1/ingestion/youtube", headers={"X-Admin-Key": "admin-secret"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "youtube_not_configured"  # got past the guard


def test_courses_and_subjects(client):
    assert client.get("/api/v1/courses").json()["exams"] == ["GATE DA"]
    subs = client.get("/api/v1/subjects", params={"course": "gate da"}).json()["subjects"]
    assert any(s["name"] == "Machine Learning" and "Linear Regression" in s["topics"] for s in subs)
    assert client.get("/api/v1/subjects", params={"course": "nope"}).status_code == 404


# ---- sessions -----------------------------------------------------------
def test_session_store_contract():
    now = [0.0]
    st = InMemorySessionStore(max_messages=4, ttl_seconds=100, clock=lambda: now[0])
    assert st.history("s") is None
    for i in range(3):
        st.append("s", "user", f"u{i}")
        st.append("s", "assistant", f"a{i}")
    h = st.history("s")
    assert [m["content"] for m in h] == ["u1", "a1", "u2", "a2"]  # capped, ordered
    assert [m["content"] for m in st.recent("s", 1)] == ["u2", "a2"]
    now[0] = 500
    assert st.history("s") is None  # TTL expiry
    st.append("x", "user", "hi")
    assert st.delete("x") is True and st.delete("x") is False


def test_history_endpoint_404_and_delete(client):
    assert client.get("/api/v1/sessions/nope/history").status_code == 404
    sid = client.post("/api/v1/chat", json={"message": "Explain gradient descent"}).json()["session_id"]
    msgs = client.get(f"/api/v1/sessions/{sid}/history").json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert client.delete(f"/api/v1/sessions/{sid}").json()["deleted"] is True
    assert client.get(f"/api/v1/sessions/{sid}/history").status_code == 404


# ---- embedding model mismatch -------------------------------------------------
def test_embedding_model_mismatch(tmp_path, build):
    path = str(tmp_path / "mm")
    a = ChromaVectorStore(path, "chunks", "model-A")
    a.upsert(["1"], ["doc"], [{"k": "v"}], [[0.1] * 4])
    b = ChromaVectorStore(path, "chunks", "model-B")
    with pytest.raises(AppError) as e:
        b.count()
    assert e.value.code == "embedding_model_mismatch" and "model-A" in e.value.message and "Re-ingest" in e.value.message
    # health reports degraded rather than crashing
    c = build(chroma_persist_directory=path)
    r = TestClient(create_app(c)).get("/api/v1/health").json()
    assert r["status"] == "degraded" and r["vector_store_reachable"] is False


# ---- Ollama LLM client -------------------------------------------------------
import requests as req_mod

from tests.conftest import FakeResponse
from app.services.generation_service import OllamaLLMClient


def _make_ollama_settings(tmp_path, **kw):
    return make_settings(tmp_path, llm_provider="ollama", ollama_model="llama3.2:latest",
                         ollama_base_url="http://localhost:11434", **kw)


def test_ollama_success(tmp_path):
    reply = {"message": {"role": "assistant", "content": '{"answer": "Chroma is a vector DB.", "follow_up_questions": []}'}}
    client = OllamaLLMClient(_make_ollama_settings(tmp_path),
                             http_post=lambda *a, **k: FakeResponse(200, reply))
    result = client.complete([{"role": "user", "content": "What is Chroma?"}])
    assert "Chroma" in result


def test_ollama_unreachable(tmp_path):
    def fail(*a, **k):
        raise req_mod.ConnectionError("refused")
    client = OllamaLLMClient(_make_ollama_settings(tmp_path), http_post=fail)
    with pytest.raises(AppError) as e:
        client.complete([{"role": "user", "content": "hi"}])
    assert e.value.code == "llm_unreachable"


def test_ollama_model_not_found(tmp_path):
    body = {"error": "model 'llama3.2:latest' not found, try pulling it first"}
    client = OllamaLLMClient(_make_ollama_settings(tmp_path),
                             http_post=lambda *a, **k: FakeResponse(404, body))
    with pytest.raises(AppError) as e:
        client.complete([{"role": "user", "content": "hi"}])
    assert e.value.code == "llm_model_rejected"


def test_ollama_malformed_response(tmp_path):
    client = OllamaLLMClient(_make_ollama_settings(tmp_path),
                             http_post=lambda *a, **k: FakeResponse(200, {"nope": 1}))
    with pytest.raises(AppError) as e:
        client.complete([{"role": "user", "content": "hi"}])
    assert e.value.code == "llm_bad_response"


def test_provider_selection_ollama(tmp_path):
    from app.container import Container
    from tests.conftest import FakeEmbedder
    s = _make_ollama_settings(tmp_path)
    c = Container.build(s, embedder=FakeEmbedder())
    assert isinstance(c.llm, OllamaLLMClient)


def test_provider_selection_groq(tmp_path):
    from app.container import Container
    from app.services.generation_service import GroqLLMClient
    s = make_settings(tmp_path, llm_provider="groq")
    c = Container.build(s, embedder=FakeEmbedder())
    assert isinstance(c.llm, GroqLLMClient)


def test_health_shows_ollama_provider(client):
    r = client.get("/api/v1/health").json()
    # tests use groq provider (make_settings default)
    assert "llm_provider" in r and "llm_model" in r
