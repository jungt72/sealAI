from __future__ import annotations

import asyncio
import json
import re
import logging
from typing import Any, Dict
from fastapi import WebSocket, WebSocketDisconnect

from app.api.v1.dependencies.auth import guard_websocket
from app.services.chat.ws_commons import choose_subprotocol, get_rate_limit_client, send_json_safe, ws_log
from app.services.chat.ws_config import get_ws_config
from app.services.chat.ws_streaming import stream_llm_direct, stream_supervised
from app.services.langgraph.graph.consult.memory_utils import write_message as stm_write_message
from app.services.langgraph.llm_factory import get_llm as make_llm
from app.services.langgraph.tools import long_term_memory as ltm
from app.services.langgraph.hybrid_routing import extract_button_payload

logger = logging.getLogger(__name__)

REMEMBER_RX = re.compile(r"^\s*(?:!remember|remember|merke(?:\s*dir)?|speicher(?:e)?)\s*[:\-]?\s*(.+)$", re.I)
GREETING_RX = re.compile(r"^(hi|hallo|hello|hey|moin)\b", re.I)


class WebSocketChatHandler:
    def __init__(self) -> None:
        self.config = get_ws_config()

    async def handle(self, ws: WebSocket) -> None:
        await ws.accept(subprotocol=choose_subprotocol(ws))
        try:
            user_payload: Dict[str, Any] = await guard_websocket(ws)
        except Exception:
            await send_json_safe(ws, {"event": "error", "message": "unauthorized"})
            await ws.close(code=1008)
            return

        try:
            ws.scope["user"] = user_payload
        except Exception:
            pass

        app = ws.app

        # LLM sollte durch Startup-Warmup existieren; sonst erzeugen
        if not getattr(app.state, "llm", None):
            app.state.llm = make_llm(streaming=True)

        if not hasattr(app.state, "ws_cancel_flags"):
            app.state.ws_cancel_flags = {}

        try:
            await self._event_loop(ws)
        except WebSocketDisconnect:
            return
        except Exception as exc:
            # VOLLEN STACKTRACE loggen, nicht nur repr(exc)
            logger.exception("WS chat error")
            ws_log("ws_chat_error", error=repr(exc))
            await send_json_safe(ws, {"event": "done", "thread_id": "ws"})

    async def _event_loop(self, ws: WebSocket) -> None:
        app = ws.app
        config = self.config

        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=config.idle_timeout_sec)
            except asyncio.TimeoutError:
                await send_json_safe(ws, {"event": "idle", "ts": int(asyncio.get_event_loop().time())})
                continue

            if isinstance(raw, str) and config.input_max_chars > 0 and len(raw) > (config.input_max_chars * 2):
                await send_json_safe(ws, {"event": "error", "code": "input_oversize", "message": f"payload too large (>{config.input_max_chars * 2} chars)"})
                await send_json_safe(ws, {"event": "done", "thread_id": "ws"})
                continue

            try:
                ws_log("RX_raw", raw=(raw if len(raw) < 256 else raw[:252] + "...}"))
            except Exception:
                pass

            try:
                data = json.loads(raw)
            except Exception:
                await send_json_safe(ws, {"event": "error", "message": "invalid_json"})
                continue

            msg_type = (data.get("type") or "").strip().lower()
            if msg_type == "ping":
                await send_json_safe(ws, {"event": "pong", "ts": data.get("ts")})
                continue
            if msg_type == "cancel":
                thread_to_cancel = (data.get("thread_id") or f"api:{(data.get('chat_id') or 'default').strip()}").strip()
                ws.app.state.ws_cancel_flags[thread_to_cancel] = True
                await send_json_safe(ws, {"event": "done", "thread_id": thread_to_cancel})
                continue

            chat_id = (data.get("chat_id") or "").strip() or "default"
            thread_id = f"api:{chat_id}"
            payload = ws.scope.get("user") or {}
            user_id = str(payload.get("sub") or payload.get("email") or chat_id)

            rl = get_rate_limit_client(app)
            if rl and config.rate_limit_per_min > 0:
                key = f"ws:ratelimit:{user_id}:{chat_id}"
                try:
                    count = rl.incr(key)
                    if count == 1:
                        rl.expire(key, 60)
                    if count > config.rate_limit_per_min:
                        await send_json_safe(ws, {"event": "error", "code": "rate_limited", "message": "Too many requests, slow down.", "retry_after_sec": int(rl.ttl(key) or 60)})
                        await send_json_safe(ws, {"event": "done", "thread_id": thread_id})
                        continue
                except Exception:
                    pass

            params_patch = data.get("params") or data.get("params_patch")
            if not isinstance(params_patch, dict):
                params_patch = None

            user_input = (data.get("input") or data.get("text") or data.get("query") or "").strip()
            if user_input and config.input_max_chars > 0 and len(user_input) > config.input_max_chars:
                await send_json_safe(ws, {"event": "error", "code": "input_too_long", "message": f"input exceeds {config.input_max_chars} chars"})
                await send_json_safe(ws, {"event": "done", "thread_id": thread_id})
                continue

            if not user_input and not params_patch:
                await send_json_safe(ws, {"event": "error", "message": "missing_input", "thread_id": thread_id})
                continue

            try:
                app.state.ws_cancel_flags.pop(thread_id, None)
            except Exception:
                pass

            if user_input:
                try:
                    stm_write_message(thread_id=thread_id, role="user", content=user_input)
                except Exception:
                    pass

            # "remember ..." Kurzbefehl
            m = REMEMBER_RX.match(user_input or "")
            if m:
                note = m.group(1).strip()
                ok = False
                try:
                    ltm.upsert_memory(user=thread_id, chat_id=thread_id, text=note, kind="note")
                    ok = True
                except Exception:
                    ok = False
                msg = "✅ Gespeichert." if ok else "⚠️ Konnte nicht speichern."
                await send_json_safe(ws, {"event": "token", "delta": msg, "thread_id": thread_id})
                await send_json_safe(ws, {"event": "done", "thread_id": thread_id})
                try:
                    stm_write_message(thread_id=thread_id, role="assistant", content=msg)
                except Exception:
                    pass
                continue

            # direkter Smalltalk
            if user_input and not params_patch and GREETING_RX.match(user_input):
                llm = getattr(app.state, "llm", make_llm(streaming=True))
                await stream_llm_direct(ws, llm, user_input=user_input, thread_id=thread_id, config=config)
                try:
                    app.state.ws_cancel_flags.pop(thread_id, None)
                except Exception:
                    pass
                continue

            mode = (data.get("mode") or config.default_route_mode).strip().lower() or config.default_route_mode
            graph_name = (data.get("graph") or config.graph_builder).strip().lower() or config.graph_builder

            routing_payload = extract_button_payload(data)
            if routing_payload.get("intent_seed") and not routing_payload.get("source"):
                routing_payload["source"] = "ui_button"
            if routing_payload.get("source") == "ui_button" and not routing_payload.get("confidence"):
                routing_payload["confidence"] = 0.95

            await send_json_safe(ws, {"event": "start", "thread_id": thread_id, "route": mode, "graph": graph_name})

            if mode == "llm":
                llm = getattr(app.state, "llm", make_llm(streaming=True))
                await stream_llm_direct(ws, llm, user_input=user_input or "", thread_id=thread_id, config=config)
            else:
                await stream_supervised(
                    ws,
                    app=app,
                    user_input=user_input or "",
                    thread_id=thread_id,
                    params_patch=params_patch,
                    builder_name=graph_name,
                    config=config,
                    routing_payload=routing_payload,
                )

            try:
                app.state.ws_cancel_flags.pop(thread_id, None)
            except Exception:
                pass


__all__ = ["WebSocketChatHandler"]
