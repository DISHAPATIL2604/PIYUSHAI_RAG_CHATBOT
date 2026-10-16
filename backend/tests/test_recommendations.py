import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.catalog import CourseRecord, VideoRecord
from tests.conftest import SAMPLE


@pytest.fixture
def sc(build):
    c = build(allow_sample_data=True)
    c.catalog.load_sample(SAMPLE)
    return c


def rec(c, q, **sel):
    return c.recommender.recommend(q, sel.get("course", "GATE DA"), sel.get("subject"), sel.get("topic"))


def test_ranking_picks_matching_subject_and_topic(sc):
    course, video = rec(sc, "Explain linear regression", subject="Machine Learning", topic="Linear Regression")
    assert course.id == "sample-course-gate-da-ml" and video.id == "SAMPLEvid01"
    assert course.matched_subject == "Machine Learning" and video.matched_topic == "Linear Regression"
    assert "Matches" in course.reason and course.is_sample and 0.45 <= course.score <= 1.1
    course, video = rec(sc, "How do I compute eigenvalues?", subject="Linear Algebra")
    assert course.id == "sample-course-gate-da-la" and video.id == "SAMPLEvid02"


def test_below_threshold_returns_none(sc):
    assert rec(sc, "What is the capital of France?", course=None) == (None, None)


def test_sample_records_excluded_by_default(build):
    c = build()  # allow_sample_data defaults to False
    c.catalog.load_sample(SAMPLE)
    assert rec(c, "Explain linear regression", subject="Machine Learning") == (None, None)
    assert TestClient(create_app(c)).get("/api/v1/courses").json()["courses"] == []


def test_url_validation(build):
    c = build()
    now = "2026-01-01T00:00:00+00:00"
    good = CourseRecord(course_id="c1", title="ML", url="https://piyushai.com/courses/ml", source_url="https://piyushai.com", content_hash="h", indexed_at=now)
    evil = CourseRecord(course_id="c2", title="Evil", url="https://evil.example.com/courses/x", source_url="x", content_hash="h", indexed_at=now)
    vid = VideoRecord(video_id="abc123", title="V", url="https://www.youtube.com/watch?v=abc123", content_hash="h", indexed_at=now)
    badvid = VideoRecord(video_id="def456", title="V2", url="https://www.youtube.com/watch?v=zzz999", content_hash="h2", indexed_at=now)
    for r in (good, evil):
        c.catalog.upsert_course(r)
    for r in (vid, badvid):
        c.catalog.upsert_video(r)
    v = c.catalog.validate_url_matches_record
    assert v("course", "c1", "https://piyushai.com/courses/ml")
    assert not v("course", "c1", "https://piyushai.com/courses/other")      # tampered URL
    assert not v("course", "c2", "https://evil.example.com/courses/x")      # non-official domain
    assert not v("course", "missing", "https://piyushai.com/courses/ml")    # not in catalog
    assert v("video", "abc123", "https://www.youtube.com/watch?v=abc123")
    assert not v("video", "def456", "https://www.youtube.com/watch?v=zzz999")  # id != URL id


def test_recommender_drops_records_failing_validation(build):
    c = build()
    evil = CourseRecord(course_id="c2", title="Machine Learning Course", url="https://evil.example.com/courses/ml",
                        description="machine learning linear regression", exam="GATE DA", subjects=["Machine Learning"],
                        topics=["Linear Regression"], source_url="x", content_hash="h", indexed_at="2026-01-01")
    c.catalog.upsert_course(evil)
    course, _ = rec(c, "Explain linear regression", subject="Machine Learning", topic="Linear Regression")
    assert course is None
