"""Chat endpoint placeholder emitting HTTP 503 while LangGraph rebuilds."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.langgraph.compile import run_langgraph_stream
from pydantic import BaseModel, Field

from app.services.auth.dependencies import RequestUser, get_current_request_user

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
    _user: RequestUser = Depends(get_current_request_user),
) -> Any:
    text = payload.input_text.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="input_text empty")

    request = _request
    request.state.langgraph_payload = payload.model_dump()
    result = await run_langgraph_stream(request)
    return result


__all__ = ["router"]
