"""Per-turn stage timing (PERF tranche 1, P0) — one structured JSON line per pipeline turn.

NO PII by construction: the payload carries stage durations + a random turn id only — never
question/answer text, never tenant/session ids. Lines go to the ``sealai_v2.timing`` logger,
quiet by default (NullHandler) so offline tests and imports never print; the API entrypoint
calls ``configure_timing_logging()`` to attach a stdout handler (the V1 lesson: unconfigured
stdlib logging is invisible in prod docker logs). Pure bookkeeping over ``time.monotonic()`` —
the timer never touches stage inputs/outputs, so it cannot alter results.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid

from sealai_v2.obs.log_redaction import SafeLogValue

logger = logging.getLogger("sealai_v2.timing")
logger.addHandler(logging.NullHandler())


def configure_timing_logging() -> None:
    """Attach a plain stdout line handler (idempotent) so timing lines reach docker logs."""
    for h in logger.handlers:
        if (
            isinstance(h, logging.StreamHandler)
            and getattr(h, "stream", None) is sys.stdout
        ):
            return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def emit(payload: dict) -> None:
    """One JSON line per turn. Module-level seam so tests can monkeypatch/capture."""
    logger.info("%s", SafeLogValue(json.dumps(payload, ensure_ascii=False)))


class TurnTimer:
    """Collects per-stage durations for one ``pipeline.run`` turn.

    Stages that did not run simply never record a key (e.g. no ``distill_ms`` without a
    session). ``total_ms`` is the user-facing wall clock of the turn, captured at the
    response point via ``finish()`` — it is NOT the sum of the stages (in-process glue is
    unmeasured, and concurrent stages overlap)."""

    def __init__(self) -> None:
        self.turn_id = uuid.uuid4().hex[:12]
        self.stages: dict[str, float] = {}
        self._start = time.monotonic()
        self.total_ms: float | None = None

    def stage(self, name: str) -> "_StageClock":
        return _StageClock(self, name)

    def record(self, name: str, duration_ms: float) -> None:
        self.stages[name] = round(duration_ms, 1)

    def finish(self) -> None:
        """Freeze ``total_ms`` at the response point (idempotent — first call wins)."""
        if self.total_ms is None:
            self.total_ms = round((time.monotonic() - self._start) * 1000.0, 1)

    def emit(self) -> None:
        self.finish()
        emit(
            {
                "event": "v2_turn_timing",
                "turn_id": self.turn_id,
                "stages": dict(self.stages),
                "total_ms": self.total_ms,
            }
        )


class _StageClock:
    """``with timer.stage("ground_ms"): …`` — a sync context manager wrapping awaited calls."""

    def __init__(self, timer: TurnTimer, name: str) -> None:
        self._timer = timer
        self._name = name
        self._t0 = 0.0

    def __enter__(self) -> "_StageClock":
        self._t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._timer.record(self._name, (time.monotonic() - self._t0) * 1000.0)
