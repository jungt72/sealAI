# backend/app/services/langgraph/graph/consult/nodes/ask_missing.py
from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.messages import AIMessage
from app.services.langgraph.prompting import render_template

try:
    from ..utils import missing_by_domain, anomaly_messages, normalize_messages
except ImportError:
    from ..utils import missing_by_domain, normalize_messages
    from ..domain_runtime import anomaly_messages

log = logging.getLogger(__name__)

FIELD_LABELS_RWDR = {
    "falltyp": "Anwendungsfall (Ersatz/Neu/Optimierung)",
    "wellen_mm": "Welle (mm)",
    "gehause_mm": "Gehäuse (mm)",
    "breite_mm": "Breite (mm)",
    "bauform": "Bauform/Profil",
    "medium": "Medium",
    "temp_min_c": "Temperatur min (°C)",
    "temp_max_c": "Temperatur max (°C)",
    "druck_bar": "Druck (bar)",
    "drehzahl_u_min": "Drehzahl (U/min)",
    "geschwindigkeit_m_s": "Relativgeschwindigkeit (m/s)",
    "umgebung": "Umgebung",
    "prioritaet": "Priorität (z. B. Preis, Lebensdauer)",
    "besondere_anforderungen": "Besondere Anforderungen",
    "bekannte_probleme": "Bekannte Probleme",
}
DISPLAY_ORDER_RWDR = [
    "falltyp","wellen_mm","gehause_mm","breite_mm","bauform","medium",
    "temp_min_c","temp_max_c","druck_bar","drehzahl_u_min","geschwindigkeit_m_s",
    "umgebung","prioritaet","besondere_anforderungen","bekannte_probleme",
]

FIELD_LABELS_HYD = {
    "falltyp": "Anwendungsfall (Ersatz/Neu/Optimierung)",
    "stange_mm": "Stange (mm)",
    "nut_d_mm": "Nut-Ø D (mm)",
    "nut_b_mm": "Nutbreite B (mm)",
    "medium": "Medium",
    "temp_max_c": "Temperatur max (°C)",
    "druck_bar": "Druck (bar)",
    "geschwindigkeit_m_s": "Relativgeschwindigkeit (m/s)",
}
DISPLAY_ORDER_HYD = [
    "falltyp","stange_mm","nut_d_mm","nut_b_mm","medium","temp_max_c","druck_bar","geschwindigkeit_m_s",
]

def _friendly_list(keys: List[str], domain: str) -> str:
    if domain == "hydraulics_rod":
        labels, order = FIELD_LABELS_HYD, DISPLAY_ORDER_HYD
    else:
        labels, order = FIELD_LABELS_RWDR, DISPLAY_ORDER_RWDR
    ordered = [k for k in order if k in keys]
    return ", ".join(f"**{labels.get(k, k)}**" for k in ordered)

def ask_missing_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Rückfragen & UI-Event (Formular öffnen) bei fehlenden Angaben."""
    consult_required = bool(state.get("consult_required", True))
    if not consult_required:
        return {**state, "messages": [], "phase": "ask_missing"}

    _ = normalize_messages(state.get("messages", []))
    params: Dict[str, Any] = state.get("params") or {}
    domain: str = (state.get("domain") or "rwdr").strip().lower()
    derived: Dict[str, Any] = state.get("derived") or {}

    lang = (params.get("lang") or state.get("lang") or "de").lower()

    missing = missing_by_domain(domain, params)
    log.info("[ask_missing_node] fehlend=%s domain=%s consult_required=%s", missing, domain, consult_required)

    if missing:
        friendly = _friendly_list(missing, domain)
        example = (
            "Welle 25, Gehäuse 47, Breite 7, Medium Öl, Tmax 80, Druck 2 bar, n 1500"
            if domain != "hydraulics_rod"
            else "Stange 25, Nut D 32, Nut B 6, Medium Öl, Tmax 80, Druck 160 bar, v 0,3 m/s"
        )

        content = render_template("ask_missing.jinja2", domain=domain, friendly=friendly, example=example, lang=lang)

        ui_event = {
            "ui_action": "open_form",
            "form_id": f"{domain}_params_v1",
            "schema_ref": f"domains/{domain}/params@1.0.0",
            "missing": missing,
            "prefill": {k: v for k, v in params.items() if v not in (None, "", [])},
        }
        log.info("[ask_missing_node] ui_event=%s", ui_event)
        return {**state, "messages": [AIMessage(content=content)], "phase": "ask_missing", "ui_event": ui_event, "missing_fields": missing}

    followups = anomaly_messages(domain, params, derived)
    if followups:
        content = render_template("ask_missing_followups.jinja2", followups=followups[:2], lang=lang)
        ui_event = {
            "ui_action": "open_form",
            "form_id": f"{domain}_params_v1",
            "schema_ref": f"domains/{domain}/params@1.0.0",
            "missing": [],
            "prefill": {k: v for k, v in params.items() if v not in (None, "", [])},
        }
        log.info("[ask_missing_node] ui_event_followups=%s", ui_event)
        return {**state, "messages": [AIMessage(content=content)], "phase": "ask_missing", "ui_event": ui_event, "missing_fields": []}

    return {**state, "messages": [], "phase": "ask_missing"}
