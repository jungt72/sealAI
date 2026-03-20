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
from app.services.auth.dependencies import RequestUser

app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_sessions():
    SESSION_STORE.clear()


def test_api_chat_endpoint_success():
    mock_updated_state = {
        "messages": [HumanMessage(content="Hallo Agent"), AIMessage(content="Hallo! Wie kann ich helfen?")],
        "sealing_state": {"cycle": {"state_revision": 1, "analysis_cycle_id": "session_test_1"}, "governance": {"release_status": "inadmissible"}},
    }
    with patch("app.agent.api.router.execute_agent", return_value=mock_updated_state):
        response = client.post("/chat", json={"message": "Hallo Agent", "session_id": "test_session"})
    assert response.status_code == 200
    assert response.json()["reply"] == "Hallo! Wie kann ich helfen?"


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
