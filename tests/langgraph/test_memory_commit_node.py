from __future__ import annotations

import asyncio

import pytest

from app.langgraph.nodes import memory_commit_node
from app.langgraph.state import LongTermMemoryRef, SealAIState


def test_memory_commit_enabled(monkeypatch):
    monkeypatch.setattr(memory_commit_node.settings, "ltm_enable", True)

    async def fake_store(user_id: str, key: str, value: str) -> int:
        fake_store.called = (user_id, key, value)
        return 77

    fake_store.called = None
    monkeypatch.setattr(memory_commit_node, "_store_ltm_entry", fake_store)

    commit_calls = {}

    def fake_commit_summary(user, chat_id, payload):
        commit_calls["data"] = (user, chat_id, payload)
        return "qdrant-1"

    monkeypatch.setattr(memory_commit_node.memory_core, "commit_summary", fake_commit_summary)

    state: SealAIState = {
        "meta": {"user_id": "user-1", "thread_id": "chat-7", "confidence_score": 0.9},
        "slots": {
            "final_recommendation": "Nutze Dichtung B.",
            "requirements": "Pumpe, Druck 150 bar.",
            "warmup": {"rapport": "Vertrauensvoll"},
        },
        "rwd_requirements": {"machine": "Pumpe", "pressure_inner": 150},
    }

    result = asyncio.run(memory_commit_node.memory_commit_node(state))

    assert fake_store.called[0] == "user-1"
    assert commit_calls["data"][0] == "user-1"
    assert result["long_term_memory_refs"][0]["id"] == "77"


def test_memory_commit_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(memory_commit_node.settings, "ltm_enable", False)
    called = {}

    async def fail_store(*_args, **_kwargs):
        called["store"] = True

    monkeypatch.setattr(memory_commit_node, "_store_ltm_entry", fail_store)
    monkeypatch.setattr(memory_commit_node.memory_core, "commit_summary", lambda *args, **kwargs: None)

    state: SealAIState = {
        "meta": {"user_id": "user-1"},
        "slots": {},
    }

    result = asyncio.run(memory_commit_node.memory_commit_node(state))

    assert result == {}
    assert "store" not in called
