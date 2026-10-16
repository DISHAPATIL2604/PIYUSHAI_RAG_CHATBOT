"""Orchestrates the RAG workflow for POST /chat."""
import re
import uuid

from app.core.config import Settings
from app.core.errors import AppError
from app.prompts import system_prompt as sp
from app.schemas.chat import ChatRequest, ChatResponse, SourceItem
from app.services.catalog_service import CatalogService
from app.services.generation_service import GenerationService, sanitize_urls
from app.services.recommendation_service import RecommendationService
from app.services.retrieval_service import RetrievalService
from app.services.session_service import SessionStore
from app.services.taxonomy import Taxonomy

PIYUSHAI_Q = re.compile(r"\b(piyush\w*|course|courses|price|pricing|fee|fees|cost|enrol\w*|batch|batches|schedule|instructor|mentor|"
                        r"subscription|discount|coupon|refund|validity|your (youtube|channel|website))\b", re.I)


FOLLOW_UP = re.compile(r"^(and|but|so|then|also|why|how about|what about)\b|\b(it|its|this|that|these|those|they|them|there)\b", re.I)


def looks_like_follow_up(text: str) -> bool:
    return len(text.split()) <= 3 or bool(FOLLOW_UP.search(text))


def is_piyushai_question(text: str) -> bool:
    return bool(PIYUSHAI_Q.search(text))


class ChatService:
    def __init__(self, settings: Settings, taxonomy: Taxonomy, catalog: CatalogService, sessions: SessionStore,
                 retrieval: RetrievalService, generation: GenerationService, recommender: RecommendationService):
        self.s, self.tax, self.catalog, self.sessions = settings, taxonomy, catalog, sessions
        self.retrieval, self.generation, self.recommender = retrieval, generation, recommender

    def validate_selection(self, req: ChatRequest) -> None:
        course = subject = None
        if req.selected_course:
            course = self.tax.canonical_course(req.selected_course)
            if not course:
                raise AppError(422, "unknown_course", f"Unknown course '{req.selected_course}'. Valid options: {', '.join(self.tax.courses)}.")
            req.selected_course = course
        if req.selected_subject:
            subject = self.tax.canonical_subject(req.selected_subject)
            if not subject:
                raise AppError(422, "unknown_subject", f"Unknown subject '{req.selected_subject}'. Valid options: {', '.join(self.tax.subject_names())}.")
            req.selected_subject = subject
        if req.selected_topic:
            topic = self.tax.canonical_topic(req.selected_topic, subject)
            if not topic:
                where = f" for subject '{subject}'" if subject else ""
                raise AppError(422, "unknown_topic", f"Unknown topic '{req.selected_topic}'{where}.")
            req.selected_topic = topic

    def _retrieve(self, req: ChatRequest, history: list[dict]):
        """Retrieve on the message itself. Only if that finds nothing AND the message looks like a follow-up
        ("and why?", "what about its limits?") is the previous user question added as context. This keeps topic
        switches from being polluted by earlier turns."""
        own = " ".join(x for x in [req.message, req.selected_topic, req.selected_subject] if x)
        chunks = self.retrieval.retrieve(own, req.selected_course, req.selected_subject)
        prev = [m["content"] for m in history if m["role"] == "user"]
        if not chunks and prev and looks_like_follow_up(req.message):
            chunks = self.retrieval.retrieve(f"{prev[-1]} {own}", req.selected_course, req.selected_subject)
        return chunks

    def _fallback_follow_ups(self, req: ChatRequest) -> list[str]:
        t = req.selected_topic or req.selected_subject
        if t:
            return [f"Can you give a worked example of {t}?", f"What are common mistakes in {t}?", f"Which topics should I study after {t}?"]
        return ["Can you give a worked example?", "What should I study next?"]

    def handle(self, req: ChatRequest) -> ChatResponse:
        if len(req.message) > self.s.max_message_chars:
            raise AppError(422, "message_too_long", f"Message is too long (max {self.s.max_message_chars} characters).")
        self.validate_selection(req)
        sid = req.session_id or str(uuid.uuid4())
        history = self.sessions.recent(sid, self.s.session_max_turns)
        chunks = self._retrieve(req, history)

        follow_ups: list[str] = []
        if chunks:
            mode = "grounded"
        elif is_piyushai_question(req.message):
            mode = "not_found"
        else:
            mode = "general_knowledge"

        if mode == "not_found":
            answer = sp.NOT_FOUND_ANSWER
        else:
            answer, follow_ups = self.generation.generate(req.message, history, chunks, req.selected_course, req.selected_subject,
                                                          req.selected_topic, self.catalog.all_urls())
            if mode == "general_knowledge":
                answer = f"{sp.GENERAL_NOTE}\n\n{answer}"

        course_rec = video_rec = None
        if mode != "not_found":
            course_rec, video_rec = self.recommender.recommend(req.message, req.selected_course, req.selected_subject, req.selected_topic)

        seen, sources = set(), []
        allowed = {c.url for c in chunks} | self.catalog.all_urls()
        for c in chunks:
            if c.url and c.url not in seen:
                seen.add(c.url)
                # Snippets echo untrusted page text, so they get the same URL allow-list as the answer.
                snippet = sanitize_urls(c.text[:200], allowed)[0]
                sources.append(SourceItem(title=c.title, url=c.url, content_type=c.content_type, snippet=snippet))

        self.sessions.append(sid, "user", req.message)
        self.sessions.append(sid, "assistant", answer, answer_mode=mode)
        if len(follow_ups) < 2:
            follow_ups = (follow_ups + self._fallback_follow_ups(req))[:4]
        return ChatResponse(session_id=sid, answer=answer, answer_mode=mode, sources=sources, course_recommendation=course_rec,
                            youtube_recommendation=video_rec, suggested_follow_up_questions=follow_ups[:4])
