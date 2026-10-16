from pydantic import BaseModel, Field


class WebsiteIngestRequest(BaseModel):
    max_pages: int | None = Field(default=None, ge=1, le=2000)


class YouTubeIngestRequest(BaseModel):
    only_new: bool = False
    since: str | None = Field(default=None, description="ISO date; skip videos published before it")


class IngestionSummary(BaseModel):
    source: str
    fetched: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: dict[str, int] = Field(default_factory=dict)
    skipped_examples: dict[str, list[str]] = Field(default_factory=dict)
    chunks_created: int = 0
    courses_in_catalog: int = 0
    videos_in_catalog: int = 0
    playlists: int = 0
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0

    def skip(self, reason: str, example: str | None = None) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1
        if example:
            lst = self.skipped_examples.setdefault(reason, [])
            if len(lst) < 5:
                lst.append(example)
