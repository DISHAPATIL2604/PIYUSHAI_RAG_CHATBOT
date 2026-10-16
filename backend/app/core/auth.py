"""Firebase Authentication verification dependency."""
from dataclasses import dataclass
from typing import Optional
from fastapi import Header, HTTPException, Request

try:
    import firebase_admin
    from firebase_admin import auth as fb_auth
except ImportError:  # pragma: no cover
    firebase_admin = None
    fb_auth = None


@dataclass
class AuthenticatedUser:
    uid: str
    email: Optional[str] = None
    name: Optional[str] = None
    claims: Optional[dict] = None


def get_current_user(request: Request, authorization: Optional[str] = Header(None)) -> AuthenticatedUser:
    container = getattr(request.app.state, "container", None) or getattr(request.state, "container", None)
    settings = container.settings if container else None
    if settings is None:
        from app.core.config import get_settings
        settings = get_settings()

    auth_required = settings.firebase_auth_required if settings else False
    project_id = settings.firebase_project_id if settings else ""

    if not authorization:
        if auth_required:
            raise HTTPException(
                status_code=401,
                detail="Authentication required. Please sign in to ask questions.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return AuthenticatedUser(uid="anonymous", email=None)

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format. Expected 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    # If Firebase Admin is available and project_id is provided, verify against Firebase
    if project_id and fb_auth:
        try:
            if not firebase_admin._apps:
                firebase_admin.initialize_app(options={"projectId": project_id})
            decoded = fb_auth.verify_id_token(token)
            return AuthenticatedUser(
                uid=decoded.get("uid", ""),
                email=decoded.get("email"),
                name=decoded.get("name"),
                claims=decoded,
            )
        except Exception as e:
            raise HTTPException(
                status_code=401,
                detail=f"Invalid or expired Firebase token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        # If project_id is not yet set or in dev mode:
        # Accept token and extract basic info
        return AuthenticatedUser(uid="authenticated-user", email=None, claims={"token": token})
