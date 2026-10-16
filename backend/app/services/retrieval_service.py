"""Query -> embedding -> similarity search -> threshold, dedupe, context cap."""
import re
from dataclasses import dataclass

from app.core.config import Settings
from app.services.embedding_service import EmbeddingProvider
from app.services.vector_store import VectorStore


@dataclass
class RetrievedChunk:
    id: str
    text: str
    url: str
    title: str
    content_type: str
    score: float
    subjects: list[str]


def _norm(t: str) -> str:
    return re.sub(r"\W+", " ", t.lower()).strip()


class RetrievalService:
    def __init__(self, settings: Settings, embedder: EmbeddingProvider, chunk_store: VectorStore):
        self.s, self.embedder, self.store = settings, embedder, chunk_store

    def retrieve(self, query: str, course: str | None = None, subject: str | None = None) -> list[RetrievedChunk]:
        """Similarity = 1 - cosine distance (Chroma collections use cosine space).
        Course and subject act as soft metadata preferences: chunks tagged with the selected subject/course rank
        first, but untagged official pages (pricing, enrollment, about) are never excluded."""
        s = self.s
        vec = self.embedder.embed_one(query)
        hits = self.store.query(vec, s.retrieval_fetch_k, None)
        hits = [h for h in hits if h.score >= s.relevance_threshold]
        marker = f"|{subject}|" if subject else None
        hits.sort(key=lambda h: (0 if marker and marker in h.metadata.get("subjects", "") else 1,
                                 0 if course and h.metadata.get("course") == course else 1, -h.score))
        out, seen_text, used_chars = [], set(), 0
        for h in hits:
            key = _norm(h.document)[:200]
            if key in seen_text:
                continue
            if used_chars + len(h.document) > s.max_context_chars and out:
                break
            seen_text.add(key)
            used_chars += len(h.document)
            m = h.metadata
            out.append(RetrievedChunk(h.id, h.document, m.get("source_url", ""), m.get("title") or m.get("source_url", ""),
                                      m.get("content_type", "other"), round(h.score, 4),
                                      [x for x in m.get("subjects", "").split("|") if x]))
            if len(out) >= s.retrieval_top_k:
                break
        return out
