import asyncio
import copy
import os
from unittest.mock import AsyncMock, patch

import pytest
for key, value in {
    "postgres_user": "test",
    "postgres_password": "test",
    "postgres_host": "localhost",
    "postgres_port": "5432",
    "postgres_db": "test",
    "database_url": "sqlite+aiosqlite:///tmp.db",
    "POSTGRES_SYNC_URL": "sqlite:///tmp.db",
    "openai_api_key": "test",
    "qdrant_url": "http://localhost",
    "redis_url": "redis://localhost:6379/0",
    "nextauth_url": "http://localhost",
    "nextauth_secret": "secret",
    "keycloak_issuer": "http://localhost",
    "keycloak_jwks_url": "http://localhost/jwks",
    "keycloak_client_id": "client",
    "keycloak_client_secret": "secret",
    "keycloak_expected_azp": "client",
}.items():
    os.environ.setdefault(key, value)

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.api.router import SESSION_STORE, chat_endpoint, persist_structured_state, router
from app.agent.api.models import ChatRequest
from app.services.auth.dependencies import RequestUser, get_current_request_user

_TEST_USER = RequestUser(user_id="user-1", username="tester", sub="user-1", roles=[], scopes=[], tenant_id="tenant-1")

app = FastAPI()
app.include_router(router)
app.dependency_overrides[get_current_request_user] = lambda: _TEST_USER
client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_sessions():
    SESSION_STORE.clear()


def test_api_chat_endpoint_success():
    mock_updated_state = {
        "messages": [HumanMessage(content="Hallo Agent"), AIMessage(content="Hallo! Wie kann ich helfen?")],
        "sealing_state": {"cycle": {"state_revision": 1, "analysis_cycle_id": "session_test_1"}, "governance": {"release_status": "inadmissible"}},
        "working_profile": {},
    }
    with patch("app.agent.api.router.prepare_structured_state", new=AsyncMock(return_value=mock_updated_state)), \
         patch("app.agent.api.router.execute_agent", return_value=mock_updated_state), \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock(return_value=None)):
        response = client.post("/chat", json={"message": "Hallo Agent", "session_id": "test_session"})
    assert response.status_code == 200
    assert response.json()["reply"] == "Hallo! Wie kann ich helfen?"


def test_chat_route_uses_injected_current_user():
    """The HTTP /chat route must forward the injected current_user to chat_endpoint."""
    mock_updated_state = {
        "messages": [HumanMessage(content="ping"), AIMessage(content="pong")],
        "sealing_state": {"cycle": {"state_revision": 1, "analysis_cycle_id": "session_x_1"}},
        "working_profile": {},
    }
    captured = {}

    async def _fake_prepare(req, *, current_user):
        captured["current_user"] = current_user
        return mock_updated_state

    with patch("app.agent.api.router.prepare_structured_state", new=AsyncMock(side_effect=_fake_prepare)), \
         patch("app.agent.api.router.execute_agent", return_value=mock_updated_state), \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock(return_value=None)):
        response = client.post("/chat", json={"message": "ping", "session_id": "x"})
    assert response.status_code == 200
    assert captured.get("current_user") is _TEST_USER


def test_chat_route_uses_evaluate_interaction_policy():
    """/chat must route through evaluate_interaction_policy, not a hardcoded decision."""
    mock_updated_state = {
        "messages": [HumanMessage(content="was ist FKM"), AIMessage(content="FKM ist...")],
        "sealing_state": {"cycle": {"state_revision": 1, "analysis_cycle_id": "session_y_1"}},
        "working_profile": {},
    }
    with patch("app.agent.api.router.evaluate_interaction_policy", wraps=__import__("app.agent.runtime", fromlist=["evaluate_interaction_policy"]).evaluate_interaction_policy) as mock_policy, \
         patch("app.agent.api.router.execute_agent", return_value=mock_updated_state), \
         patch("app.agent.api.router.create_initial_state", return_value={"cycle": {"state_revision": 0, "analysis_cycle_id": ""}}):
        response = client.post("/chat", json={"message": "was ist FKM", "session_id": "y"})
    assert response.status_code == 200
    mock_policy.assert_called_once_with("was ist FKM")


def test_chat_endpoint_fast_path_with_current_user():
    """Messages triggering fast-path decision bypass prepare/persist_structured_state."""
    request = ChatRequest(message="was ist FKM", session_id="fast-1")
    mock_updated_state = {
        "messages": [HumanMessage(content="was ist FKM"), AIMessage(content="FKM ist...")],
        "sealing_state": {"cycle": {"state_revision": 0, "analysis_cycle_id": ""}},
        "working_profile": {},
    }
    with patch("app.agent.api.router.execute_agent", return_value=mock_updated_state), \
         patch("app.agent.api.router.create_initial_state", return_value={"cycle": {"state_revision": 0, "analysis_cycle_id": ""}}), \
         patch("app.agent.api.router.prepare_structured_state", new=AsyncMock()) as mock_prepare, \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock()) as mock_persist:
        asyncio.run(chat_endpoint(request, current_user=_TEST_USER))
    mock_prepare.assert_not_called()
    mock_persist.assert_not_called()


def test_chat_endpoint_structured_path_reachable_with_current_user():
    """Messages triggering structured path call prepare and persist."""
    request = ChatRequest(message="Bitte Dichtung auslegen", session_id="struct-1")
    mock_state = {
        "messages": [HumanMessage(content="Bitte Dichtung auslegen"), AIMessage(content="Analyse...")],
        "sealing_state": {"cycle": {"state_revision": 1, "analysis_cycle_id": "cycle-1"}},
        "working_profile": {},
        "case_state": {"case_meta": {"binding_level": "ORIENTATION"}, "result_contract": {}, "qualified_action_gate": {"allowed": False}},
    }
    with patch("app.agent.api.router.prepare_structured_state", new=AsyncMock(return_value=mock_state)) as mock_prepare, \
         patch("app.agent.api.router.execute_agent", return_value=mock_state), \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock(return_value=None)) as mock_persist:
        asyncio.run(chat_endpoint(request, current_user=_TEST_USER))
    mock_prepare.assert_called_once()
    mock_persist.assert_called_once()


def test_persist_structured_state_advances_revision_when_request_did_not():
    user = RequestUser(user_id="user-1", username="tester", sub="user-1", roles=[], scopes=[], tenant_id="tenant-1")
    state = {
        "messages": [HumanMessage(content="Bitte weiter")],
        "sealing_state": {"cycle": {"state_revision": 5, "analysis_cycle_id": "cycle-5"}},
        "working_profile": {},
        "relevant_fact_cards": [],
        "owner_id": "user-1",
        "tenant_id": "tenant-1",
        "loaded_state_revision": 5,
        "case_state": {
            "case_meta": {"state_revision": 5, "version": 5, "analysis_cycle_id": "cycle-5"},
            "result_contract": {"state_revision": 5, "analysis_cycle_id": "cycle-5"},
            "sealing_requirement_spec": {"state_revision": 5, "analysis_cycle_id": "cycle-5"},
        },
    }
    decision = type("Decision", (), {"runtime_path": "STRUCTURED_GUIDANCE", "binding_level": "ORIENTATION"})()
    captured = {}

    async def _fake_save_structured_case(*, tenant_id, owner_id, case_id, state, runtime_path, binding_level):
        captured["state"] = copy.deepcopy(state)

    with patch("app.agent.api.router.save_structured_case", new=AsyncMock(side_effect=_fake_save_structured_case)):
        asyncio.run(persist_structured_state(current_user=user, session_id="case-1", state=state, decision=decision))

    saved_state = captured["state"]
    assert saved_state["sealing_state"]["cycle"]["snapshot_parent_revision"] == 5
    assert saved_state["sealing_state"]["cycle"]["state_revision"] == 6
    assert "::structured_persist::rev6::" in saved_state["sealing_state"]["cycle"]["analysis_cycle_id"]


def test_chat_endpoint_with_current_user_returns_structured_payload():
    request = ChatRequest(message="Bitte pruefen", session_id="case-1")
    user = RequestUser(user_id="user-1", username="tester", sub="user-1", roles=[], scopes=[], tenant_id="tenant-1")
    state = {
        "messages": [AIMessage(content="Antwort")],
        "sealing_state": {"cycle": {"state_revision": 2, "analysis_cycle_id": "cycle-2"}},
        "working_profile": {},
        "relevant_fact_cards": [],
        "case_state": {"case_meta": {"binding_level": "ORIENTATION"}, "result_contract": {}, "qualified_action_gate": {"allowed": False}},
    }
    with patch("app.agent.api.router.prepare_structured_state", new=AsyncMock(return_value=state)), \
         patch("app.agent.api.router.execute_agent", return_value=state), \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock(return_value=None)):
        response = asyncio.run(chat_endpoint(request, current_user=user))
    assert response.visible_case_narrative is not None
    assert response.version_provenance is not None
