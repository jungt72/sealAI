"""SSE event contract helpers for backend chat streams."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4


SSEEventType = Literal[
    "delta",
    "state_update",
    "final",
    "error",
    "interrupted",
    "done",
    "metadata",
]

_TURN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def stable_turn_id(
    *, session_id: str | None, message: str | None, explicit_turn_id: str | None = None
) -> str:
    if explicit_turn_id:
        candidate = explicit_turn_id.strip()
        if _TURN_ID_RE.fullmatch(candidate):
            return candidate
    return f"turn:{uuid4().hex}"


def infer_event_type(payload: dict[str, Any]) -> SSEEventType:
    raw_type = str(payload.get("type") or payload.get("event_type") or "metadata")
    if raw_type in {"state_update"}:
        return "state_update"
    if raw_type in {"error"}:
        return "error"
    if raw_type in {"interrupted"}:
        return "interrupted"
    if raw_type in {"done", "turn_complete", "stream_end"}:
        return "done"
    if raw_type in {"text_chunk", "answer.token", "delta"}:
        return "delta"
    if raw_type in {"final"}:
        return "final"
    return "metadata"


def _event_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "turn_id",
            "turnId",
            "event_id",
            "eventId",
            "sequence",
            "event_type",
            "is_final",
            "error_code",
        }
    }


@dataclass
class SSEEventBuilder:
    turn_id: str
    sequence: int = 0
    final_emitted: bool = False

    @classmethod
    def for_request(cls, request: Any) -> "SSEEventBuilder":
        explicit_turn_id = getattr(request, "turn_id", None) or getattr(
            request, "request_id", None
        )
        return cls(
            turn_id=stable_turn_id(
                session_id=str(getattr(request, "session_id", "") or "default"),
                message=str(getattr(request, "message", "") or ""),
                explicit_turn_id=str(explicit_turn_id) if explicit_turn_id else None,
            )
        )

    def event(
        self,
        payload: dict[str, Any],
        *,
        event_type: SSEEventType | None = None,
        is_final: bool = False,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        normalized = dict(payload)
        normalized_type = event_type or infer_event_type(normalized)
        # P1-2 TEIL A: one central per-turn timing — mark time-to-first-chunk on the
        # first emitted frame, and stamp first_progress_ms/latency_ms on the final
        # state_update so EVERY TurnRoute fills the same fields from the same source.
        # No-op when the streaming timer was never started (nested mobile trace is
        # left byte-identical).
        from app.agent.runtime.turn_timing import mark_first_progress, turn_timing  # noqa: PLC0415

        mark_first_progress()
        if is_final and normalized_type == "state_update":
            first_progress_ms, latency_ms = turn_timing()
            if first_progress_ms is not None or latency_ms is not None:
                trace = (
                    dict(normalized.get("trace") or {})
                    if isinstance(normalized.get("trace"), dict)
                    else {}
                )
                if (
                    trace.get("first_progress_ms") is None
                    and first_progress_ms is not None
                ):
                    trace["first_progress_ms"] = first_progress_ms
                if trace.get("latency_ms") is None and latency_ms is not None:
                    trace["latency_ms"] = latency_ms
                normalized["trace"] = trace
        if is_final:
            if self.final_emitted:
                raise ValueError("sse_final_event_already_emitted")
            self.final_emitted = True
        self.sequence += 1
        normalized.update(
            {
                "turn_id": self.turn_id,
                "event_id": f"{self.turn_id}:{self.sequence}",
                "sequence": self.sequence,
                "event_type": normalized_type,
                "is_final": bool(is_final),
                "error_code": error_code,
                "data": _event_data(normalized),
            }
        )
        return normalized

    def frame(
        self,
        payload: dict[str, Any],
        *,
        event_type: SSEEventType | None = None,
        is_final: bool = False,
        error_code: str | None = None,
    ) -> str:
        event = self.event(
            payload,
            event_type=event_type,
            is_final=is_final,
            error_code=error_code,
        )
        return f"data: {json.dumps(event, default=str)}\n\n"
