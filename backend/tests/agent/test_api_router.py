import asyncio
import copy
import os
from types import SimpleNamespace
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

from app.agent.api.router import (
    SESSION_STORE,
    _apply_review_decision,
    _cache_loaded_state,
    _resolve_runtime_dispatch,
    event_generator,
    build_runtime_payload,
    chat_endpoint,
    persist_canonical_state,
    persist_structured_state,
    router,
)
from app.agent.api.models import ChatRequest
from app.agent.api.models import ReviewRequest
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    GovernanceState,
    GovernedSessionState,
    RequirementClass,
    RfqState,
)
from app.services.auth.dependencies import RequestUser, get_current_request_user

_TEST_USER = RequestUser(user_id="user-1", username="tester", sub="user-1", roles=[], scopes=[], tenant_id="tenant-1")
_PUBLIC_CHAT_RESPONSE_KEYS = {
    "reply",
    "session_id",
    "sealing_state",
    "policy_path",
    "run_meta",
    "response_class",
    "interaction_class",
    "runtime_path",
    "binding_level",
    "has_case_state",
    "case_id",
    "qualified_action_gate",
    "result_contract",
    "rfq_ready",
    "visible_case_narrative",
    "result_form",
    "path",
    "stream_mode",
    "required_fields",
    "coverage_status",
    "boundary_flags",
    "escalation_reason",
    "case_state",
    "working_profile",
    "version_provenance",
    "next_step_contract",
    "structured_state",
}

app = FastAPI()
app.include_router(router)
app.dependency_overrides[get_current_request_user] = lambda: _TEST_USER
client = TestClient(app)


class _EnumLike(str):
    @property
    def value(self) -> str:
        return str(self)


@pytest.fixture(autouse=True)
def clear_sessions():
    SESSION_STORE.clear()


def test_api_chat_endpoint_success():
    mock_updated_state = {
        "messages": [HumanMessage(content="Hallo Agent"), AIMessage(content="Hallo! Wie kann ich helfen?")],
        "sealing_state": {"cycle": {"state_revision": 1, "analysis_cycle_id": "session_test_1"}, "governance": {"release_status": "inadmissible"}},
        "working_profile": {},
    }
    legacy_dispatch = SimpleNamespace(
        gate_route="governed_needed",
        gate_reason="legacy_test",
        runtime_mode="legacy_fallback",
        gate_applied=False,
    )
    legacy_decision = SimpleNamespace(
        path=_EnumLike("fast"),
        result_form=_EnumLike("response"),
        has_case_state=False,
        interaction_class="guidance",
        runtime_path="FAST_GUIDANCE",
        binding_level="ORIENTATION",
    )
    with patch("app.agent.api.router.prepare_structured_state", new=AsyncMock(return_value=mock_updated_state)), \
         patch("app.agent.api.router.execute_agent", return_value=mock_updated_state), \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock(return_value=None)), \
         patch("app.agent.api.router._resolve_runtime_dispatch", new=AsyncMock(return_value=legacy_dispatch)), \
         patch("app.agent.api.router.evaluate_interaction_policy_async", new=AsyncMock(return_value=legacy_decision)):
        response = client.post("/chat", json={"message": "Hallo Agent", "session_id": "test_session"})
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == _PUBLIC_CHAT_RESPONSE_KEYS
    assert body["reply"] == "Hallo! Wie kann ich helfen?"


def test_api_chat_endpoint_uses_central_user_facing_reply_assembly():
    mock_updated_state = {
        "messages": [HumanMessage(content="Hallo Agent"), AIMessage(content="Hallo! Wie kann ich helfen?")],
        "sealing_state": {"cycle": {"state_revision": 1, "analysis_cycle_id": "session_test_1"}, "governance": {"release_status": "inadmissible"}},
        "working_profile": {},
    }
    assembled = {
        "reply": "Assembled legacy reply",
        "structured_state": None,
        "policy_path": "fast",
        "run_meta": None,
        "response_class": "conversational_answer",
    }
    legacy_dispatch = SimpleNamespace(
        gate_route="governed_needed",
        gate_reason="legacy_test",
        runtime_mode="legacy_fallback",
        gate_applied=False,
    )
    legacy_decision = SimpleNamespace(
        path=_EnumLike("fast"),
        result_form=_EnumLike("response"),
        has_case_state=False,
        interaction_class="guidance",
        runtime_path="FAST_GUIDANCE",
        binding_level="ORIENTATION",
    )
    with patch("app.agent.api.router.prepare_structured_state", new=AsyncMock(return_value=mock_updated_state)), \
         patch("app.agent.api.router.execute_agent", return_value=mock_updated_state), \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock(return_value=None)), \
         patch("app.agent.api.router._resolve_runtime_dispatch", new=AsyncMock(return_value=legacy_dispatch)), \
         patch("app.agent.api.router.evaluate_interaction_policy_async", new=AsyncMock(return_value=legacy_decision)), \
         patch("app.agent.api.models.assemble_user_facing_reply", return_value=assembled) as mock_assemble:
        response = client.post("/chat", json={"message": "Hallo Agent", "session_id": "test_session"})

    assert response.status_code == 200
    assert response.json()["reply"] == "Assembled legacy reply"
    mock_assemble.assert_called()


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
    decision = type(
        "Decision",
        (),
        {
            "path": _EnumLike("fast"),
            "result_form": _EnumLike("direct_answer"),
            "stream_mode": "token_stream",
            "interaction_class": "GUIDANCE",
            "runtime_path": "FAST_GUIDANCE",
            "binding_level": "ORIENTATION",
            "has_case_state": False,
            "coverage_status": None,
            "boundary_flags": (),
            "escalation_reason": None,
            "required_fields": (),
        },
    )()
    mock_updated_state = {
        "messages": [HumanMessage(content="was ist FKM"), AIMessage(content="FKM ist...")],
        "sealing_state": {"cycle": {"state_revision": 1, "analysis_cycle_id": "session_y_1"}},
        "working_profile": {},
    }
    mock_policy = AsyncMock(return_value=decision)
    with patch("app.agent.api.router.evaluate_interaction_policy_async", mock_policy), \
         patch("app.agent.api.router.prepare_structured_state", new=AsyncMock(return_value=mock_updated_state)), \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock(return_value=None)), \
         patch("app.agent.api.router.execute_agent", return_value=mock_updated_state), \
         patch("app.agent.api.router.create_initial_state", return_value={"cycle": {"state_revision": 0, "analysis_cycle_id": ""}}):
        response = client.post("/chat", json={"message": "was ist FKM", "session_id": "y"})
    assert response.status_code == 200
    mock_policy.assert_called_once_with("was ist FKM")


def test_chat_endpoint_fast_path_with_current_user():
    """Messages triggering fast-path still run through canonical persisted state."""
    request = ChatRequest(message="was ist FKM", session_id="fast-1")
    decision = type(
        "Decision",
        (),
        {
            "path": _EnumLike("fast"),
            "result_form": _EnumLike("direct_answer"),
            "stream_mode": "token_stream",
            "interaction_class": "GUIDANCE",
            "runtime_path": "FAST_GUIDANCE",
            "binding_level": "ORIENTATION",
            "has_case_state": False,
            "coverage_status": None,
            "boundary_flags": (),
            "escalation_reason": None,
            "required_fields": (),
        },
    )()
    mock_updated_state = {
        "messages": [HumanMessage(content="was ist FKM"), AIMessage(content="FKM ist...")],
        "sealing_state": {"cycle": {"state_revision": 0, "analysis_cycle_id": ""}},
        "working_profile": {},
    }
    with patch("app.agent.api.router.evaluate_interaction_policy_async", AsyncMock(return_value=decision)), \
         patch("app.agent.api.router.execute_agent", return_value=mock_updated_state), \
         patch("app.agent.api.router.prepare_structured_state", new=AsyncMock(return_value=mock_updated_state)) as mock_prepare, \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock()) as mock_persist:
        asyncio.run(chat_endpoint(request, current_user=_TEST_USER))
    mock_prepare.assert_called_once()
    mock_persist.assert_called_once()


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
    assert saved_state["case_state"]["case_meta"]["snapshot_parent_revision"] == 5
    assert saved_state["case_state"]["case_meta"]["state_revision"] == 6
    assert saved_state["case_state"]["case_meta"]["analysis_cycle_id"] == saved_state["sealing_state"]["cycle"]["analysis_cycle_id"]
    assert saved_state["case_state"]["case_meta"]["version"] == 6


def test_cache_loaded_state_uses_case_state_revision_as_loaded_authority():
    state = {
        "messages": [],
        "sealing_state": {"cycle": {"state_revision": 3, "analysis_cycle_id": "legacy-cycle"}},
        "working_profile": {},
        "case_state": {"case_meta": {"state_revision": 9, "analysis_cycle_id": "case-cycle", "version": 9}},
    }

    cached = _cache_loaded_state(state=state, current_user=_TEST_USER, session_id="case-load-auth")

    assert cached["loaded_state_revision"] == 9


def test_persist_canonical_state_uses_case_state_revision_as_primary_authority():
    user = RequestUser(user_id="user-1", username="tester", sub="user-1", roles=[], scopes=[], tenant_id="tenant-1")
    state = {
        "messages": [HumanMessage(content="Bitte weiter")],
        "sealing_state": {"cycle": {"state_revision": 5, "analysis_cycle_id": "legacy-cycle"}},
        "working_profile": {},
        "relevant_fact_cards": [],
        "owner_id": "user-1",
        "tenant_id": "tenant-1",
        "loaded_state_revision": 7,
        "case_state": {
            "case_meta": {"state_revision": 8, "version": 8, "analysis_cycle_id": "case-cycle", "snapshot_parent_revision": 7},
            "result_contract": {"state_revision": 8, "analysis_cycle_id": "case-cycle"},
            "sealing_requirement_spec": {"state_revision": 8, "analysis_cycle_id": "case-cycle"},
        },
    }
    captured = {}

    async def _fake_save_structured_case(*, tenant_id, owner_id, case_id, state, runtime_path, binding_level):
        captured["state"] = copy.deepcopy(state)

    with patch("app.agent.api.router.save_structured_case", new=AsyncMock(side_effect=_fake_save_structured_case)):
        saved = asyncio.run(
            persist_canonical_state(
                current_user=user,
                session_id="case-1",
                state=state,
                runtime_path="STRUCTURED_GUIDANCE",
                binding_level="ORIENTATION",
            )
        )

    assert captured["state"]["case_state"]["case_meta"]["state_revision"] == 8
    assert captured["state"]["sealing_state"]["cycle"]["state_revision"] == 5
    assert saved["loaded_state_revision"] == 8


def test_chat_endpoint_with_current_user_returns_structured_payload():
    request = ChatRequest(message="Bitte pruefen", session_id="case-1")
    user = RequestUser(user_id="user-1", username="tester", sub="user-1", roles=[], scopes=[], tenant_id="tenant-1")
    state = {
        "messages": [AIMessage(content="Antwort")],
        "sealing_state": {
            "cycle": {"state_revision": 2, "analysis_cycle_id": "cycle-2"},
            "selection": {
                "structured_snapshot_contract": {
                    "case_status": "withheld_review",
                    "output_status": "withheld_review",
                    "primary_reason": "review_pending",
                    "next_step": "human_review",
                    "primary_allowed_action": "await_review",
                    "active_blockers": ["review_pending"],
                },
                "state_trace_audit_projection": {
                    "primary_status_reason": "review_pending",
                    "contributing_reasons": ["review_pending"],
                    "blocking_reasons": ["review_pending"],
                    "trace_flags": [],
                },
            },
            "asserted": {},
        },
        "working_profile": {},
        "relevant_fact_cards": [],
        "case_state": {"case_meta": {"binding_level": "ORIENTATION"}, "result_contract": {}, "qualified_action_gate": {"allowed": False}},
    }
    with patch("app.agent.api.router.prepare_structured_state", new=AsyncMock(return_value=state)), \
         patch("app.agent.api.router.execute_agent", return_value=state), \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock(return_value=None)):
        response = asyncio.run(chat_endpoint(request, current_user=user))
    dumped = response.model_dump()
    assert set(dumped.keys()) == _PUBLIC_CHAT_RESPONSE_KEYS
    assert response.visible_case_narrative is not None
    assert response.version_provenance is not None
    assert response.policy_path == "structured"
    assert response.run_meta == response.version_provenance
    assert response.response_class == "governed_recommendation"
    assert response.structured_state.model_dump() == {
        "case_status": "withheld_review",
        "output_status": "withheld_review",
        "next_step": "human_review",
        "primary_allowed_action": "await_review",
        "active_blockers": ["review_pending"],
    }


def test_chat_endpoint_fast_path_keeps_structured_state_none():
    request = ChatRequest(message="was ist FKM", session_id="fast-2")
    decision = type(
        "Decision",
        (),
        {
            "path": _EnumLike("fast"),
            "result_form": _EnumLike("direct_answer"),
            "stream_mode": "token_stream",
            "interaction_class": "GUIDANCE",
            "runtime_path": "FAST_GUIDANCE",
            "binding_level": "ORIENTATION",
            "has_case_state": False,
            "coverage_status": None,
            "boundary_flags": (),
            "escalation_reason": None,
            "required_fields": (),
        },
    )()
    state = {
        "messages": [HumanMessage(content="was ist FKM"), AIMessage(content="FKM ist...")],
        "sealing_state": {"cycle": {"state_revision": 0, "analysis_cycle_id": ""}},
        "working_profile": {},
    }
    with patch("app.agent.api.router.evaluate_interaction_policy_async", AsyncMock(return_value=decision)), \
         patch("app.agent.api.router.prepare_structured_state", new=AsyncMock(return_value=state)), \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock(return_value=None)), \
         patch("app.agent.api.router.execute_agent", return_value=state), \
         patch("app.agent.api.router.create_initial_state", return_value={"cycle": {"state_revision": 0, "analysis_cycle_id": ""}}):
        response = asyncio.run(chat_endpoint(request, current_user=_TEST_USER))
    dumped = response.model_dump()
    assert set(dumped.keys()) == _PUBLIC_CHAT_RESPONSE_KEYS
    assert response.policy_path == "fast"
    assert response.response_class == "conversational_answer"
    assert response.run_meta is None
    assert response.structured_state is None


def test_workspace_read_contract_projects_canonical_state() -> None:
    persisted_state = {
        "messages": [],
        "working_profile": {"medium": "water"},
        "case_state": {
            "case_meta": {"phase": "case-workspace-phase"},
            "governance_state": {
                "release_status": "rfq_ready",
                "rfq_admissibility": "ready",
                "review_required": False,
                "review_state": "approved",
            },
            "recipient_selection": {
                "selected_partner_id": "case-workspace-partner",
            },
            "rfq_state": {
                "status": "ready",
                "rfq_confirmed": True,
                "rfq_handover_initiated": True,
                "rfq_html_report_present": True,
                "handover_ready": True,
                "blockers": [],
                "open_points": [],
            },
            "result_contract": {
                "release_status": "rfq_ready",
                "required_disclaimers": [],
            },
        },
        "sealing_state": {
            "cycle": {"state_revision": 4, "phase": "legacy-workspace-phase"},
            "governance": {"release_status": "rfq_ready", "rfq_admissibility": "ready"},
            "handover": {"is_handover_ready": False},
            "selection": {"selected_partner_id": "legacy-workspace-partner"},
        },
    }

    with patch(
        "app.agent.api.router.load_structured_case",
        new=AsyncMock(return_value=copy.deepcopy(persisted_state)),
    ):
        response = client.get("/workspace/case-1")

    assert response.status_code == 200
    body = response.json()
    assert body["case_summary"]["phase"] == "case-workspace-phase"
    assert body["partner_matching"]["selected_partner_id"] == "case-workspace-partner"
    assert body["rfq_status"]["rfq_confirmed"] is True
    assert body["rfq_status"]["handover_initiated"] is True
    assert body["rfq_status"]["has_html_report"] is True


def test_workspace_rfq_document_reads_canonical_html_report() -> None:
    persisted_state = {
        "messages": [],
        "working_profile": {},
        "case_state": {
            "rfq_state": {
                "handover_ready": True,
                "rfq_object": {
                    "object_type": "rfq_payload_basis",
                    "object_version": "rfq_payload_basis_v1",
                    "confirmed_parameters": {"medium": "Steam", "pressure_bar": 12},
                },
            },
        },
        "sealing_state": {
            "handover": {
                "rfq_html_report": "<html><body>legacy</body></html>",
            },
        },
    }

    with patch(
        "app.agent.api.router.load_structured_case",
        new=AsyncMock(return_value=copy.deepcopy(persisted_state)),
    ):
        response = client.get("/workspace/case-1/rfq-document")

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'inline; filename="sealai-rfq-document.html"'
    assert "Technical RFQ Document" in response.text
    assert "Steam" in response.text
    assert "legacy" not in response.text


def test_workspace_rfq_document_blocks_when_canonical_rfq_basis_is_not_releasable() -> None:
    persisted_state = {
        "messages": [],
        "working_profile": {},
        "case_state": {
            "rfq_state": {
                "handover_ready": False,
                "critical_review_passed": False,
                "rfq_object": {
                    "object_type": "rfq_payload_basis",
                    "object_version": "rfq_payload_basis_v1",
                    "confirmed_parameters": {"medium": "Steam"},
                },
            },
        },
        "sealing_state": {
            "handover": {
                "is_handover_ready": False,
            },
        },
    }

    with patch(
        "app.agent.api.router.load_structured_case",
        new=AsyncMock(return_value=copy.deepcopy(persisted_state)),
    ):
        response = client.get("/workspace/case-1/rfq-document")

    assert response.status_code == 409
    assert response.json()["detail"] == "RFQ document is blocked until the mandatory critical review passes."


def test_workspace_rfq_document_returns_404_without_generated_html_report() -> None:
    persisted_state = {
        "messages": [],
        "working_profile": {},
        "case_state": {},
        "sealing_state": {"handover": {}},
    }

    with patch(
        "app.agent.api.router.load_structured_case",
        new=AsyncMock(return_value=copy.deepcopy(persisted_state)),
    ):
        response = client.get("/workspace/case-1/rfq-document")

    assert response.status_code == 404
    assert response.json()["detail"] == "No RFQ document has been generated yet."


def test_workspace_projection_prefers_canonical_rfq_object_and_matching_state() -> None:
    persisted_state = {
        "messages": [],
        "working_profile": {},
        "case_state": {
            "matching_state": {
                "status": "matched_primary_candidate",
                "matchability_status": "ready_for_matching",
                "match_candidates": [
                    {
                        "candidate_id": "ptfe::g25::acme",
                        "material_family": "PTFE",
                        "grade_name": "G25",
                        "manufacturer_name": "Acme",
                        "viability_status": "viable",
                        "fit_reasons": ["temperature window is covered.", "medium 'steam' is supported."],
                    }
                ],
            },
            "rfq_state": {
                "status": "rfq_ready",
                "rfq_confirmed": False,
                "handover_ready": True,
                "open_points": ["confirm buyer drawing revision"],
                "rfq_object": {
                    "object_type": "rfq_payload_basis",
                    "object_version": "rfq_payload_basis_v1",
                    "confirmed_parameters": {"medium": "Steam", "pressure_bar": 12},
                    "qualified_material_ids": ["ptfe::g25::acme"],
                },
            },
        },
        "sealing_state": {
            "governance": {"release_status": "rfq_ready"},
            "handover": {},
        },
    }

    with patch(
        "app.agent.api.router.load_structured_case",
        new=AsyncMock(return_value=copy.deepcopy(persisted_state)),
    ):
        response = client.get("/workspace/case-1")

    assert response.status_code == 200
    body = response.json()
    assert body["rfq_package"]["has_draft"] is True
    assert body["rfq_package"]["rfq_basis_status"] == "rfq_ready"
    assert body["rfq_package"]["operating_context_redacted"]["medium"] == "Steam"
    assert body["partner_matching"]["matching_ready"] is True
    assert body["partner_matching"]["material_fit_items"][0]["material"] == "G25"
    assert body["partner_matching"]["material_fit_items"][0]["fit_basis"] == "temperature window is covered.; medium 'steam' is supported."
    assert body["partner_matching"]["open_manufacturer_questions"] == ["confirm buyer drawing revision"]
    assert body["partner_matching"]["data_source"] == "candidate_derived"
    assert body["rfq_status"]["handover_ready"] is True


def test_workspace_projection_exposes_matching_blockers_when_not_ready() -> None:
    persisted_state = {
        "messages": [],
        "working_profile": {},
        "case_state": {
            "matching_state": {
                "status": "not_ready",
                "matchability_status": "blocked_review_required",
                "blocking_reasons": ["review_required", "no_match_candidates"],
            },
            "rfq_state": {
                "status": "inadmissible",
                "rfq_confirmed": False,
                "handover_ready": False,
            },
        },
        "sealing_state": {
            "governance": {"release_status": "manufacturer_validation_required"},
            "handover": {},
        },
    }

    with patch(
        "app.agent.api.router.load_structured_case",
        new=AsyncMock(return_value=copy.deepcopy(persisted_state)),
    ):
        response = client.get("/workspace/case-1")

    assert response.status_code == 200
    body = response.json()
    assert body["partner_matching"]["matching_ready"] is False
    assert body["partner_matching"]["not_ready_reasons"] == ["review_required", "no_match_candidates"]


def test_review_route_requires_auth() -> None:
    local_app = FastAPI()
    local_app.include_router(router)
    local_client = TestClient(local_app)

    response = local_client.post(
        "/review",
        json={"session_id": "case-1", "action": "approve"},
    )

    assert response.status_code == 401


def test_chat_stream_route_requires_auth() -> None:
    local_app = FastAPI()
    local_app.include_router(router)
    local_client = TestClient(local_app)

    response = local_client.post(
        "/chat/stream",
        json={"message": "Hallo", "session_id": "case-1"},
    )

    assert response.status_code == 401


def test_chat_and_stream_use_shared_runtime_dispatcher() -> None:
    request = ChatRequest(message="Hallo", session_id="case-shared")
    dispatch_calls = []

    async def _fake_dispatch(req, *, current_user):
        dispatch_calls.append(
            {
                "message": req.message,
                "session_id": req.session_id,
                "current_user": current_user,
            }
        )
        return type(
            "Resolution",
            (),
            {
                "runtime_mode": "governed_needed",
                "gate_route": "governed_needed",
                "gate_reason": "binary_gate_disabled",
                "gate_applied": False,
                "session_zone": None,
            },
        )()

    async def _fake_prepare(*_args, **_kwargs):
        return {
            "messages": [HumanMessage(content="Hallo"), AIMessage(content="Antwort")],
            "sealing_state": {"cycle": {"state_revision": 1, "analysis_cycle_id": "cycle-1"}},
            "working_profile": {},
        }

    async def _fake_sse_gen(*_args, **_kwargs):
        yield "data: [DONE]\n\n"

    decision = type(
        "Decision",
        (),
        {
            "path": _EnumLike("fast"),
            "result_form": _EnumLike("direct_answer"),
            "stream_mode": "token_stream",
            "interaction_class": "GUIDANCE",
            "runtime_path": "FAST_GUIDANCE",
            "binding_level": "ORIENTATION",
            "has_case_state": False,
            "coverage_status": None,
            "boundary_flags": (),
            "escalation_reason": None,
            "required_fields": (),
        },
    )()

    with patch("app.agent.api.router._resolve_runtime_dispatch", new=AsyncMock(side_effect=_fake_dispatch)), \
         patch("app.agent.api.router.prepare_structured_state", new=AsyncMock(side_effect=_fake_prepare)), \
         patch("app.agent.api.router.evaluate_interaction_policy_async", new=AsyncMock(return_value=decision)), \
         patch("app.agent.api.router.execute_agent", new=AsyncMock(return_value={
             "messages": [HumanMessage(content="Hallo"), AIMessage(content="Antwort")],
             "sealing_state": {"cycle": {"state_revision": 1, "analysis_cycle_id": "cycle-1"}},
             "working_profile": {},
         })), \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock(return_value=None)), \
         patch("app.agent.api.router.agent_sse_generator", side_effect=_fake_sse_gen):
        asyncio.run(chat_endpoint(request, current_user=_TEST_USER))
        asyncio.run(_collect_stream_frames(event_generator(request, current_user=_TEST_USER)))

    assert len(dispatch_calls) == 2
    assert all(call["message"] == "Hallo" for call in dispatch_calls)
    assert all(call["session_id"] == "case-shared" for call in dispatch_calls)
    assert all(call["current_user"] is _TEST_USER for call in dispatch_calls)


def test_chat_endpoint_uses_conversation_runtime_when_dispatcher_routes_conversation() -> None:
    request = ChatRequest(message="Hallo", session_id="case-conv")
    resolution = type(
        "Resolution",
        (),
        {
            "runtime_mode": "instant_light_reply",
            "gate_route": "instant_light_reply",
            "gate_reason": "deterministic_instant:greeting_or_smalltalk",
            "gate_applied": True,
            "session_zone": "conversation",
        },
    )()

    with patch("app.agent.api.router._resolve_runtime_dispatch", new=AsyncMock(return_value=resolution)), \
         patch("app.agent.runtime.conversation_runtime.run_conversation", new=AsyncMock(return_value=type("ConversationResult", (), {"reply_text": "Konversationsantwort"})())) as mock_run, \
         patch("app.agent.api.router.prepare_structured_state", new=AsyncMock()) as mock_prepare, \
         patch("app.agent.api.router.execute_agent") as mock_execute, \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock()) as mock_persist:
        response = asyncio.run(chat_endpoint(request, current_user=_TEST_USER))

    assert response.reply == "Konversationsantwort"
    assert response.response_class == "conversational_answer"
    assert response.policy_path == "fast"
    mock_prepare.assert_not_called()
    mock_execute.assert_not_called()
    mock_persist.assert_not_called()
    assert mock_run.await_args.kwargs["mode"] == "instant_light_reply"


def test_stream_endpoint_uses_conversation_runtime_when_dispatcher_routes_conversation() -> None:
    request = ChatRequest(message="Hallo", session_id="case-conv-stream")
    resolution = type(
        "Resolution",
        (),
        {
            "runtime_mode": "light_exploration",
            "gate_route": "light_exploration",
            "gate_reason": "deterministic_light:goal_problem_or_uncertainty",
            "gate_applied": True,
            "session_zone": "conversation",
        },
    )()

    captured_stream = {}

    async def _fake_conversation(*_args, **_kwargs):
        captured_stream.update(_kwargs)
        yield 'data: {"type":"text_chunk","text":"Hallo"}\n\n'
        yield "data: [DONE]\n\n"

    with patch("app.agent.api.router._resolve_runtime_dispatch", new=AsyncMock(return_value=resolution)), \
         patch("app.agent.runtime.conversation_runtime.stream_conversation", side_effect=_fake_conversation), \
         patch("app.agent.api.router.prepare_structured_state", new=AsyncMock()) as mock_prepare:
        frames = asyncio.run(_collect_stream_frames(event_generator(request, current_user=_TEST_USER)))

    assert frames == ['data: {"type":"text_chunk","text":"Hallo"}\n\n', "data: [DONE]\n\n"]
    mock_prepare.assert_not_called()
    assert captured_stream["mode"] == "light_exploration"


def test_conversation_json_and_sse_share_runtime_without_governed_side_effects() -> None:
    request = ChatRequest(message="Hallo", session_id="case-conv-parity")
    resolution = type(
        "Resolution",
        (),
        {
            "runtime_mode": "light_exploration",
            "gate_route": "light_exploration",
            "gate_reason": "deterministic_light:goal_problem_or_uncertainty",
            "gate_applied": True,
            "session_zone": "conversation",
        },
    )()

    async def _fake_run_conversation(*_args, **_kwargs):
        return type("ConversationResult", (), {"reply_text": "Gemeinsame Antwort"})()

    async def _fake_stream_conversation(*_args, **_kwargs):
        yield 'data: {"type":"text_chunk","text":"Gemeinsame Antwort"}\n\n'
        yield "data: [DONE]\n\n"

    with patch("app.agent.api.router._resolve_runtime_dispatch", new=AsyncMock(return_value=resolution)), \
         patch("app.agent.runtime.conversation_runtime.run_conversation", side_effect=_fake_run_conversation), \
         patch("app.agent.runtime.conversation_runtime.stream_conversation", side_effect=_fake_stream_conversation), \
         patch("app.agent.api.router.prepare_structured_state", new=AsyncMock()) as mock_prepare, \
         patch("app.agent.api.router.execute_agent", new=AsyncMock()) as mock_execute, \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock()) as mock_persist:
        response = asyncio.run(chat_endpoint(request, current_user=_TEST_USER))
        frames = asyncio.run(_collect_stream_frames(event_generator(request, current_user=_TEST_USER)))

    assert response.reply == "Gemeinsame Antwort"
    assert frames == ['data: {"type":"text_chunk","text":"Gemeinsame Antwort"}\n\n', "data: [DONE]\n\n"]
    mock_prepare.assert_not_called()
    mock_execute.assert_not_called()
    mock_persist.assert_not_called()


def test_runtime_dispatch_fails_open_to_governed_when_gate_resolution_errors() -> None:
    request = ChatRequest(message="Hallo", session_id="case-fail-open")

    with patch("app.agent.api.router._ENABLE_BINARY_GATE", True), \
         patch("app.agent.api.router._ENABLE_CONVERSATION_RUNTIME", True), \
         patch("redis.asyncio.Redis.from_url", side_effect=RuntimeError("redis down")):
        resolution = asyncio.run(_resolve_runtime_dispatch(request, current_user=_TEST_USER))

    assert resolution.runtime_mode == "governed_needed"
    assert resolution.gate_route == "governed_needed"
    assert resolution.gate_applied is False
    assert resolution.gate_reason.startswith("gate_session_fail_open:")


def test_runtime_dispatch_preserves_sticky_governed_session() -> None:
    from app.agent.runtime.gate import GateDecision
    from app.agent.runtime.session_manager import SessionEnvelope

    request = ChatRequest(message="Nur Smalltalk", session_id="case-sticky")
    envelope = SessionEnvelope(
        session_id="case-sticky",
        tenant_id="tenant-1",
        user_id="user-1",
        session_zone="governed",
    )

    class _RedisContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    with patch("app.agent.api.router._ENABLE_BINARY_GATE", True), \
         patch("app.agent.api.router._ENABLE_CONVERSATION_RUNTIME", True), \
         patch("redis.asyncio.Redis.from_url", return_value=_RedisContext()), \
         patch("app.agent.runtime.session_manager.get_or_create_session_async", new=AsyncMock(return_value=envelope)), \
         patch("app.agent.runtime.gate.decide_route_async", new=AsyncMock(return_value=GateDecision(route='governed_needed', reason='sticky_governed_session'))), \
         patch("app.agent.runtime.session_manager.apply_gate_decision_and_persist_async", new=AsyncMock(return_value=envelope)):
        resolution = asyncio.run(_resolve_runtime_dispatch(request, current_user=_TEST_USER))

    assert resolution.runtime_mode == "governed_needed"
    assert resolution.gate_route == "governed_needed"
    assert resolution.gate_reason == "sticky_governed_session"
    assert resolution.session_zone == "governed"


async def _collect_stream_frames(gen):
    frames = []
    async for frame in gen:
        frames.append(frame)
    return frames


def test_review_route_loads_and_persists_canonical_state() -> None:
    state = {
        "messages": [HumanMessage(content="Bitte prüfen")],
        "sealing_state": {
            "cycle": {"state_revision": 2, "analysis_cycle_id": "cycle-2"},
            "review": {"review_required": True, "review_state": "pending"},
            "governance": {"release_status": "manufacturer_validation_required", "rfq_admissibility": "provisional"},
            "selection": {},
        },
        "working_profile": {},
        "relevant_fact_cards": [],
        "case_state": {"case_meta": {"binding_level": "ORIENTATION"}, "result_contract": {}},
    }
    node_result = {
        "sealing_state": {
            "cycle": {"state_revision": 3, "analysis_cycle_id": "cycle-3"},
            "review": {"review_required": False, "review_state": "approved"},
            "governance": {"release_status": "rfq_ready", "rfq_admissibility": "ready"},
            "handover": {"is_handover_ready": False},
            "selection": {},
        },
        "case_state": {
            "governance_state": {"review_state": "case-approved", "release_status": "rfq_ready"},
            "rfq_state": {
                "handover_ready": True,
                "handover_status": "releasable",
                "rfq_object": {
                    "qualified_material_ids": ["ptfe::g25::acme"],
                    "qualified_materials": [],
                    "confirmed_parameters": {},
                    "dimensions": {},
                },
            },
        },
        "messages": [AIMessage(content="Review abgeschlossen")],
    }
    saved = {}

    async def _fake_load_structured_case(*, tenant_id, owner_id, case_id):
        saved["loaded_scope"] = (tenant_id, owner_id, case_id)
        return copy.deepcopy(state)

    async def _fake_save_structured_case(*, tenant_id, owner_id, case_id, state, runtime_path, binding_level):
        saved["saved_scope"] = (tenant_id, owner_id, case_id)
        saved["runtime_path"] = runtime_path
        saved["binding_level"] = binding_level
        saved["state"] = copy.deepcopy(state)

    with patch("app.agent.api.router.load_structured_case", new=AsyncMock(side_effect=_fake_load_structured_case)), \
         patch("app.agent.api.router.save_structured_case", new=AsyncMock(side_effect=_fake_save_structured_case)), \
         patch("app.agent.api.router._governed_native_review_commit", return_value=(copy.deepcopy(state) | node_result, "Review abgeschlossen")):
        response = client.post("/review", json={"session_id": "case-1", "action": "approve"})

    assert response.status_code == 200
    assert saved["loaded_scope"] == ("tenant-1", "user-1", "case-1")
    assert saved["saved_scope"] == ("tenant-1", "user-1", "case-1")
    assert saved["runtime_path"] == "STRUCTURED_QUALIFICATION"
    assert saved["binding_level"] == "ORIENTATION"
    assert saved["state"]["messages"][-1].content == "Review abgeschlossen"
    assert response.json()["release_status"] == "rfq_ready"
    assert response.json()["review_state"] == "case-approved"
    assert response.json()["is_handover_ready"] is True
    assert response.json()["handover"]["is_handover_ready"] is True
    assert response.json()["handover"]["handover_status"] == "releasable"
    assert response.json()["handover"]["handover_payload"]["qualified_material_ids"] == ["ptfe::g25::acme"]


def test_review_route_falls_back_to_raw_handover_when_case_state_lacks_payload() -> None:
    state = {
        "messages": [HumanMessage(content="Bitte prüfen")],
        "sealing_state": {
            "cycle": {"state_revision": 2, "analysis_cycle_id": "cycle-2"},
            "review": {"review_required": True, "review_state": "pending"},
            "governance": {"release_status": "manufacturer_validation_required", "rfq_admissibility": "provisional"},
            "selection": {},
        },
        "working_profile": {},
        "relevant_fact_cards": [],
        "case_state": {"case_meta": {"binding_level": "ORIENTATION"}, "result_contract": {}},
    }
    node_result = {
        "sealing_state": {
            "cycle": {"state_revision": 3, "analysis_cycle_id": "cycle-3"},
            "review": {"review_required": False, "review_state": "approved"},
            "governance": {"release_status": "rfq_ready", "rfq_admissibility": "ready"},
            "handover": {
                "is_handover_ready": True,
                "handover_status": "releasable",
                "handover_payload": {"qualified_material_ids": ["legacy-mat"]},
            },
            "selection": {},
        },
        "case_state": {
            "governance_state": {"review_state": "case-approved", "release_status": "rfq_ready"},
            "rfq_state": {"handover_ready": True},
        },
        "messages": [AIMessage(content="Review abgeschlossen")],
    }

    async def _fake_load_structured_case(*, tenant_id, owner_id, case_id):
        return copy.deepcopy(state)

    async def _fake_save_structured_case(*, tenant_id, owner_id, case_id, state, runtime_path, binding_level):
        return None

    with patch("app.agent.api.router.load_structured_case", new=AsyncMock(side_effect=_fake_load_structured_case)), \
         patch("app.agent.api.router.save_structured_case", new=AsyncMock(side_effect=_fake_save_structured_case)), \
         patch("app.agent.api.router._governed_native_review_commit", return_value=(copy.deepcopy(state) | node_result, "Review abgeschlossen")):
        response = client.post("/review", json={"session_id": "case-1", "action": "approve"})

    assert response.status_code == 200
    assert response.json()["handover"]["is_handover_ready"] is True
    assert response.json()["handover"]["handover_payload"]["qualified_material_ids"] == ["legacy-mat"]


def test_review_route_omits_handover_payload_when_rfq_basis_is_blocked() -> None:
    state = {
        "messages": [HumanMessage(content="Bitte prüfen")],
        "sealing_state": {
            "cycle": {"state_revision": 2, "analysis_cycle_id": "cycle-2"},
            "review": {"review_required": True, "review_state": "pending"},
            "governance": {"release_status": "manufacturer_validation_required", "rfq_admissibility": "provisional"},
            "selection": {},
        },
        "working_profile": {},
        "relevant_fact_cards": [],
        "case_state": {"case_meta": {"binding_level": "ORIENTATION"}, "result_contract": {}},
    }
    node_result = {
        "sealing_state": {
            "cycle": {"state_revision": 3, "analysis_cycle_id": "cycle-3"},
            "review": {
                "review_required": False,
                "review_state": "approved",
                "critical_review_status": "failed",
                "critical_review_passed": False,
                "blocking_findings": ["selected_manufacturer_missing"],
            },
            "governance": {"release_status": "rfq_ready", "rfq_admissibility": "ready"},
            "handover": {"is_handover_ready": False, "handover_status": "reviewable"},
            "selection": {},
        },
        "case_state": {
            "governance_state": {"review_state": "case-approved", "release_status": "rfq_ready"},
            "rfq_state": {
                "handover_ready": False,
                "handover_status": "blocked_critical_review",
                "critical_review_passed": False,
                "rfq_object": {
                    "qualified_material_ids": ["ptfe::g25::acme"],
                    "qualified_materials": [],
                    "confirmed_parameters": {},
                    "dimensions": {},
                },
            },
        },
        "messages": [AIMessage(content="Review abgeschlossen")],
    }

    async def _fake_load_structured_case(*, tenant_id, owner_id, case_id):
        return copy.deepcopy(state)

    async def _fake_save_structured_case(*, tenant_id, owner_id, case_id, state, runtime_path, binding_level):
        return None

    with patch("app.agent.api.router.load_structured_case", new=AsyncMock(side_effect=_fake_load_structured_case)), \
         patch("app.agent.api.router.save_structured_case", new=AsyncMock(side_effect=_fake_save_structured_case)), \
         patch("app.agent.api.router._governed_native_review_commit", return_value=(copy.deepcopy(state) | node_result, "Review abgeschlossen")):
        response = client.post("/review", json={"session_id": "case-1", "action": "approve"})

    assert response.status_code == 200
    assert response.json()["is_handover_ready"] is False
    assert response.json()["handover"]["is_handover_ready"] is False
    assert response.json()["handover"]["handover_status"] == "blocked_critical_review"
    assert "handover_payload" not in response.json()["handover"]


def test_review_route_guards_legacy_final_response_reply() -> None:
    state = {
        "messages": [HumanMessage(content="Bitte prüfen")],
        "sealing_state": {
            "cycle": {"state_revision": 2, "analysis_cycle_id": "cycle-2"},
            "review": {"review_required": True, "review_state": "pending"},
            "governance": {"release_status": "manufacturer_validation_required", "rfq_admissibility": "provisional"},
            "selection": {},
        },
        "working_profile": {},
        "relevant_fact_cards": [],
        "case_state": {"case_meta": {"binding_level": "ORIENTATION"}, "result_contract": {}},
    }
    node_result = {
        "sealing_state": {
            "cycle": {"state_revision": 3, "analysis_cycle_id": "cycle-3"},
            "review": {"review_required": False, "review_state": "approved"},
            "governance": {"release_status": "rfq_ready", "rfq_admissibility": "ready"},
            "handover": {"is_handover_ready": False, "handover_status": "reviewable"},
            "selection": {},
        },
        "case_state": {
            "governance_state": {"review_state": "case-approved", "release_status": "rfq_ready", "rfq_admissibility": "ready"},
            "rfq_state": {"handover_ready": False, "rfq_admissibility": "ready"},
            "qualified_action_gate": {"allowed": False},
        },
        "messages": [AIMessage(content="Die technische Richtung ist final freigegeben.")],
    }

    async def _fake_load_structured_case(*, tenant_id, owner_id, case_id):
        return copy.deepcopy(state)

    async def _fake_save_structured_case(*, tenant_id, owner_id, case_id, state, runtime_path, binding_level):
        return None

    with patch("app.agent.api.router.load_structured_case", new=AsyncMock(side_effect=_fake_load_structured_case)), \
         patch("app.agent.api.router.save_structured_case", new=AsyncMock(side_effect=_fake_save_structured_case)), \
         patch("app.agent.api.router._governed_native_review_commit", return_value=(copy.deepcopy(state) | node_result, "Die technische Richtung ist final freigegeben.")):
        response = client.post("/review", json={"session_id": "case-1", "action": "approve"})

    assert response.status_code == 200
    assert response.json()["reply"] == "Ich kann die technische Richtung belastbar einordnen und die offenen Pruefpunkte klar benennen."


def test_review_route_uses_central_user_facing_reply_assembly() -> None:
    state = {
        "messages": [HumanMessage(content="Bitte prüfen")],
        "sealing_state": {
            "cycle": {"state_revision": 2, "analysis_cycle_id": "cycle-2"},
            "review": {"review_required": True, "review_state": "pending"},
            "governance": {"release_status": "manufacturer_validation_required", "rfq_admissibility": "provisional"},
            "selection": {},
        },
        "working_profile": {},
        "relevant_fact_cards": [],
        "case_state": {"case_meta": {"binding_level": "ORIENTATION"}, "result_contract": {}},
    }
    node_result = {
        "sealing_state": {
            "cycle": {"state_revision": 3, "analysis_cycle_id": "cycle-3"},
            "review": {"review_required": False, "review_state": "approved"},
            "governance": {"release_status": "rfq_ready", "rfq_admissibility": "ready"},
            "handover": {"is_handover_ready": False, "handover_status": "reviewable"},
            "selection": {},
        },
        "case_state": {
            "governance_state": {"review_state": "case-approved", "release_status": "rfq_ready", "rfq_admissibility": "ready"},
            "rfq_state": {"handover_ready": False, "rfq_admissibility": "ready"},
            "qualified_action_gate": {"allowed": False},
        },
        "messages": [AIMessage(content="Review abgeschlossen")],
    }
    assembled = {
        "reply": "Assembled review reply",
        "structured_state": {
            "case_status": "withheld_review",
            "output_status": "withheld_review",
            "next_step": "confirmed_result_review",
            "primary_allowed_action": "await_review",
            "active_blockers": [],
        },
        "policy_path": "structured",
        "run_meta": None,
        "response_class": "governed_recommendation",
    }
    live_governed_state = GovernedSessionState(
        asserted=AssertedState(
            assertions={
                "medium": AssertedClaim(field_name="medium", asserted_value="Dampf", confidence="confirmed"),
                "pressure_bar": AssertedClaim(field_name="pressure_bar", asserted_value=16.0, confidence="confirmed"),
                "temperature_c": AssertedClaim(field_name="temperature_c", asserted_value=180.0, confidence="confirmed"),
                "geometry_context": AssertedClaim(field_name="geometry_context", asserted_value="Nut im Gehaeuse", confidence="confirmed"),
            }
        ),
        governance=GovernanceState(
            gov_class="A",
            rfq_admissible=True,
            requirement_class=RequirementClass(class_id="PTFE10", description="Steam sealing class"),
            open_validation_points=[],
        ),
        rfq=RfqState(status="reviewable", rfq_ready=False, rfq_admissible=True),
    )

    async def _fake_load_structured_case(*, tenant_id, owner_id, case_id):
        return copy.deepcopy(state)

    async def _fake_save_structured_case(*, tenant_id, owner_id, case_id, state, runtime_path, binding_level):
        return None

    with patch("app.agent.api.router.load_structured_case", new=AsyncMock(side_effect=_fake_load_structured_case)), \
         patch("app.agent.api.router.save_structured_case", new=AsyncMock(side_effect=_fake_save_structured_case)), \
         patch("app.agent.api.router._governed_native_review_commit", return_value=(copy.deepcopy(state) | node_result, "Review abgeschlossen")), \
         patch("app.agent.api.router._load_live_governed_state", new=AsyncMock(return_value=live_governed_state)), \
         patch("app.agent.api.router.collect_governed_visible_reply", new=AsyncMock(return_value="Rendered review reply")) as mock_collect, \
         patch("app.agent.api.router.assemble_user_facing_reply", return_value=assembled) as mock_assemble:
        response = client.post("/review", json={"session_id": "case-1", "action": "approve"})

    assert response.status_code == 200
    assert response.json()["reply"] == "Assembled review reply"
    mock_collect.assert_called()
    mock_assemble.assert_called()


def test_apply_review_decision_aligns_case_state_review_lifecycle() -> None:
    state = {
        "messages": [],
        "sealing_state": {
            "cycle": {"state_revision": 2, "analysis_cycle_id": "cycle-2"},
            "review": {"review_required": True, "review_state": "pending"},
            "governance": {
                "release_status": "manufacturer_validation_required",
                "rfq_admissibility": "provisional",
            },
            "selection": {"selected_partner_id": "partner-1"},
        },
        "working_profile": {},
        "relevant_fact_cards": [],
        "case_state": {
            "case_meta": {"binding_level": "ORIENTATION", "runtime_path": "STRUCTURED_QUALIFICATION"},
            "governance_state": {
                "review_state": "pending",
                "review_required": True,
                "release_status": "manufacturer_validation_required",
                "rfq_admissibility": "provisional",
            },
            "recipient_selection": {"selected_partner_id": "partner-1"},
            "result_contract": {},
        },
    }

    patched = _apply_review_decision(
        state,
        ReviewRequest(session_id="case-1", action="approve", reviewer_notes="ok"),
    )

    assert patched["sealing_state"]["review"]["review_state"] == "approved"
    assert patched["sealing_state"]["review"]["review_required"] is False
    assert patched["sealing_state"]["governance"]["release_status"] == "rfq_ready"
    assert patched["sealing_state"]["governance"]["rfq_admissibility"] == "ready"
    assert patched["sealing_state"]["cycle"]["snapshot_parent_revision"] == 2
    assert patched["sealing_state"]["cycle"]["state_revision"] == 3
    assert patched["case_state"]["governance_state"]["review_state"] == "approved"
    assert patched["case_state"]["governance_state"]["review_required"] is False
    assert patched["case_state"]["governance_state"]["release_status"] == "rfq_ready"
    assert patched["case_state"]["governance_state"]["rfq_admissibility"] == "ready"
    assert patched["case_state"]["case_meta"]["snapshot_parent_revision"] == 2
    assert patched["case_state"]["case_meta"]["state_revision"] == 3
    assert patched["case_state"]["case_meta"]["analysis_cycle_id"] == patched["sealing_state"]["cycle"]["analysis_cycle_id"]
    assert patched["case_state"]["case_meta"]["version"] == 3
    assert patched["case_state"]["recipient_selection"]["selected_partner_id"] == "partner-1"


def test_apply_review_decision_reject_aligns_selection_readiness() -> None:
    state = {
        "messages": [],
        "sealing_state": {
            "cycle": {"state_revision": 4, "analysis_cycle_id": "cycle-4"},
            "review": {"review_required": True, "review_state": "pending"},
            "governance": {"release_status": "rfq_ready", "rfq_admissibility": "ready"},
            "selection": {
                "release_status": "rfq_ready",
                "rfq_admissibility": "ready",
                "output_blocked": False,
                "recommendation_artifact": {
                    "release_status": "rfq_ready",
                    "rfq_admissibility": "ready",
                    "output_blocked": False,
                },
            },
        },
        "working_profile": {},
        "relevant_fact_cards": [],
        "case_state": {
            "case_meta": {"binding_level": "ORIENTATION", "runtime_path": "STRUCTURED_QUALIFICATION"},
            "governance_state": {
                "review_state": "pending",
                "review_required": True,
                "release_status": "rfq_ready",
                "rfq_admissibility": "ready",
            },
            "result_contract": {},
        },
    }

    patched = _apply_review_decision(
        state,
        ReviewRequest(session_id="case-1", action="reject", reviewer_notes="blocked"),
    )

    assert patched["sealing_state"]["review"]["review_required"] is False
    assert patched["sealing_state"]["review"]["review_state"] == "rejected"
    assert patched["sealing_state"]["selection"]["release_status"] == "inadmissible"
    assert patched["sealing_state"]["selection"]["rfq_admissibility"] == "inadmissible"
    assert patched["sealing_state"]["selection"]["output_blocked"] is True
    assert patched["sealing_state"]["selection"]["recommendation_artifact"]["output_blocked"] is True
    assert patched["case_state"]["governance_state"]["release_status"] == "inadmissible"
    assert patched["case_state"]["governance_state"]["rfq_admissibility"] == "inadmissible"
    assert patched["case_state"]["governance_state"]["review_state"] == "rejected"
    assert patched["case_state"]["governance_state"]["review_required"] is False


def test_build_runtime_payload_classifies_governed_result_clarification_and_escalation():
    decision = type(
        "Decision",
        (),
        {
            "path": _EnumLike("structured"),
            "result_form": _EnumLike("deterministic_result"),
            "stream_mode": "structured_progress_stream",
            "interaction_class": "STRUCTURED",
            "runtime_path": "STRUCTURED_QUALIFICATION",
            "binding_level": "ORIENTATION",
            "has_case_state": True,
            "coverage_status": None,
            "boundary_flags": (),
            "escalation_reason": None,
            "required_fields": (),
        },
    )()

    governed = build_runtime_payload(
        decision,
        session_id="s1",
        reply="Ergebnis",
        structured_state={"output_status": "governed_non_binding_result"},
        version_provenance={"policy_version": "v1"},
    )
    clarification = build_runtime_payload(
        decision,
        session_id="s2",
        reply="Bitte eingeben",
        structured_state={"output_status": "clarification_needed"},
    )
    escalation = build_runtime_payload(
        decision,
        session_id="s3",
        reply="Eskalation",
        structured_state={"output_status": "withheld_escalation"},
    )

    assert governed["response_class"] == "governed_recommendation"
    assert clarification["response_class"] == "structured_clarification"
    assert escalation["response_class"] == "structured_clarification"


def test_build_runtime_payload_keeps_non_structured_paths_in_conversational_answer():
    blocked_decision = type(
        "Decision",
        (),
        {
            "path": _EnumLike("blocked"),
            "result_form": _EnumLike("deterministic_result"),
            "stream_mode": "single_response",
            "interaction_class": "BLOCKED",
            "runtime_path": "BLOCKED_RESPONSE",
            "binding_level": "ORIENTATION",
            "has_case_state": False,
            "coverage_status": None,
            "boundary_flags": (),
            "escalation_reason": "policy_blocked",
            "required_fields": (),
        },
    )()
    payload = build_runtime_payload(
        blocked_decision,
        session_id="s4",
        reply="Nicht möglich",
        structured_state=None,
    )
    assert payload["response_class"] == "conversational_answer"


def test_structured_api_exposure_ignores_internal_snapshot_fields():
    from app.agent.agent.selection import build_structured_api_exposure

    selection_state = {
        "structured_snapshot_contract": {
            "case_status": "withheld_review",
            "output_status": "withheld_review",
            "primary_reason": "review_pending",
            "next_step": "human_review",
            "primary_allowed_action": "await_review",
            "active_blockers": ["review_pending"],
            "unexpected_internal_detail": "must_not_leak",
        }
    }

    exposure = build_structured_api_exposure(selection_state)
    assert exposure == {
        "case_status": "withheld_review",
        "output_status": "withheld_review",
        "next_step": "human_review",
        "primary_allowed_action": "await_review",
        "active_blockers": ["review_pending"],
    }


def test_structured_api_exposure_requires_explicit_snapshot_contract():
    from app.agent.agent.selection import build_structured_api_exposure

    selection_state = {
        "case_summary_projection": {
            "current_case_status": "withheld_review",
            "confirmed_core_fields": ["medium", "pressure", "temperature"],
            "missing_core_fields": [],
            "active_blockers": ["review_pending"],
            "next_step": "human_review",
        },
        "actionability_projection": {
            "actionability_status": "review_pending",
            "primary_allowed_action": "await_review",
            "blocked_actions": ["consume_governed_result"],
            "next_expected_user_action": "human_review",
        },
        "state_trace_audit_projection": {
            "primary_status_reason": "review_pending",
            "contributing_reasons": ["review_pending"],
            "blocking_reasons": ["review_pending"],
            "trace_flags": [],
        },
    }

    assert build_structured_api_exposure(selection_state) is None


def test_structured_api_exposure_can_fall_back_to_case_state_review_truth():
    from app.agent.agent.selection import build_structured_api_exposure

    exposure = build_structured_api_exposure(
        {},
        case_state={
            "governance_state": {
                "release_status": "manufacturer_validation_required",
                "rfq_admissibility": "provisional",
                "review_required": True,
            },
            "rfq_state": {
                "blocking_reasons": ["review_required"],
                "blockers": ["review_required"],
            },
        },
    )

    assert exposure == {
        "case_status": "withheld_review",
        "output_status": "withheld_review",
        "next_step": "human_review",
        "primary_allowed_action": "await_review",
        "active_blockers": ["review_pending", "review_required"],
    }
