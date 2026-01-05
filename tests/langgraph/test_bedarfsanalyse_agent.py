from __future__ import annotations

import json
import os

import pytest
from langchain_core.messages import HumanMessage

from app.langgraph.nodes.bedarfsanalyse_agent import bedarfsanalyse_node
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


def _base_state() -> SealAIState:
    return {
        "messages": [HumanMessage(content="Wir brauchen Hilfe bei einer Gleitringdichtung.")],
        "slots": {},
        "meta": {"user_id": "user-1"},
    }


def test_bedarfsanalyse_node_writes_structured_state(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "0")
    fake_llm = _FakeLLM(
        {
            "requirements": "Einbausituation: Pumpe, Medium Wasser",
            "context_hint": "Kühlwasserpumpe",
            "message": "Ich fasse zusammen: Pumpe, Medium Wasser. Bitte ergänze Druck und Temperatur.",
        }
    )
    state = _base_state()
    result = bedarfsanalyse_node(state, config={"configurable": {"bedarfsanalyse_llm": fake_llm}})

    assert result["slots"]["requirements"] == "Einbausituation: Pumpe, Medium Wasser"
    assert result["meta"]["requirements"] == "Kühlwasserpumpe"
    assert result["message_out"].startswith("Ich fasse zusammen")
    assert result["msg_type"] == "msg-bedarfsanalyse"


def test_bedarfsanalyse_node_interrupts_on_fallback(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "0")
    fake_llm = _FakeLLM(
        {
            "requirements": "Ich brauche mehr Details, z. B. Medium und Temperatur.",
            "context_hint": "",
            "fallback_reason": "missing_parameters",
            "message": "Ich brauche mehr Details, z. B. Medium und Temperatur.",
        }
    )
    state = _base_state()
    with pytest.raises(InterruptSignal):
        bedarfsanalyse_node(state, config={"configurable": {"bedarfsanalyse_llm": fake_llm}})
