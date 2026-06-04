"""Authority-conformant case phase validation.

This module validates explicit case lifecycle phase values only. It does not
derive phase from readiness, route, rendering, graph cycle, or projection data.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

AUTHORITY_CASE_PHASES: frozenset[str] = frozenset(
    {
        "clarification",
        "recommendation",
        "matching",
        "rfq_handover",
    }
)


def _non_empty(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return None if not value.strip() else value
    text = str(value).strip()
    return text or None


def derive_case_phase(
    *,
    phase: Any = None,
    authority_values: Iterable[Any] | None = None,
    **non_authority_signals: Any,
) -> str | None:
    """Return one explicit authority case phase value, or ``None``.

    Only ``phase`` and ``authority_values`` are authority sources. Extra
    keyword arguments are accepted so callers can pass nearby context without
    accidentally turning it into lifecycle truth.
    """

    del non_authority_signals

    raw_values: list[Any] = [phase]
    if authority_values is not None:
        raw_values.extend(authority_values)

    selected: str | None = None
    for value in raw_values:
        text = _non_empty(value)
        if text is None:
            continue
        if text not in AUTHORITY_CASE_PHASES:
            return None
        if selected is None:
            selected = text
            continue
        if selected != text:
            return None

    return selected
