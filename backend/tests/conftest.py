"""Shared fakes. No network, no model downloads: embeddings are a deterministic hashed bag-of-words."""
import json
import math
import re
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.container import Container
from app.core.config import Settings
from app.main import create_app
from app.services.crawler import Crawler, FetchResult
from app.services.embedding_service import EmbeddingProvider
from app.services.generation_service import LLMClient

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "sample" / "sample_catalog.json"
STOP = set("the a an is of to and in for what how explain does do i me my you are on it this that with about can why".split())


class FakeEmbedder(EmbeddingProvider):
    model_name = "fake-bow"

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * 512
            for tok in re.findall(r"[a-z0-9]+", t.lower()):
                if tok not in STOP:
                    v[zlib.crc32(tok.encode()) % 512] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


class FakeLLM(LLMClient):
    def __init__(self, reply=None):
        self.reply, self.calls, self.last_messages = reply, 0, None

    def complete(self, messages):
        self.calls += 1
        self.last_messages = messages
        r = self.reply(messages) if callable(self.reply) else self.reply
        if isinstance(r, Exception):
            raise r
        return r if r is not None else json.dumps({"answer": "Test answer.", "follow_up_questions": ["Q one?", "Q two?"]})


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body if body is not None else {}, headers or {}

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def make_settings(tmp_path, **kw) -> Settings:
    base = dict(_env_file=None, chroma_persist_directory=str(tmp_path / "chroma"), catalog_directory=str(tmp_path / "catalog"),
                groq_api_key="test-groq-key", youtube_api_key="test-yt-key", admin_api_key="admin-secret",
                llm_provider="groq", relevance_threshold=0.2, crawl_delay_seconds=0, crawl_seed_urls="https://piyushai.com/")
    base.update(kw)
    return Settings(**base)


def fake_fetcher(site: dict[str, FetchResult | str]):
    calls = []

    def fetch(url):
        calls.append(url)
        v = site.get(url)
        if v is None:
            return FetchResult(404, "", "text/html", url)
        return v if isinstance(v, FetchResult) else FetchResult(200, v, "text/html", url)

    fetch.calls = calls
    return fetch


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def build(tmp_path):
    def _build(**kw):
        llm = kw.pop("llm", FakeLLM())
        build_kw = {k: kw.pop(k) for k in ("crawler", "youtube_client", "sessions") if k in kw}
        s = make_settings(tmp_path, **kw)
        return Container.build(s, embedder=FakeEmbedder(), llm=llm, **build_kw)

    return _build


@pytest.fixture
def container(build):
    return build()


@pytest.fixture
def client(container):
    return TestClient(create_app(container))


def index_chunk(c: Container, url: str, title: str, text: str, subjects=(), ctype="article", course=""):
    meta = {"source_url": url, "title": title, "content_type": ctype, "subjects": "|" + "|".join(subjects) + "|" if subjects else "",
            "topics": "", "course": course, "content_hash": "h-" + url, "indexed_at": "2026-01-01", "is_sample": False}
    c.chunk_store.upsert([f"id-{url}"], [text], [meta], c.embedder.embed([f"{title}\n{text}"]))
