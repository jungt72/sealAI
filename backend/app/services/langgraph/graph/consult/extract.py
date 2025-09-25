# backend/app/services/langgraph/graph/consult/extract.py
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from app.services.langgraph.llm_factory import get_llm
from app.services.langgraph.prompting import render_template

log = logging.getLogger(__name__)

# ============================================================
# einfache Heuristik als Fallback
# ============================================================

_NUMBER = r"[-+]?\d+(?:[.,]\d+)?"

def _to_float(x: Any) -> Optional[float]:
    try:
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip().replace(",", ".")
        return float(s)
    except Exception:
        return None

def heuristic_extract(user_input: str) -> Dict[str, Any]:
    txt = (user_input or "").lower()
    out: Dict[str, Any] = {"source": "heuristic"}

    if any(w in txt for w in ["rwdr", "wellendichtring", "radialwellendichtring"]):
        out["domain"] = "rwdr"; out["falltyp"] = "rwdr"
    elif any(w in txt for w in ["stangendichtung", "kolbenstange", "hydraulik"]):
        out["domain"] = "hydraulics_rod"; out["falltyp"] = "hydraulics_rod"

    m = re.search(rf"(?P<d>{_NUMBER})\s*[x×]\s*(?P<D>{_NUMBER})\s*[x×]\s*(?P<b>{_NUMBER})\s*mm", txt)
    if m:
        out["wellen_mm"]  = _to_float(m.group("d"))
        out["gehause_mm"] = _to_float(m.group("D"))
        out["breite_mm"]  = _to_float(m.group("b"))
    else:
        md = re.search(rf"(?:welle|d)\s*[:=]?\s*({_NUMBER})\s*mm", txt)
        mD = re.search(rf"(?:gehäuse|gehause|D)\s*[:=]?\s*({_NUMBER})\s*mm", txt)
        mb = re.search(rf"(?:breite|b)\s*[:=]?\s*({_NUMBER})\s*mm", txt)
        if md: out["wellen_mm"]  = _to_float(md.group(1))
        if mD: out["gehause_mm"] = _to_float(mD.group(1))
        if mb: out["breite_mm"]  = _to_float(mb.group(1))

    tmax = re.search(rf"(?:tmax|temp(?:eratur)?(?:\s*max)?)\s*[:=]?\s*({_NUMBER})\s*°?\s*c", txt)
    if not tmax:
        tmax = re.search(rf"({_NUMBER})\s*°?\s*c", txt)
    if tmax:
        out["temp_max_c"] = _to_float(tmax.group(1))

    p = re.search(rf"(?:p(?:_?max)?|druck)\s*[:=]?\s*({_NUMBER})\s*bar", txt)
    if p:
        out["druck_bar"] = _to_float(p.group(1))

    rpm = re.search(rf"(?:n|drehzahl|rpm)\s*[:=]?\s*({_NUMBER})\s*(?:u/?min|rpm)", txt)
    if rpm:
        out["drehzahl_u_min"] = _to_float(rpm.group(1))

    v = re.search(rf"(?:v|geschwindigkeit)\s*[:=]?\s*({_NUMBER})\s*m/?s", txt)
    if v:
        out["geschwindigkeit_m_s"] = _to_float(v.group(1))

    med = re.search(r"(?:medium|medien|stoff)\s*[:=]\s*([a-z0-9\-_/.,\s]+)", txt)
    if med:
        out["medium"] = med.group(1).strip()
    else:
        for k in ["öl", "oel", "diesel", "benzin", "kraftstoff", "wasser", "dampf", "säure", "saeure", "lauge"]:
            if k in txt:
                out["medium"] = k; break

    return out

# ============================================================
# robustes JSON aus LLM
# ============================================================

_JSON_RX = re.compile(r"\{[\s\S]*\}")

def _safe_json(text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(text, str):
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = _JSON_RX.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None

# ============================================================
# Öffentliche API (SIGNATUR passt zu build.py)
# ============================================================

def extract_params_with_llm(user_input: str, *, rag_context: str | None = None) -> Dict[str, Any]:
    """
    Extrahiert Pflicht-/Kernparameter aus der Nutzeranfrage.
    - FIX: korrektes Rendering von Jinja (keine zusätzlichen Positional-Args)
    - Normales Chat-Completion + robustes JSON-Parsing
    - Fallback: lokale Heuristik
    """
    try:
        sys_prompt = render_template(
            "consult_extract_params.jinja2",
            messages=[{"type": "user", "content": (user_input or "").strip()}],
            params_json="{}",
        )
    except Exception as e:
        log.warning("[extract_params_with_llm] template_render_failed: %r", e)
        return heuristic_extract(user_input)

    messages: List[Any] = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=user_input or ""),
    ]

    llm = get_llm(streaming=False)

    try:
        resp = llm.invoke(messages)
        text = getattr(resp, "content", "") or ""
    except Exception as e:
        log.warning("[extract_params_with_llm] llm_invoke_failed_plain: %r", e)
        return heuristic_extract(user_input)

    data = _safe_json(text)
    if not isinstance(data, dict):
        log.info("[extract_params_with_llm] no_json_in_response – using heuristic")
        return heuristic_extract(user_input)

    normalized: Dict[str, Any] = {}

    def _pick(name: str, *aliases: str, cast=None):
        for k in (name, *aliases):
            if k in data and data[k] is not None:
                v = data[k]
                if cast:
                    try:
                        v = cast(v)
                    except Exception:
                        pass
                normalized[name] = v
                return

    _pick("falltyp")
    _pick("domain")
    _pick("wellen_mm", "stange_mm", cast=_to_float)
    _pick("gehause_mm", "nut_d_mm", cast=_to_float)
    _pick("breite_mm", "nut_b_mm", cast=_to_float)
    _pick("temp_max_c", cast=_to_float)
    _pick("drehzahl_u_min", cast=_to_float)
    _pick("druck_bar", cast=_to_float)
    _pick("geschwindigkeit_m_s", cast=_to_float)
    _pick("medium")

    for k, v in data.items():
        if k not in normalized:
            normalized[k] = v

    normalized.setdefault("source", "llm_json")
    return normalized

def extract_params(user_input: str, *, rag_context: str | None = None) -> Dict[str, Any]:
    return extract_params_with_llm(user_input, rag_context=rag_context)
