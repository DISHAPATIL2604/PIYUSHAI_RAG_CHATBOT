"""Website + YouTube ingestion. Writes (a) RAG chunks to the chunk index and (b) structured catalogs."""
import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from typing import Iterator
from urllib.parse import urlparse

import requests

from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.catalog import CourseRecord, VideoRecord
from app.schemas.ingestion import IngestionSummary
from app.services.catalog_service import CatalogService
from app.services.crawler import Crawler, PageContent
from app.services.embedding_service import EmbeddingProvider
from app.services.taxonomy import Taxonomy
from app.services.vector_store import VectorStore

log = logging.getLogger(__name__)

PRICE_RE = re.compile(r"(?:₹|Rs\.?\s?|INR\s?|\$)\s?\d[\d,]*(?:\.\d+)?")
COURSE_PAGE_RE = re.compile(r"/courses?/[^/]+", re.I)
BATCH = 64


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(*parts: str, n: int = 32) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:n]


def chunk_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    """Paragraph/sentence-aware chunks with word-aligned overlap."""
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    if not text:
        return []
    pieces: list[str] = []
    for para in re.split(r"\n{2,}", text):
        para = para.strip()
        if not para:
            continue
        units = [para] if len(para) <= size else re.split(r"(?<=[.!?])\s+", para)
        for u in units:
            while len(u) > size:  # very long sentence: hard split on a space
                cut = u.rfind(" ", 0, size)
                cut = cut if cut > 0 else size
                pieces.append(u[:cut].strip())
                u = u[cut:].strip()
            if u:
                pieces.append(u)
    chunks: list[str] = []
    cur = ""
    for p in pieces:
        if cur and len(cur) + 1 + len(p) > size:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap > 0 else ""
            if tail and " " in tail:
                tail = tail[tail.index(" ") + 1:]
            cur = f"{tail} {p}".strip()
        else:
            cur = f"{cur}\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def classify(url: str, title: str) -> str:
    path = urlparse(url).path.lower()
    if re.search(r"/courses?\b|/batch|/program", path):
        return "course"
    if re.search(r"/blog|/article|/post|/notes|/resources", path):
        return "article"
    if "/about" in path:
        return "about"
    if "/video" in path or "/watch" in path:
        return "video"
    if "/playlist" in path:
        return "playlist"
    return "other"


class _BaseIngestor:
    def __init__(self, settings: Settings, embedder: EmbeddingProvider, chunk_store: VectorStore,
                 catalog: CatalogService, taxonomy: Taxonomy):
        self.s, self.embedder, self.chunks, self.catalog, self.tax = settings, embedder, chunk_store, catalog, taxonomy

    def _replace_chunks(self, source_key: str, key_value: str, doc_title: str, text: str, base_meta: dict) -> int:
        """Delete old chunks of this source, then upsert fresh deterministic ones. Returns chunks written."""
        old = self.chunks.get(where={source_key: key_value})
        if old:
            self.chunks.delete(ids=[h.id for h in old])
        pieces = chunk_text(text, self.s.chunk_size, self.s.chunk_overlap)
        ids = [sha(key_value, str(i), base_meta["content_hash"]) for i in range(len(pieces))]
        for start in range(0, len(pieces), BATCH):
            part = pieces[start:start + BATCH]
            metas = [{**base_meta, "chunk_index": start + j} for j in range(len(part))]
            vecs = self.embedder.embed([f"{doc_title}\n{p}" for p in part])
            self.chunks.upsert(ids[start:start + BATCH], part, metas, vecs)
        return len(pieces)

    def _chunks_unchanged(self, key: str, value: str, content_hash: str) -> bool:
        existing = self.chunks.get(where={key: value})
        return bool(existing) and all(h.metadata.get("content_hash") == content_hash for h in existing)

    def _finish(self, summary: IngestionSummary, started: float) -> IngestionSummary:
        counts = self.catalog.counts()
        summary.courses_in_catalog, summary.videos_in_catalog = counts["courses"], counts["videos"]
        summary.duration_seconds = round(time.monotonic() - started, 2)
        return summary


class WebsiteIngestor(_BaseIngestor):
    def __init__(self, *args, crawler: Crawler | None = None, **kw):
        super().__init__(*args, **kw)
        self.crawler = crawler or Crawler(self.s)

    def run(self, max_pages: int | None = None) -> IngestionSummary:
        started = time.monotonic()
        summary = IngestionSummary(source="websites")
        crawl = self.crawler.crawl(max_pages)
        summary.fetched = crawl.fetched
        summary.errors.extend(crawl.errors)
        for url, reason in crawl.skipped:
            summary.skip(reason, url)
        for page in crawl.pages:
            try:
                self._ingest_page(page, summary)
            except AppError:
                raise
            except Exception as e:  # one bad page must not abort the run
                log.exception("Failed to ingest %s", page.url)
                summary.errors.append(f"{page.url}: {type(e).__name__}")
        return self._finish(summary, started)

    def _ingest_page(self, page: PageContent, summary: IngestionSummary) -> None:
        ctype = classify(page.url, page.title)
        subjects, topics = self.tax.tag(" ".join([page.title, page.description or "", " ".join(page.headings), urlparse(page.url).path.replace("-", " ")]))
        if self._chunks_unchanged("source_url", page.url, page.content_hash):
            summary.unchanged += 1
        else:
            existed = bool(self.chunks.get(where={"source_url": page.url}))
            meta = {"source_url": page.url, "title": page.title or page.url, "content_type": ctype,
                    "subjects": "|" + "|".join(subjects) + "|" if subjects else "", "topics": "|" + "|".join(topics) + "|" if topics else "",
                    "course": self.tax.courses[0] if subjects and self.tax.courses else "", "content_hash": page.content_hash,
                    "indexed_at": now_iso(), "extraction": page.method, "is_sample": False}
            summary.chunks_created += self._replace_chunks("source_url", page.url, page.title, page.text, meta)
            summary.updated += existed
            summary.new += not existed
        if ctype == "course" and COURSE_PAGE_RE.search(urlparse(page.url).path):
            price = PRICE_RE.search(page.text)
            blob = f"{page.title} {page.text[:1500]}"
            exam = self.tax.courses[0] if re.search(r"\bGATE\b", blob, re.I) and re.search(r"\b(DA|data science)\b", blob, re.I) and self.tax.courses else None
            rec = CourseRecord(
                course_id=sha(page.url, n=16), title=page.title or page.url, url=page.url,
                description=page.description or page.text[:500], price=price.group(0).strip() if price else None,
                enrollment_url=page.enroll_url, exam=exam, subjects=subjects, topics=topics,
                source_url=page.url, content_hash=page.content_hash, indexed_at=now_iso())
            self.catalog.upsert_course(rec)


class YouTubeClient:
    BASE = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: str, http_get=requests.get, timeout: float = 15.0):
        self.key, self._get_fn, self.timeout = api_key, http_get, timeout

    def _get(self, path: str, **params) -> dict:
        try:
            r = self._get_fn(self.BASE + path, params={**params, "key": self.key}, timeout=self.timeout)
        except requests.Timeout as e:
            raise AppError(504, "youtube_timeout", "YouTube API timed out.") from e
        except requests.RequestException as e:
            raise AppError(502, "youtube_unreachable", "Could not reach the YouTube API.") from e
        if r.status_code == 200:
            return r.json()
        try:
            reason = (r.json().get("error", {}).get("errors") or [{}])[0].get("reason", "")
        except Exception:
            reason = ""
        if r.status_code in (403, 429) and reason in ("quotaExceeded", "rateLimitExceeded", "dailyLimitExceeded", ""):
            raise AppError(429, "youtube_quota_exceeded", "YouTube API quota or rate limit reached. Try again later (quota resets daily).")
        if r.status_code in (400, 403) and reason in ("keyInvalid", "API_KEY_INVALID", "accessNotConfigured"):
            raise AppError(502, "youtube_key_rejected", "YouTube rejected YOUTUBE_API_KEY (invalid, or YouTube Data API v3 not enabled).")
        raise AppError(502, "youtube_error", f"YouTube API error (HTTP {r.status_code}).")

    def resolve_channel(self, handle: str) -> dict:
        data = self._get("/channels", part="contentDetails,snippet", forHandle="@" + handle.lstrip("@"))
        items = data.get("items") or []
        if not items:
            raise AppError(502, "youtube_channel_not_found", f"No YouTube channel found for handle @{handle.lstrip('@')}.")
        it = items[0]
        return {"channel_id": it["id"], "title": (it.get("snippet") or {}).get("title"),
                "uploads": ((it.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")}

    def playlist_items(self, playlist_id: str) -> Iterator[dict]:
        token = None
        while True:
            params = {"part": "snippet,contentDetails", "playlistId": playlist_id, "maxResults": 50}
            if token:
                params["pageToken"] = token
            data = self._get("/playlistItems", **params)
            for it in data.get("items") or []:
                yield it
            token = data.get("nextPageToken")
            if not token:
                return

    def playlists(self, channel_id: str) -> list[dict]:
        out, token = [], None
        while True:
            params = {"part": "snippet", "channelId": channel_id, "maxResults": 50}
            if token:
                params["pageToken"] = token
            data = self._get("/playlists", **params)
            out.extend(data.get("items") or [])
            token = data.get("nextPageToken")
            if not token:
                return out


class YouTubeIngestor(_BaseIngestor):
    def __init__(self, *args, client: YouTubeClient | None = None, **kw):
        super().__init__(*args, **kw)
        self.client = client

    def run(self, only_new: bool = False, since: str | None = None) -> IngestionSummary:
        started = time.monotonic()
        if self.client is None:
            if not self.s.youtube_api_key:
                raise AppError(503, "youtube_not_configured", "YOUTUBE_API_KEY is not set. Add it to backend/.env to ingest YouTube metadata.")
            self.client = YouTubeClient(self.s.youtube_api_key)
        summary = IngestionSummary(source="youtube")
        ch = self.client.resolve_channel(self.s.youtube_channel_handle)
        pls = self.client.playlists(ch["channel_id"])
        summary.playlists = len(pls)

        videos: dict[str, dict] = {}   # video_id -> {title, description, published}
        member: dict[str, list[tuple[str, str]]] = {}
        sources = [(ch["uploads"], None)] if ch.get("uploads") else []
        sources += [(p["id"], (p.get("snippet") or {}).get("title") or "") for p in pls]
        for pid, ptitle in sources:
            for it in self.client.playlist_items(pid):
                sn = it.get("snippet") or {}
                vid = (it.get("contentDetails") or {}).get("videoId") or (sn.get("resourceId") or {}).get("videoId")
                title = sn.get("title")
                if not vid or not title or title in ("Private video", "Deleted video"):
                    summary.skip("unavailable_video", vid)
                    continue
                v = videos.setdefault(vid, {"title": title, "description": sn.get("description") or None,
                                            "published": (it.get("contentDetails") or {}).get("videoPublishedAt") or sn.get("publishedAt")})
                if ptitle is not None:
                    member.setdefault(vid, []).append((pid, ptitle))
        for vid, v in videos.items():
            summary.fetched += 1
            if since and v["published"] and v["published"] < since:
                summary.skip("older_than_since", vid)
                continue
            mem = member.get(vid, [])
            chash = hashlib.sha256("|".join([v["title"], v["description"] or "", *sorted(t for _, t in mem)]).encode()).hexdigest()
            existing = self.catalog.get_video(vid)
            if existing and (only_new or existing.content_hash == chash):
                summary.unchanged += 1
                continue
            url = f"https://www.youtube.com/watch?v={vid}"
            subjects, topics = self.tax.tag(" ".join([v["title"], v["description"] or "", " ".join(t for _, t in mem)]))
            rec = VideoRecord(video_id=vid, title=v["title"], url=url, description=v["description"], published_at=v["published"],
                              playlist_ids=[p for p, _ in mem], playlist_titles=[t for _, t in mem], subjects=subjects, topics=topics,
                              has_transcript=False, source="youtube_api", content_hash=chash, indexed_at=now_iso())
            status = self.catalog.upsert_video(rec)
            meta = {"source_url": url, "video_id": vid, "title": rec.title, "content_type": "video",
                    "subjects": "|" + "|".join(subjects) + "|" if subjects else "", "topics": "|" + "|".join(topics) + "|" if topics else "",
                    "course": self.tax.courses[0] if subjects and self.tax.courses else "", "content_hash": chash,
                    "indexed_at": now_iso(), "extraction": "youtube_api", "is_sample": False}
            text = f"{rec.title}\n\n{rec.description or ''}\n\nPlaylists: {', '.join(rec.playlist_titles)}".strip()
            summary.chunks_created += self._replace_chunks("video_id", vid, rec.title, text, meta)
            summary.new += status == "new"
            summary.updated += status == "updated"
        for p in pls:
            sn = p.get("snippet") or {}
            if not sn.get("title"):
                continue
            purl = f"https://www.youtube.com/playlist?list={p['id']}"
            phash = hashlib.sha256(f"{sn['title']}|{sn.get('description') or ''}".encode()).hexdigest()
            if self._chunks_unchanged("source_url", purl, phash):
                continue
            subjects, topics = self.tax.tag(f"{sn['title']} {sn.get('description') or ''}")
            meta = {"source_url": purl, "title": sn["title"], "content_type": "playlist",
                    "subjects": "|" + "|".join(subjects) + "|" if subjects else "", "topics": "|" + "|".join(topics) + "|" if topics else "",
                    "course": self.tax.courses[0] if subjects and self.tax.courses else "", "content_hash": phash,
                    "indexed_at": now_iso(), "extraction": "youtube_api", "is_sample": False}
            summary.chunks_created += self._replace_chunks("source_url", purl, sn["title"], f"{sn['title']}\n\n{sn.get('description') or ''}", meta)
        return self._finish(summary, started)
