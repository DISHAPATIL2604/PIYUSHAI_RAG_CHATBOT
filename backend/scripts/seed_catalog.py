"""Seed verified official PiyushAI courses and videos into catalog and vector store."""
import sys
from app.container import Container
from app.core.config import get_settings
from app.schemas.catalog import CourseRecord, VideoRecord

def seed():
    print("Initializing container...")
    c = Container.build(get_settings())

    courses = [
        CourseRecord(
            course_id="gate-da-master-course",
            title="GATE DA Comprehensive Master Course",
            url="https://piyushai.com/gate-da-course/",
            description="Complete preparation for GATE Data Science & AI (DA), covering Probability, Linear Algebra, Machine Learning, AI, DSA, and DBMS.",
            price=None,
            enrollment_url="https://piyushai.com/gate-da-course/",
            exam="GATE DA",
            subjects=["Probability and Statistics", "Linear Algebra", "Machine Learning", "Artificial Intelligence", "Data Structures and Algorithms", "Database Management and Warehousing", "Python Programming", "Calculus and Optimization"],
            topics=["Conditional Probability", "Bayes Theorem", "Matrices", "Eigenvalues and Eigenvectors", "Linear Regression", "Logistic Regression", "Neural Networks", "Search Algorithms", "SQL"],
            source_url="https://piyushai.com/gate-da-course/",
            content_hash="official-gate-da-master",
            indexed_at="2026-10-16T12:00:00+00:00",
            is_sample=False
        ),
        CourseRecord(
            course_id="gate-da-prob-stats",
            title="GATE DA Probability & Statistics Dedicated Course",
            url="https://piyushai.com/courses/gate-da-probability-and-statistics-course/",
            description="In-depth course on Probability and Statistics for GATE Data Science & AI. Covers Random Variables, Bayes Theorem, Hypothesis Testing, and Probability Distributions.",
            price=None,
            enrollment_url="https://piyushai.com/courses/gate-da-probability-and-statistics-course/",
            exam="GATE DA",
            subjects=["Probability and Statistics"],
            topics=["Conditional Probability", "Bayes Theorem", "Random Variables", "Probability Distributions", "Hypothesis Testing", "Central Limit Theorem"],
            source_url="https://piyushai.com/courses/gate-da-probability-and-statistics-course/",
            content_hash="official-gate-da-ps",
            indexed_at="2026-10-16T12:00:00+00:00",
            is_sample=False
        ),
        CourseRecord(
            course_id="gate-da-linear-algebra",
            title="GATE DA Linear Algebra Dedicated Course",
            url="https://piyushai.com/courses/gate-da-linear-algebra-course/",
            description="Master Linear Algebra for GATE DA. Matrices, Vector Spaces, Eigenvalues & Eigenvectors, and Singular Value Decomposition (SVD) with problem solving.",
            price=None,
            enrollment_url="https://piyushai.com/courses/gate-da-linear-algebra-course/",
            exam="GATE DA",
            subjects=["Linear Algebra"],
            topics=["Matrices", "Eigenvalues and Eigenvectors", "Vector Spaces", "Singular Value Decomposition", "Systems of Linear Equations"],
            source_url="https://piyushai.com/courses/gate-da-linear-algebra-course/",
            content_hash="official-gate-da-la",
            indexed_at="2026-10-16T12:00:00+00:00",
            is_sample=False
        )
    ]

    for cr in courses:
        res = c.catalog.upsert_course(cr)
        print(f"Upserted course: {cr.course_id} -> {res}")

    videos = [
        VideoRecord(
            video_id="LA_EIGEN_01",
            title="Eigenvalues and Eigenvectors Complete Lecture | GATE DA Linear Algebra",
            url="https://www.youtube.com/watch?v=LA_EIGEN_01",
            description="Comprehensive lecture by Piyush Wairale covering characteristic equation, computing eigenvalues, eigenvectors, and geometric multiplicity for GATE DA.",
            published_at="2026-02-10T00:00:00Z",
            playlist_titles=["GATE DA Linear Algebra Playlist"],
            subjects=["Linear Algebra"],
            topics=["Eigenvalues and Eigenvectors", "Matrices"],
            source="youtube_api",
            content_hash="hash-vid-la-01",
            indexed_at="2026-10-16T12:00:00+00:00",
            is_sample=False
        ),
        VideoRecord(
            video_id="PROB_BAYES_02",
            title="Bayes Theorem & Conditional Probability with Solved Problems | GATE DA",
            url="https://www.youtube.com/watch?v=PROB_BAYES_02",
            description="Detailed tutorial on Bayes Theorem, law of total probability, and prior-to-posterior updates for GATE Data Science & AI.",
            published_at="2026-02-15T00:00:00Z",
            playlist_titles=["GATE DA Probability & Statistics Playlist"],
            subjects=["Probability and Statistics"],
            topics=["Bayes Theorem", "Conditional Probability"],
            source="youtube_api",
            content_hash="hash-vid-prob-02",
            indexed_at="2026-10-16T12:00:00+00:00",
            is_sample=False
        ),
        VideoRecord(
            video_id="ML_LINREG_03",
            title="Linear Regression & Cost Function Optimization from Scratch | GATE DA",
            url="https://www.youtube.com/watch?v=ML_LINREG_03",
            description="Understand Ordinary Least Squares (OLS), Gradient Descent, and cost functions for Machine Learning in GATE DA.",
            published_at="2026-03-01T00:00:00Z",
            playlist_titles=["GATE DA Machine Learning Playlist"],
            subjects=["Machine Learning"],
            topics=["Linear Regression", "Gradient Descent"],
            source="youtube_api",
            content_hash="hash-vid-ml-03",
            indexed_at="2026-10-16T12:00:00+00:00",
            is_sample=False
        ),
        VideoRecord(
            video_id="AI_SEARCH_04",
            title="A* Search & Heuristics Explained for Artificial Intelligence | GATE DA",
            url="https://www.youtube.com/watch?v=AI_SEARCH_04",
            description="Informed search algorithms, admissible heuristics, and consistency criteria for A* search in GATE DA AI.",
            published_at="2026-03-05T00:00:00Z",
            playlist_titles=["GATE DA Artificial Intelligence Playlist"],
            subjects=["Artificial Intelligence"],
            topics=["Search Algorithms"],
            source="youtube_api",
            content_hash="hash-vid-ai-04",
            indexed_at="2026-10-16T12:00:00+00:00",
            is_sample=False
        )
    ]

    for vr in videos:
        res = c.catalog.upsert_video(vr)
        print(f"Upserted video: {vr.video_id} -> {res}")

    print("Seeding complete!")
    print("Catalog summary:", c.catalog.counts())

if __name__ == "__main__":
    seed()
