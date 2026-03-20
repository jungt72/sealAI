import pytest
import asyncio
import copy
import json
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from app.agent.api.router import download_rfq_action, download_rfq_artifact, case_review_action, router, SESSION_STORE, chat_endpoint, event_generator
from app.agent.api.models import CaseActionRequest, CaseReviewRequest, ChatRequest
from app.agent.cli import create_initial_state
from app.agent.case_state import sync_case_state_to_state, sync_material_cycle_control
from app.agent.domain.rwdr import RWDRSelectorOutputDTO
from app.agent.material_core import PromotedCandidateRegistryRecordDTO
from langchain_core.messages import AIMessage, HumanMessage
from app.services.auth.dependencies import RequestUser

# Temporäre App für den Router-Test
app = FastAPI()
app.include_router(router)

@pytest.fixture(autouse=True)
def clear_sessions():
    """Löscht den Session Store vor jedem Test."""
    SESSION_STORE.clear()


def _structured_mock_state(*, messages, revision: int, rwdr_output: RWDRSelectorOutputDTO | None = None):
    sealing_state = create_initial_state()
    sealing_state["cycle"]["state_revision"] = revision
    sealing_state["cycle"]["analysis_cycle_id"] = f"session_test_{revision}"
    sealing_state["governance"]["release_status"] = "inadmissible"
    if rwdr_output is not None:
        sealing_state["rwdr"] = {"output": rwdr_output}
    return {
        "messages": messages,
        "sealing_state": sealing_state,
        "working_profile": {},
        "relevant_fact_cards": [],
    }


def test_chat_endpoint_transports_visible_case_narrative(current_user=None):
    request = ChatRequest(message="Bitte pruefen", session_id="case-1")
    current_user = current_user or RequestUser(
        user_id="user-1",
        username="tester",
        sub="user-1",
        roles=[],
        scopes=[],
        tenant_id="tenant-1",
    )
    state = _structured_mock_state(messages=[AIMessage(content="Antwort")], revision=2)

    with patch("app.agent.api.router.route_interaction") as route_mock, \
         patch("app.agent.api.router.prepare_structured_state", new=AsyncMock(return_value=state)), \
         patch("app.agent.api.router.execute_agent", new=AsyncMock(return_value=state)), \
         patch("app.agent.api.router.persist_structured_state", new=AsyncMock(return_value=None)):
        route_mock.return_value = type("Decision", (), {
            "has_case_state": True,
            "runtime_path": "STRUCTURED_QUALIFICATION",
            "binding_level": "QUALIFIED_PRESELECTION",
            "interaction_class": "structured_case",
        })()
        response = asyncio.run(chat_endpoint(request, current_user=current_user))

    assert response.visible_case_narrative is not None
    # 0B.2: governed_summary may carry a coverage prefix when policy signals are present
    assert "Aktuelle technische Richtung" in response.visible_case_narrative.governed_summary


def _qualified_material_action_state(*, revision: int = 3):
    sealing_state = create_initial_state()
    sealing_state["asserted"]["medium_profile"] = {"name": "Wasser", "resistance_rating": "A"}
    sealing_state["asserted"]["machine_profile"] = {"material": "PTFE"}
    sealing_state["asserted"]["operating_conditions"] = {"temperature": 120.0, "pressure": 10.0}
    sealing_state["normalized"]["identity_records"] = {
        "material_family": {
            "raw_value": "PTFE",
            "normalized_value": "PTFE",
            "identity_class": "identity_confirmed",
            "source_fact_ids": ["fc-qualified-1"],
        },
        "grade_name": {
            "raw_value": "G25",
            "normalized_value": "G25",
            "identity_class": "identity_confirmed",
            "source_fact_ids": ["fc-qualified-1"],
        },
        "manufacturer_name": {
            "raw_value": "Acme",
            "normalized_value": "Acme",
            "identity_class": "identity_confirmed",
            "source_fact_ids": ["fc-qualified-1"],
        },
    }
    sealing_state["governance"].update(
        {
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "compound_required",
            "gate_failures": [],
            "unknowns_release_blocking": [],
            "unknowns_manufacturer_validation": [],
            "conflicts": [],
        }
    )
    sealing_state["selection"] = {
        "selection_status": "winner_selected",
        "candidates": [
            {
                "candidate_id": "ptfe::g25::acme",
                "candidate_kind": "manufacturer_grade",
                "material_family": "PTFE",
                "grade_name": "G25",
                "manufacturer_name": "Acme",
                "evidence_refs": ["fc-qualified-1"],
                "viability_status": "viable",
                "block_reason": None,
            }
        ],
        "viable_candidate_ids": ["ptfe::g25::acme"],
        "qualified_candidate_ids": ["ptfe::g25::acme"],
        "exploratory_candidate_ids": [],
        "promoted_candidate_ids": ["ptfe::g25::acme"],
        "transition_candidate_ids": [],
        "blocked_candidates": [],
        "blocked_by_candidate_source": [],
        "winner_candidate_id": "ptfe::g25::acme",
        "candidate_source_adapter": "promoted_candidate_registry_provider_v1",
        "candidate_source_origin": "promoted_candidate_registry_v1",
        "candidate_source_origins": ["promoted_candidate_registry_v1"],
        "recommendation_artifact": {
            "selection_status": "winner_selected",
            "winner_candidate_id": "ptfe::g25::acme",
            "candidate_ids": ["ptfe::g25::acme"],
            "viable_candidate_ids": ["ptfe::g25::acme"],
            "blocked_candidates": [],
            "evidence_basis": ["fc-qualified-1"],
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "compound_required",
            "output_blocked": False,
            "trace_provenance_refs": ["fc-qualified-1", f"cycle-{revision}"],
        },
        "release_status": "rfq_ready",
        "rfq_admissibility": "ready",
        "specificity_level": "compound_required",
        "output_blocked": False,
    }
    sealing_state["cycle"].update(
        {
            "analysis_cycle_id": f"cycle-{revision}",
            "state_revision": revision,
            "contract_obsolete": False,
            "contract_obsolete_reason": None,
        }
    )
    state = {
        "messages": [AIMessage(content="Qualified material reply")],
        "sealing_state": sealing_state,
        "working_profile": {
            "diameter": 50.0,
            "speed": 1500.0,
            "pressure": 10.0,
            "temperature": 120.0,
            "medium": "Wasser",
            "material": "PTFE",
            "v_m_s": 3.927,
            "pv_value": 39.27,
        },
        "relevant_fact_cards": [
            {
                "id": "fc-qualified-1",
                "evidence_id": "fc-qualified-1",
                "topic": "PTFE G25 Acme datasheet",
                "content": "PTFE grade G25 from Acme has a temperature limit up to 260 C and a maximum pressure of 50 bar.",
                "source_ref": "datasheet-acme-g25",
                "source_type": "manufacturer_datasheet",
                "source_rank": 1,
                "metadata": {
                    "material_family": "PTFE",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                    "temperature_min_c": -20,
                    "temperature_max_c": 260,
                    "pressure_max_bar": 50,
                },
            }
        ],
    }
    state = sync_material_cycle_control(state)
    return sync_case_state_to_state(
        state,
        session_id="qualified-action-case",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="QUALIFIED_PRESELECTION",
    )


def _exploratory_material_action_state(*, revision: int = 3):
    sealing_state = create_initial_state()
    sealing_state["asserted"]["medium_profile"] = {"name": "Wasser", "resistance_rating": "A"}
    sealing_state["asserted"]["machine_profile"] = {"material": "PTFE"}
    sealing_state["asserted"]["operating_conditions"] = {"temperature": 120.0, "pressure": 10.0}
    sealing_state["normalized"]["identity_records"] = {
        "material_family": {
            "raw_value": "PTFE",
            "normalized_value": "PTFE",
            "identity_class": "identity_confirmed",
            "source_fact_ids": ["fc-1"],
        },
    }
    sealing_state["governance"].update(
        {
            "release_status": "manufacturer_validation_required",
            "rfq_admissibility": "provisional",
            "specificity_level": "subfamily",
            "gate_failures": [],
            "unknowns_release_blocking": [],
            "unknowns_manufacturer_validation": ["manufacturer_name_unconfirmed_for_compound"],
            "conflicts": [],
        }
    )
    sealing_state["selection"] = {
        "selection_status": "winner_selected",
        "candidates": [
            {
                "candidate_id": "ptfe",
                "candidate_kind": "family",
                "material_family": "PTFE",
                "evidence_refs": ["fc-1"],
                "viability_status": "viable",
                "block_reason": None,
            }
        ],
        "viable_candidate_ids": ["ptfe"],
        "qualified_candidate_ids": [],
        "exploratory_candidate_ids": ["ptfe"],
        "promoted_candidate_ids": [],
        "transition_candidate_ids": ["ptfe"],
        "blocked_candidates": [],
        "blocked_by_candidate_source": [],
        "winner_candidate_id": "ptfe",
        "direction_authority": "evidence_oriented",
        "candidate_source_adapter": "material_candidate_source_adapter_v1",
        "candidate_source_origin": "retrieval_fact_card_transition_adapter",
        "candidate_source_origins": ["retrieval_fact_card_transition_adapter"],
        "recommendation_artifact": {
            "selection_status": "winner_selected",
            "winner_candidate_id": "ptfe",
            "candidate_ids": ["ptfe"],
            "viable_candidate_ids": ["ptfe"],
            "blocked_candidates": [],
            "evidence_basis": ["fc-1"],
            "release_status": "manufacturer_validation_required",
            "rfq_admissibility": "provisional",
            "specificity_level": "subfamily",
            "output_blocked": True,
            "trace_provenance_refs": ["fc-1", f"cycle-{revision}"],
        },
        "release_status": "manufacturer_validation_required",
        "rfq_admissibility": "provisional",
        "specificity_level": "subfamily",
        "output_blocked": True,
    }
    sealing_state["cycle"].update(
        {
            "analysis_cycle_id": f"cycle-{revision}",
            "state_revision": revision,
            "contract_obsolete": False,
            "contract_obsolete_reason": None,
        }
    )
    state = {
        "messages": [AIMessage(content="Exploratory material reply")],
        "sealing_state": sealing_state,
        "working_profile": {
            "diameter": 50.0,
            "speed": 1500.0,
            "pressure": 10.0,
            "temperature": 120.0,
            "medium": "Wasser",
            "material": "PTFE",
            "v_m_s": 3.927,
            "pv_value": 39.27,
        },
        "relevant_fact_cards": [
            {
                "id": "fc-1",
                "evidence_id": "fc-1",
                "topic": "PTFE datasheet",
                "content": "PTFE has a temperature limit up to 260 C and a maximum pressure of 50 bar.",
                "source_ref": "datasheet-ptfe-1",
                "metadata": {
                    "material_family": "PTFE",
                    "temperature_min_c": -20,
                    "temperature_max_c": 260,
                    "pressure_max_bar": 50,
                },
            }
        ],
    }
    state = sync_material_cycle_control(state)
    state = sync_case_state_to_state(
        state,
        session_id="exploratory-action-case",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="QUALIFIED_PRESELECTION",
    )
    state["case_state"]["qualified_action_gate"] = {
        "action": "download_rfq",
        "allowed": True,
        "rfq_ready": True,
        "binding_level": "RFQ_BASIS",
        "source_type": "legacy",
        "source_ref": "legacy",
        "block_reasons": [],
        "summary": "legacy_ready",
    }
    return state


@pytest.fixture()
def agent_request_user():
    return RequestUser(
        user_id="user-test",
        username="tester",
        sub="user-test",
        roles=[],
        scopes=[],
        tenant_id="tenant-test",
    )


@pytest.fixture(autouse=True)
def fake_structured_case_store(monkeypatch):
    # A5: Store key is (tenant_id, owner_id, case_id) — tenant-complete.
    store = {}

    async def _fake_load_structured_case(*, tenant_id: str, owner_id: str, case_id: str):
        state = store.get((tenant_id, owner_id, case_id))
        return copy.deepcopy(state) if state is not None else None

    async def _fake_save_structured_case(*, tenant_id: str, owner_id: str, case_id: str, state, runtime_path: str, binding_level: str):
        store[(tenant_id, owner_id, case_id)] = copy.deepcopy(state)

    monkeypatch.setattr("app.agent.api.router.load_structured_case", _fake_load_structured_case)
    monkeypatch.setattr("app.agent.api.router.save_structured_case", _fake_save_structured_case)
    yield store

def test_api_chat_endpoint_success(agent_request_user):
    """
    Test Phase F2:
    Verifiziert den POST /chat Endpunkt mit einem gemockten Fast-Knowledge-Pfad.
    "Hallo Agent" routes to FAST_KNOWLEDGE (direct path) — result_form="direct".
    """
    from app.agent.runtime import RuntimeExecutionResult

    mock_fast_result = RuntimeExecutionResult(reply="Hallo! Wie kann ich helfen?", working_profile=None)

    with patch("app.agent.api.router.execute_fast_knowledge", new=AsyncMock(return_value=mock_fast_result)):
        response = asyncio.run(
            chat_endpoint(
                ChatRequest(message="Hallo Agent", session_id="test_session"),
                current_user=agent_request_user,
            )
        )

        # "Hallo Agent" is a conversational opening → FAST_KNOWLEDGE, direct path.
        # Direct responses carry orientation semantics — no result_contract, no qualified_action_gate.
        data = response.model_dump()

        assert data["reply"] == "Hallo! Wie kann ich helfen?"
        assert data["session_id"] == "test_session"
        assert data["result_form"] == "direct"
        assert data["binding_level"] == "KNOWLEDGE"
        assert data["rfq_ready"] is False
        assert data["case_state"] is None
        assert data["result_contract"] is None
        assert data["qualified_action_gate"] is None
        assert data["visible_case_narrative"] is not None

def test_api_session_persistence(agent_request_user):
    """
    Test Phase F2:
    Verifiziert, dass der Session-Store Nachrichten akkumuliert.
    """
    session_id = "persistence_test"
    
    # Erste Anfrage
    mock_state_1 = _structured_mock_state(
        messages=[HumanMessage(content="Erste Nachricht"), AIMessage(content="Verstanden.")],
        revision=1,
    )
    
    with patch("app.agent.api.router.execute_agent", new=AsyncMock(return_value=mock_state_1)):
        asyncio.run(
            chat_endpoint(
                ChatRequest(message="Erste Nachricht", session_id=session_id),
                current_user=agent_request_user,
            )
        )
    
    # Prüfen, ob Session existiert (A5: key is tenant-complete)
    cache_key = f"{agent_request_user.tenant_id}:{agent_request_user.user_id}:{session_id}"
    assert cache_key in SESSION_STORE
    assert len(SESSION_STORE[cache_key]["messages"]) == 2
    
    # Zweite Anfrage
    mock_state_2 = _structured_mock_state(
        messages=[
            HumanMessage(content="Erste Nachricht"),
            AIMessage(content="Verstanden."),
            HumanMessage(content="Zweite Nachricht"),
            AIMessage(content="Fortgesetzt."),
        ],
        revision=2,
    )
    
    with patch("app.agent.api.router.execute_agent", new=AsyncMock(return_value=mock_state_2)):
        response = asyncio.run(
            chat_endpoint(
                ChatRequest(message="Zweite Nachricht", session_id=session_id),
                current_user=agent_request_user,
            )
        )
    
    assert response.reply == "Fortgesetzt."
    assert len(SESSION_STORE[cache_key]["messages"]) == 4

def test_api_chat_empty_message():
    """
    Test Phase F2:
    Leere Nachrichten werden bereits auf Pydantic-Ebene (F1) abgelehnt.
    """
    with pytest.raises(ValidationError):
        ChatRequest(message="")


def test_create_initial_state_has_structured_governed_output_defaults():
    sealing_state = create_initial_state()

    assert sealing_state["asserted"]["sealing_requirement_spec"]["contract_version"] == "sealing_requirement_spec_v1"
    assert sealing_state["result_contract"]["analysis_cycle_id"] == "session_init_1"
    assert sealing_state["selection"]["candidate_clusters"] == []

def test_api_chat_stream_endpoint(agent_request_user):
    """
    Test Phase F3:
    Verifiziert den Streaming-Endpunkt /chat/stream.
    """
    session_id = "stream_test"
    
    # Asynchroner Mock für astream_events
    async def mock_astream_events(state, version):
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": AIMessage(content="Stream")}
        }
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": AIMessage(content="ing")}
        }
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {
                **_structured_mock_state(
                    messages=state["messages"] + [AIMessage(content="Streaming")],
                    revision=10,
                ),
            }}
        }

    class _MockGraph:
        def astream_events(self, state, version="v2"):
            return mock_astream_events(state, version)

    with patch("app.agent.api.router.get_agent_graph", return_value=_MockGraph()):
        chunks = []
        async def _collect():
            async for chunk in event_generator(
                ChatRequest(message="Starte Stream", session_id=session_id),
                current_user=agent_request_user,
            ):
                chunks.append(chunk)

        asyncio.run(_collect())
        content = "".join(chunks)

        assert "Stream" in content
        assert "ing" in content
        assert "state" in content
        assert "10" in content
        assert "[DONE]" in content


def test_api_chat_stream_endpoint_projects_rwdr_payload(agent_request_user):
    session_id = "stream_rwdr_test"
    # 0A.3: Pre-seed SESSION_STORE with asserted medium so the policy routes to
    # qualified for "RWDR Stream" (qualification keyword + asserted state basis).
    SESSION_STORE[f"{agent_request_user.tenant_id}:{agent_request_user.user_id}:{session_id}"] = {
        "sealing_state": {
            "asserted": {"medium_profile": {"name": "Wasser"}, "operating_conditions": {}},
            "governance": {"unknowns_release_blocking": []},
        },
        "messages": [],
        "working_profile": {},
        "relevant_fact_cards": [],
        "tenant_id": "tenant-test",
        "owner_id": agent_request_user.user_id,
    }

    mock_rwdr_output = RWDRSelectorOutputDTO(
        type_class="engineering_review_required",
        modifiers=[],
        warnings=[],
        review_flags=["review_water_with_pressure"],
        hard_stop=None,
        reasoning=["Projected in SSE payload."],
    )

    async def mock_astream_events(state, version):
        del version
        structured_output = _structured_mock_state(
            messages=state["messages"] + [AIMessage(content="RWDR streaming")],
            revision=11,
            rwdr_output=mock_rwdr_output,
        )
        structured_output["sealing_state"]["rwdr"]["flow"] = {
            "active": True,
            "stage": "stage_2",
            "missing_fields": ["available_width_mm"],
            "next_field": "available_width_mm",
            "ready_for_decision": False,
            "decision_executed": False,
        }
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": structured_output}
        }

    class _MockGraph:
        def astream_events(self, state, version="v2"):
            return mock_astream_events(state, version)

    with patch("app.agent.api.router.get_agent_graph", return_value=_MockGraph()):
        chunks = []

        async def _collect():
            async for chunk in event_generator(
                ChatRequest(message="RWDR Stream", session_id=session_id),
                current_user=agent_request_user,
            ):
                chunks.append(chunk)

        asyncio.run(_collect())
        content = "".join(chunks)

        assert "\"rwdr\"" in content
        assert "\"stage_2\"" in content
        assert "\"rwdr_output\"" in content
        assert "\"engineering_review_required\"" in content


def test_api_chat_endpoint_transports_structured_rwdr_output(agent_request_user):
    # 0A.3: Pre-seed SESSION_STORE with asserted medium so the policy routes to
    # qualified for "RWDR" (qualification keyword + asserted state basis).
    SESSION_STORE[f"{agent_request_user.tenant_id}:{agent_request_user.user_id}:rwdr_session"] = {
        "sealing_state": {
            "asserted": {"medium_profile": {"name": "Wasser"}, "operating_conditions": {}},
            "governance": {"unknowns_release_blocking": []},
        },
        "messages": [],
        "working_profile": {},
        "relevant_fact_cards": [],
        "tenant_id": "tenant-test",
        "owner_id": agent_request_user.user_id,
    }
    mock_updated_state = _structured_mock_state(
        messages=[
            HumanMessage(content="RWDR"),
            AIMessage(content="RWDR preselection ready."),
        ],
        revision=2,
        rwdr_output=RWDRSelectorOutputDTO(
            type_class="standard_rwdr",
            modifiers=[],
            warnings=[],
            review_flags=[],
            hard_stop=None,
            reasoning=["Deterministic RWDR output attached to chat response."],
        ),
    )

    with patch("app.agent.api.router.execute_agent", new=AsyncMock(return_value=mock_updated_state)):
        response = asyncio.run(
            chat_endpoint(
                ChatRequest(message="RWDR", session_id="rwdr_session"),
                current_user=agent_request_user,
            )
        )

    assert response.rwdr_output is not None
    assert response.rwdr_output.type_class == "standard_rwdr"


def test_allowed_promoted_fresh_case_executes_rfq_action_successfully(fake_structured_case_store, agent_request_user, monkeypatch):
    # 0B.1: re-evaluation during load_and_refresh_structured_case requires a governed registry entry
    monkeypatch.setattr(
        "app.agent.material_core.load_promoted_candidate_registry_records",
        lambda: (PromotedCandidateRegistryRecordDTO(
            registry_record_id="registry-ptfe-g25-acme",
            material_family="PTFE", grade_name="G25", manufacturer_name="Acme",
            promotion_state="promoted", registry_authority="governed",
            source_refs=["registry:ptfe:g25:acme"], evidence_refs=[],
        ),),
    )
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "rfq-case-1")] = _qualified_material_action_state()

    response = asyncio.run(
        download_rfq_action(
            "rfq-case-1",
            CaseActionRequest(action="download_rfq"),
            current_user=agent_request_user,
        )
    )

    payload = response.model_dump()
    assert payload["allowed"] is True
    assert payload["executed"] is True
    assert payload["block_reasons"] == []
    assert payload["result_contract"]["release_status"] == "rfq_ready"
    assert payload["result_contract"]["qualified_action"]["summary"] == "qualified_action_enabled"
    spec = payload["action_payload"]["sealing_requirement_spec"]
    artifact = payload["action_payload"]["render_artifact"]
    assert payload["action_payload"]["contract_version"] == "sealing_requirement_spec_v1"
    assert payload["action_payload"]["rendering_status"] == "rendered"
    assert payload["action_payload"]["message"] == spec["rendering_message"]
    assert payload["case_state"]["sealing_requirement_spec"] == spec
    assert payload["case_state"]["candidate_clusters"] == spec["candidate_clusters"]
    # _advance_case_state_only_revision stamps a compound cycle id on action writes
    assert spec["analysis_cycle_id"].startswith("cycle-3::")
    assert spec["state_revision"] == 4
    assert spec["binding_level"] == "RFQ_BASIS"
    assert spec["release_status"] == "rfq_ready"
    assert spec["rfq_admissibility"] == "ready"
    assert spec["specificity_level"] == "compound_required"
    assert spec["contract_obsolete"] is False
    assert spec["qualified_action"]["summary"] == "qualified_action_enabled"
    assert spec["selection_snapshot"]["winner_candidate_id"] == "ptfe::g25::acme"
    assert spec["selection_snapshot"]["material_direction_contract"] == {
        "authority_layer": "governed_authority",
        "direction_layer": "governed_direction",
        "source_provenance": "promoted_candidate_registry_v1",
    }
    assert [cluster["cluster_key"] for cluster in spec["candidate_clusters"]] == [
        "selected",
        "qualified_viable",
        "viable",
    ]
    assert spec["candidate_clusters"][0]["candidate_ids"] == ["ptfe::g25::acme"]
    assert spec["candidate_clusters"][0]["material_direction_contract"] == {
        "authority_layer": "governed_authority",
        "direction_layer": "governed_direction",
        "source_provenance": "promoted_candidate_registry_v1",
    }
    assert spec["render_artifact"] == artifact
    assert artifact["artifact_type"] == "sealing_requirement_spec_markdown"
    assert artifact["artifact_version"] == "sealing_requirement_spec_render_v1"
    assert artifact["mime_type"] == "text/markdown"
    assert artifact["filename"] == "sealing-requirement-spec-cycle-3.md"
    assert "# Sealing Requirement Spec" in artifact["content"]
    assert "- Winner Candidate ID: ptfe::g25::acme" in artifact["content"]
    assert artifact["source_ref"] == "case_state.rendered_sealing_requirement_spec"
    assert payload["case_state"]["qualified_action_status"]["last_status"] == "executed"
    assert payload["case_state"]["qualified_action_status"]["executed"] is True
    assert payload["case_state"]["qualified_action_status"]["current_gate_allows_action"] is True
    assert payload["case_state"]["qualified_action_status"]["artifact_provenance"] == {
        "artifact_type": "sealing_requirement_spec_markdown",
        "artifact_version": "sealing_requirement_spec_render_v1",
        "filename": "sealing-requirement-spec-cycle-3.md",
        "mime_type": "text/markdown",
        "source_ref": "case_state.rendered_sealing_requirement_spec",
    }
    assert payload["case_state"]["qualified_action_history"][0]["artifact_provenance"] == payload["case_state"]["qualified_action_status"]["artifact_provenance"]
    assert payload["case_state"]["qualified_action_history"][0]["last_status"] == "executed"
    assert payload["audit_event"]["event_type"] == "qualified_action"
    assert payload["audit_event"]["details"]["status"] == "executed"


def test_allowed_promoted_fresh_case_downloads_render_artifact(fake_structured_case_store, agent_request_user, monkeypatch):
    # 0B.1: re-evaluation during load_and_refresh_structured_case requires a governed registry entry
    monkeypatch.setattr(
        "app.agent.material_core.load_promoted_candidate_registry_records",
        lambda: (PromotedCandidateRegistryRecordDTO(
            registry_record_id="registry-ptfe-g25-acme",
            material_family="PTFE", grade_name="G25", manufacturer_name="Acme",
            promotion_state="promoted", registry_authority="governed",
            source_refs=["registry:ptfe:g25:acme"], evidence_refs=[],
        ),),
    )
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "rfq-case-1-artifact")] = _qualified_material_action_state()

    response = asyncio.run(
        download_rfq_artifact(
            "rfq-case-1-artifact",
            current_user=agent_request_user,
        )
    )

    assert response.media_type == "text/markdown"
    assert response.headers["content-disposition"] == 'attachment; filename="sealing-requirement-spec-cycle-3.md"'
    assert response.body.decode("utf-8").startswith("# Sealing Requirement Spec")
    assert "- Winner Candidate ID: ptfe::g25::acme" in response.body.decode("utf-8")
    saved_state = fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "rfq-case-1-artifact")]
    status = saved_state["case_state"]["qualified_action_status"]
    assert status["action"] == "download_rfq"
    assert status["last_status"] == "executed"
    assert status["executed"] is True
    assert status["source_ref"] == "api.agent.actions.download_rfq_artifact"
    assert status["artifact_provenance"] == {
        "artifact_type": "sealing_requirement_spec_markdown",
        "artifact_version": "sealing_requirement_spec_render_v1",
        "filename": "sealing-requirement-spec-cycle-3.md",
        "mime_type": "text/markdown",
        "source_ref": "case_state.rendered_sealing_requirement_spec",
    }
    assert saved_state["case_state"]["qualified_action_history"][0] == status
    assert saved_state["case_state"]["audit_trail"][-1]["event_type"] == "qualified_action"
    assert saved_state["case_state"]["audit_trail"][-1]["details"]["status"] == "executed"


def test_exploratory_case_is_blocked_server_side(fake_structured_case_store, agent_request_user):
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "rfq-case-2")] = _exploratory_material_action_state()

    response = asyncio.run(
        download_rfq_action(
            "rfq-case-2",
            CaseActionRequest(action="download_rfq"),
            current_user=agent_request_user,
        )
    )

    payload = response.model_dump()
    assert payload["allowed"] is False
    assert payload["executed"] is False
    assert "exploratory_candidate_source_only" in payload["block_reasons"]
    assert payload["case_state"]["sealing_requirement_spec"]["selection_snapshot"]["material_direction_contract"] == {
        "authority_layer": "not_trust_granting",
        "direction_layer": "evidence_oriented_direction",
        "source_provenance": "retrieval_fact_card_transition_adapter",
    }
    assert payload["case_state"]["qualified_action_status"]["last_status"] == "blocked"
    assert payload["case_state"]["qualified_action_status"]["block_reasons"] == payload["block_reasons"]
    assert payload["case_state"]["qualified_action_history"][0]["last_status"] == "blocked"
    assert payload["audit_event"]["event_type"] == "qualified_action"
    assert payload["audit_event"]["details"]["status"] == "blocked"


def test_blocked_case_cannot_download_render_artifact(fake_structured_case_store, agent_request_user):
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "rfq-case-2-artifact")] = _exploratory_material_action_state()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            download_rfq_artifact(
                "rfq-case-2-artifact",
                current_user=agent_request_user,
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "rfq_action_blocked"
    assert "exploratory_candidate_source_only" in exc_info.value.detail["block_reasons"]
    saved_state = fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "rfq-case-2-artifact")]
    status = saved_state["case_state"]["qualified_action_status"]
    assert status["action"] == "download_rfq"
    assert status["last_status"] == "blocked"
    assert status["executed"] is False
    assert status["source_ref"] == "api.agent.actions.download_rfq_artifact"
    assert status["artifact_provenance"] is None
    assert saved_state["case_state"]["qualified_action_history"][0] == status
    assert saved_state["case_state"]["audit_trail"][-1]["event_type"] == "qualified_action"
    assert saved_state["case_state"]["audit_trail"][-1]["details"]["status"] == "blocked"


def test_stale_requires_recompute_case_is_blocked_server_side(fake_structured_case_store, agent_request_user, monkeypatch):
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "rfq-case-3")] = _qualified_material_action_state()
    monkeypatch.setattr(
        "app.agent.material_core.load_promoted_candidate_registry_records",
        lambda: (
            PromotedCandidateRegistryRecordDTO(
                registry_record_id="registry-ptfe-g25-acme",
                material_family="PTFE",
                grade_name="G25",
                manufacturer_name="Acme",
                source_refs=["registry:ptfe:g25:acme:v2"],
                evidence_refs=[],
            ),
        ),
    )

    response = asyncio.run(
        download_rfq_action(
            "rfq-case-3",
            CaseActionRequest(action="download_rfq"),
            current_user=agent_request_user,
        )
    )

    payload = response.model_dump()
    assert payload["allowed"] is False
    assert payload["executed"] is False
    assert "requires_recompute" in payload["block_reasons"]


def test_cross_user_access_to_another_case_is_not_found(fake_structured_case_store, agent_request_user):
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "rfq-case-4")] = _qualified_material_action_state()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            download_rfq_action(
                "rfq-case-4",
                CaseActionRequest(action="download_rfq"),
                current_user=RequestUser(
                    user_id="user-other",
                    username="other",
                    sub="user-other",
                    roles=[],
                    scopes=[],
                    tenant_id="tenant-other",
                ),
            )
        )

    assert exc_info.value.status_code == 404


def test_legacy_rfq_ready_does_not_bypass_server_side_gate(fake_structured_case_store, agent_request_user):
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "rfq-case-5")] = _exploratory_material_action_state()

    response = asyncio.run(
        download_rfq_action(
            "rfq-case-5",
            CaseActionRequest(action="download_rfq"),
            current_user=agent_request_user,
        )
    )

    payload = response.model_dump()
    assert payload["allowed"] is False
    assert payload["qualified_action_gate"]["allowed"] is False
    assert payload["case_state"]["qualified_action_status"]["last_status"] == "blocked"


def test_blocked_rfq_gate_keeps_visible_handover_prequalified_in_action_response(fake_structured_case_store, agent_request_user):
    state = _exploratory_material_action_state()
    state["sealing_state"]["governance"]["release_status"] = "rfq_ready"
    state["sealing_state"]["governance"]["rfq_admissibility"] = "ready"
    state["sealing_state"]["selection"]["release_status"] = "rfq_ready"
    state["sealing_state"]["selection"]["rfq_admissibility"] = "ready"
    state["sealing_state"]["selection"]["recommendation_artifact"]["release_status"] = "rfq_ready"
    state["sealing_state"]["selection"]["recommendation_artifact"]["rfq_admissibility"] = "ready"
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "rfq-case-5-visible")] = state

    response = asyncio.run(
        download_rfq_action(
            "rfq-case-5-visible",
            CaseActionRequest(action="download_rfq"),
            current_user=agent_request_user,
        )
    )

    payload = response.model_dump()
    governed_summary = str(payload["visible_case_narrative"]["governed_summary"])
    authority_item = next(
        item for item in payload["visible_case_narrative"]["technical_direction"]
        if item["key"] == "technical_direction_authority"
    )
    assert payload["allowed"] is False
    assert payload["qualified_action_gate"]["allowed"] is False
    assert payload["binding_level"] == "QUALIFIED_PRESELECTION"
    assert payload["result_contract"]["rfq_admissibility"] == "ready"
    assert "Handover-Status: Prequalified." in governed_summary
    assert "Handover-Status: RFQ ready." not in governed_summary
    assert "Autoritaet: Evidence-oriented direction." in governed_summary
    assert authority_item["value"] == "Evidence-oriented direction"


def test_qualified_action_status_matches_newest_history_entry(fake_structured_case_store, agent_request_user):
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "rfq-case-6")] = _qualified_material_action_state()

    response = asyncio.run(
        download_rfq_action(
            "rfq-case-6",
            CaseActionRequest(action="download_rfq"),
            current_user=agent_request_user,
        )
    )

    case_state = response.model_dump()["case_state"]
    assert case_state["qualified_action_status"] == case_state["qualified_action_history"][0]


def test_history_is_server_side_bounded_and_trims_old_entries(fake_structured_case_store, agent_request_user, monkeypatch):
    # 0B.1: re-evaluation during load_and_refresh_structured_case requires a governed registry entry
    monkeypatch.setattr(
        "app.agent.material_core.load_promoted_candidate_registry_records",
        lambda: (PromotedCandidateRegistryRecordDTO(
            registry_record_id="registry-ptfe-g25-acme",
            material_family="PTFE", grade_name="G25", manufacturer_name="Acme",
            promotion_state="promoted", registry_authority="governed",
            source_refs=["registry:ptfe:g25:acme"], evidence_refs=[],
        ),),
    )
    state = _qualified_material_action_state()
    history = []
    for index in range(6):
        history.append(
            {
                "action": "download_rfq",
                "last_status": "blocked",
                "allowed_at_execution_time": False,
                "executed": False,
                "block_reasons": [f"reason-{index}"],
                "timestamp": f"2026-03-13T00:00:0{index}+00:00",
                "binding_level": "QUALIFIED_PRESELECTION",
                "runtime_path": "STRUCTURED_QUALIFICATION",
                "source_ref": "api.agent.actions.download_rfq_action",
                "action_payload_stub": None,
                "current_gate_allows_action": False,
            }
        )
    state["case_state"]["qualified_action_history"] = history
    state["case_state"]["qualified_action_status"] = history[0]
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "rfq-case-7")] = state

    response = asyncio.run(
        download_rfq_action(
            "rfq-case-7",
            CaseActionRequest(action="download_rfq"),
            current_user=agent_request_user,
        )
    )

    saved_history = response.model_dump()["case_state"]["qualified_action_history"]
    assert len(saved_history) == 5
    assert saved_history[0]["last_status"] == "executed"
    assert saved_history[-1]["block_reasons"] == ["reason-3"]


def test_fast_path_cannot_accidentally_execute_structured_rfq_action(agent_request_user):
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            download_rfq_action(
                "fast-only-case",
                CaseActionRequest(action="download_rfq"),
                current_user=agent_request_user,
            )
        )

    assert exc_info.value.status_code == 404


def test_event_generator_final_payload_includes_complete_visible_case_narrative_atomically(agent_request_user):
    """
    Transport-Contract: case_state und visible_case_narrative werden im SELBEN SSE-Chunk
    gesendet (build_runtime_payload → json.dumps → single yield). React 18 Batching
    greift nur, wenn beide im gleichen onmessage-Callback ankommen.
    Absicherung von: Mixed-Path / Partial-Narrative / Stream-Atomizitäts-Contract.

    0A.3: Pre-seed SESSION_STORE with asserted medium so the message "Empfehle ein Material"
    routes to qualified path (qualification keyword + asserted state basis). The qualified
    path includes case_state in the final SSE payload.
    """
    session_id = "stream_narrative_atomicity_test"
    SESSION_STORE[f"{agent_request_user.tenant_id}:{agent_request_user.user_id}:{session_id}"] = {
        "sealing_state": {
            "asserted": {"medium_profile": {"name": "Wasser"}, "operating_conditions": {}},
            "governance": {"unknowns_release_blocking": []},
        },
        "messages": [],
        "working_profile": {},
        "relevant_fact_cards": [],
        "tenant_id": "tenant-test",
        "owner_id": agent_request_user.user_id,
    }

    async def mock_astream_events(state, version):
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": AIMessage(content="Antwort")}
        }
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {
                **_structured_mock_state(
                    messages=state["messages"] + [AIMessage(content="Narrative-Antwort")],
                    revision=5,
                ),
            }}
        }

    class _MockGraph:
        def astream_events(self, state, version="v2"):
            return mock_astream_events(state, version)

    with patch("app.agent.api.router.get_agent_graph", return_value=_MockGraph()):
        chunks = []

        async def _collect():
            async for chunk in event_generator(
                # 0A.3: Use qualification message so qualified path runs and case_state
                # appears in the final SSE payload (atomicity contract for qualified path).
                ChatRequest(message="Empfehle ein Material", session_id=session_id),
                current_user=agent_request_user,
            ):
                chunks.append(chunk)

        asyncio.run(_collect())

    # Finde den Chunk mit case_state (finaler Payload, nicht Token-Chunks)
    final_payload = None
    for chunk in chunks:
        if chunk.startswith("data: ") and "case_state" in chunk:
            raw = chunk[len("data: "):].strip()
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and "case_state" in parsed:
                    final_payload = parsed
                    break
            except (json.JSONDecodeError, ValueError):
                continue

    assert final_payload is not None, "Kein SSE-Chunk mit case_state gefunden"

    # Atomizitäts-Contract: visible_case_narrative muss im GLEICHEN Chunk sein
    assert "visible_case_narrative" in final_payload, (
        "visible_case_narrative muss im selben SSE-Chunk wie case_state liegen — "
        "React 18 Batching gilt nur wenn beide im gleichen onmessage-Callback ankommen"
    )

    vcn = final_payload["visible_case_narrative"]
    assert vcn is not None, "visible_case_narrative darf nicht None sein im finalen Payload"

    _REQUIRED_KEYS = {
        "governed_summary", "technical_direction", "validity_envelope",
        "failure_analysis", "next_best_inputs", "suggested_next_questions",
        "case_summary", "qualification_status",
    }
    missing = _REQUIRED_KEYS - set(vcn.keys())
    assert not missing, f"visible_case_narrative fehlen strukturell erforderliche Keys: {missing}"

    assert isinstance(vcn["qualification_status"], list) and len(vcn["qualification_status"]) > 0, (
        "qualification_status muss nicht-leere Liste sein — Backend garantiert hard_stops/review_cases/missing_critical_summary"
    )
    assert isinstance(vcn["case_summary"], list) and len(vcn["case_summary"]) > 0, (
        "case_summary muss nicht-leere Liste sein — Backend garantiert resume_readiness"
    )


def test_download_rfq_action_response_includes_complete_visible_case_narrative(fake_structured_case_store, agent_request_user):
    """
    Transport-Contract: download_rfq_action liefert visible_case_narrative vollständig
    im CaseActionResponse. Frontend-seitig benötigt applyExternalCaseState beide Felder
    im selben Payload-Objekt — kein separater Fetch, kein Drift möglich.
    """
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "rfq-narrative-vcn-case")] = _qualified_material_action_state()

    response = asyncio.run(
        download_rfq_action(
            "rfq-narrative-vcn-case",
            CaseActionRequest(action="download_rfq"),
            current_user=agent_request_user,
        )
    )

    assert response.visible_case_narrative is not None, (
        "download_rfq_action muss visible_case_narrative im CaseActionResponse enthalten"
    )

    vcn = response.visible_case_narrative.model_dump()
    _REQUIRED_KEYS = {
        "governed_summary", "technical_direction", "validity_envelope",
        "failure_analysis", "next_best_inputs", "suggested_next_questions",
        "case_summary", "qualification_status",
    }
    missing = _REQUIRED_KEYS - set(vcn.keys())
    assert not missing, f"visible_case_narrative im Action-Response fehlen Keys: {missing}"

    assert isinstance(vcn["qualification_status"], list) and len(vcn["qualification_status"]) > 0
    assert isinstance(vcn["case_summary"], list) and len(vcn["case_summary"]) > 0


# ── A5: Tenant-boundary tests for persistence, session/cache, and action paths ──

def test_cross_tenant_access_to_case_is_not_found(fake_structured_case_store, agent_request_user):
    """A5: A user on tenant-B cannot access a case belonging to tenant-A, even with the
    same user_id. The storage key is tenant-scoped so the lookup structurally fails."""
    # Seed under the legitimate user's tenant
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "a5-tenant-case")] = _qualified_material_action_state()

    cross_tenant_user = RequestUser(
        user_id=agent_request_user.user_id,  # same user_id, different tenant
        username="same-user-other-tenant",
        sub=agent_request_user.user_id,
        roles=[],
        scopes=[],
        tenant_id="tenant-intruder",
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            download_rfq_action(
                "a5-tenant-case",
                CaseActionRequest(action="download_rfq"),
                current_user=cross_tenant_user,
            )
        )

    assert exc_info.value.status_code == 404


def test_session_cache_key_is_tenant_scoped(agent_request_user):
    """A5: Two users with identical user_id but different tenant_id must produce
    different SESSION_STORE keys. No cross-tenant cache collision is possible."""
    from app.agent.api.router import _case_cache_key

    user_a = RequestUser(
        user_id="shared-sub-42", username="u", sub="shared-sub-42",
        roles=[], scopes=[], tenant_id="tenant-alpha",
    )
    user_b = RequestUser(
        user_id="shared-sub-42", username="u", sub="shared-sub-42",
        roles=[], scopes=[], tenant_id="tenant-beta",
    )

    key_a = _case_cache_key(user_a.tenant_id or user_a.user_id, user_a.user_id, "same-case")
    key_b = _case_cache_key(user_b.tenant_id or user_b.user_id, user_b.user_id, "same-case")

    assert key_a != key_b, "Tenant-A and Tenant-B must never share a SESSION_STORE key"
    assert "tenant-alpha" in key_a
    assert "tenant-beta" in key_b


def test_rfq_action_cross_tenant_is_not_found(fake_structured_case_store, agent_request_user):
    """A5: download_rfq_action must respect the same tenant boundary as normal case load."""
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "a5-rfq-tenant-case")] = _qualified_material_action_state()

    intruder = RequestUser(
        user_id=agent_request_user.user_id,
        username="intruder",
        sub=agent_request_user.user_id,
        roles=[],
        scopes=[],
        tenant_id="tenant-evil",
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            download_rfq_action(
                "a5-rfq-tenant-case",
                CaseActionRequest(action="download_rfq"),
                current_user=intruder,
            )
        )

    assert exc_info.value.status_code == 404


def test_review_action_cross_tenant_is_not_found(fake_structured_case_store, agent_request_user):
    """A5: case_review_action must respect the same tenant boundary as all other case paths."""
    state = _qualified_material_action_state(revision=3)
    state["case_state"]["case_meta"]["review_required"] = True
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "a5-review-tenant-case")] = state

    intruder = RequestUser(
        user_id=agent_request_user.user_id,
        username="intruder",
        sub=agent_request_user.user_id,
        roles=[],
        scopes=[],
        tenant_id="tenant-evil",
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            case_review_action(
                "a5-review-tenant-case",
                CaseReviewRequest(
                    review_decision="approved",
                    review_state="completed",
                    review_note="hijack attempt",
                    review_reason="final_review",
                ),
                current_user=intruder,
            )
        )

    assert exc_info.value.status_code == 404


def test_same_tenant_same_user_can_save_and_load(fake_structured_case_store, agent_request_user, monkeypatch):
    """A5: The happy path — same tenant + same user can save and reload a case."""
    monkeypatch.setattr(
        "app.agent.material_core.load_promoted_candidate_registry_records",
        lambda: (PromotedCandidateRegistryRecordDTO(
            registry_record_id="registry-ptfe-g25-acme",
            material_family="PTFE", grade_name="G25", manufacturer_name="Acme",
            promotion_state="promoted", registry_authority="governed",
            source_refs=["registry:ptfe:g25:acme"], evidence_refs=[],
        ),),
    )
    fake_structured_case_store[(agent_request_user.tenant_id, agent_request_user.user_id, "a5-happy-case")] = _qualified_material_action_state()

    response = asyncio.run(
        download_rfq_action(
            "a5-happy-case",
            CaseActionRequest(action="download_rfq"),
            current_user=agent_request_user,
        )
    )

    assert response.allowed is True
    assert response.executed is True
