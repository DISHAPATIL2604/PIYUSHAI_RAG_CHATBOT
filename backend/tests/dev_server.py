"""Offline dev/E2E server: REAL FastAPI + REAL ChromaDB persistence, but MOCKED embedder and LLM, plus SAMPLE data.
    uvicorn tests.dev_server:app --port 8000
Never use for production answers: embeddings are a toy bag-of-words and answers are canned."""
import json
import os
import tempfile
from pathlib import Path

from app.container import Container
from app.main import create_app
from tests.conftest import SAMPLE, FakeEmbedder, FakeLLM, index_chunk, make_settings

root = Path(os.environ.get("DEV_DATA_DIR") or tempfile.mkdtemp(prefix="piyushai-dev-"))
settings = make_settings(root, allow_sample_data=True)
llm = FakeLLM(lambda m: json.dumps({"answer": "DEV-MODE canned answer (mock LLM). Context size: %d chars." % len(m[-1]["content"]),
                                    "follow_up_questions": ["What is the cost function?", "How do I evaluate the model?"]}))
container = Container.build(settings, embedder=FakeEmbedder(), llm=llm)
if container.chunk_store.count() == 0:
    container.catalog.load_sample(SAMPLE)
    index_chunk(container, "https://example.invalid/sample/blog/linear-regression", "[SAMPLE] Linear Regression",
                "SAMPLE DATA. Linear regression fits a straight line to data by minimising squared error.", ["Machine Learning"])
app = create_app(container)
