from __future__ import annotations

import os
import sys
from types import ModuleType

os.environ.setdefault("postgres_user", "test")
os.environ.setdefault("postgres_password", "test")
os.environ.setdefault("postgres_host", "localhost")
os.environ.setdefault("postgres_port", "5432")
os.environ.setdefault("postgres_db", "testdb")
os.environ.setdefault("database_url", "postgresql+asyncpg://test:test@localhost:5432/testdb")
os.environ.setdefault("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/testdb")
os.environ.setdefault("openai_api_key", "sk-test")
os.environ.setdefault("qdrant_url", "http://localhost:6333")
os.environ.setdefault("qdrant_collection", "test")
os.environ.setdefault("redis_url", "redis://localhost:6379/0")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_expected_azp", "test-client")

if "app.services.langgraph.llm_factory" not in sys.modules:
    stub = ModuleType("app.services.langgraph.llm_factory")
    stub.get_llm = lambda *args, **kwargs: None
    sys.modules["app.services.langgraph.llm_factory"] = stub
if "app.services.langgraph.prompt_registry" not in sys.modules:
    stub = ModuleType("app.services.langgraph.prompt_registry")
    stub.get_agent_prompt = lambda *_args, **_kwargs: ""
    sys.modules["app.services.langgraph.prompt_registry"] = stub
if "app.services.langgraph.graph.consult.memory_utils" not in sys.modules:
    stub = ModuleType("app.services.langgraph.graph.consult.memory_utils")
    stub.read_history = lambda *_args, **_kwargs: []
    stub.write_message = lambda *_args, **_kwargs: None
    sys.modules["app.services.langgraph.graph.consult.memory_utils"] = stub
if "app.services.langgraph.tools" not in sys.modules:
    sys.modules["app.services.langgraph.tools"] = ModuleType("app.services.langgraph.tools")
if "app.services.langgraph.tools.long_term_memory" not in sys.modules:
    stub = ModuleType("app.services.langgraph.tools.long_term_memory")
    stub.prewarm_ltm = lambda *_args, **_kwargs: None
    stub.upsert_memory = lambda *_args, **_kwargs: None
    sys.modules["app.services.langgraph.tools.long_term_memory"] = stub

from app.api.v1.endpoints import chat_ws


def test_ws_thread_key_includes_tenant() -> None:
    key = chat_ws._build_ws_thread_key(
        tenant_id="tenant-1",
        user_id="user-1",
        chat_id="chat-1",
    )
    assert key == "tenant-1:user-1:chat-1"
