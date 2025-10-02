from fastapi import APIRouter, WebSocket

from app.services.chat import WebSocketChatHandler

router = APIRouter()
_handler = WebSocketChatHandler()


@router.websocket("/ai/ws")
async def ws_chat(ws: WebSocket) -> None:
    await _handler.handle(ws)
