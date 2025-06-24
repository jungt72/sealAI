# 📁 backend/app/api/v1/endpoints/ws_chat.py
"""
WebSocket-Endpoint für den Chat-Stream.
Kompatibel mit Starlette ≥0.27 (CloseCode) UND älteren Versionen.
"""

from __future__ import annotations

import json
from typing import AsyncGenerator, Dict, List

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from starlette.websockets import WebSocketState

from app.services.auth.dependencies import get_current_ws_user
from app.services.chat.chat_chain import run_chat_ws  # eigene WS-Logik (s. u.)

# -----------------------------------------------------------------------------
#   Kompatibilität: CloseCode in neueren Starlette-Releases
# -----------------------------------------------------------------------------
try:
    from starlette.websockets import CloseCode  # Starlette ≥0.27
except ImportError:  # ältere Versionen → Fallback definieren
    class CloseCode:
        NORMAL_CLOSURE = 1000
        GOING_AWAY = 1001
        PROTOCOL_ERROR = 1002
        INTERNAL_ERROR = 1011

# -----------------------------------------------------------------------------
router = APIRouter(prefix="/ai", tags=["AI (WebSocket)"])

# -----------------------------------------------------------------------------
@router.websocket("/ws")
async def chat_ws_endpoint(
    websocket: WebSocket,
    username: str = Depends(get_current_ws_user),
):
    """
    Bidirektionaler Chat-Stream.

    Client schickt JSON:
    ```json
    { "chat_id": "abc", "message": "Frage?" }
    ```

    Server streamt reinen Text (Token/Chunk-Weise).  
    Wenn fertig → schließt mit CloseCode.NORMAL_CLOSURE.
    """
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()                # Blockiert
            try:
                data: Dict = json.loads(raw)
                chat_id: str = data.get("chat_id", "default")
                message: str = data.get("message", "").strip()
            except Exception:
                await websocket.close(code=CloseCode.PROTOCOL_ERROR)
                return

            # --- Chat-Pipeline ------------------------------------------------
            async for chunk in run_chat_ws(username, chat_id, message):
                # kann entweder reinen Text oder JSON streamen
                if websocket.application_state != WebSocketState.CONNECTED:
                    break
                await websocket.send_text(chunk)

    except WebSocketDisconnect:
        # Ordentlicher Abbruch durch den Client
        return
    except Exception as exc:
        # Unerwarteter Fehler → 1011
        try:
            await websocket.close(code=CloseCode.INTERNAL_ERROR)
        finally:
            raise exc
