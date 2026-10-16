"""Environment-based configuration (loaded from backend/.env)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "PiyushAI RAG Chatbot"
    app_version: str = "0.1.0"

    # Secrets / providers
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:latest"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    youtube_api_key: str = ""
    admin_api_key: str = ""
    firebase_project_id: str = ""
    firebase_auth_required: bool = False

    # Storage
    chroma_persist_directory: str = "../data/chroma"
    catalog_directory: str = "../data/catalog"
    backend_cors_origins: str = "http://localhost:5173"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"

    # Chunking / retrieval
    chunk_size: int = 800
    chunk_overlap: int = 120
    retrieval_top_k: int = 5
    retrieval_fetch_k: int = 15
    relevance_threshold: float = 0.35
    max_context_chars: int = 6000
    max_message_chars: int = 2000

    # Recommendations
    recommendation_min_score: float = 0.45
    allow_sample_data: bool = False
    rec_w_semantic: float = 0.60
    rec_w_subject: float = 0.20
    rec_w_topic: float = 0.15
    rec_w_course: float = 0.05
    rec_w_recency: float = 0.03

    # Generation
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1500
    llm_timeout_seconds: float = 30.0
    llm_retry_max_wait_seconds: float = 5.0
    session_max_turns: int = 6
    session_max_messages: int = 200
    session_max_sessions: int = 1000
    session_ttl_seconds: int = 6 * 3600

    # Crawling
    crawl_user_agent: str = "PiyushAI-RAG-Bot/0.1 (educational project)"
    crawl_delay_seconds: float = 1.0
    crawl_max_pages: int = 100
    crawl_max_depth: int = 3
    crawl_min_text_chars: int = 300
    crawl_timeout_seconds: float = 20.0
    enable_playwright: bool = False
    crawl_seed_urls: str = "https://piyushai.com/,https://www.piyushwairale.com/"
    official_domains: str = "piyushai.com,piyushwairale.com"
    youtube_channel_handle: str = "piyushwairaleiitm"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    @property
    def seed_urls(self) -> list[str]:
        return [u.strip() for u in self.crawl_seed_urls.split(",") if u.strip()]

    @property
    def domains(self) -> list[str]:
        return [d.strip().lower() for d in self.official_domains.split(",") if d.strip()]

    def resolve_path(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()

    @property
    def chroma_path(self) -> Path:
        return self.resolve_path(self.chroma_persist_directory)

    @property
    def catalog_path(self) -> Path:
        return self.resolve_path(self.catalog_directory)


@lru_cache
def get_settings() -> Settings:
    return Settings()
