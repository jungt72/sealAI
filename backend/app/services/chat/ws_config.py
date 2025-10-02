from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Set, Tuple


@dataclass(frozen=True)
class WebSocketConfig:
    coalesce_min_chars: int
    coalesce_max_latency_ms: float
    idle_timeout_sec: int
    first_token_timeout_ms: int
    input_max_chars: int
    rate_limit_per_min: int
    micro_chunk_chars: int
    emit_final_text: bool
    debug_events: bool
    event_timeout_sec: int
    force_sync_fallback: bool
    flush_endings: Tuple[str, ...]
    stream_nodes: Set[str]
    graph_builder: str
    default_route_mode: str


def _parse_stream_nodes(raw: str) -> Set[str]:
    raw = (raw or "").strip()
    if not raw or raw in {"*", "all"}:
        return {"*"}
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


@lru_cache(maxsize=1)
def get_ws_config() -> WebSocketConfig:
    flush_endings: Tuple[str, ...] = (
        ". ",
        "? ",
        "! ",
        "\n\n",
        ":",
        ";",
        "…",
        ", ",
        ") ",
        "] ",
        " }",
    )

    return WebSocketConfig(
        # CHANGE: aggressiveres Streaming / schnellere ersten Tokens
        coalesce_min_chars=int(os.getenv("WS_COALESCE_MIN_CHARS", "20")),     # vorher 24
        coalesce_max_latency_ms=float(os.getenv("WS_COALESCE_MAX_LAT_MS", "120")),  # vorher 40
        idle_timeout_sec=int(os.getenv("WS_IDLE_TIMEOUT_SEC", "45")),
        first_token_timeout_ms=int(os.getenv("WS_FIRST_TOKEN_TIMEOUT_MS", "1500")),  # vorher 2000
        input_max_chars=int(os.getenv("WS_INPUT_MAX_CHARS", "4000")),
        rate_limit_per_min=int(os.getenv("WS_RATE_LIMIT_PER_MIN", "30")),
        micro_chunk_chars=int(os.getenv("WS_MICRO_CHUNK_CHARS", "16")),       # vorher 0
        emit_final_text=os.getenv("WS_EMIT_FINAL_TEXT", "0") == "1",
        debug_events=os.getenv("WS_DEBUG_EVENTS", "1") == "1",
        event_timeout_sec=int(os.getenv("WS_EVENT_TIMEOUT_SEC", "25")),
        force_sync_fallback=os.getenv("WS_FORCE_SYNC", "0") == "1",
        flush_endings=flush_endings,
        stream_nodes=_parse_stream_nodes(os.getenv("WS_STREAM_NODES", "*")),
        graph_builder=os.getenv("GRAPH_BUILDER", "supervisor").lower(),
        default_route_mode=os.getenv("WS_MODE", "graph").strip().lower() or "graph",
    )


__all__ = ["WebSocketConfig", "get_ws_config"]
