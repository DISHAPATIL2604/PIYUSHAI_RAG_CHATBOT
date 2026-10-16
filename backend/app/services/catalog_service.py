"""Structured course/video catalogs: JSON files are the source of truth; Chroma collections give semantic matching."""
import json
import logging
import re
import threading
from pathlib import Path
from urllib.parse import urlparse

from app.schemas.catalog import CourseRecord, VideoRecord
from app.services.embedding_service import EmbeddingProvider
from app.services.vector_store import VectorStore

log = logging.getLogger(__name__)


def course_embedding_text(r: CourseRecord) -> str:
    return f"{r.title}. {r.description or ''} Subjects: {', '.join(r.subjects)}. Topics: {', '.join(r.topics)}".strip()


def video_embedding_text(r: VideoRecord) -> str:
    return f"{r.title}. {(r.description or '')[:600]} Playlists: {', '.join(r.playlist_titles)}. Topics: {', '.join(r.topics)}".strip()


class CatalogService:
    def __init__(self, base_dir: Path, course_store: VectorStore, video_store: VectorStore,
                 embedder: EmbeddingProvider, official_domains: list[str]):
        self.base_dir = Path(base_dir)
        self.course_store, self.video_store, self.embedder = course_store, video_store, embedder
        self.official_domains = [d.lower() for d in official_domains]
        self._lock = threading.RLock()

    # ---- persistence -------------------------------------------------
    def _file(self, kind: str) -> Path:
        return self.base_dir / f"{kind}s.json"

    def _load(self, kind: str) -> dict[str, dict]:
        f = self._file(kind)
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}

    def _save(self, kind: str, data: dict) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._file(kind).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._file(kind))

    # ---- upserts (return "new" | "updated" | "unchanged") -----------------
    def upsert_course(self, rec: CourseRecord) -> str:
        return self._upsert("course", rec.course_id, rec, self.course_store, course_embedding_text(rec))

    def upsert_video(self, rec: VideoRecord) -> str:
        return self._upsert("video", rec.video_id, rec, self.video_store, video_embedding_text(rec))

    def _upsert(self, kind, rid, rec, store: VectorStore, text: str) -> str:
        with self._lock:
            data = self._load(kind)
            old = data.get(rid)
            if old and old.get("content_hash") == rec.content_hash and old.get("is_sample") == rec.is_sample:
                return "unchanged"
            data[rid] = rec.model_dump()
            self._save(kind, data)
            store.upsert([rid], [text], [{"id": rid, "kind": kind, "is_sample": rec.is_sample}], self.embedder.embed([text]))
            return "updated" if old else "new"

    # ---- reads -----------------------------------------------------------
    def get_course(self, cid: str) -> CourseRecord | None:
        d = self._load("course").get(cid)
        return CourseRecord(**d) if d else None

    def get_video(self, vid: str) -> VideoRecord | None:
        d = self._load("video").get(vid)
        return VideoRecord(**d) if d else None

    def list_courses(self, exam: str | None = None, include_sample: bool = True) -> list[CourseRecord]:
        recs = [CourseRecord(**d) for d in self._load("course").values()]
        return [r for r in recs if (include_sample or not r.is_sample) and (not exam or (r.exam or "").lower() == exam.lower())]

    def list_videos(self, include_sample: bool = True) -> list[VideoRecord]:
        return [VideoRecord(**d) for d in self._load("video").values() if include_sample or not d.get("is_sample")]

    def counts(self) -> dict[str, int]:
        return {"courses": len(self._load("course")), "videos": len(self._load("video"))}

    def all_urls(self) -> set[str]:
        return {d["url"] for k in ("course", "video") for d in self._load(k).values()}

    # ---- validation ------------------------------------------------------
    def is_official_host(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in self.official_domains)

    def validate_url_matches_record(self, kind: str, rid: str, url: str, allow_sample: bool = False) -> bool:
        rec = self.get_course(rid) if kind == "course" else self.get_video(rid)
        if rec is None or url != rec.url:
            return False
        if rec.is_sample:
            return allow_sample
        if kind == "course":
            return self.is_official_host(url)
        return re.fullmatch(r"https://www\.youtube\.com/watch\?v=" + re.escape(rec.video_id), url) is not None

    # ---- sample data (clearly labelled, never official) --------------------
    def load_sample(self, path: Path) -> tuple[int, int]:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for c in data.get("courses", []):
            self.upsert_course(CourseRecord(**{**c, "is_sample": True}))
        for v in data.get("videos", []):
            self.upsert_video(VideoRecord(**{**v, "is_sample": True}))
        return len(data.get("courses", [])), len(data.get("videos", []))
