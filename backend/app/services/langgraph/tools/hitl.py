from __future__ import annotations
from typing import Dict, Any

def hitl_required(reason: str) -> Dict[str, Any]:
    return {"hitl_required": True, "reason": reason, "status": "pending_review"}
