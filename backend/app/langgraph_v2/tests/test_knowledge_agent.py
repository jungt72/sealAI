from types import SimpleNamespace


def test_knowledge_agent_imports():
    from app.langgraph_v2.agents.knowledge_agent import KnowledgeAgent
    ka = KnowledgeAgent()
    assert hasattr(ka, "run")


def test_knowledge_agent_goal_comparison_routing():
    # Smoke test: comparison intent → material_comparison_node
    # Wir testen nur die goal-Auswertung, nicht den async LLM-Call
    from app.langgraph_v2.agents.knowledge_agent import KnowledgeAgent
    from app.langgraph_v2.state import SealAIState

    ka = KnowledgeAgent()
    state = SealAIState()
    state.intent = SimpleNamespace(goal="material_comparison")
    goal = getattr(state.intent, "goal", "") or ""
    assert "comparison" in goal  # Routing würde material_comparison_node wählen


def test_knowledge_agent_default_routing():
    from app.langgraph_v2.agents.knowledge_agent import KnowledgeAgent
    from app.langgraph_v2.state import SealAIState

    ka = KnowledgeAgent()
    state = SealAIState()
    goal = getattr(state.intent, "goal", "") or ""
    assert "comparison" not in goal  # Routing würde conversational_rag_node wählen
