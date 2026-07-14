"""Sampling policy for high-volume metadata-only runtime telemetry.

Metrics counters must use every event; this policy applies only to log/trace copies. Error events
remain unsampled. An invalid configured rate fails closed to zero informational telemetry.
"""

from __future__ import annotations

import os
import random
from collections.abc import Callable

_ENV_NAME = "SEALAI_V2_TELEMETRY_SAMPLE_RATE"


def resolve_telemetry_sample_rate(value: str | None = None) -> float:
    raw = os.getenv(_ENV_NAME) if value is None else value
    if raw is None or not raw.strip():
        return 1.0
    try:
        rate = float(raw)
    except ValueError:
        return 0.0
    if not 0.0 <= rate <= 1.0:
        return 0.0
    return rate


def should_sample(
    rate: float, *, random_value: Callable[[], float] = random.random
) -> bool:
    if rate <= 0.0:
        return False
    if rate >= 1.0:
        return True
    return random_value() < rate
