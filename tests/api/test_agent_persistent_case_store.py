from __future__ import annotations

import anyio
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.api.models import ChatRequest
from app.agent.api.models import CaseActionRequest
from app.agent.api.router import SESSION_STORE, chat_endpoint, download_rfq_action
from app.agent.cli import create_initial_state
from app.agent.material_core import PromotedCandidateRegistryRecordDTO
from app.services.auth.dependencies import RequestUser


def _build_structured_state(*, reply: str, revision: int, temperature: float = 80.0, pressure: float = 10.0) -> dict:
    sealing_state = create_initial_state()
    sealing_state["asserted"]["medium_profile"] = {
        "name": "Wasser",
        "resistance_rating": "A",
    }
    sealing_state["asserted"]["machine_profile"] = {
        "material": "PTFE",
    }
    sealing_state["asserted"]["operating_conditions"] = {
        "temperature": temperature,
        "pressure": pressure,
    }
    sealing_state["normalized"]["identity_records"] = {
        "material_family": {
            "raw_value": "PTFE",
            "normalized_value": "PTFE",
            "identity_class": "identity_confirmed",
            "source_fact_ids": ["fc-1"],
        }
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
        "blocked_candidates": [],
        "winner_candidate_id": "ptfe",
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
    return {
        "messages": [AIMessage(content=reply)],
        "sealing_state": sealing_state,
        "working_profile": {
            "diameter": 50.0,
            "speed": 1500.0,
            "pressure": pressure,
            "temperature": temperature,
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


def _build_provider_structured_state(*, reply: str, revision: int) -> dict:
    state = _build_structured_state(reply=reply, revision=revision, temperature=120.0, pressure=10.0)
    state["sealing_state"]["normalized"]["identity_records"] = {
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
    state["sealing_state"]["governance"].update(
        {
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "compound_required",
            "unknowns_manufacturer_validation": [],
        }
    )
    state["sealing_state"]["selection"] = {
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
    state["relevant_fact_cards"] = [
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
    ]
    return state


def _other_user() -> RequestUser:
    return RequestUser(
        user_id="user-other",
        username="other",
        sub="user-other",
        roles=[],
        scopes=[],
        tenant_id="tenant-other",
    )


def test_structured_case_persists_after_first_turn(monkeypatch, agent_request_user, agent_structured_case_store):
    from app.agent.api import router as router_mod

    async def _fake_execute_agent(_state):
        return _build_structured_state(reply="Structured first reply", revision=3)

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)

    async def _call():
        return await chat_endpoint(
            ChatRequest(
                message="Bitte strukturiere den Fall.",
                session_id="persist-1",
            ),
            current_user=agent_request_user,
        )

    response = anyio.run(_call)

    assert response.has_case_state is True
    persisted = agent_structured_case_store[(agent_request_user.user_id, "persist-1")]
    assert persisted["sealing_state"]["cycle"]["state_revision"] == 3
    assert persisted["case_state"]["case_meta"]["case_id"] == "persist-1"


def test_second_structured_turn_resumes_persisted_case_instead_of_blank_memory_state(
    monkeypatch,
    agent_request_user,
):
    from app.agent.api import router as router_mod

    calls = {"count": 0}

    async def _fake_execute_agent(state):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                **_build_structured_state(reply="First reply", revision=3),
                "messages": state["messages"] + [AIMessage(content="First reply")],
            }
        assert len(state["messages"]) == 3
        assert state["messages"][0].content == "Erster Turn"
        assert state["messages"][1].content == "First reply"
        assert state["messages"][2].content == "Zweiter Turn"
        return {
            **_build_structured_state(reply="Second reply", revision=4),
            "messages": state["messages"] + [AIMessage(content="Second reply")],
        }

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)

    async def _first_turn():
        return await chat_endpoint(
            ChatRequest(message="Erster Turn", session_id="resume-1"),
            current_user=agent_request_user,
        )

    async def _second_turn():
        return await chat_endpoint(
            ChatRequest(message="Zweiter Turn", session_id="resume-1"),
            current_user=agent_request_user,
        )

    anyio.run(_first_turn)
    SESSION_STORE.clear()
    response = anyio.run(_second_turn)

    assert response.reply == "Second reply"
    assert response.case_state["case_meta"]["state_revision"] == 4


def test_user_scoped_isolation_prevents_cross_user_case_reuse(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    calls = {"count": 0}

    async def _fake_execute_agent(state):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                **_build_structured_state(reply="Owner reply", revision=3),
                "messages": state["messages"] + [AIMessage(content="Owner reply")],
            }
        assert len(state["messages"]) == 1
        assert state["messages"][0].content == "Fremder Turn"
        return {
            **_build_structured_state(reply="Other reply", revision=1),
            "messages": state["messages"] + [AIMessage(content="Other reply")],
        }

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)

    async def _owner_turn():
        return await chat_endpoint(
            ChatRequest(message="Owner Turn", session_id="shared-case"),
            current_user=agent_request_user,
        )

    async def _other_turn():
        return await chat_endpoint(
            ChatRequest(message="Fremder Turn", session_id="shared-case"),
            current_user=_other_user(),
        )

    anyio.run(_owner_turn)
    SESSION_STORE.clear()
    response = anyio.run(_other_turn)

    assert response.reply == "Other reply"
    assert response.case_id == "shared-case"


def test_fast_path_does_not_require_structured_persistence_path(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    async def _fail_load(*, owner_id: str, case_id: str):
        raise AssertionError(f"structured persistence load must not run for fast path: {owner_id}:{case_id}")

    async def _fail_save(*, owner_id: str, case_id: str, state, runtime_path: str, binding_level: str):
        raise AssertionError(f"structured persistence save must not run for fast path: {owner_id}:{case_id}")

    monkeypatch.setattr(router_mod, "load_structured_case", _fail_load)
    monkeypatch.setattr(router_mod, "save_structured_case", _fail_save)

    async def _call():
        return await chat_endpoint(
            ChatRequest(
                message="Berechne bei 40 mm und 1000 rpm die Umfangsgeschwindigkeit.",
                session_id="fast-1",
            ),
            current_user=agent_request_user,
        )

    response = anyio.run(_call)

    assert response.runtime_path == "FAST_CALCULATION"
    assert response.has_case_state is False


def test_invalidation_cycle_data_survives_structured_resume(monkeypatch, agent_request_user):
    from app.agent.api import router as router_mod

    calls = {"count": 0}

    async def _fake_execute_agent(state):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                **_build_structured_state(reply="Initial reply", revision=3, temperature=80.0),
                "messages": state["messages"] + [AIMessage(content="Initial reply")],
            }
        cycle = state["sealing_state"]["cycle"]
        assert cycle["material_input_revision"] == 3
        assert cycle["material_input_fingerprint"]
        return {
            **_build_structured_state(reply="Resumed reply", revision=4, temperature=120.0),
            "messages": state["messages"] + [AIMessage(content="Resumed reply")],
        }

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)

    async def _first_turn():
        return await chat_endpoint(
            ChatRequest(message="Start", session_id="resume-cycle-1"),
            current_user=agent_request_user,
        )

    async def _second_turn():
        return await chat_endpoint(
            ChatRequest(message="Temperatur jetzt 120 C", session_id="resume-cycle-1"),
            current_user=agent_request_user,
        )

    anyio.run(_first_turn)
    SESSION_STORE.clear()
    response = anyio.run(_second_turn)

    invalidation = response.case_state["invalidation_state"]
    assert invalidation["recompute_completed"] is True
    assert "temperature_c_changed" in invalidation["recompute_reasons"]
    assert invalidation["material_input_revision"] == 4


def test_resume_path_preserves_provider_provenance_and_recomputes_invalidation_deterministically(
    monkeypatch,
    agent_request_user,
):
    from app.agent.api import router as router_mod

    calls = {"count": 0}

    async def _fake_execute_agent(state):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                **_build_provider_structured_state(reply="Initial provider reply", revision=3),
                "messages": state["messages"] + [AIMessage(content="Initial provider reply")],
            }
        cycle = state["sealing_state"]["cycle"]
        assert cycle["provider_contract_fingerprint"]
        assert cycle["matched_promoted_registry_record_ids"] == ["registry-ptfe-g25-acme"]
        return {
            **_build_provider_structured_state(reply="Resumed provider reply", revision=4),
            "messages": state["messages"] + [AIMessage(content="Resumed provider reply")],
        }

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)

    async def _first_turn():
        return await chat_endpoint(
            ChatRequest(message="Provider Start", session_id="resume-provider-1"),
            current_user=agent_request_user,
        )

    async def _second_turn():
        return await chat_endpoint(
            ChatRequest(message="Provider Resume", session_id="resume-provider-1"),
            current_user=agent_request_user,
        )

    anyio.run(_first_turn)
    SESSION_STORE.clear()
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
    response = anyio.run(_second_turn)

    invalidation = response.case_state["invalidation_state"]
    assert invalidation["recompute_completed"] is True
    assert "provider_contract_fingerprint_changed" in invalidation["recompute_reasons"]
    assert invalidation["provider_contract_revision"] == 4
    assert response.case_state["qualification_results"]["material_core"]["status"] != "stale_requires_recompute"


def test_resumed_structured_case_exposes_last_qualified_action_status_after_reload(
    monkeypatch,
    agent_request_user,
):
    from app.agent.api import router as router_mod

    async def _fake_execute_agent(state):
        return {
            **_build_provider_structured_state(reply="Persisted qualified reply", revision=4),
            "messages": state["messages"] + [AIMessage(content="Persisted qualified reply")],
        }

    monkeypatch.setattr(router_mod, "execute_agent", _fake_execute_agent)

    async def _first_turn():
        return await chat_endpoint(
            ChatRequest(message="Bitte qualifiziere den promoted Fall.", session_id="resume-action-1"),
            current_user=agent_request_user,
        )

    anyio.run(_first_turn)
    anyio.run(
        lambda: download_rfq_action(
            "resume-action-1",
            CaseActionRequest(action="download_rfq"),
            current_user=agent_request_user,
        )
    )
    SESSION_STORE.clear()

    async def _resume_turn():
        return await chat_endpoint(
            ChatRequest(message="Zeige den Fall erneut.", session_id="resume-action-1"),
            current_user=agent_request_user,
        )

    response = anyio.run(_resume_turn)

    status = response.case_state["qualified_action_status"]
    assert status["last_status"] == "executed"
    assert status["executed"] is True
    assert status["action_payload_stub"] == "rfq_download_contract_v1"
    history = response.case_state["qualified_action_history"]
    assert history[0]["last_status"] == "executed"
    assert history[0]["executed"] is True
