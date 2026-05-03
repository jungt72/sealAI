from __future__ import annotations

from typing import Any

from app.agent.api.dispatch import _compose_knowledge_answer_if_enabled
from app.domain.pre_gate_classification import PreGateClassification
from app.services.knowledge_service import KnowledgeService


def _history_from_governed_state(governed_state: Any | None) -> tuple[Any, ...]:
    if governed_state is None:
        return ()
    return tuple(getattr(governed_state, "conversation_messages", ()) or ())


async def build_case_side_knowledge_response(
    *,
    message: str,
    override_class: str,
    conversation_route: Any | None = None,
    governed_state: Any | None = None,
) -> Any:
    """Answer a knowledge side-question inside an active governed session.

    The governed case remains the source of engineering truth. This helper only
    routes educational side questions through the same no-case KnowledgeService
    contract used before a case exists, so active-case knowledge does not fall
    back to the legacy light/exploration runtime or mutate case state.
    """

    source_classification = PreGateClassification.KNOWLEDGE_QUERY
    knowledge_response = KnowledgeService().answer(
        message,
        source_classification=source_classification,
    )
    recent_history = _history_from_governed_state(governed_state)
    return await _compose_knowledge_answer_if_enabled(
        user_message=message,
        knowledge_response=knowledge_response,
        conversation_route=conversation_route,
        recent_history=recent_history,
    )
