from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import redis
from fastapi import WebSocket
from fastapi import WebSocketDisconnect


def ws_log(message: str, **extra: Any) -> None:
    try:
        if extra:
            print(f"[ws] {message} " + json.dumps(extra, ensure_ascii=False, default=str))
        else:
            print(f"[ws] {message}")
    except Exception:
        try:
            print(f"[ws] {message} {extra}")
        except Exception:
            pass


async def send_json_safe(ws: WebSocket, payload: Dict[str, Any]) -> bool:
    try:
        await ws.send_json(payload)
        return True
    except WebSocketDisconnect:
        return False
    except Exception:
        return False


def choose_subprotocol(ws: WebSocket) -> Optional[str]:
    raw = ws.headers.get("sec-websocket-protocol")
    if not raw:
        return None
    return raw.split(",")[0].strip() or None


def get_rate_limit_client(app) -> Optional[redis.Redis]:
    client = getattr(app.state, "redis_rl", None)
    if client is not None:
        return client
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        app.state.redis_rl = client
        return client
    except Exception:
        return None


__all__ = ["ws_log", "send_json_safe", "choose_subprotocol", "get_rate_limit_client"]
