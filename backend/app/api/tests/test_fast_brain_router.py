from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

pytest.skip(
    "Legacy Fast-Brain router test disabled during agent-path canonization.",
    allow_module_level=True,
)

sys.path.append(str(Path(__file__).resolve().parents[3]))

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
os.environ.setdefault("nextauth_url", "http://localhost:3000")
os.environ.setdefault("nextauth_secret", "test-secret")
os.environ.setdefault("keycloak_issuer", "http://localhost/realms/test")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_client_id", "test-client")
os.environ.setdefault("keycloak_client_secret", "test-secret")
os.environ.setdefault("keycloak_expected_azp", "test-client")

from app.services.fast_brain import router as fast_router  # noqa: E402


def test_live_physics_tool_adds_deterministic_material_warnings(monkeypatch):
    async def _fake_query(*args, **kwargs):
        return {"status": "no_match", "matches": {"material_limits": []}}

    monkeypatch.setattr(fast_router, "aquery_deterministic_norms", _fake_query)

    payload = json.loads(
        asyncio.run(
            fast_router.live_physics_tool.ainvoke(
                {
                    "shaft_diameter_mm": 100.0,
                    "speed_rpm": 3000.0,
                    "pressure_bar": 12.0,
                    "temperature_c": 80.0,
                }
            )
        )
    )

    assert payload["v_m_s"] == 15.71
    assert payload["pv"] == 18.85
    warnings = payload["warnings"]
    assert any("NBR-Limit von 12.00 m/s" in warning for warning in warnings)
    assert any("FKM-Limit von 3.00 MPa*m/s" in warning for warning in warnings)
    assert any("PTFE-Limit von 10.00 MPa*m/s" in warning for warning in warnings)
    assert any(
        warning == "Ich finde keine spezifischen Normwerte in der Datenbank für dieses Material."
        for warning in warnings
    )
    assert all(
        row["database_message"] == "Ich finde keine spezifischen Normwerte in der Datenbank für dieses Material."
        for row in payload["material_screening"]
    )


def test_live_physics_tool_prefers_db_speed_limit_rows(monkeypatch):
    async def _fake_query(material: str, temp: float, pressure: float):
        if material != "FKM":
            return {"status": "no_match", "matches": {"material_limits": []}}
        return {
            "status": "ok",
            "matches": {
                "material_limits": [
                    {
                        "material": "FKM",
                        "limit_kind": "speed_m_s",
                        "max_value": 10.0,
                        "conditions": {},
                        "source_ref": "DB-FKM-V-01",
                    }
                ]
            },
        }

    monkeypatch.setattr(fast_router, "aquery_deterministic_norms", _fake_query)

    payload = json.loads(
        asyncio.run(
            fast_router.live_physics_tool.ainvoke(
                {
                    "shaft_diameter_mm": 100.0,
                    "speed_rpm": 3000.0,
                    "pressure_bar": 1.0,
                    "temperature_c": 40.0,
                }
            )
        )
    )

    assert any(
        "FKM-Limit von 10.00 m/s" in warning and "DB-FKM-V-01" in warning
        for warning in payload["warnings"]
    )


def test_fast_brain_router_forces_handoff_on_live_physics_tool_error():
    class _FailingTool:
        name = "live_physics_tool"

        async def ainvoke(self, _args):
            raise RuntimeError("tool offline")

    class _SingleCallLLM:
        async def ainvoke(self, _messages):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_1",
                        "name": "live_physics_tool",
                        "args": {"shaft_diameter_mm": 100.0, "speed_rpm": 3000.0},
                    }
                ],
            )

    router = fast_router.FastBrainRouter.__new__(fast_router.FastBrainRouter)
    router.llm = None
    router.tools = [_FailingTool()]
    router._tool_by_name = {"live_physics_tool": router.tools[0]}
    router.llm_with_tools = _SingleCallLLM()

    result = asyncio.run(router.chat("Bitte schnell rechnen", []))

    assert result["status"] == "handoff_to_langgraph"
    assert result["handoff_to_slow_brain"] is True
    assert result["route"] == "slow_brain"
    assert "technischer Probleme" in result["content"]
    assert result["state_patch"] == {}


def test_fast_brain_router_handoffs_trade_name_knowledge_query_without_llm_call():
    class _ExplodingLLM:
        async def ainvoke(self, _messages):
            raise AssertionError("LLM must not be called for deterministic knowledge handoff")

    router = fast_router.FastBrainRouter.__new__(fast_router.FastBrainRouter)
    router.llm = None
    router.tools = []
    router._tool_by_name = {}
    router.llm_with_tools = _ExplodingLLM()

    result = asyncio.run(router.chat("Was kannst du mir ueber Kyrolon sagen?", []))

    assert result["status"] == "handoff_to_langgraph"
    assert result["handoff_to_slow_brain"] is True
    assert result["route"] == "slow_brain"
    assert result["state_patch"] == {}
    assert "wissensbasierte" in result["content"]


def test_fast_brain_router_handoffs_general_material_knowledge_query():
    class _ExplodingLLM:
        async def ainvoke(self, _messages):
            raise AssertionError("LLM must not be called for deterministic knowledge handoff")

    router = fast_router.FastBrainRouter.__new__(fast_router.FastBrainRouter)
    router.llm = None
    router.tools = []
    router._tool_by_name = {}
    router.llm_with_tools = _ExplodingLLM()

    result = asyncio.run(router.chat("Was ist PTFE?", []))

    assert result["status"] == "handoff_to_langgraph"
    assert result["handoff_to_slow_brain"] is True
    assert result["route"] == "slow_brain"


def test_fast_brain_router_keeps_engineering_query_on_fast_path():
    class _StaticLLM:
        async def ainvoke(self, _messages):
            return AIMessage(content="Bitte nenne noch den Druck.")

    router = fast_router.FastBrainRouter.__new__(fast_router.FastBrainRouter)
    router.llm = None
    router.tools = []
    router._tool_by_name = {}
    router.llm_with_tools = _StaticLLM()

    result = asyncio.run(router.chat("Berechne die Umfangsgeschwindigkeit bei 60 mm und 1500 rpm", []))

    assert result["status"] == "chat_continue"
    assert result["handoff_to_slow_brain"] is False
    assert result["route"] == "fast_brain"
    assert "Druck" in result["content"]
