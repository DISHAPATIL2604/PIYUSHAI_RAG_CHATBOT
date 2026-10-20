from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=128)
    message: str
    selected_course: str | None = None
    selected_subject: str | None = None
    selected_topic: str | None = None

    @field_validator("message")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("message must not be empty")
        return v

    @field_validator("session_id", "selected_course", "selected_subject", "selected_topic")
    @classmethod
    def _blank_to_none(cls, v):
        return v.strip() or None if isinstance(v, str) else v


class SourceItem(BaseModel):
    title: str
    url: str
    content_type: str
    snippet: str | None = None


class Recommendation(BaseModel):
    kind: Literal["course", "video"]
    id: str
    title: str
    url: str
    matched_subject: str | None = None
    matched_topic: str | None = None
    score: float
    reason: str
    is_sample: bool = False


class ResourceRecommendation(BaseModel):
    title: str
    url: str
    kind: str = "webpage"  # "webpage", "article", or "video"
    reason: str | None = None
    is_sample: bool = False


class CourseRecommendation(BaseModel):
    id: str
    title: str
    url: str
    reason: str
    is_sample: bool = False


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    answer_mode: Literal["grounded", "general_knowledge", "not_found"]
    sources: list[SourceItem] = Field(default_factory=list)
    related_resource: ResourceRecommendation | None = None
    recommended_course: CourseRecommendation | None = None
    course_recommendation: Recommendation | None = None
    youtube_recommendation: Recommendation | None = None
    suggested_follow_up_questions: list[str] = Field(default_factory=list)


class SessionMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    timestamp: str
    answer_mode: str | None = None
    related_resource_title: str | None = None
    related_resource_url: str | None = None
    recommended_course_id: str | None = None
    recommended_course_name: str | None = None
    recommended_course_url: str | None = None


class SessionHistory(BaseModel):
    session_id: str
    messages: list[SessionMessage]


class ChatSessionSummary(BaseModel):
    chat_id: str
    title: str
    selected_course_id: str | None = None
    selected_course_name: str | None = None
    created_at: str
    updated_at: str


class ChatMessageRecord(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    timestamp: str
    related_resource_title: str | None = None
    related_resource_url: str | None = None
    recommended_course_id: str | None = None
    recommended_course_name: str | None = None
    recommended_course_url: str | None = None


class UserProfileData(BaseModel):
    uid: str
    email: str | None = None
    display_name: str | None = None
    created_at: str
    updated_at: str
    preferences: dict = Field(default_factory=dict)
