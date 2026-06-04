from __future__ import annotations

from typing import Any

from app.agent.api.dispatch import (
    _compose_knowledge_answer_if_enabled,
    _knowledge_rag_retriever,
)
from app.domain.pre_gate_classification import PreGateClassification
from app.services.knowledge_service import KnowledgeService
from app.services.rag.constants import RAG_SHARED_TENANT_ID


def _history_from_governed_state(governed_state: Any | None) -> tuple[Any, ...]:
    if governed_state is None:
        return ()
    return tuple(getattr(governed_state, "conversation_messages", ()) or ())


def _rag_scope_from_user(current_user: Any | None) -> tuple[str, str | None]:
    tenant_id = str(getattr(current_user, "tenant_id", "") or "").strip()
    user_id = str(getattr(current_user, "user_id", "") or "").strip()
    return tenant_id or RAG_SHARED_TENANT_ID, user_id or None


async def build_case_side_knowledge_response(
    *,
    message: str,
    override_class: str,
    conversation_route: Any | None = None,
    governed_state: Any | None = None,
    current_user: Any | None = None,
) -> Any:
    """Answer a knowledge side-question inside an active governed session.

    The governed case remains the source of engineering truth. This helper only
    routes educational side questions through the same no-case KnowledgeService
    contract used before a case exists, so active-case knowledge does not fall
    back to the legacy light/exploration runtime or mutate case state.
    """

    source_classification = PreGateClassification.KNOWLEDGE_QUERY
    tenant_id, user_id = _rag_scope_from_user(current_user)
    knowledge_response = KnowledgeService(
        rag_retriever=_knowledge_rag_retriever,
    ).answer(
        message,
        source_classification=source_classification,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    recent_history = _history_from_governed_state(governed_state)
    return await _compose_knowledge_answer_if_enabled(
        user_message=message,
        knowledge_response=knowledge_response,
        conversation_route=conversation_route,
        recent_history=recent_history,
        full_history_context=True,
    )
