"""
Integration coverage for LangGraph v2 parameter patch -> state -> chat config.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

# Ensure backend is on path (tests run from repo root in some setups).
sys.path.append(str(Path(__file__).resolve().parents[3]))

# Minimal env defaults for settings to load (avoid import-time config failures).
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

from starlette.requests import Request  # noqa: E402

from app.api.v1.endpoints import langgraph_v2 as endpoint  # noqa: E402
from app.api.v1.endpoints import state as state_endpoint  # noqa: E402
from app.langgraph_v2.utils.parameter_patch import ParametersPatchRequest  # noqa: E402
from app.services.auth.dependencies import RequestUser  # noqa: E402


def _request() -> Request:
    return Request({"type": "http", "headers": []})


class _Snapshot:
    def __init__(self, values=None, config=None):
        self.values = values or {}
        self.next = []
        self.config = config or {}


class _MemoryGraph:
    checkpointer = object()

    def __init__(self):
        self._state_by_thread = {}

    def get_graph(self):
        return SimpleNamespace(nodes={endpoint.PARAMETERS_PATCH_AS_NODE: object(), "supervisor_policy_node": object()})

    async def aget_state(self, config):
        thread_id = config["configurable"]["thread_id"]
        values = self._state_by_thread.get(thread_id, {})
        return _Snapshot(values=values, config=config)

    async def aupdate_state(self, config, updates, as_node=None):
        del as_node
        thread_id = config["configurable"]["thread_id"]
        current = self._state_by_thread.get(thread_id, {})
        self._state_by_thread[thread_id] = _deep_merge(current, updates)


def _deep_merge(base, update):
    merged = dict(base or {})
    for key, value in (update or {}).items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _install_memory_graph(monkeypatch):
    graph = _MemoryGraph()

    async def _dummy_graph():
        return graph

    monkeypatch.setattr(endpoint, "get_sealai_graph_v2", _dummy_graph)
    monkeypatch.setattr(state_endpoint, "get_sealai_graph_v2", _dummy_graph)
    return graph


def test_param_patch_state_chat_config_alignment(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER", "memory")
    _install_memory_graph(monkeypatch)

    chat_id = "chat-param-sync"
    user_id = "user-param-sync"
    request = _request()
    user = RequestUser(user_id=user_id, username="tester", sub="sub-test", roles=[])

    patch_body = ParametersPatchRequest(
        chat_id=chat_id,
        parameters={"medium": "oil", "pressure_bar": 2},
    )
    patch_response = asyncio.run(endpoint.patch_parameters(patch_body, request, user=user))

    state_response = asyncio.run(state_endpoint.get_state(request, thread_id=chat_id, user=user))
    assert state_response["working_profile"]["medium"] == "oil"
    assert state_response["working_profile"]["pressure_bar"] == 2
    assert patch_response["applied_fields"] == ["medium", "pressure_bar"]
    assert patch_response["asserted_fields"] == ["medium", "pressure_bar"]
    assert state_response["config"]["configurable"]["thread_id"] == f"{user.user_id}:{chat_id}"

    graph, config = asyncio.run(endpoint._build_graph_config(thread_id=chat_id, user_id=user.user_id))
    assert config["configurable"]["thread_id"] == f"{user.user_id}:{chat_id}"
    snapshot = asyncio.run(graph.aget_state(config))
    state_values = state_endpoint._state_to_dict(snapshot.values)
    params = state_endpoint._serialize_working_profile(
        state_endpoint._state_field(state_values, "working_profile", "engineering_profile")
    )
    assert params["medium"] == "oil"
    assert params["pressure_bar"] == 2
    assert state_values["working_profile"]["normalized_profile"]["medium"] == "oil"
    assert state_values["reasoning"]["observed_inputs"]["medium"]["raw"] == "oil"
    assert state_values["reasoning"]["current_assertion_cycle_id"] == 1
    assert state_values["reasoning"]["asserted_profile_revision"] == 1


def test_param_patch_merges_existing_parameters(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER", "memory")
    _install_memory_graph(monkeypatch)

    chat_id = "chat-param-merge"
    user_id = "user-param-merge"
    request = _request()
    user = RequestUser(user_id=user_id, username="tester", sub="sub-test", roles=[])

    first_patch = ParametersPatchRequest(
        chat_id=chat_id,
        parameters={"medium": "oil"},
    )
    asyncio.run(endpoint.patch_parameters(first_patch, request, user=user))

    second_patch = ParametersPatchRequest(
        chat_id=chat_id,
        parameters={"pressure_bar": 10},
    )
    asyncio.run(endpoint.patch_parameters(second_patch, request, user=user))

    state_response = asyncio.run(state_endpoint.get_state(request, thread_id=chat_id, user=user))
    assert state_response["working_profile"]["medium"] == "oil"
    assert state_response["working_profile"]["pressure_bar"] == 10


def test_param_patch_promotes_via_normalized_layer(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER", "memory")
    graph = _install_memory_graph(monkeypatch)

    chat_id = "chat-param-promote"
    user_id = "user-param-promote"
    request = _request()
    user = RequestUser(user_id=user_id, username="tester", sub="sub-test", roles=[])

    graph._state_by_thread[f"{user_id}:{chat_id}"] = {
        "working_profile": {"extracted_params": {"pressure_bar": 25, "medium": "steam"}},
        "reasoning": {"extracted_parameter_provenance": {"pressure_bar": "p1_context_extracted", "medium": "frontdoor_extracted"}},
    }

    patch_body = ParametersPatchRequest(
        chat_id=chat_id,
        parameters={"pressure_bar": 25},
    )
    patch_response = asyncio.run(endpoint.patch_parameters(patch_body, request, user=user))

    state_response = asyncio.run(state_endpoint.get_state(request, thread_id=chat_id, user=user))
    assert state_response["working_profile"]["pressure_bar"] == 25
    assert patch_response["applied_fields"] == ["pressure_bar"]
    assert patch_response["asserted_fields"] == ["pressure_bar"]
    assert state_response["state"]["working_profile"]["normalized_profile"]["medium"] == "steam"
    assert state_response["state"]["working_profile"]["normalized_profile"]["pressure_bar"] == 25
    assert state_response["state"]["working_profile"]["extracted_params"]["medium"] == "steam"
    assert state_response["state"]["working_profile"]["extracted_params"]["pressure_bar"] == 25
    assert state_response["state"]["reasoning"]["current_assertion_cycle_id"] == 1
    assert state_response["state"]["reasoning"]["asserted_profile_revision"] == 1


def test_param_patch_family_only_identity_stays_out_of_asserted_but_is_staged(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER", "memory")
    _install_memory_graph(monkeypatch)

    chat_id = "chat-param-family-only"
    user_id = "user-param-family-only"
    request = _request()
    user = RequestUser(user_id=user_id, username="tester", sub="sub-test", roles=[])

    patch_body = ParametersPatchRequest(chat_id=chat_id, parameters={"material": "PTFE"})
    patch_response = asyncio.run(endpoint.patch_parameters(patch_body, request, user=user))

    state_response = asyncio.run(state_endpoint.get_state(request, thread_id=chat_id, user=user))
    state_values = state_response["state"]

    assert patch_response["applied_fields"] == ["material"]
    assert patch_response["asserted_fields"] == []
    assert "material" not in state_response["working_profile"]
    assert state_values["working_profile"]["normalized_profile"]["material"] == "PTFE"
    assert state_values["working_profile"]["extracted_params"]["material"] == "PTFE"
    assert state_values["reasoning"]["observed_inputs"]["material"]["raw"] == "PTFE"
    assert state_values["reasoning"]["extracted_parameter_identity"]["material"]["identity_class"] == "family_only"
    assert state_values["reasoning"].get("current_assertion_cycle_id", 0) == 0
    assert state_values["reasoning"].get("asserted_profile_revision", 0) == 0


def test_new_assertion_invalidates_old_derived_artifacts(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER", "memory")
    graph = _install_memory_graph(monkeypatch)

    chat_id = "chat-cycle-invalid"
    user_id = "user-cycle-invalid"
    request = _request()
    user = RequestUser(user_id=user_id, username="tester", sub="sub-test", roles=[])

    graph._state_by_thread[f"{user_id}:{chat_id}"] = {
        "working_profile": {
            "engineering_profile": {"pressure_bar": 10},
            "calc_results": {"v_surface_m_s": 2.5},
            "live_calc_tile": {"status": "ok", "v_surface_m_s": 2.5, "parameters": {"pressure_bar": 10}},
        },
        "reasoning": {
            "parameter_versions": {"pressure_bar": 1},
            "current_assertion_cycle_id": 1,
            "asserted_profile_revision": 1,
            "derived_artifacts_stale": False,
        },
        "system": {
            "final_text": "Alte Antwort",
            "final_answer": "Alte Antwort",
            "rfq_admissibility": {
                "status": "ready",
                "reason": None,
                "open_points": [],
                "blockers": [],
                "governed_ready": True,
                "derived_from_assertion_cycle_id": 1,
                "derived_from_assertion_revision": 1,
            },
            "rfq_pdf_base64": "JVBERi0xLjQK",
            "rfq_html_report": "<html>rfq</html>",
            "sealing_requirement_spec": {
                "spec_id": "srs-c1-r1",
                "operating_envelope": {"pressure_bar": 10},
            },
            "rfq_draft": {
                "rfq_id": "rfq-draft-c1-r1",
                "rfq_basis_status": "rfq_ready",
            },
            "rfq_confirmed": True,
            "answer_contract": {
                "resolved_parameters": {"pressure_bar": 10},
                "calc_results": {},
                "selected_fact_ids": [],
                "required_disclaimers": [],
                "respond_with_uncertainty": False,
            },
            "verification_report": {
                "contract_hash": "c1",
                "draft_hash": "d1",
                "status": "pass",
                "failed_claim_spans": [],
            },
        },
    }

    patch_body = ParametersPatchRequest(chat_id=chat_id, parameters={"pressure_bar": 20})
    asyncio.run(endpoint.patch_parameters(patch_body, request, user=user))

    state_response = asyncio.run(state_endpoint.get_state(request, thread_id=chat_id, user=user))
    reasoning = state_response["state"]["reasoning"]
    working_profile_state = state_response["state"]["working_profile"]
    system_state = state_response["state"]["system"]

    assert reasoning["current_assertion_cycle_id"] == 2
    assert reasoning["asserted_profile_revision"] == 2
    assert reasoning["derived_artifacts_stale"] is True
    assert working_profile_state["derived_artifacts_stale"] is True
    assert working_profile_state["live_calc_tile"]["status"] == "insufficient_data"
    assert system_state["final_text"] is None
    assert system_state["final_answer"] is None
    assert system_state["answer_contract"]["obsolete"] is True
    assert system_state["answer_contract"]["obsolete_reason"] == "assertion_revision_changed:pressure_bar"
    assert system_state["verification_report"] is None
    assert system_state["derived_artifacts_stale"] is True
    assert system_state["rfq_admissibility"]["status"] == "inadmissible"
    assert system_state["rfq_admissibility"]["governed_ready"] is False
    assert system_state["rfq_admissibility"]["derived_from_assertion_cycle_id"] == 2
    assert system_state["rfq_admissibility"]["derived_from_assertion_revision"] == 2
    assert system_state["sealing_requirement_spec"] is None
    assert system_state["rfq_draft"] is None
    assert system_state["rfq_confirmed"] is False
    assert system_state["rfq_pdf_base64"] is None
    assert system_state["rfq_html_report"] is None


def test_state_falls_back_to_legacy_thread(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CHECKPOINTER_BACKEND", "memory")
    graph = _install_memory_graph(monkeypatch)

    chat_id = "chat-legacy-fallback"
    request = _request()
    user = RequestUser(user_id="user-claim", username="tester", sub="legacy-sub", roles=[])

    graph, legacy_config = asyncio.run(
        state_endpoint._build_state_config_with_checkpointer(thread_id=chat_id, user_id=user.sub, username=user.username)
    )
    asyncio.run(
        graph.aupdate_state(
            legacy_config,
            {"working_profile": {"engineering_profile": {"medium": "oil"}}},
            as_node=endpoint.PARAMETERS_PATCH_AS_NODE,
        )
    )

    state_response = asyncio.run(state_endpoint.get_state(request, thread_id=chat_id, user=user))
    assert state_response["working_profile"]["medium"] == "oil"
    assert state_response["config"]["configurable"]["thread_id"] == f"{user.sub}:{chat_id}"
