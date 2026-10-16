"""Course/video recommendations from the structured catalogs only. Never uses LLM text or free-form chunks.

score = w_semantic * cosine(query, record) + w_subject * [subject match] + w_topic * [topic match]
        + w_course * [selected exam match] (+ w_recency * recency for videos)
A record is returned only if score >= RECOMMENDATION_MIN_SCORE AND its URL validates against the catalog.
"""
import logging
from datetime import datetime, timezone

from app.core.config import Settings
from app.schemas.chat import Recommendation
from app.services.catalog_service import CatalogService
from app.services.embedding_service import EmbeddingProvider
from app.services.taxonomy import Taxonomy
from app.services.vector_store import VectorStore

log = logging.getLogger(__name__)


class RecommendationService:
    def __init__(self, settings: Settings, embedder: EmbeddingProvider, catalog: CatalogService, taxonomy: Taxonomy,
                 course_store: VectorStore, video_store: VectorStore):
        self.s, self.embedder, self.catalog, self.tax = settings, embedder, catalog, taxonomy
        self.course_store, self.video_store = course_store, video_store

    def recommend(self, question: str, course: str | None, subject: str | None, topic: str | None
                  ) -> tuple[Recommendation | None, Recommendation | None]:
        q_subjects, q_topics = self.tax.tag(f"{question} {subject or ''} {topic or ''}")
        want_subjects = {x.lower() for x in ([subject] if subject else []) + q_subjects}
        want_topics = {x.lower() for x in ([topic] if topic else []) + q_topics}
        text = " ".join(x for x in [question, topic, subject] if x)
        vec = self.embedder.embed_one(text)
        return (self._best("course", self.course_store, vec, course, want_subjects, want_topics),
                self._best("video", self.video_store, vec, course, want_subjects, want_topics))

    def _best(self, kind, store, vec, course, want_subjects, want_topics) -> Recommendation | None:
        s = self.s
        scored = []
        for hit in store.query(vec, 10):
            rec = self.catalog.get_course(hit.id) if kind == "course" else self.catalog.get_video(hit.id)
            if rec is None or (rec.is_sample and not s.allow_sample_data):
                continue
            subj = next((x for x in rec.subjects if x.lower() in want_subjects), None)
            top = next((x for x in rec.topics if x.lower() in want_topics), None)
            course_match = bool(course and kind == "course" and (rec.exam or "").lower() == course.lower())
            course_match = course_match or bool(course and kind == "video" and rec.subjects)  # tagged GATE DA videos
            score = s.rec_w_semantic * max(hit.score, 0.0) + s.rec_w_subject * bool(subj) + s.rec_w_topic * bool(top) + s.rec_w_course * course_match
            if kind == "video":
                score += s.rec_w_recency * _recency(rec.published_at)
            scored.append((score, rec, subj, top))
        scored.sort(key=lambda t: -t[0])
        for score, rec, subj, top in scored:
            if score < s.recommendation_min_score:
                break
            rid = rec.course_id if kind == "course" else rec.video_id
            if not self.catalog.validate_url_matches_record(kind, rid, rec.url, allow_sample=s.allow_sample_data):
                log.warning("Dropped %s recommendation %s: URL failed validation", kind, rid)
                continue
            parts = ([f"subject: {subj}"] if subj else []) + ([f"topic: {top}"] if top else [])
            reason = "Matches " + " and ".join(parts) if parts else "Closest semantic match to your question"
            return Recommendation(kind=kind, id=rid, title=rec.title, url=rec.url, matched_subject=subj, matched_topic=top,
                                  score=round(score, 3), reason=reason, is_sample=rec.is_sample)
        return None


def _recency(published_at: str | None) -> float:
    """1.0 for videos published today decaying linearly to 0 over two years."""
    if not published_at:
        return 0.0
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, 1 - (datetime.now(timezone.utc) - dt).days / 730)
    except ValueError:
        return 0.0
