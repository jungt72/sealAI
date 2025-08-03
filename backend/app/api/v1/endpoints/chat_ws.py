# backend/app/api/v1/endpoints/chat_ws.py

from fastapi import APIRouter, WebSocket, Query, Depends, WebSocketDisconnect
from fastapi.websockets import WebSocketState
import asyncio
import json
import structlog

from app.services.auth.token import verify_access_token
from app.services.langgraph.langgraph_chat import run_langgraph_stream

router = APIRouter()
log = structlog.get_logger(__name__)


async def _close(ws: WebSocket, code: int, reason: str, detail: str | None = None):
    if detail:
        log.warning("WS close", detail=detail)
    if ws.application_state == WebSocketState.CONNECTED:
        try:
            await ws.close(code=code, reason=reason)
        except RuntimeError:
            pass


async def get_user_id(ws: WebSocket, token: str = Query(...)) -> str:
    if not token:
        await _close(ws, 1008, "unauthenticated", "Missing token")
        raise WebSocketDisconnect(code=1008, reason="unauthenticated")
    try:
        payload = verify_access_token(token)
        return payload["sub"]
    except Exception as exc:
        await _close(ws, 1008, "forbidden", f"JWT error: {exc}")
        raise WebSocketDisconnect(code=1008, reason="forbidden")


@router.websocket("/ws")
async def chat_stream(
    ws: WebSocket,
    user_id: str = Depends(get_user_id),
):
    await ws.accept(subprotocol="json")
    log.info("WS connected", client=ws.client, uid=user_id)

    stop_event = asyncio.Event()

    async def send_ping():
        try:
            while not stop_event.is_set():
                await asyncio.sleep(30)
                if ws.application_state == WebSocketState.CONNECTED:
                    try:
                        await ws.send_json({"type": "ping"})
                    except Exception as e:
                        log.debug("Ping error (breaking loop):", exc_info=e)
                        break
        except asyncio.CancelledError:
            log.debug("Ping task cancelled (normal on WS close).")

    ping_task = asyncio.create_task(send_ping())

    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=60)
                msg = json.loads(raw)
                chat_id = msg.get("chat_id", "debug")
                user_text = msg.get("input") or msg.get("text", "")
                if not user_text:
                    await ws.send_json(
                        {
                            "type": "error",
                            "code": "bad_request",
                            "detail": "Missing field: input or text",
                        }
                    )
                    continue
            except asyncio.TimeoutError:
                await _close(ws, 1000, "timeout", "No input within 60 s.")
                break
            except WebSocketDisconnect:
                break
            except Exception as exc:
                await ws.send_json(
                    {"type": "error", "code": "invalid_payload", "detail": str(exc)}
                )
                continue

            # ----- LangGraph-Streaming starten -----
            try:
                async for chunk in run_langgraph_stream(
                    user_id=user_id,
                    chat_id=chat_id,
                    user_text=user_text,
                    app=ws.app,  # FastAPI app
                ):
                    await ws.send_json(chunk)
            except Exception as exc:
                await ws.send_json(
                    {"type": "error", "code": "internal_error", "detail": str(exc)}
                )
                break

    finally:
        stop_event.set()
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            log.debug("Ping task cancelled (handled in finally).")
        except Exception as exc:
            log.warning("Ping task error in finally", exc_info=exc)
        await _close(ws, 1000, "normal_closure")
        log.info("WS disconnected", uid=user_id)
