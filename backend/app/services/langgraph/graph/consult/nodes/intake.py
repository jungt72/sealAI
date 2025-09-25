# backend/app/services/langgraph/graph/consult/nodes/intake.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage, AIMessage
from app.services.langgraph.prompting import (
    render_template,
    messages_for_template,
    strip_json_fence,
)
from ..utils import normalize_messages
# Vereinheitlichte LLM-Factory für Consult
from ..config import create_llm
# NEU: Frühe Pflichtfeldprüfung für sofortiges Sidebar-Open
from ..domain_runtime import missing_by_domain

log = logging.getLogger(__name__)

def intake_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analysiert die Eingabe, klassifiziert den Intent und extrahiert Parameter.
    Deterministischer Output: state['triage'], state['params'].
    Öffnet (falls Pflichtfelder fehlen) direkt die Sidebar-Form via ui_event.
    """
    msgs = normalize_messages(state.get("messages", []))
    params = dict(state.get("params") or {})

    prompt = render_template(
        "intake_triage.jinja2",
        messages=messages_for_template(msgs),
        params=params,
        params_json=json.dumps(params, ensure_ascii=False),
    )

    try:
        llm = create_llm(streaming=False)
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = strip_json_fence(getattr(resp, "content", "") or "")
        data = json.loads(raw)
    except Exception as e:
        log.warning("intake_node: parse_or_llm_error: %s", e, exc_info=True)
        data = {}

    intent = str((data.get("intent") or "unknown")).strip().lower()
    new_params = dict(params)
    if isinstance(data.get("params"), dict):
        for k, v in data["params"].items():
            if v not in (None, "", "unknown"):
                new_params[k] = v

    triage = {
        "intent": intent if intent in ("greeting", "smalltalk", "consult", "unknown") else "unknown",
        "confidence": 1.0 if intent in ("greeting", "smalltalk", "consult") else 0.0,
        "reply": "",
        "flags": {"source": "intake_triage"},
    }

    # ----- NEU: Sidebar sofort öffnen, wenn Kern-Pflichtfelder fehlen -----
    # einfache Domänenschätzung
    domain_guess = "hydraulics_rod" if any(k in new_params for k in ("stange_mm", "nut_d_mm", "nut_b_mm")) else "rwdr"
    missing = missing_by_domain(domain_guess, new_params)

    ui_event = None
    assistant_msg = None
    if missing:
        # Beispielzeile je Domain
        example = (
            "Stange 25, Nut D 32, Nut B 6, Medium Öl, Tmax 80, Druck 160 bar, v 0,3 m/s"
            if domain_guess == "hydraulics_rod"
            else "Welle 25, Gehäuse 47, Breite 7, Medium Öl, Tmax 80, Druck 2 bar, n 1500"
        )
        # Hinweistext (Template nutzt intern 'friendly_required', der bestehende ask_missing-Node
        # übergibt historisch 'friendly' – wir bleiben kompatibel)
        assistant_msg = AIMessage(
            content=render_template(
                "ask_missing.jinja2",
                domain=domain_guess,
                friendly=", ".join(missing),  # kompatibel zu bestehendem Template-Gebrauch
                example=example,
                lang="de",
            )
        )
        # UI-Event für das Frontend (Frontend lauscht auf sealai:ui_action/ui_event)
        ui_event = {
            "ui_action": "open_form",
            "form_id": f"{domain_guess}_params_v1",
            "schema_ref": f"domains/{domain_guess}/params@1.0.0",
            "missing": missing,
            "prefill": {k: v for k, v in new_params.items() if v not in (None, "", [])},
        }
        log.info("[intake_node] early_open_form domain=%s missing=%s", domain_guess, missing)

    return {
        "messages": ([assistant_msg] if assistant_msg else []),
        "params": new_params,
        "triage": triage,
        "phase": "intake",
        **({"ui_event": ui_event} if ui_event else {}),
    }
