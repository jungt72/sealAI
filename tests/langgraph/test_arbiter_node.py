from __future__ import annotations

import json
import os

import pytest
from langchain_core.messages import HumanMessage

from app.langgraph.nodes.arbiter_node import arbiter_node
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
    def __init__(self, payload: dict[str, str]):
        self.payload = payload

    def invoke(self, _messages):
        return type("Resp", (), {"content": json.dumps(self.payload)})


def _state() -> SealAIState:
    return {
        "messages": [HumanMessage(content="Vorschlag A vs. B – wähle den besten.")],
        "slots": {},
        "meta": {"user_id": "user-1"},
    }


def test_arbiter_node_structured_response(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "0")
    fake_llm = _FakeLLM(
        {
            "final_recommendation": "Nutze Dichtung B mit Stützring.",
            "reasoning": "Beste Balance aus Druckfestigkeit und Preis.",
            "message": "Ich empfehle Dichtung B mit Stützring. Grund: Beste Balance aus Druckfestigkeit und Preis.",
        }
    )
    result = arbiter_node(_state(), config={"configurable": {"arbiter_llm": fake_llm}})

    assert result["slots"]["final_recommendation"] == "Nutze Dichtung B mit Stützring."
    assert result["meta"]["arbiter_reasoning"] == "Beste Balance aus Druckfestigkeit und Preis."
    assert result["message_out"].startswith("Ich empfehle Dichtung B")
    assert result["msg_type"] == "msg-arbiter"


def test_arbiter_node_interrupt_on_fallback(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "0")
    fake_llm = _FakeLLM(
        {
            "final_recommendation": "",
            "reasoning": "",
            "fallback_reason": "need_more_data",
            "message": "Bitte bestätige die zulässige Temperatur, bevor ich entscheide.",
        }
    )
    with pytest.raises(InterruptSignal):
        arbiter_node(_state(), config={"configurable": {"arbiter_llm": fake_llm}})
