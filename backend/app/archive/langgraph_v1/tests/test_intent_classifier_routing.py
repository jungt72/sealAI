from __future__ import annotations

import importlib
import os
import sys
import types

from sqlalchemy.orm import declarative_base

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
}.items():  # pragma: no cover - env guard
    os.environ.setdefault(key, value)

from langchain_core.messages import AIMessage

from app.langgraph.state import MetaInfo, SealAIState
from app.langgraph.nodes.intent_classifier import build_clarify_message, intent_classifier_node


def _install_database_stub() -> None:
    if "app.database" in sys.modules:
        return

    dummy_module = types.ModuleType("app.database")

    class _AsyncSessionStub:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, *_args, **_kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return None

            return _Result()

        def add(self, *_args, **_kwargs):
            return None

        async def commit(self):
            return None

        async def rollback(self):
            return None

        async def refresh(self, *_args, **_kwargs):
            return None

    class _AsyncSessionFactory:
        def __call__(self):
            return _AsyncSessionStub()

    dummy_module.AsyncSessionLocal = _AsyncSessionFactory()
    async def _get_db():
        yield None

    dummy_module.get_db = _get_db
    dummy_module.Base = declarative_base()
    sys.modules["app.database"] = dummy_module


class _FakeLLM:
    def __init__(self, response: str) -> None:
        self._response = response

    async def ainvoke(self, _messages, **_kwargs):
        return AIMessage(content=self._response)

    def invoke(self, _messages):
        return AIMessage(content=self._response)


def test_general_intent_prompts_for_clarification():
    _install_database_stub()
    module = importlib.import_module("app.langgraph.compile")
    graph = module.create_main_graph(require_async=False)

    state: SealAIState = {
        "messages": [],
        "slots": {"user_query": "Wie spät ist es gerade?"},
        "routing": {},
        "context_refs": [],
        "meta": MetaInfo(thread_id="t-1", user_id="u-1", trace_id="trace-1"),
    }

    fake_classifier = _FakeLLM('{"type": "general", "confidence": 0.95, "reason": "allgemeine Frage"}')
    fake_general = _FakeLLM("Dies ist eine knappe Antwort für allgemeine Fragen.")
    config = {
        "configurable": {
            "thread_id": "t-1",
            "user_id": "u-1",
            "intent_classifier_llm": fake_classifier,
            "general_answer_llm": fake_general,
        }
    }

    result = graph.invoke(state, config=config)

    slots = result.get("slots") or {}
    expected_message = build_clarify_message(state["slots"]["user_query"])
    assert slots.get("final_answer") == expected_message
    assert slots.get("final_answer_source") == "intent_clarification"
    assert result.get("msg_type") == "msg-intent-clarify"


def test_intent_classifier_uses_user_choice():
    state: SealAIState = {
        "slots": {"user_query": "?"}, 
        "pending_intent_choice": True,
        "message_in": "Bitte eine ausführliche Beratung.",
    }
    result = intent_classifier_node(state, config={"configurable": {}})
    intent = result["intent"]
    assert intent["type"] == "consultation"
    assert result["intent_confidence"] == 1.0
    assert not result["pending_intent_choice"]


def test_numeric_choice_prefers_consultation():
    state: SealAIState = {
        "slots": {"user_query": "Noch einmal bitte"}, 
        "pending_intent_choice": True,
        "message_in": "2",
    }
    result = intent_classifier_node(state, config={"configurable": {}})
    intent = result["intent"]
    assert intent["type"] == "consultation"
    assert result["intent_confidence"] == 1.0
    assert not result["pending_intent_choice"]
