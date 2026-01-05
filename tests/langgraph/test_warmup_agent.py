from __future__ import annotations

import json
import os
from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from app.langgraph.nodes.warmup_agent import warmup_agent_node
from app.langgraph.state import SealAIState
from app.langgraph.types import InterruptSignal

for key, value in {
    "POSTGRES_USER": "test",
    "POSTGRES_PASSWORD": "test",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
    "POSTGRES_SYNC_URL": "postgresql+psycopg2://test:test@localhost:5432/test",
    "OPENAI_API_KEY": "test-key",
    "QDRANT_URL": "http://localhost",
    "QDRANT_COLLECTION": "test",
    "REDIS_URL": "redis://localhost:6379/0",
    "NEXTAUTH_URL": "http://localhost",
    "NEXTAUTH_SECRET": "secret",
    "KEYCLOAK_ISSUER": "http://localhost/realms/test",
    "KEYCLOAK_JWKS_URL": "http://localhost/realms/test/protocol/openid-connect/certs",
    "KEYCLOAK_CLIENT_ID": "test-client",
    "KEYCLOAK_CLIENT_SECRET": "secret",
    "KEYCLOAK_EXPECTED_AZP": "test",
}.items():
    os.environ.setdefault(key, value)


class _FakeLLM:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.last_messages = None

    def invoke(self, messages):
        self.last_messages = messages
        return type("Resp", (), {"content": json.dumps(self.payload)})


def _base_state() -> SealAIState:
    return {
        "messages": [HumanMessage(content="Hallo, ich brauche Hilfe bei einer Pumpe.")],
        "slots": {},
        "meta": {"user_id": "user-1"},
    }


def test_warmup_agent_structured_response(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "0")
    fake_llm = _FakeLLM(
        {
            "message": "Hallo! Schön, dass du da bist. Worum geht es heute?",
            "slots": {"warmup": "User begrüßt", "context_hint": "Pumpen"},
            "meta": {"warmup": True},
        }
    )
    state = _base_state()
    result = warmup_agent_node(state, config={"configurable": {"warmup_llm": fake_llm}})

    assert result["message_out"] == "Hallo! Schön, dass du da bist. Worum geht es heute?"
    assert result["msg_type"] == "msg-warmup"
    assert result["slots"]["warmup"] == "User begrüßt"
    assert result["slots"]["context_hint"] == "Pumpen"
    assert result["meta"]["warmup"]["warmup"] is True


def test_warmup_agent_interrupt_on_fallback(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "0")
    fake_llm = _FakeLLM(
        {
            "message": "Ich bin mir nicht sicher, was du brauchst. Magst du dein Ziel beschreiben?",
            "slots": {"warmup": "Unklarheit", "context_hint": ""},
            "meta": {"warmup": False, "fallback_reason": "no_context"},
        }
    )
    state = _base_state()
    with pytest.raises(InterruptSignal):
        warmup_agent_node(state, config={"configurable": {"warmup_llm": fake_llm}})
