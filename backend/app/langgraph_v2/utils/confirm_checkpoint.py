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
    working_profile = state.working_profile.as_dict() if state.working_profile else {}
    governance_metadata = {}
    contract = getattr(state.system, "answer_contract", None)
    if contract is not None:
        raw_governance = getattr(contract, "governance_metadata", None)
        if hasattr(raw_governance, "model_dump"):
            governance_metadata = raw_governance.model_dump(exclude_none=True)
        elif isinstance(raw_governance, dict):
            governance_metadata = dict(raw_governance)
    if not governance_metadata:
        raw_governance = getattr(state.system, "governance_metadata", None)
        if hasattr(raw_governance, "model_dump"):
            governance_metadata = raw_governance.model_dump(exclude_none=True)
        elif isinstance(raw_governance, dict):
            governance_metadata = dict(raw_governance)

    candidate_semantics = []
    if contract is not None:
        raw_candidates = getattr(contract, "candidate_semantics", None)
        if isinstance(raw_candidates, list):
            candidate_semantics = [dict(item) if isinstance(item, dict) else item.model_dump(exclude_none=True) for item in raw_candidates]

    rfq_admissibility = {}
    raw_rfq = getattr(state.system, "rfq_admissibility", None)
    if hasattr(raw_rfq, "model_dump"):
        rfq_admissibility = raw_rfq.model_dump(exclude_none=True)
    elif isinstance(raw_rfq, dict):
        rfq_admissibility = dict(raw_rfq)

    preview = {
        "text": state.system.governed_output_text or state.system.final_text or state.system.final_answer or "",
        "summary": state.reasoning.discovery_summary,
        "working_profile": working_profile,
        "coverage_score": float(state.reasoning.coverage_score or 0.0),
        "coverage_gaps": list(state.reasoning.coverage_gaps or []),
        "governance_metadata": governance_metadata,
        "rfq_admissibility": rfq_admissibility,
        "candidate_semantics": candidate_semantics,
    }
    payload = ConfirmCheckpointPayload(
        checkpoint_id=checkpoint_id,
        required_user_sub=state.conversation.user_id or "",
        conversation_id=state.conversation.thread_id or "",
        action=action,
        risk=risk,
        preview=preview,
        diff=None,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    return payload.model_dump()


__all__ = ["ConfirmCheckpointPayload", "build_confirm_checkpoint_payload"]
