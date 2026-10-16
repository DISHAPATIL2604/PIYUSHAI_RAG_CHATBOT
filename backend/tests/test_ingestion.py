"""Crawler rules, website + YouTube ingestion, duplicate/incremental behaviour."""
import json

import pytest
import requests
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.main import create_app
from app.services.crawler import Crawler, FetchResult, normalize_url
from app.services.ingestion_service import YouTubeClient, chunk_text
from tests.conftest import FakeResponse, fake_fetcher, make_settings

LONG = " ".join(f"Sentence number {i} explains machine learning and linear regression for GATE DA students in detail." for i in range(12))
NAV = '<nav>NAVTEXT Home | About | Login</nav><header>HEADERTEXT</header>'


def page(title, body, extra="", desc="A page"):
    return (f'<html><head><title>{title}</title><meta name="description" content="{desc}"></head><body>{NAV}'
            f'<main><h1>{title}</h1><p>{body}</p>{extra}</main><footer>FOOTERTEXT</footer></body></html>')


def site(course_body=LONG):
    return {
        "https://piyushai.com/robots.txt": "User-agent: *\nDisallow: /private\nSitemap: https://piyushai.com/sitemap.xml\n",
        "https://piyushai.com/sitemap.xml": "<urlset><url><loc>https://piyushai.com/courses/gate-da-ml</loc></url>"
                                            "<url><loc>https://piyushai.com/private/secret</loc></url>"
                                            "<url><loc>https://piyushai.com/app</loc></url>"
                                            "<url><loc>https://piyushai.com/app2</loc></url></urlset>",
        "https://piyushai.com/": page("PiyushAI Home", LONG, '<a href="/courses/gate-da-ml?utm_source=x#top">ML</a><a href="/private/x">p</a><a href="https://other.com/x">o</a>'),
        "https://piyushai.com/courses/gate-da-ml": page("GATE DA Machine Learning Course", course_body, '<a href="/enroll/ml">Enroll now</a><p>Fee: ₹4,999</p>', "ML course for GATE DA"),
        "https://piyushai.com/private/secret": page("Secret", LONG),
        "https://piyushai.com/private/x": page("Secret2", LONG),
        "https://piyushai.com/app": '<html><head><title>App</title></head><body><div id="root"></div><script>window.__x=1</script></body></html>',
        "https://piyushai.com/app2": '<html><head><title>App2</title></head><body><div id="root"></div>'
                                      f'<script id="__NEXT_DATA__" type="application/json">{json.dumps({"props": {"about": LONG}})}</script></body></html>',
    }


def crawler_for(tmp_path, pages, **kw):
    s = make_settings(tmp_path, **kw)
    f = fake_fetcher(pages)
    return Crawler(s, fetch=f, sleep=lambda _: None), f


def test_normalize_url():
    assert normalize_url("HTTPS://PiyushAI.com/courses/?utm_source=a&id=2#frag") == "https://piyushai.com/courses?id=2"


def test_chunking_overlaps_and_respects_size():
    ch = chunk_text(LONG, size=300, overlap=60)
    assert len(ch) > 3 and all(len(c) <= 380 for c in ch)
    assert any(ch[i][-20:].split()[-1] in ch[i + 1] for i in range(len(ch) - 1))
    assert chunk_text("", 300, 60) == []


def test_crawler_respects_robots_cleans_nav_and_uses_fallbacks(tmp_path):
    cr, f = crawler_for(tmp_path, site())
    res = cr.crawl()
    urls = {p.url: p for p in res.pages}
    assert "https://piyushai.com/courses/gate-da-ml" in urls and "https://piyushai.com/" in urls
    skipped = dict(res.skipped)
    assert skipped["https://piyushai.com/private/secret"] == "robots_disallowed"
    assert "https://piyushai.com/private/secret" not in f.calls and "https://piyushai.com/private/x" not in f.calls  # never fetched
    assert "https://other.com/x" not in f.calls                                  # out-of-scope domain
    assert skipped["https://piyushai.com/app"] == "skipped_no_content"          # JS shell, no fallback worked
    assert urls["https://piyushai.com/app2"].method == "embedded_json"          # __NEXT_DATA__ fallback
    for p in res.pages:
        assert not any(w in p.text for w in ("NAVTEXT", "HEADERTEXT", "FOOTERTEXT"))
    assert urls["https://piyushai.com/courses/gate-da-ml"].enroll_url == "https://piyushai.com/enroll/ml"


def test_robots_5xx_is_conservative(tmp_path):
    pages = site()
    pages["https://piyushai.com/robots.txt"] = FetchResult(503, "", "text/plain")
    res = crawler_for(tmp_path, pages)[0].crawl()
    assert res.pages == [] and all(r == "robots_unavailable" for _, r in res.skipped)


def test_crawler_rate_limits_per_domain(tmp_path):
    slept, t = [], [0.0]
    s = make_settings(tmp_path, crawl_delay_seconds=1.0)
    cr = Crawler(s, fetch=fake_fetcher(site()), sleep=lambda x: (slept.append(x), t.__setitem__(0, t[0] + x)), clock=lambda: t[0])
    cr.crawl(max_pages=2)
    assert slept and all(abs(x - 1.0) < 1e-9 for x in slept)


def test_duplicate_content_pages_are_skipped(tmp_path):
    pages = site()
    pages["https://piyushai.com/courses/copy"] = pages["https://piyushai.com/"]
    pages["https://piyushai.com/sitemap.xml"] = pages["https://piyushai.com/sitemap.xml"].replace("</urlset>", "<url><loc>https://piyushai.com/courses/copy</loc></url></urlset>")
    res = crawler_for(tmp_path, pages)[0].crawl()
    assert ("https://piyushai.com/courses/copy", "duplicate") in res.skipped


def test_playwright_fallback_only_when_enabled(tmp_path):
    shell = {"https://piyushai.com/robots.txt": "", "https://piyushai.com/": '<html><body><div id="root"></div></body></html>'}
    rendered = page("Rendered", LONG)
    off = Crawler(make_settings(tmp_path), fetch=fake_fetcher(shell), sleep=lambda _: None, render=lambda u: rendered)
    assert off.crawl().pages == []
    on = Crawler(make_settings(tmp_path, enable_playwright=True), fetch=fake_fetcher(shell), sleep=lambda _: None, render=lambda u: rendered)
    assert on.crawl().pages[0].method == "playwright"


# ---- website ingestion + dedupe ------------------------------------------------------------
def test_website_ingestion_is_idempotent_and_replaces_changed_pages(build, tmp_path):
    pages = site()
    c = build(crawler=Crawler(make_settings(tmp_path), fetch=fake_fetcher(pages), sleep=lambda _: None))
    first = c.website_ingestor.run()
    n_chunks, n_courses = c.chunk_store.count(), c.catalog.counts()["courses"]
    assert first.new >= 2 and first.chunks_created == n_chunks and n_courses == 1
    assert first.skipped["robots_disallowed"] >= 1 and first.skipped["skipped_no_content"] == 1
    course = c.catalog.list_courses()[0]
    assert course.price == "₹4,999" and course.enrollment_url == "https://piyushai.com/enroll/ml" and course.exam == "GATE DA"
    assert "Machine Learning" in course.subjects and not course.is_sample

    second = c.website_ingestor.run()                       # re-run: no duplicates
    assert second.new == 0 and second.updated == 0 and second.unchanged >= 2 and second.chunks_created == 0
    assert c.chunk_store.count() == n_chunks and c.catalog.counts()["courses"] == 1

    pages["https://piyushai.com/courses/gate-da-ml"] = page("GATE DA Machine Learning Course", "Totally NEWCONTENT marker. " + LONG[:400], "", "ML course")
    third = c.website_ingestor.run()                         # changed page replaces old chunks
    assert third.updated == 1
    texts = [h.document for h in c.chunk_store.get(where={"source_url": "https://piyushai.com/courses/gate-da-ml"})]
    assert texts and any("NEWCONTENT" in t for t in texts) and not any("Sentence number 11" in t for t in texts)
    assert c.catalog.list_courses()[0].price is None        # price vanished -> stored as null, never guessed


def test_website_endpoint_returns_summary(build, tmp_path):
    c = build(crawler=Crawler(make_settings(tmp_path), fetch=fake_fetcher(site()), sleep=lambda _: None))
    r = TestClient(create_app(c)).post("/api/v1/ingestion/websites", headers={"X-Admin-Key": "admin-secret"}, json={"max_pages": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["fetched"] <= 5 and body["chunks_created"] > 0 and "duration_seconds" in body and "skipped" in body


# ---- YouTube ------------------------------------------------------------------------------------
def yt_get(calls=None, quota=False):
    def item(vid, title, desc="", pub="2026-02-01T00:00:00Z"):
        return {"snippet": {"title": title, "description": desc, "resourceId": {"videoId": vid}}, "contentDetails": {"videoId": vid, "videoPublishedAt": pub}}

    def get(url, params=None, timeout=None):
        if calls is not None:
            calls.append((url, dict(params)))
        if quota:
            return FakeResponse(403, {"error": {"errors": [{"reason": "quotaExceeded"}]}})
        if url.endswith("/channels"):
            assert params["forHandle"] == "@piyushwairaleiitm"
            return FakeResponse(200, {"items": [{"id": "UC1", "snippet": {"title": "Piyush"}, "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]})
        if url.endswith("/playlists"):
            return FakeResponse(200, {"items": [{"id": "PL1", "snippet": {"title": "Machine Learning for GATE DA", "description": "ML playlist"}}]})
        pid, tok = params["playlistId"], params.get("pageToken")
        if pid == "UU1" and not tok:
            return FakeResponse(200, {"items": [item("v1", "Linear Regression Explained", "Least squares and gradient descent"),
                                                item("v0", "Private video"), {"snippet": {"description": "no title"}, "contentDetails": {}}],
                                      "nextPageToken": "T2"})
        if pid == "UU1" and tok == "T2":
            return FakeResponse(200, {"items": [item("v2", "Eigenvalues made easy", "Linear algebra eigenvalues", "2026-03-01T00:00:00Z")]})
        if pid == "PL1":
            return FakeResponse(200, {"items": [item("v1", "Linear Regression Explained")]})
        return FakeResponse(200, {"items": []})

    return get


def yt_container(build, tmp_path, **kw):
    s = make_settings(tmp_path)
    return build(youtube_client=YouTubeClient("k", http_get=yt_get(**kw)))


def test_youtube_ingestion_pagination_membership_and_dedupe(build, tmp_path):
    calls = []
    c = yt_container(build, tmp_path, calls=calls)
    s1 = c.youtube_ingestor.run()
    assert any(p.get("pageToken") == "T2" for _, p in calls)                    # followed pagination
    assert s1.new == 2 and s1.playlists == 1 and s1.skipped["unavailable_video"] == 2 and s1.videos_in_catalog == 2
    v1 = c.catalog.get_video("v1")
    assert v1.url == "https://www.youtube.com/watch?v=v1" and v1.playlist_titles == ["Machine Learning for GATE DA"]
    assert "Machine Learning" in v1.subjects and "Linear Regression" in v1.topics and v1.has_transcript is False
    assert c.catalog.get_video("v2").subjects == ["Linear Algebra"] and c.catalog.get_video("v2").playlist_ids == []
    n = c.chunk_store.count()
    s2 = c.youtube_ingestor.run()                                                # second run: nothing new
    assert s2.new == 0 and s2.updated == 0 and s2.unchanged == 2 and c.chunk_store.count() == n and s2.videos_in_catalog == 2


def test_youtube_only_new_and_since(build, tmp_path):
    c = yt_container(build, tmp_path)
    s = c.youtube_ingestor.run(since="2026-02-15")
    assert s.new == 1 and s.skipped["older_than_since"] == 1 and c.catalog.get_video("v2") and not c.catalog.get_video("v1")
    assert c.youtube_ingestor.run(only_new=True).new == 1                       # picks up the one that was missing


def test_youtube_missing_key_and_quota_errors(build, tmp_path):
    c = build(youtube_api_key="")
    r = TestClient(create_app(c)).post("/api/v1/ingestion/youtube", headers={"X-Admin-Key": "admin-secret"})
    assert r.status_code == 503 and "YOUTUBE_API_KEY" in r.json()["error"]["message"]
    q = yt_container(build, tmp_path, quota=True)
    r = TestClient(create_app(q)).post("/api/v1/ingestion/youtube", headers={"X-Admin-Key": "admin-secret"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "youtube_quota_exceeded"


def test_youtube_timeout_maps_to_504():
    def boom(*a, **k):
        raise requests.Timeout()
    with pytest.raises(AppError) as e:
        YouTubeClient("k", http_get=boom).resolve_channel("x")
    assert e.value.status_code == 504
