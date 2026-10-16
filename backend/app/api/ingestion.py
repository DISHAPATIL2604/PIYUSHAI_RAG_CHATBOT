from fastapi import APIRouter, Depends, Request

from app.container import get_container
from app.core.security import require_admin
from app.schemas.ingestion import IngestionSummary, WebsiteIngestRequest, YouTubeIngestRequest

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion (admin)"], dependencies=[Depends(require_admin)])


@router.post("/websites", response_model=IngestionSummary)
def ingest_websites(request: Request, body: WebsiteIngestRequest | None = None):
    return get_container(request).website_ingestor.run(max_pages=body.max_pages if body else None)


@router.post("/youtube", response_model=IngestionSummary)
def ingest_youtube(request: Request, body: YouTubeIngestRequest | None = None):
    b = body or YouTubeIngestRequest()
    return get_container(request).youtube_ingestor.run(only_new=b.only_new, since=b.since)
