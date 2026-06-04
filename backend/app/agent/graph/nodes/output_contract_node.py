"""Thin graph adapter for governed output contract assembly.

The Sprint 2 output policy and public payload assembly live in
``app.agent.graph.output_contract_assembly``. This module remains the graph node
import surface and test-compatibility facade.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from app.agent.domain.admissibility import check_inquiry_admissibility
from app.agent.graph import GraphState
from app.agent.graph import output_contract_assembly as _assembly
from app.agent.graph.output_contract_assembly import (
    _determine_response_class,
    _is_fast_confirm_applicable,
    _reply_clarification,
    _reply_state_update,
    build_clarification_strategy_fields,
    build_governed_conversation_strategy_contract,
    build_inquiry_summary,
    classify_message_as_knowledge_override,
)


async def output_contract_node(state: GraphState) -> GraphState:
    """Zone 7 adapter: delegate output policy and assembly to the service."""
    _assembly.interrupt = interrupt
    _assembly.check_inquiry_admissibility = check_inquiry_admissibility
    return await _assembly.output_contract_node(state)


__all__: tuple[str, ...] = (
    "_determine_response_class",
    "_is_fast_confirm_applicable",
    "_reply_clarification",
    "_reply_state_update",
    "Any",
    "build_clarification_strategy_fields",
    "build_governed_conversation_strategy_contract",
    "build_inquiry_summary",
    "check_inquiry_admissibility",
    "classify_message_as_knowledge_override",
    "interrupt",
    "output_contract_node",
)
