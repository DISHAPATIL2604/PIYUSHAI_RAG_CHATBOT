from fastapi import APIRouter, Depends, HTTPException, Request

from app.container import get_container
from app.core.auth import AuthenticatedUser, get_current_user
from app.schemas.chat import ChatRequest, ChatResponse, SessionHistory

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    return get_container(request).chat.handle(req)


@router.get("/sessions/{session_id}/history", response_model=SessionHistory)
def history(session_id: str, request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    msgs = get_container(request).sessions.history(session_id)
    if msgs is None:
        raise HTTPException(404, f"Session '{session_id}' not found.")
    return {"session_id": session_id, "messages": msgs}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, request: Request, user: AuthenticatedUser = Depends(get_current_user)):
    return {"session_id": session_id, "deleted": get_container(request).sessions.delete(session_id)}
