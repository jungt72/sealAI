from __future__ import annotations
from typing import Dict, Any

UI = dict(
    DECISION_READY="decision_ready",
    RFQ_READY="rfq_ready",
    NO_PARTNER_AVAILABLE="no_partner_available",
    OPEN_FORM="open_form",
)

def make_event(action: str, **payload: Any) -> Dict[str, Any]:
    return {"ui_action": action, "payload": payload}
