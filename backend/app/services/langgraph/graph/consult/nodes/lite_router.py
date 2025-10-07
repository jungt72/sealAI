# backend/app/services/langgraph/graph/consult/nodes/lite_router.py
from __future__ import annotations

import re
from typing import Any, Dict, List

from ..utils import normalize_messages

# (unverändert) Regexe …
RE_GREET = re.compile(
    r"\b(hi|hallo|hello|hey|servus|moin|grüß(?:e)?\s*dich|guten\s*(?:morgen|tag|abend))\b",
    re.I,
)
RE_SMALLTALK = re.compile(
    r"\b(wie\s+geht'?s|alles\s+gut|was\s+geht|na\s+du|danke|bitte|tschüss|ciao|bye|weitere\s+infor?\w*|mehr\s+details?)\b",
    re.I,
)
RE_TECH_HINT = re.compile(
    r"\b(rwdr|hydraulik|dichtung|welle|gehäuse|rpm|u\/min|bar|°c|tmax|werkstoff|profil|rag|query|bm25)\b",
    re.I,
)

def _join_user_text(msgs: List) -> str:
    out: List[str] = []
    for m in msgs:
        role = (getattr(m, "type", "") or getattr(m, "role", "")).lower()
        content = getattr(m, "content", "")
        if isinstance(m, dict):
            role = (m.get("type") or m.get("role") or "").lower()
            content = m.get("content")
        if role in ("human", "user") and isinstance(content, str) and content.strip():
            out.append(content.strip())
    return " ".join(out)

def _fallback_text_from_state(state: Dict[str, Any]) -> str:
    # NEU: WS/HTTP-Fallbacks wie im RAG-Node
    for k in ("input", "user_input", "question", "query"):
        v = state.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def _with_route(state: Dict[str, Any], route: str) -> Dict[str, Any]:
    return {**state, "route": route, "phase": "lite_router"}


SMALLTALK_LENGTH_THRESHOLD = 40


def lite_router_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entscheidet, ob wir in Smalltalk verzweigen oder in den technischen Flow.
      - Gruß-/Smalltalk-Phrasen bei kurzen Texten → smalltalk
      - technische Stichwörter → default
      - sonst: sehr kurze Eingaben → smalltalk
    """
    msgs = normalize_messages(state.get("messages", []))

    # Formular-Patches/Submits liefern in der Regel Parameter – diese sollen immer in den
    # technischen Flow laufen, auch wenn der User-Text sehr kurz ist (z. B. "form submit" aus der Sidebar).
    params = state.get("params") or {}
    if isinstance(params, dict) and params:
        return _with_route(state, "default")

    text = _join_user_text(msgs)

    # NEU: wenn keine messages vorhanden, auf input/question/query zurückfallen
    if not text:
        text = _fallback_text_from_state(state)

    tlen = len(text)

    if not text:
        return _with_route(state, "default")

    if RE_TECH_HINT.search(text):
        return _with_route(state, "default")

    if RE_GREET.search(text) or RE_SMALLTALK.search(text):
        if tlen <= 80:
            return _with_route(state, "smalltalk")

    if tlen <= SMALLTALK_LENGTH_THRESHOLD:
        return _with_route(state, "smalltalk")

    return _with_route(state, "default")
