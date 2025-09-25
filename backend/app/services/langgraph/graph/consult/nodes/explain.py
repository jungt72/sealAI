# backend/app/services/langgraph/graph/consult/nodes/explain.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Callable
import json
import structlog
from langchain_core.messages import AIMessage
from app.services.langgraph.prompting import render_template

log = structlog.get_logger(__name__)

def _top_sources(docs: List[Dict[str, Any]], k: int = 3) -> List[str]:
    if not docs:
        return []
    def _score(d: Dict[str, Any]) -> float:
        try:
            if d.get("fused_score") is not None:
                return float(d["fused_score"])
            return max(float(d.get("vector_score") or 0.0),
                       float(d.get("keyword_score") or 0.0) / 100.0)
        except Exception:
            return 0.0
    tops = sorted(docs, key=_score, reverse=True)[:k]
    out: List[str] = []
    for d in tops:
        src = d.get("source") or (d.get("metadata") or {}).get("source") or ""
        if src:
            out.append(str(src))
    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq

def _emit_text(events: Optional[Callable[[Dict[str, Any]], None]],
               node: str, text: str, chunk_size: int = 180) -> None:
    if not events or not text:
        return
    for i in range(0, len(text), chunk_size):
        events({"type": "stream_text", "node": node, "text": text[i:i+chunk_size]})

def _last_ai_text(state: Dict[str, Any]) -> str:
    """Zieht den Text der letzten AIMessage (string oder tool-structured)."""
    msgs = state.get("messages") or []
    last_ai = None
    for m in reversed(msgs):
        t = (getattr(m, "type", "") or getattr(m, "role", "") or "").lower()
        if t in ("ai", "assistant"):
            last_ai = m
            break
    if not last_ai:
        return ""
    content = getattr(last_ai, "content", None)
    if isinstance(content, str):
        return content.strip()
    # LangChain kann Liste aus {"type":"text","text":"..."} liefern
    out_parts: List[str] = []
    if isinstance(content, list):
        for p in content:
            if isinstance(p, str):
                out_parts.append(p)
            elif isinstance(p, dict) and isinstance(p.get("text"), str):
                out_parts.append(p["text"])
    return "\n".join(out_parts).strip()

def _parse_recommendation(text: str) -> Dict[str, Any]:
    """
    Akzeptiert:
      1) {"empfehlungen":[{typ, werkstoff, begruendung, vorteile, einschraenkungen, ...}, ...]}
      2) {"main": {...}, "alternativen": [...], "hinweise":[...]}
      3) {"text": "<JSON string>"}  -> wird rekursiv geparst
    """
    if not text:
        return {}

    def _loads_maybe(s: str):
        try:
            return json.loads(s)
        except Exception:
            return None

    obj = _loads_maybe(text)
    if isinstance(obj, dict) and "text" in obj and isinstance(obj["text"], str):
        obj2 = _loads_maybe(obj["text"])
        if isinstance(obj2, dict):
            obj = obj2

    if not isinstance(obj, dict):
        return {}

    # Form 2
    if "main" in obj or "alternativen" in obj:
        main = obj.get("main") or {}
        alternativen = obj.get("alternativen") or []
        hinweise = obj.get("hinweise") or []
        return {"main": main, "alternativen": alternativen, "hinweise": hinweise}

    # Form 1
    if isinstance(obj.get("empfehlungen"), list) and obj["empfehlungen"]:
        recs = obj["empfehlungen"]
        main = recs[0] if isinstance(recs[0], dict) else {}
        alternativen = [r for r in recs[1:] if isinstance(r, dict)]
        return {"main": main, "alternativen": alternativen, "hinweise": obj.get("hinweise") or []}

    return {}

def explain_node(state: Dict[str, Any], *, events: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    """
    Rendert die Empfehlung als freundliches Markdown (explain.jinja2),
    streamt Chunks (falls WS-Events übergeben werden) und hängt eine AIMessage an.
    Holt sich – falls nötig – main/alternativen automatisch aus der letzten AI-JSON.
    """
    params: Dict[str, Any] = state.get("params") or {}
    docs: List[Dict[str, Any]] = state.get("retrieved_docs") or state.get("docs") or []
    sources = _top_sources(docs, k=3)

    # Falls main/alternativen/hinweise fehlen, aus der letzten AI-Message extrahieren
    main = state.get("main") or {}
    alternativen = state.get("alternativen") or []
    hinweise = state.get("hinweise") or []
    if not main and not alternativen:
        parsed = _parse_recommendation(_last_ai_text(state))
        if parsed:
            main = parsed.get("main") or main
            alternativen = parsed.get("alternativen") or alternativen
            if not hinweise:
                hinweise = parsed.get("hinweise") or []

    md = render_template(
        "explain.jinja2",
        main=main or {},
        alternativen=alternativen or [],
        derived=state.get("derived") or {},
        hinweise=hinweise or [],
        params=params,
        sources=sources,
    ).strip()

    _emit_text(events, node="explain", text=md)

    msgs = (state.get("messages") or []) + [AIMessage(content=md)]
    return {
        **state,
        "main": main,
        "alternativen": alternativen,
        "hinweise": hinweise,
        "phase": "explain",
        "messages": msgs,
        "explanation": md,
        "retrieved_docs": docs,
    }
