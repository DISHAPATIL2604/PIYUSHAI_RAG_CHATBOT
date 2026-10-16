"""VectorStore interface + ChromaDB implementation (cosine space, persistent)."""
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.errors import AppError


@dataclass
class VectorHit:
    id: str
    document: str
    metadata: dict
    score: float  # cosine similarity in [-1, 1]; for Chroma cosine distance d: similarity = 1 - d


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, ids: list[str], documents: list[str], metadatas: list[dict], embeddings: list[list[float]]) -> None: ...

    @abstractmethod
    def query(self, embedding: list[float], n: int, where: dict | None = None) -> list[VectorHit]: ...

    @abstractmethod
    def get(self, where: dict | None = None, ids: list[str] | None = None) -> list[VectorHit]: ...

    @abstractmethod
    def delete(self, ids: list[str] | None = None, where: dict | None = None) -> None: ...

    @abstractmethod
    def count(self) -> int: ...


_clients: dict[str, object] = {}
_clients_lock = threading.Lock()


def _client(path: str):
    import chromadb

    with _clients_lock:
        if path not in _clients:
            _clients[path] = chromadb.PersistentClient(path=path)
        return _clients[path]


def _clean(meta: dict) -> dict:
    return {k: v for k, v in meta.items() if v is not None and isinstance(v, (str, int, float, bool))}


class ChromaVectorStore(VectorStore):
    """One Chroma collection. The embedding model name is stored in the collection metadata;
    opening a collection built with a different model raises a clear error instead of mixing vectors."""

    def __init__(self, persist_dir: str, name: str, embedding_model: str):
        self.persist_dir, self.name, self.embedding_model = str(persist_dir), name, embedding_model
        self._collection = None
        self._lock = threading.Lock()

    @property
    def col(self):
        with self._lock:
            if self._collection is None:
                col = _client(self.persist_dir).get_or_create_collection(
                    name=self.name, metadata={"hnsw:space": "cosine", "embedding_model": self.embedding_model}
                )
                built_with = (col.metadata or {}).get("embedding_model")
                if built_with and built_with != self.embedding_model:
                    raise AppError(
                        409, "embedding_model_mismatch",
                        f"Collection '{self.name}' was built with embedding model '{built_with}' but EMBEDDING_MODEL is "
                        f"'{self.embedding_model}'. Re-ingest into a fresh CHROMA_PERSIST_DIRECTORY (or delete the old one), "
                        f"or set EMBEDDING_MODEL back to '{built_with}'.",
                    )
                self._collection = col
            return self._collection

    def upsert(self, ids, documents, metadatas, embeddings):
        if ids:
            self.col.upsert(ids=ids, documents=documents, metadatas=[_clean(m) for m in metadatas], embeddings=embeddings)

    def query(self, embedding, n, where=None):
        total = self.col.count()
        if total == 0:
            return []
        res = self.col.query(query_embeddings=[embedding], n_results=min(n, total), where=where or None,
                             include=["documents", "metadatas", "distances"])
        return [
            VectorHit(i, d, m or {}, 1.0 - float(dist))
            for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])
        ]

    def get(self, where=None, ids=None):
        res = self.col.get(ids=ids, where=where or None, include=["documents", "metadatas"])
        return [VectorHit(i, d, m or {}, 1.0) for i, d, m in zip(res["ids"], res["documents"], res["metadatas"])]

    def delete(self, ids=None, where=None):
        if ids:
            self.col.delete(ids=ids)
        elif where:
            self.col.delete(where=where)

    def count(self) -> int:
        return self.col.count()
