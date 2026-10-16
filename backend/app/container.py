"""Dependency container: builds all services once; tests can inject fakes."""
import threading
from dataclasses import dataclass

from fastapi import Request

from app.core.config import Settings
from app.services.catalog_service import CatalogService
from app.services.chat_service import ChatService
from app.services.embedding_service import EmbeddingProvider, SentenceTransformerEmbeddingProvider
from app.services.generation_service import GenerationService, GroqLLMClient, LLMClient, OllamaLLMClient
from app.services.ingestion_service import WebsiteIngestor, YouTubeIngestor
from app.services.recommendation_service import RecommendationService
from app.services.retrieval_service import RetrievalService
from app.services.session_service import InMemorySessionStore, SessionStore
from app.services.taxonomy import Taxonomy
from app.services.vector_store import ChromaVectorStore, VectorStore


@dataclass
class Container:
    settings: Settings
    taxonomy: Taxonomy
    embedder: EmbeddingProvider
    chunk_store: VectorStore
    course_store: VectorStore
    video_store: VectorStore
    catalog: CatalogService
    sessions: SessionStore
    llm: LLMClient
    retrieval: RetrievalService
    recommender: RecommendationService
    generation: GenerationService
    chat: ChatService
    website_ingestor: WebsiteIngestor
    youtube_ingestor: YouTubeIngestor

    @classmethod
    def build(cls, settings: Settings, embedder: EmbeddingProvider | None = None, llm: LLMClient | None = None,
              sessions: SessionStore | None = None, crawler=None, youtube_client=None) -> "Container":
        tax = Taxonomy.load()
        embedder = embedder or SentenceTransformerEmbeddingProvider(settings.embedding_model)
        path, model = str(settings.chroma_path), settings.embedding_model
        chunks = ChromaVectorStore(path, "chunks", model)
        courses = ChromaVectorStore(path, "courses", model)
        videos = ChromaVectorStore(path, "videos", model)
        catalog = CatalogService(settings.catalog_path, courses, videos, embedder, settings.domains)
        sessions = sessions or InMemorySessionStore(settings.session_max_messages, settings.session_max_sessions, settings.session_ttl_seconds)
        if llm is None:
            if settings.llm_provider.lower() == "ollama":
                llm = OllamaLLMClient(settings)
            else:
                llm = GroqLLMClient(settings)
        retrieval = RetrievalService(settings, embedder, chunks)
        recommender = RecommendationService(settings, embedder, catalog, tax, courses, videos)
        generation = GenerationService(settings, llm)
        chat = ChatService(settings, tax, catalog, sessions, retrieval, generation, recommender)
        web = WebsiteIngestor(settings, embedder, chunks, catalog, tax, crawler=crawler)
        yt = YouTubeIngestor(settings, embedder, chunks, catalog, tax, client=youtube_client)
        return cls(settings, tax, embedder, chunks, courses, videos, catalog, sessions, llm, retrieval, recommender, generation, chat, web, yt)


_lock = threading.Lock()


def get_container(request: Request) -> Container:
    app = request.app
    if getattr(app.state, "container", None) is None:
        with _lock:
            if getattr(app.state, "container", None) is None:
                from app.core.config import get_settings

                app.state.container = Container.build(get_settings())
    return app.state.container
