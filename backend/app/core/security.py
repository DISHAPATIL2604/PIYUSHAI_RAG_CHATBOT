"""X-Admin-Key protection for administrative endpoints (fails closed)."""
import secrets

from fastapi import Header, HTTPException, Request


def require_admin(request: Request, x_admin_key: str | None = Header(default=None)) -> None:
    from app.container import get_container

    expected = get_container(request).settings.admin_api_key
    if not expected:
        raise HTTPException(503, "Admin endpoints are disabled: ADMIN_API_KEY is not configured on the server.")
    if not x_admin_key:
        raise HTTPException(401, "Missing X-Admin-Key header.")
    if not secrets.compare_digest(x_admin_key.encode(), expected.encode()):
        raise HTTPException(403, "Invalid admin key.")
