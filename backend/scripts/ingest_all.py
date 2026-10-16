"""Run both ingestion pipelines:  python -m scripts.ingest_all [--websites-only|--youtube-only] [--max-pages N]"""
import argparse
import json
import sys

from app.container import Container
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import setup_logging


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Ingest PiyushAI websites and YouTube metadata.")
    ap.add_argument("--websites-only", action="store_true")
    ap.add_argument("--youtube-only", action="store_true")
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--only-new", action="store_true", help="YouTube: skip videos already indexed")
    args = ap.parse_args(argv)
    setup_logging()
    c = Container.build(get_settings())
    ok = failed = 0
    jobs = []
    if not args.youtube_only:
        jobs.append(("websites", lambda: c.website_ingestor.run(max_pages=args.max_pages)))
    if not args.websites_only:
        if c.settings.youtube_api_key:
            jobs.append(("youtube", lambda: c.youtube_ingestor.run(only_new=args.only_new)))
        else:
            print("WARNING: YOUTUBE_API_KEY not set - skipping YouTube ingestion.", file=sys.stderr)
    for name, job in jobs:
        try:
            print(f"== {name} ==")
            print(json.dumps(job().model_dump(), indent=2))
            ok += 1
        except AppError as e:
            print(f"ERROR in {name}: {e.message}", file=sys.stderr)
            failed += 1
    return 1 if jobs and ok == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
