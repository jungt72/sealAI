# backend/app/api/v1/endpoints/ai.py
"""
AI-Endpoints (v1)
──────────────────────────────────────────────────────────────────────────────
• /chat/stream  –  Server-Sent Streaming (Text-Chunks)
• /chat         –  Einmal-Antwort (klassisch)
──────────────────────────────────────────────────────────────────────────────
"""

from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED

from app.services.chat.chat_chain import (
    run_chat,
    run_chat_streaming,
)
from app.api.v1.dependencies.auth import get_current_request_user  # ↺ liefert username
from app.api.v1.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# 1) Streaming-Endpoint – liefert “text/event-stream”
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/chat/stream",
    response_class=StreamingResponse,  # <- wichtig
    status_code=200,
    summary="LangChain Chat-Stream (Server-Sent)",
)
async def chat_stream_endpoint(
    data: ChatRequest,
    request: Request,
    username: str = Depends(get_current_request_user),
) -> StreamingResponse:
    """
    Gibt einen StreamingResponse zurück (Chunked Transfer).  
    Der Frontend-Reader kann die Tokens nacheinander einlesen.
    """
    async def generator() -> AsyncGenerator[bytes, None]:
        try:
            async for chunk in run_chat_streaming(
                username=username,
                chat_id=data.chat_id,
                message=data.input_text,
                request=request,
            ):
                # Jede Zeile im SSE-Format (oder einfach nur Raw-Chunks)
                # Hier: „reines“ Chunk-Streaming, Frontend parst selbst.
                yield chunk.encode("utf-8")
        except HTTPException as exc:
            # Fehler an den Client propagieren und Stream beenden
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            yield f"[ERROR] {detail}".encode("utf-8")

    # FastAPI erkennt an response_class, dass kein JSON-Encoding erfolgen soll
    return StreamingResponse(generator(), media_type="text/plain")


# ─────────────────────────────────────────────────────────────────────────────
# 2) Einmal-Endpoint – klassische Request-/-Response
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=200,
    summary="LangChain Chat (klassisch)",
)
async def chat_endpoint(
    data: ChatRequest,
    request: Request,
    username: str = Depends(get_current_request_user),
) -> ChatResponse:
    """
    Gibt nach einem einzigen Prompt die komplette Antwort zurück
    (kein Streaming).
    """
    try:
        answer = await run_chat(
            input_text=data.input_text,
            chat_id=data.chat_id,
            request=request,
        )
        return ChatResponse(answer=answer)
    except HTTPException as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Interner Serverfehler: {exc}",
        ) from exc
