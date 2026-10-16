from fastapi import APIRouter, HTTPException, Request

from app.container import get_container

router = APIRouter(prefix="/api/v1", tags=["catalog"])


@router.get("/courses")
def courses(request: Request):
    c = get_container(request)
    include_sample = c.settings.allow_sample_data
    recs = c.catalog.list_courses(include_sample=include_sample)
    return {
        "exams": c.taxonomy.courses,
        "courses": [{"course_id": r.course_id, "title": r.title, "url": r.url, "exam": r.exam, "subjects": r.subjects,
                     "price": r.price, "is_sample": r.is_sample} for r in recs],
    }


@router.get("/subjects")
def subjects(request: Request, course: str | None = None):
    tax = get_container(request).taxonomy
    if course and not tax.canonical_course(course):
        raise HTTPException(404, f"Unknown course '{course}'. Valid options: {', '.join(tax.courses)}.")
    return {"course": tax.canonical_course(course) if course else None, "subjects": tax.subject_list(course)}
