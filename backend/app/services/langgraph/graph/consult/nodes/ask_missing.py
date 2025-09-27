# backend/app/services/langgraph/graph/consult/nodes/ask_missing.py
from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.messages import AIMessage
from app.services.langgraph.prompting import render_template
from ..utils import (
    missing_by_domain,
    optional_missing_by_domain,
    anomaly_messages,
    normalize_messages,
    friendly_required_list,
    friendly_optional_list,
)

log = logging.getLogger(__name__)


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
    optional_missing = optional_missing_by_domain(domain, params)
    log.info(
        "[ask_missing_node] fehlend=%s optional=%s domain=%s consult_required=%s",
        missing,
        optional_missing,
        domain,
        consult_required,
    )

    prefill = {k: v for k, v in params.items() if v not in (None, "", [])}
    form_id = f"{domain}_params_v1"
    schema_ref = f"domains/{domain}/params@1.0.0"

    if missing:
        friendly_required = friendly_required_list(domain, missing)
        friendly_optional = friendly_optional_list(domain, optional_missing)
        friendly_legacy = friendly_required or ", ".join(missing)
        example = (
            "Welle 25, Gehäuse 47, Breite 7, Medium Öl, Tmax 80, Druck 2 bar, n 1500"
            if domain != "hydraulics_rod"
            else "Stange 25, Nut D 32, Nut B 6, Medium Öl, Tmax 80, Druck 160 bar, v 0,3 m/s"
        )

        content = render_template(
            "ask_missing.jinja2",
            domain=domain,
            friendly=friendly_legacy,
            friendly_required=friendly_required,
            friendly_optional=friendly_optional,
            missing_required=missing,
            missing_optional=optional_missing,
            example=example,
            lang=lang,
        )

        ui_event = {
            "ui_action": "open_form",
            "form_id": form_id,
            "schema_ref": schema_ref,
            "missing": missing,
            "prefill": prefill,
        }
        log.info("[ask_missing_node] ui_event=%s", ui_event)
        return {
            **state,
            "messages": [AIMessage(content=content)],
            "phase": "ask_missing",
            "ui_event": ui_event,
            "missing_fields": missing,
        }

    followups = anomaly_messages(domain, params, derived)
    if followups:
        content = render_template("ask_missing_followups.jinja2", followups=followups[:2], lang=lang)
        ui_event = {
            "ui_action": "open_form",
            "form_id": form_id,
            "schema_ref": schema_ref,
            "missing": [],
            "prefill": prefill,
        }
        log.info("[ask_missing_node] ui_event_followups=%s", ui_event)
        return {
            **state,
            "messages": [AIMessage(content=content)],
            "phase": "ask_missing",
            "ui_event": ui_event,
            "missing_fields": [],
        }

    if prefill:
        prev_event = state.get("ui_event") if isinstance(state, dict) else None
        if isinstance(prev_event, dict):
            merged_prefill = {}
            existing_prefill = prev_event.get("prefill") if isinstance(prev_event.get("prefill"), dict) else {}
            merged_prefill.update(existing_prefill)
            merged_prefill.update(prefill)

            merged_event = {
                **prev_event,
                "prefill": merged_prefill,
                "form_id": prev_event.get("form_id") or form_id,
                "schema_ref": prev_event.get("schema_ref") or schema_ref,
            }
            if "missing" not in merged_event:
                merged_event["missing"] = []
            return {**state, "messages": [], "phase": "ask_missing", "ui_event": merged_event, "missing_fields": []}

        ui_event = {
            "ui_action": "form_sync",
            "form_id": form_id,
            "schema_ref": schema_ref,
            "missing": [],
            "prefill": prefill,
        }
        return {**state, "messages": [], "phase": "ask_missing", "ui_event": ui_event, "missing_fields": []}

    return {**state, "messages": [], "phase": "ask_missing", "missing_fields": []}
