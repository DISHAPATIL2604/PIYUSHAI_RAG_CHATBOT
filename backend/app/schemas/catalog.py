from pydantic import BaseModel, Field


class CourseRecord(BaseModel):
    course_id: str
    title: str
    url: str
    description: str | None = None
    price: str | None = None
    enrollment_url: str | None = None
    exam: str | None = None  # e.g. "GATE DA"
    subjects: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    source_url: str
    content_hash: str
    indexed_at: str
    is_sample: bool = False


class VideoRecord(BaseModel):
    video_id: str
    title: str
    url: str
    description: str | None = None
    published_at: str | None = None
    playlist_ids: list[str] = Field(default_factory=list)
    playlist_titles: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    has_transcript: bool = False
    source: str = "youtube_api"
    content_hash: str
    indexed_at: str
    is_sample: bool = False
