"""Per-turn streaming timing — one central measurement for the whole runtime.

P1-2 TEIL A (Gap-Audit S1). Instead of per-path copies of `first_progress_ms` /
`latency_ms` (today only the mobile triage path fills them), the streaming layer
measures *once* per turn and every TurnRoute reads the same two numbers from the
same source:

* ``first_progress_ms`` — time from turn start to the first emitted SSE frame
  (time-to-first-chunk).
* ``latency_ms`` — time from turn start to "now" (read when the final
  ``state_update`` is serialized → total turn duration).

Contextvar-scoped so concurrent turns never cross. If the timer was never started
(non-streaming callers), every reader degrades to ``None`` — no exceptions.
"""

from __future__ import annotations

import time
from contextvars import ContextVar

_START: ContextVar[float | None] = ContextVar("turn_timing_start", default=None)
_FIRST_PROGRESS_MS: ContextVar[int | None] = ContextVar(
    "turn_timing_first_progress_ms", default=None
)


def start_turn_timer() -> None:
    """Begin (or restart) the per-turn timer at the streaming entry."""
    _START.set(time.monotonic())
    _FIRST_PROGRESS_MS.set(None)


def mark_first_progress() -> int | None:
    """Record time-to-first-chunk on the first emitted frame (idempotent)."""
    start = _START.get()
    if start is None:
        return None
    existing = _FIRST_PROGRESS_MS.get()
    if existing is not None:
        return existing
    ms = max(0, int((time.monotonic() - start) * 1000))
    _FIRST_PROGRESS_MS.set(ms)
    return ms


def turn_timing() -> tuple[int | None, int | None]:
    """Return ``(first_progress_ms, latency_ms)`` for the current turn.

    ``latency_ms`` is measured to *now* (caller emits this on the final frame).
    ``(None, None)`` when the timer was never started.
    """
    start = _START.get()
    if start is None:
        return None, None
    latency_ms = max(0, int((time.monotonic() - start) * 1000))
    return _FIRST_PROGRESS_MS.get(), latency_ms
