from __future__ import annotations

import asyncio
from langchain_core.messages import AIMessage

from app.langgraph.nodes.general_answer import general_answer_node
from app.langgraph.state import SealAIState


class _FakeLLM:
    def __init__(self, response: str) -> None:
        self._response = response
        self.observed_prompt = None
        self.observed_config = None

    async def ainvoke(self, messages, config=None):
        self.observed_prompt = messages
        self.observed_config = config
        return AIMessage(content=self._response)


def test_general_answer_node_returns_short_reply():
    fake_llm = _FakeLLM("Dies ist eine knappe Antwort.")
    state: SealAIState = {
        "messages": [],
        "slots": {"user_query": "Was ist eine Dichtung?"},
        "intent": {"type": "general"},
        "message_in": "Was ist eine Dichtung?",
    }
    config = {"configurable": {"thread_id": "t-1", "user_id": "u-1", "general_answer_llm": fake_llm}}

    result = asyncio.run(general_answer_node(state, config=config))

    assert result["message_out"] == "Dies ist eine knappe Antwort."
    assert result["msg_type"] == "msg-general-answer"
    assert result["slots"]["final_answer"] == "Dies ist eine knappe Antwort."
    assert result["slots"]["final_answer_source"] == "general_short_answer"
    assert fake_llm.observed_prompt[0].content.startswith("Du bist ein hilfreicher Assistent.")
