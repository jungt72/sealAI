from __future__ import annotations

from typing import Any, Dict, Literal, Optional
from datetime import datetime, timezone
import uuid

from pydantic import BaseModel, Field

from app.langgraph_v2.state import SealAIState


class ConfirmCheckpointPayload(BaseModel):
    checkpoint_id: str
    required_user_sub: str
    conversation_id: str
    action: str
    risk: Literal["low", "med", "high"] = "med"
    preview: Dict[str, Any] = Field(default_factory=dict)
    diff: Optional[Dict[str, Any]] = None
    created_at: str


def build_confirm_checkpoint_payload(
    state: SealAIState,
    *,
    action: str,
    checkpoint_id: str | None = None,
    risk: Literal["low", "med", "high"] = "med",
) -> Dict[str, Any]:
    checkpoint_id = checkpoint_id or str(uuid.uuid4())
    parameters = state.parameters.as_dict() if state.parameters else {}
    preview = {
        "text": state.final_text or "",
        "summary": state.discovery_summary,
        "parameters": parameters,
        "coverage_score": float(getattr(state, "coverage_score", 0.0) or 0.0),
        "coverage_gaps": list(getattr(state, "coverage_gaps", None) or []),
    }
    payload = ConfirmCheckpointPayload(
        checkpoint_id=checkpoint_id,
        required_user_sub=state.user_id or "",
        conversation_id=state.thread_id or "",
        action=action,
        risk=risk,
        preview=preview,
        diff=None,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    return payload.model_dump()


__all__ = ["ConfirmCheckpointPayload", "build_confirm_checkpoint_payload"]
