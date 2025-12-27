from __future__ import annotations

import asyncio
import json
import os

import pytest
from langchain_core.messages import HumanMessage

from app.langgraph.nodes.review_and_rwdr_node import review_and_rwdr_node
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

    async def ainvoke(self, _messages, config=None):
        return type("Resp", (), {"content": json.dumps(self.payload)})


def _base_state() -> SealAIState:
    return {
        "messages": [HumanMessage(content="Wir benötigen eine Validierung der Anforderungen.")],
        "slots": {},
        "meta": {"user_id": "user-1"},
    }


def test_review_node_structured_response(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "0")
    fake_llm = _FakeLLM(
        {
            "validated_requirements": "Druck 150 bar, Temperatur 80°C bestätigt.",
            "identified_issues": "Medium nicht spezifiziert.",
            "recommendations": "Bitte Medium und Viskosität nachreichen.",
            "message": "Validierung: Druck 150 bar, Temperatur 80°C. Medium fehlt.",
        }
    )
    result = asyncio.run(
        review_and_rwdr_node(
            _base_state(), config={"configurable": {"review_llm": fake_llm}}
        )
    )

    assert result["slots"]["requirements_validated"] == "Druck 150 bar, Temperatur 80°C bestätigt."
    assert result["meta"]["review_issues"] == "Medium nicht spezifiziert."
    assert result["meta"]["review_recommendations"] == "Bitte Medium und Viskosität nachreichen."
    assert result["message_out"].startswith("Validierung")
    assert result["msg_type"] == "msg-review"


def test_review_node_interrupt_on_fallback(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_USE_FAKE_LLM", "0")
    fake_llm = _FakeLLM(
        {
            "validated_requirements": "",
            "identified_issues": "",
            "recommendations": "",
            "fallback_reason": "missing_data",
            "message": "Bitte bestätige Medium und Temperatur, damit ich die Anforderungen prüfen kann.",
        }
    )
    with pytest.raises(InterruptSignal):
        asyncio.run(
            review_and_rwdr_node(
                _base_state(), config={"configurable": {"review_llm": fake_llm}}
            )
        )
