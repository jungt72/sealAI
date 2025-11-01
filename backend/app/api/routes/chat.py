"""Chat endpoint placeholder emitting HTTP 503 while LangGraph rebuilds."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.services.auth.dependencies import get_current_request_user

router = APIRouter()


class ParameterItem(BaseModel):
    name: str
    value: int | float | str | bool
    unit: str = Field(default="none")
    source: str = Field(default="user")


class ChatStreamRequest(BaseModel):
    chat_id: str = Field(..., min_length=1)
    input_text: str = Field(..., min_length=1)


@router.post("/chat/stream", status_code=status.HTTP_200_OK)
async def chat_stream(
    payload: ChatStreamRequest,
    _request: Request,
    _username: str = Depends(get_current_request_user),
) -> None:
    text = payload.input_text.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="input_text empty")

    # Fast fail until LangGraph streaming is re-enabled
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="LangGraph temporarily unavailable. Use WS /chat/stream.",
    )


__all__ = ["router"]
