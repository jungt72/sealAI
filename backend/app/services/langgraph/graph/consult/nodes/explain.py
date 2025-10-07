from __future__ import annotations

import logging
import json
from typing import Any, Dict, List, Tuple

from langchain_core.messages import AIMessage

log = logging.getLogger(__name__)

def _hashable_key(obj: Any) -> Any:
    if isinstance(obj, dict):
        try:
            return json.dumps(obj, sort_keys=True, ensure_ascii=False)
        except Exception:
            return tuple(sorted((str(k), _hashable_key(v)) for k, v in obj.items()))
    if isinstance(obj, (list, tuple, set)):
        return tuple(_hashable_key(x) for x in obj)
    return obj if isinstance(obj, (str, int, float, bool, type(None))) else str(obj)

def _dedup_dicts(seq: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for d in seq or []:
        k = _hashable_key(d)
        if k in seen:
            continue
        seen.add(k)
        out.append(d)
    return out

def explain_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Baut eine kurze Begründung/Erklärung mit optionalen Belegen.
    Wichtig: KEIN set(dict) – Dedup über hashbare Schlüssel.
    """
    msgs = state.get("messages") or []
    derived: Dict[str, Any] = state.get("derived") or {}
    citations: List[Dict[str, Any]] = state.get("citations") or []

    # Stabil deduplizieren (z. B. gleiche Quelle mehrfach)
    citations = _dedup_dicts(citations)

    reason = derived.get("reason") or derived.get("explain") or ""
    if not isinstance(reason, str):
        reason = str(reason or "")

    text = "Kurzbegründung:\n" + (reason.strip() or "Die Empfehlung basiert auf den erkannten Parametern und Regeln.")
    if citations:
        text += "\n\nQuellen/Belege:"
        for c in citations[:5]:
            src = c.get("source") or c.get("title") or c.get("url") or "Quelle"
            text += f"\n• {src}"

    return {
        **state,
        "messages": [AIMessage(content=text)],
        "phase": "explain",
        "citations": citations,
    }
