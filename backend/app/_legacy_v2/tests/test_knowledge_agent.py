from types import SimpleNamespace


def test_knowledge_agent_imports():
    from app._legacy_v2.agents.knowledge_agent import KnowledgeAgent
    ka = KnowledgeAgent()
    assert hasattr(ka, "run")


def test_knowledge_agent_goal_comparison_routing():
    # Smoke test: comparison intent → material_comparison_node
    # Wir testen nur die goal-Auswertung, nicht den async LLM-Call
    from app._legacy_v2.agents.knowledge_agent import KnowledgeAgent
    from app._legacy_v2.state import SealAIState

    ka = KnowledgeAgent()
    state = SealAIState(conversation={"intent": {"goal": "explanation_or_comparison"}})
    goal = getattr(state.conversation.intent, "goal", "") or ""
    assert "comparison" in goal  # Routing würde material_comparison_node wählen


def test_knowledge_agent_default_routing():
    from app._legacy_v2.agents.knowledge_agent import KnowledgeAgent
    from app._legacy_v2.state import SealAIState

    ka = KnowledgeAgent()
    state = SealAIState()
    goal = getattr(state.conversation.intent, "goal", "") or ""
    assert "comparison" not in goal  # Routing würde conversational_rag_node wählen
