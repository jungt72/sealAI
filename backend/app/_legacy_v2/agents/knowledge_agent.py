from __future__ import annotations

from typing import Any, Dict

from app._legacy_v2.state import SealAIState


class KnowledgeAgent:
    """
    Beantwortet freie Fachfragen, Norm-Erklärungen,
    Materialvergleiche, Hersteller-Vergleiche.
    Kein Auslegungs-Reasoning — reines Wissen.

    Intern: delegiert an conversational_rag_node oder
    material_comparison_node je nach intent.goal.

    Auslegungsstand im State bleibt unberührt.
    """

    async def run(self, state: SealAIState, llm: Any) -> Dict[str, Any]:
        from app._legacy_v2.nodes.conversational_rag import (
            conversational_rag_node,
        )
        from app._legacy_v2.nodes.nodes_flows import (
            material_comparison_node,
        )
        goal = getattr(state.conversation.intent, "goal", "") or ""
        if "comparison" in goal:
            # material_comparison_node is a pre-processing step (writes
            # comparison_notes to working_memory). Run it first, then
            # synthesise the final answer via conversational_rag_node.
            comp_patch = await material_comparison_node(state)
            merged = state.model_copy(deep=True)
            if "working_memory" in comp_patch:
                merged.reasoning.working_memory = comp_patch["working_memory"]
            if "requires_rag" in comp_patch:
                merged.reasoning.requires_rag = bool(comp_patch["requires_rag"])
            if "need_sources" in comp_patch:
                merged.reasoning.need_sources = bool(comp_patch["need_sources"])
            return await conversational_rag_node(merged, config={})
        return await conversational_rag_node(state, config={})


__all__ = ["KnowledgeAgent"]
