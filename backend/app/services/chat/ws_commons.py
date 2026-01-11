from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

try:
    import redis  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    redis = None  # type: ignore[assignment]
from app.services.redis_client import make_redis_client
from app.utils.json import to_jsonable_dict


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
        # Debug logging for serialization issues
        ws_log(f"Sending payload type: {type(payload)}, keys: {list(payload.keys()) if isinstance(payload, dict) else 'not dict'}")
        for k, v in payload.items():
            ws_log(f"Payload[{k}]: type={type(v)}, class={v.__class__.__name__}")
        # Convert payload to jsonable
        jsonable_payload = to_jsonable_dict(payload)
        await ws.send_json(jsonable_payload)
        return True
    except WebSocketDisconnect:
        return False
    except Exception as e:
        ws_log(f"send_json_safe error: {type(e).__name__}: {str(e)}")
        return False


def choose_subprotocol(ws: WebSocket) -> Optional[str]:
    raw = ws.headers.get("sec-websocket-protocol")
    if not raw:
        return None
    return raw.split(",")[0].strip() or None


def get_rate_limit_client(app) -> Optional["redis.Redis"]:
    if redis is None:
        return None
    client = getattr(app.state, "redis_rl", None)
    if client is not None:
        return client
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        client = make_redis_client(url, decode_responses=True)
        app.state.redis_rl = client
        return client
    except Exception:
        return None


__all__ = ["ws_log", "send_json_safe", "choose_subprotocol", "get_rate_limit_client"]
