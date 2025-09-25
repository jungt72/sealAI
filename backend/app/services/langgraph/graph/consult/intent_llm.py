from __future__ import annotations

"""
LLM-basierter Intent-Router (verpflichtend).
- Nutzt ChatOpenAI (Model per ENV, Default: gpt-5-mini).
- Gibt eines der erlaubten Labels zurück, sonst 'chitchat'.
- Fallback: robuste Heuristik, falls LLM fehlschlägt.
"""

import os
import re
import logging
from typing import Any, Dict, List, Optional, TypedDict

log = logging.getLogger("uvicorn.error")

# Erlaubte Ziele (müssen mit build.py übereinstimmen)
ALLOWED_ROUTES: List[str] = [
    "rag_qa",
    "material_agent",
    "profile_agent",
    "calc_agent",
    "report_agent",
    "memory_export",
    "memory_delete",
    "chitchat",
]

# Prompt für den reinen Label-Output
_INTENT_PROMPT = """Du bist ein Intent-Router. Antworte NUR mit einem Label (genau wie angegeben):
{allowed}

Eingabe: {query}
Label:"""

# Heuristiken als Fallback
_HEURISTICS: List[tuple[str, re.Pattern]] = [
    ("memory_export", re.compile(r"\b(export|download|herunterladen|daten\s*export)\b", re.I)),
    ("memory_delete", re.compile(r"\b(löschen|delete|entfernen)\b", re.I)),
    ("calc_agent",    re.compile(r"\b(rechnen|berechne|calculate|calc|formel|formulas?)\b", re.I)),
    ("report_agent",  re.compile(r"\b(report|bericht|pdf|zusammenfassung|protokoll)\b", re.I)),
    ("material_agent",re.compile(r"\b(material|werkstoff|elastomer|ptfe|fkm|nbr|epdm)\b", re.I)),
    ("profile_agent", re.compile(r"\b(profil|o-ring|x-ring|u-profil|lippe|dichtung\s*profil)\b", re.I)),
    ("rag_qa",        re.compile(r"\b(warum|wie|quelle|dokument|datenblatt|docs?)\b", re.I)),
]

# State-Shape (nur für Typing; zur Laufzeit wird ein dict genutzt)
class ConsultState(TypedDict, total=False):
    user: str
    chat_id: Optional[str]
    input: str
    route: str
    response: str
    citations: List[Dict[str, Any]]

# LLM-Konfiguration
try:
    from langchain_openai import ChatOpenAI
    _LLM_OK = bool(os.getenv("OPENAI_API_KEY"))
except Exception:
    ChatOpenAI = None  # type: ignore
    _LLM_OK = False

def _classify_heuristic(query: str) -> str:
    q = (query or "").lower()
    for label, pattern in _HEURISTICS:
        if pattern.search(q):
            return label
    if re.search(r"[?]|(wie|warum|wieso|quelle|beleg)", q):
        return "rag_qa"
    return "chitchat"

def _classify_llm(query: str) -> str:
    if not (_LLM_OK and ChatOpenAI):
        raise RuntimeError("LLM not available")
    model_name = os.getenv("OPENAI_INTENT_MODEL", "gpt-5-mini")
    llm = ChatOpenAI(model=model_name, temperature=0, max_tokens=6)  # type: ignore
    prompt = _INTENT_PROMPT.format(allowed=", ".join(ALLOWED_ROUTES), query=query.strip())
    try:
        resp = llm.invoke(prompt)  # type: ignore
        label = str(getattr(resp, "content", "")).strip().lower()
        if label in ALLOWED_ROUTES:
            return label
    except Exception as exc:
        log.warning("LLM Intent error: %r", exc)
    # Fallback falls Ausgabe nicht sauber ist
    return _classify_heuristic(query)

def intent_router_node(state: ConsultState) -> ConsultState:
    """Graph-Node: setzt state['route'] über LLM (mit Heuristik-Fallback)."""
    query = state.get("input", "") or ""
    try:
        route = _classify_llm(query)
    except Exception:
        route = _classify_heuristic(query)

    if route not in ALLOWED_ROUTES:
        route = "chitchat"

    state["route"] = route
    return state
