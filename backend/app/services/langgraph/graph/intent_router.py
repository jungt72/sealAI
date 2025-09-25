# backend/app/services/langgraph/graph/intent_router.py
from __future__ import annotations

import json
import os
import re
from typing import Any, Literal, Sequence

from ..prompting import render_template
from app.services.langgraph.llm_router import get_router_llm, get_router_fallback_llm
from langchain_core.messages import HumanMessage

_TEMPLATE_FILE = "intent_router.jinja2"

# Fast-Path Regex für Selektionsfälle (Material/Typ/Bauform/RWDR/Hydraulik & Maße)
_FAST_SELECT_RX = re.compile(
    r"(?i)\b(rwdr|wellendichtring|bauform\s*[a-z0-9]{1,4}|hydraulik|stangendichtung|kolbenstange|nut\s*[db]|"
    r"\d{1,3}\s*[x×/]\s*\d{1,3}\s*[x×/\-]?\s*\d{1,3}|material\s*(wahl|auswahl|empfehlung)|"
    r"(ptfe|nbr|hnbr|fk[mh]|epdm)\b)"
)

def _last_user_text(messages: Sequence[Any]) -> str:
    if not messages:
        return ""
    for m in reversed(messages):
        content = getattr(m, "content", None)
        if content:
            return str(content)
        if isinstance(m, dict):
            c = m.get("content") or m.get("text") or m.get("message")
            if c:
                return str(c)
    return ""

def _strip_json_fence(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text.strip().strip("`").strip()

def _conf_min() -> float:
    try:
        return float(os.getenv("INTENT_CONF_MIN", "0.60"))
    except Exception:
        return 0.60

def classify_intent(_: Any, messages: Sequence[Any]) -> Literal["material_select", "llm"]:
    """
    LLM-first Routing:
      - "material_select": Graph (Selektions-Workflow) verwenden
      - "llm": Direkter LLM-Stream (Erklärung/Smalltalk/Wissen)
    """
    user_text = _last_user_text(messages).strip()

    # 1) Fast-Path (regex)
    if _FAST_SELECT_RX.search(user_text):
        return "material_select"

    # 2) Router-LLMs
    router = get_router_llm()
    fallback = get_router_fallback_llm()
    prompt = render_template(_TEMPLATE_FILE, input_text=user_text)

    def _ask(llm) -> tuple[str, float]:
        resp = llm.invoke([HumanMessage(content=prompt)])
        content = getattr(resp, "content", None) or str(resp)
        raw = _strip_json_fence(content)
        data = json.loads(raw)
        intent = str(data.get("intent") or "").strip().lower()
        conf = float(data.get("confidence") or 0.0)
        return intent, conf

    try:
        intent, conf = _ask(router)
    except Exception:
        try:
            intent, conf = _ask(fallback)
        except Exception:
            # fail-open zu material_select, damit echte Selektionsfälle nie „untergehen“
            return "material_select"

    if conf < _conf_min():
        try:
            i2, c2 = _ask(fallback)
            if c2 >= conf:
                intent, conf = i2, c2
        except Exception:
            pass

    if intent == "llm" and conf >= _conf_min():
        return "llm"
    return "material_select"
