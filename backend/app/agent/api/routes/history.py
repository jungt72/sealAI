import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.agent.api.models import ConversationResponse
from app.agent.state.models import GovernedSessionState
from app.agent.state.persistence import get_latest_governed_case_snapshot_async
from app.services.auth.dependencies import RequestUser, get_current_request_user
from app.services.history.persist import load_structured_case
from app.agent.api.deps import _canonical_scope
from app.agent.api.utils import _serialize_governed_history_payload

_log = logging.getLogger(__name__)

router = APIRouter()

@router.get("/chat/history/{case_id}", response_model=List[ConversationResponse])
async def get_live_chat_history(
    case_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
):
    tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=case_id)

    from app.agent.api.loaders import _load_live_governed_state # noqa: PLC0415
    governed = await _load_live_governed_state(
        current_user=current_user,
        session_id=case_id,
        create_if_missing=False,
    )
    if not governed:
        snapshot = await get_latest_governed_case_snapshot_async(
            case_number=case_id,
            user_id=owner_id,
        )
        if snapshot and snapshot.state_json:
            governed = GovernedSessionState.model_validate(snapshot.state_json)
    if governed:
        return [
            ConversationResponse(**m)
            for m in _serialize_governed_history_payload(state=governed)
        ]

    state = await load_structured_case(
        tenant_id=tenant_id,
        owner_id=owner_id,
        case_id=case_id,
    )

    if not state:
        return []

    messages = state.get("messages") or []
    return [
        ConversationResponse(
            role="user" if hasattr(m, "type") and m.type == "human" else "assistant",
            content=m.content if hasattr(m, "content") else str(m),
        )
        for m in messages
    ]
