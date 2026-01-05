from __future__ import annotations

import json
import os

import pytest
from langchain_core.messages import HumanMessage

from app.langgraph.nodes.confidence_gate_node import confidence_gate_node
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
        "messages": [HumanMessage(content="Bitte bewerte die Empfehlung.")],
        "slots": {},
        "meta": {"user_id": "user-1"},
    }


def test_confidence_gate_structured_response(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "0")
    fake_llm = _FakeLLM(
        {
            "confidence_score": 0.95,
            "confidence_reason": "Alle Anforderungen konsistent.",
            "message": "Vertrauen hoch – Empfehlung freigeben.",
        }
    )
    result = confidence_gate_node(_base_state(), config={"configurable": {"confidence_gate_llm": fake_llm}})

    assert result["meta"]["confidence_score"] == 0.95
    assert result["meta"]["confidence_reason"] == "Alle Anforderungen konsistent."
    assert result["message_out"].startswith("Vertrauen hoch")
    assert result["msg_type"] == "msg-confidence-gate"
    assert "confidence_gate" not in (result.get("slots") or {})


def test_confidence_gate_requests_review(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "0")
    fake_llm = _FakeLLM(
        {
            "confidence_score": 0.6,
            "confidence_reason": "Druckangaben fehlen.",
            "message": "Bitte überprüfe die Parameter erneut.",
        }
    )
    result = confidence_gate_node(_base_state(), config={"configurable": {"confidence_gate_llm": fake_llm}})

    assert result["meta"]["confidence_score"] == 0.6
    assert result["slots"]["confidence_gate"] == "review_required"


def test_confidence_gate_interrupt_on_fallback(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "0")
    fake_llm = _FakeLLM(
        {
            "confidence_score": 0.5,
            "confidence_reason": "Keine ausreichenden Daten.",
            "fallback_reason": "need_more_info",
            "message": "Ich benötige weitere Details zur Anwendung.",
        }
    )
    with pytest.raises(InterruptSignal):
        confidence_gate_node(_base_state(), config={"configurable": {"confidence_gate_llm": fake_llm}})
