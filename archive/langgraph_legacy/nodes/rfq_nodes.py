from __future__ import annotations
from typing import Dict, Any
from datetime import datetime
import os, uuid
from app.services.langgraph.pdf.rfq_renderer import generate_rfq_pdf
from app.services.langgraph.tools.telemetry import telemetry, RFQ_GENERATED
from app.services.langgraph.tools.ui_events import UI, make_event

def decision_ready(state: Dict[str, Any]) -> Dict[str, Any]:
    state.setdefault("ui_events", []).append(make_event(UI["DECISION_READY"], summary={
        "params": state.get("params"),
        "derived": state.get("derived"),
        "candidate_count": len(state.get("candidates") or []),
    }))
    return state

def await_user_action(state: Dict[str, Any]) -> Dict[str, Any]:
    return state

def generate_rfq_pdf_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("user_action") != "export_pdf":
        return state
    out_dir = os.getenv("RFQ_PDF_DIR", "/app/data/rfq")
    os.makedirs(out_dir, exist_ok=True)
    fname = f"rfq_{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:6]}.pdf"
    path = os.path.join(out_dir, fname)
    payload = {
        "params": state.get("params"),
        "derived": state.get("derived"),
        "candidates": state.get("candidates"),
        "sources": state.get("sources"),
        "legal_notice": "Verbindliche Eignungszusage obliegt dem Hersteller.",
    }
    generate_rfq_pdf(payload, path)
    state["rfq_pdf"] = {"path": path, "created_at": datetime.utcnow().isoformat() + "Z", "download_token": uuid.uuid4().hex}
    telemetry.incr(RFQ_GENERATED, 1)
    return state

def deliver_pdf(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("rfq_pdf"):
        state.setdefault("ui_events", []).append(make_event(UI["RFQ_READY"], pdf=state["rfq_pdf"]))
    return state
