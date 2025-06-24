# backend/app/api/v1/endpoints/chat_ws.py
"""
Bidirektionaler Chat-Stream via WebSocket (OpenAI API-kompatibles Streaming)
URL:  ws[s]://…/api/v1/ai/ws?token=<JWT>&json_stream=1

Client →  {"chat_id": "...", "input": "..."}
Server →  • JSON-Tokens wie OpenAI-API
          • Abschluss-Frame {"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}
          • Fehler-Frame    {"type": "error", ...}
"""

from __future__ import annotations

import asyncio, json, logging
from typing import Any

from fastapi import APIRouter, WebSocket, status
from fastapi.websockets import WebSocketDisconnect, WebSocketState
from jose import JWTError

from app.services.auth.token import verify_access_token
from app.services.chat.chat_chain import _prepare_inputs, get_memory_for_thread
from app.services.llm.llm_factory import get_llm
from app.services.prompt.prompt_orchestrator import build_dynamic_prompt
from langchain_core.runnables import RunnableLambda, RunnableWithMessageHistory

router = APIRouter()
log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Helper
# --------------------------------------------------------------------------- #
async def _close(ws: WebSocket, code: int, reason: str, detail: str | None = None) -> None:
    """WebSocket sauber schließen – egal ob schon accepted oder nicht."""
    if detail:
        log.warning(detail)
    if ws.application_state != WebSocketState.CONNECTED:
        await ws.close(code=code, reason=reason)
    else:
        await ws.close(code=code, reason=reason)

async def _authenticate(ws: WebSocket) -> dict[str, Any] | None:
    """JWT aus ?token=… lesen & verifizieren."""
    token = ws.query_params.get("token")
    if not token:
        await _close(ws, 4401, "unauthenticated", "missing token")
        return None
    try:
        return verify_access_token(token)
    except (JWTError, ValueError) as exc:
        await _close(ws, 4403, "forbidden", f"JWT error: {exc}")
        return None

# --------------------------------------------------------------------------- #
# Haupt-Endpoint
# --------------------------------------------------------------------------- #
@router.websocket("/ws")   # ergibt final: /api/v1/ai/ws
async def chat_stream(ws: WebSocket) -> None:
    # 1) Auth --> erst **dann** accept()
    payload = await _authenticate(ws)
    if payload is None:
        return
    await ws.accept()

    user_id: str = payload["sub"]
    username: str = payload.get("preferred_username", user_id)
    log.info("🆗 WS connected %s (uid=%s)", ws.client, user_id)

    json_stream = ws.query_params.get("json_stream") == "1"
    llm = get_llm()

    try:
        while True:
            raw = await ws.receive_text()
            log.info(f"🟢 WebSocket-Input erhalten: {raw!r}")   # <<<<<< DEBUG LOG
            if not raw.strip():
                continue
            if not raw.strip():
                continue

            try:
                msg       = json.loads(raw)
                chat_id   = msg["chat_id"]
                user_text = msg["input"].strip()
                if not user_text:
                    raise ValueError("input empty")
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                log.warning(f"❌ WS invalid_payload: {exc}")
                await ws.send_json({"type": "error",
                                    "code": "invalid_payload",
                                    "detail": str(exc)})
                continue

            session_id = f"{user_id}:{chat_id}"

            # Prompt-Vorbereitung (inkl. RAG, Memory etc.)
            try:
                inputs = await _prepare_inputs(username, chat_id, user_text)
                log.info(f"### WS DEBUG: inputs={inputs!r} type={type(inputs)}")
                if not isinstance(inputs, dict):
                    raise TypeError(f"Prepared input must be a dict, got {type(inputs)}: {inputs!r}")
                for k, v in inputs.items():
                    log.info(f"### WS DEBUG: input-field '{k}' type={type(v)} value={v!r}")
            except Exception as exc:
                log.exception(f"❌ Input-Preparation failed: {exc}")
                await ws.send_json({"type": "error",
                                    "code": "internal_error",
                                    "detail": f"Input-Preparation failed: {exc}"})
                continue

            # Prompt + LLM als Chain mit Memory
            try:
                chain = RunnableWithMessageHistory(
                    # WICHTIG: PromptTemplate → format_prompt(**inputs) → PromptValue (korrekt für llm.invoke)
                    RunnableLambda(lambda i: llm.invoke(build_dynamic_prompt(i).format_prompt(**i))),
                    get_memory_for_thread,
                    input_messages_key="input",
                    history_messages_key="chat_history"
                ).with_config(configurable={"session_id": session_id})
            except Exception as exc:
                log.exception("❌ Chain-Erstellung fehlgeschlagen")
                await ws.send_json({"type": "error",
                                    "code": "internal_error",
                                    "detail": f"Chain-Erstellung fehlgeschlagen: {exc}"})
                continue

            # 4) Streaming-Loop (OpenAI-kompatibel)
            if json_stream:
                try:
                    async for token in chain.astream(inputs):
                        text = getattr(token, "content", None)
                        if text is None:
                            text = str(token)
                        await ws.send_json({
                            "choices": [{"delta": {"content": text}, "index": 0}]
                        })
                        await asyncio.sleep(0)
                    await ws.send_json({
                        "choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}]
                    })
                except TypeError as exc:
                    log.exception(f"Streaming loop failed (TypeError): {exc}")
                    await ws.send_json({"type": "error",
                                        "code": "prompt_input_error",
                                        "detail": str(exc)})
                except Exception as exc:
                    log.exception("Streaming loop failed: %s", exc)
                    await ws.send_json({"type": "error",
                                        "code": "internal_error",
                                        "detail": str(exc)})
            else:
                bucket: list[str] = []
                try:
                    async for token in chain.astream(inputs):
                        text = getattr(token, "content", None)
                        if text is None:
                            text = str(token)
                        bucket.append(text)
                        if sum(len(t) for t in bucket) > 256:
                            await ws.send_text("".join(bucket))
                            bucket.clear()
                            await asyncio.sleep(0)
                    if bucket:
                        await ws.send_text("".join(bucket))
                    await ws.send_json({"type": "end"})
                except TypeError as exc:
                    log.exception(f"Streaming loop failed (TypeError): {exc}")
                    await ws.send_json({"type": "error",
                                        "code": "prompt_input_error",
                                        "detail": str(exc)})
                except Exception as exc:
                    log.exception("Streaming loop failed: %s", exc)
                    await ws.send_json({"type": "error",
                                        "code": "internal_error",
                                        "detail": str(exc)})

    except WebSocketDisconnect:
        log.info("🔌 WS disconnected %s (uid=%s)", ws.client, user_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("WS crash uid=%s: %s", user_id, exc)
        await _close(ws, status.WS_1011_INTERNAL_ERROR, "internal_error")
