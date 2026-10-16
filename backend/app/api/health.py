from fastapi import APIRouter, Request

from app.container import get_container

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
def health(request: Request):
    c = get_container(request)
    s = c.settings
    info = {"status": "ok", "version": s.app_version, "embedding_model": s.embedding_model,
            "llm_provider": s.llm_provider,
            "llm_model": s.ollama_model if s.llm_provider == "ollama" else s.groq_model,
            "ollama_configured": s.llm_provider == "ollama",
            "groq_configured": bool(s.groq_api_key), "youtube_configured": bool(s.youtube_api_key),
            "admin_key_configured": bool(s.admin_api_key)}
    try:
        info.update(vector_store_reachable=True, indexed_chunks=c.chunk_store.count(), **{
            "indexed_" + k: v for k, v in c.catalog.counts().items()})
    except Exception as e:  # e.g. embedding model mismatch
        info.update(status="degraded", vector_store_reachable=False, vector_store_error=getattr(e, "message", type(e).__name__))
    return info
