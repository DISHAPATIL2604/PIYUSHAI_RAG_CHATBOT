"""Embedding provider interface + local Sentence Transformers implementation (no paid API)."""
import logging
import threading
from abc import ABC, abstractmethod

from app.core.errors import AppError

log = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    model_name: str

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return L2-normalised vectors (so cosine similarity == dot product)."""

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Loads the model lazily on first use. The first run downloads it from Hugging Face (~90 MB for MiniLM)."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                try:
                    from sentence_transformers import SentenceTransformer

                    try:
                        self._model = SentenceTransformer(self.model_name, local_files_only=True)
                    except Exception:
                        self._model = SentenceTransformer(self.model_name)
                except ImportError as e:
                    raise AppError(503, "embedding_unavailable", "sentence-transformers is not installed. Run: pip install -r requirements.txt") from e
                except Exception as e:  # network / model-name problems
                    raise AppError(
                        503, "embedding_unavailable",
                        f"Could not load embedding model '{self.model_name}'. The first run needs internet access to download it. "
                        f"Check EMBEDDING_MODEL. ({type(e).__name__})",
                    ) from e
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        return model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False).tolist()
