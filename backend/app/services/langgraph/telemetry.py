from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .config.runtime import get_runtime_config

log = logging.getLogger("uvicorn.error")


@dataclass
class RoutingEvent:
    event: str
    thread_id: Optional[str] = None
    user_id: Optional[str] = None
    source: Optional[str] = None
    intent_candidate: Optional[str] = None
    intent_final: Optional[str] = None
    confidence: Optional[float] = None
    next_node: Optional[str] = None
    fallback: bool = False
    duration_ms: Optional[float] = None
    feature_flag_state: Optional[bool] = None
    extras: Optional[Dict[str, Any]] = None

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "event": self.event,
            "thread_id": self.thread_id,
            "user_id": self.user_id,
            "source": self.source,
            "intent_candidate": self.intent_candidate,
            "intent_final": self.intent_final,
            "confidence": self.confidence,
            "next_node": self.next_node,
            "fallback": self.fallback,
            "duration_ms": self.duration_ms,
            "feature_flag_state": self.feature_flag_state,
        }
        if self.extras:
            payload.update(self.extras)
        return {k: v for k, v in payload.items() if v is not None}


def emit_routing_event(event: RoutingEvent) -> None:
    payload = event.to_payload()
    cfg = get_runtime_config()
    payload.setdefault("feature_flag_state", cfg.hybrid_routing_enabled)
    try:
        log.info("[telemetry] %s", json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:  # pragma: no cover - logging fallback
        log.info("[telemetry] %s %s", event.event, payload)


class RoutingTimer:
    __slots__ = ("_start",)

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def stop(self) -> float:
        end = time.perf_counter()
        return round((end - self._start) * 1000.0, 3)


__all__ = ["emit_routing_event", "RoutingEvent", "RoutingTimer"]
