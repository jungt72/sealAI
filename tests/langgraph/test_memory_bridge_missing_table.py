from __future__ import annotations

import asyncio

from sqlalchemy.exc import ProgrammingError

from app.langgraph.nodes import memory_bridge
from app.langgraph.state import SealAIState


def test_memory_bridge_handles_missing_chat_transcripts_table(monkeypatch):
    class _FakeUndefinedTable(Exception):
        def __str__(self) -> str:
            return 'relation "chat_transcripts" does not exist'

    class DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def rollback(self):
            DummySession.rollback_called = True

        async def execute(self, *_args, **_kwargs):
            raise ProgrammingError("SELECT 1", {}, _FakeUndefinedTable())

    DummySession.rollback_called = False

    def dummy_session_factory():
        return DummySession()

    async def _fake_refs(_user_id: str):
        return []

    monkeypatch.setattr(memory_bridge, "AsyncSessionLocal", dummy_session_factory)
    monkeypatch.setattr(memory_bridge, "_load_ltm_refs", _fake_refs)

    state: SealAIState = {
        "messages": [],
        "meta": {"user_id": "alice"},
    }

    result = asyncio.run(memory_bridge.memory_bridge_node(state))

    assert result["long_term_memory_refs"] == []
    assert result["slots"]["memory_injections"] == []
    assert DummySession.rollback_called
