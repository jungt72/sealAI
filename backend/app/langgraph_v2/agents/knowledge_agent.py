from __future__ import annotations

from typing import Any, Dict

from app.langgraph_v2.state import SealAIState


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
        from app.langgraph_v2.nodes.conversational_rag import (
            conversational_rag_node,
        )
        from app.langgraph_v2.nodes.nodes_flows import (
            material_comparison_node,
        )
        goal = getattr(state.intent, "goal", "") or ""
        if "comparison" in goal:
            return await material_comparison_node(state)
        return await conversational_rag_node(state, config={})


__all__ = ["KnowledgeAgent"]
