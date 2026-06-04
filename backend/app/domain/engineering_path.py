"""Authority-conformant engineering path validation.

This module deliberately validates explicit ``engineering_path`` authority
values only. Neighbouring signals such as motion type, sealing type, seal
family, or requirement class seal type are not semantic derivation sources.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

AUTHORITY_ENGINEERING_PATHS: frozenset[str] = frozenset(
    {
        "ms_pump",
        "rwdr",
        "static",
        "labyrinth",
        "hyd_pneu",
        "unclear_rotary",
    }
)


def _non_empty(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return None if not value.strip() else value
    text = str(value).strip()
    return text or None


def derive_engineering_path(
    *,
    engineering_path: Any = None,
    authority_values: Iterable[Any] | None = None,
    **non_authority_signals: Any,
) -> str | None:
    """Return one explicit authority ``engineering_path`` value, or ``None``.

    Only ``engineering_path`` and ``authority_values`` are authority sources.
    Extra keyword arguments are accepted so callers can pass nearby context
    without accidentally turning it into engineering truth.
    """

    del non_authority_signals

    raw_values: list[Any] = [engineering_path]
    if authority_values is not None:
        raw_values.extend(authority_values)

    selected: str | None = None
    for value in raw_values:
        text = _non_empty(value)
        if text is None:
            continue
        if text not in AUTHORITY_ENGINEERING_PATHS:
            return None
        if selected is None:
            selected = text
            continue
        if selected != text:
            return None

    return selected
