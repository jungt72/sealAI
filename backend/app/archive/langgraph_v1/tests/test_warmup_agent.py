from langchain_core.messages import AIMessage, HumanMessage

from app.langgraph.nodes import warmup_agent
from app.langgraph.nodes.warmup_agent import warmup_agent_node
from app.langgraph.state import MetaInfo, SealAIState


class _FakeLLM:
    def __init__(self, response: str) -> None:
        self._response = response
        self.invocations = 0

    def invoke(self, messages):
        self.invocations += 1
        return AIMessage(content=self._response)


def _base_state() -> SealAIState:
    return SealAIState(
        messages=[HumanMessage(content="Wir suchen eine Dichtung für eine Aggregate-Linie.", id="msg-u")],
        slots={"user_profile": {"name": "Sabine"}, "company": "ACME Motion"},
        meta=MetaInfo(thread_id="t-1", user_id="user-42", trace_id="trace-1"),
    )


def test_warmup_agent_parses_llm_json(monkeypatch):
    fake_response = (
        "Hallo Sabine, schön dass du da bist!\n"
        "Wie läuft es aktuell bei ACME Motion? "
        "Ich freue mich auf Details.\n"
        '{"rapport": "Wertschätzung ausgesprochen, nach Projektdruck gefragt.",'
        '"user_mood": "fokussiert",'
        '"ready_for_analysis": true}'
    )
    fake_llm = _FakeLLM(fake_response)
    monkeypatch.setattr(warmup_agent, "_use_offline_mode", lambda: False)
    monkeypatch.setattr(warmup_agent, "_get_llm", lambda config: fake_llm)

    result = warmup_agent_node(_base_state(), config={"configurable": {}})

    assert fake_llm.invocations == 1
    warmup = result.get("warmup") or {}
    assert warmup.get("user_mood") == "fokussiert"
    assert warmup.get("ready_for_analysis") is True
    assert "warmup" in result.get("meta", {})
    assert result.get("phase") == "warmup"
    assert isinstance(result.get("messages", [])[-1], AIMessage)


def test_warmup_agent_offline_fallback(monkeypatch):
    monkeypatch.setattr(warmup_agent, "_use_offline_mode", lambda: True)

    result = warmup_agent_node(_base_state(), config={"configurable": {}})

    warmup = result.get("warmup") or {}
    assert warmup.get("ready_for_analysis") is True
    assert "messages" in result
    assert result["messages"][-1].type == "ai"
