"""Utility helpers to robustly extract JSON from LLM outputs."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Tuple


_FENCE_RE = re.compile(r"```(?:json)?(.*?)```", re.DOTALL | re.IGNORECASE)
_JSON_LIKE_RE = re.compile(r"\{.*\}", re.DOTALL)


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _find_json_substring(text: str) -> str | None:
    """Find the first JSON-looking substring."""
    match = _JSON_LIKE_RE.search(text)
    if match:
        return match.group(0)
    return None


def extract_json_obj(raw: Any, default: Dict[str, Any] | None = None) -> Tuple[Dict[str, Any], bool]:
    """
    Try to parse a JSON object from arbitrary LLM output.

    Returns (data, success_flag). On failure, returns (default or {}, False).
    """
    if raw is None:
        return (default or {}, False)

    if isinstance(raw, dict):
        return (raw, True)

    text = str(raw)
    if not text.strip():
        return (default or {}, False)

    # 1) Strip fences
    candidate = _strip_fences(text)

    # 2) Try full parse
    for payload in (candidate, _find_json_substring(candidate) or candidate):
        try:
            data = json.loads(payload)
            if isinstance(data, dict):
                return (data, True)
        except Exception:
            continue

    return (default or {}, False)


__all__ = ["extract_json_obj"]
