"""Simplified SSE chat endpoint after LangGraph removal."""
from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.routes.chat_utils import ensure_system_prompt
from app.services.auth.dependencies import get_current_request_user
from app.utils.json import to_jsonable

router = APIRouter()


class ParameterItem(BaseModel):
    name: str
    value: int | float | str | bool
    unit: str = Field(default="none")
    source: str = Field(default="user")


class ChatStreamRequest(BaseModel):
    chat_id: str = Field(..., min_length=1)
    input_text: str = Field(..., min_length=1)


def _sse(event: str, data: Any) -> bytes:
    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")


@router.post("/chat/stream", response_class=StreamingResponse, status_code=status.HTTP_200_OK)
async def chat_stream(
    payload: ChatStreamRequest,
    _request: Request,
    username: str = Depends(get_current_request_user),
) -> StreamingResponse:
    text = payload.input_text.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="input_text empty")

    system_prompt = ensure_system_prompt()
    message = (
        "LangGraph wurde entfernt. "
        "Die Chat-Funktion befindet sich im Neuaufbau. "
        "Eingabe wurde protokolliert."
    )

    async def event_stream() -> AsyncGenerator[bytes, None]:
        yield _sse(
            "final",
            {
                "prompt": system_prompt,
                "response": message,
                "user": username,
                "chat_id": payload.chat_id.strip(),
                "input": text,
            },
        )
        yield _sse("done", {"done": True})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


__all__ = ["router"]
