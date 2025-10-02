"""Lightweight metrics wrapper: optional Prometheus integration.

If `prometheus_client` is installed, exposes counters/gauges; otherwise functions are no-op.
"""
from __future__ import annotations

try:
    from prometheus_client import Counter, Summary
    _PROM = True
except Exception:
    _PROM = False

if _PROM:
    PROMPT_RENDER_FAIL = Counter("sealai_prompt_render_failures_total", "Prompt render failures")
    PROMPT_TOKENS = Summary("sealai_prompt_tokens", "Prompt token counts")

    def inc_prompt_render_failures() -> None:
        PROMPT_RENDER_FAIL.inc()

    def observe_prompt_tokens(n: int) -> None:
        PROMPT_TOKENS.observe(n)
else:
    def inc_prompt_render_failures() -> None:  # type: ignore
        return None

    def observe_prompt_tokens(n: int) -> None:  # type: ignore
        return None

