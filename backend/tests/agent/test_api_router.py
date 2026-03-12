import asyncio
import json
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.api.models import ChatRequest
from app.agent.api.router import SESSION_STORE, chat_endpoint, chat_stream_endpoint, event_generator, router
from app.agent.agent.selection import SAFEGUARDED_WITHHELD_REPLY


app_for_tests = FastAPI()
app_for_tests.include_router(router)
client = TestClient(app_for_tests)


@pytest.fixture(autouse=True)
def clear_sessions():
    SESSION_STORE.clear()


def test_chat_returns_blocked_reply_when_selection_withheld():
    mock_updated_state = {
        "messages": [
            HumanMessage(content="Hallo Agent"),
            AIMessage(content="No governed recommendation can be released from the current evidence."),
        ],
        "sealing_state": {
            "cycle": {"state_revision": 1, "analysis_cycle_id": "session_test_1"},
            "selection": {
                "selection_status": "blocked_no_candidates",
                "candidates": [],
                "viable_candidate_ids": [],
                "blocked_candidates": [],
                "winner_candidate_id": None,
                "recommendation_artifact": {
                    "selection_status": "blocked_no_candidates",
                    "winner_candidate_id": None,
                    "candidate_ids": [],
                    "viable_candidate_ids": [],
                    "blocked_candidates": [],
                    "evidence_basis": [],
                    "release_status": "inadmissible",
                    "rfq_admissibility": "inadmissible",
                    "specificity_level": "family_only",
                    "output_blocked": True,
                    "trace_provenance_refs": [],
                },
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "output_blocked": True,
            },
        },
    }

    async def run_test():
        with patch("app.agent.api.router.execute_agent", return_value=mock_updated_state):
            return await chat_endpoint(ChatRequest(message="Hallo Agent", session_id="test_session"))

    response = asyncio.run(run_test())
    assert response.reply == "No governed recommendation can be released from the current evidence."
    assert response.sealing_state["selection"]["release_status"] == "inadmissible"


def test_chat_returns_final_reply_only_when_selection_released():
    mock_updated_state = {
        "messages": [
            HumanMessage(content="Empfehlung"),
            AIMessage(
                content=(
                    "Technischer Eignungsraum vorbereitet. Freigabe bleibt an Governance, "
                    "Scope-of-validity und dokumentierte Open Points gebunden."
                )
            ),
        ],
        "sealing_state": {
            "cycle": {"state_revision": 2, "analysis_cycle_id": "session_test_2"},
            "relevant_evidence": [
                {
                    "evidence_id": "fc-1",
                    "source_ref": "SRC-G461",
                    "topic": "Acme G461",
                    "metadata": {"material_family": "PTFE", "grade_name": "G461", "manufacturer_name": "Acme"},
                    "normalized_evidence": {
                        "datasheet_contract": {
                            "selection_readiness": {
                                "rfq_ready_eligible": True,
                                "blocking_reasons": [],
                                "max_specificity_level": "compound_required",
                            }
                        }
                    },
                }
            ],
            "selection": {
                "selection_status": "winner_selected",
                "candidates": [{"candidate_id": "ptfe", "material_family": "PTFE"}],
                "winner_candidate_id": "ptfe",
                "recommendation_artifact": {
                    "selection_status": "winner_selected",
                    "winner_candidate_id": "ptfe",
                    "candidate_ids": ["ptfe"],
                    "viable_candidate_ids": ["ptfe"],
                    "blocked_candidates": [],
                    "evidence_basis": ["fc-1"],
                    "release_status": "rfq_ready",
                    "rfq_admissibility": "ready",
                    "specificity_level": "compound_required",
                    "output_blocked": False,
                    "trace_provenance_refs": ["fc-1", "session_test_2"],
                },
                "release_status": "rfq_ready",
                "rfq_admissibility": "ready",
                "specificity_level": "compound_required",
                "output_blocked": False,
                "viable_candidate_ids": ["ptfe"],
                "blocked_candidates": [],
            },
        },
    }

    async def run_test():
        with patch("app.agent.api.router.execute_agent", return_value=mock_updated_state):
            return await chat_endpoint(ChatRequest(message="Empfehlung", session_id="released_session"))

    response = asyncio.run(run_test())
    assert response.reply == (
        "Technischer Eignungsraum vorbereitet. Freigabe bleibt an Governance, "
        "Scope-of-validity und dokumentierte Open Points gebunden."
    )
    assert response.sealing_state["relevant_evidence"][0]["normalized_evidence"]["datasheet_contract"]["selection_readiness"]["rfq_ready_eligible"] is True


def test_chat_returns_contract_blockers_in_state_for_manufacturer_validation():
    mock_updated_state = {
        "messages": [
            HumanMessage(content="Audit block"),
            AIMessage(content="Technischer Eignungsraum vorbereitet. Freigabe bleibt an Governance, Scope-of-validity und dokumentierte Open Points gebunden."),
        ],
        "sealing_state": {
            "cycle": {"state_revision": 7, "analysis_cycle_id": "session_test_7"},
            "governance": {
                "release_status": "manufacturer_validation_required",
                "rfq_admissibility": "provisional",
                "specificity_level": "subfamily",
                "unknowns_manufacturer_validation": ["audit_gate_not_passed"],
                "unknowns_release_blocking": [],
                "conflicts": [],
            },
            "relevant_evidence": [
                {
                    "evidence_id": "fc-audit",
                    "source_ref": "SRC-AUDIT",
                    "topic": "Acme G461",
                    "metadata": {"material_family": "PTFE", "grade_name": "G461", "manufacturer_name": "Acme"},
                    "normalized_evidence": {
                        "datasheet_contract": {
                            "selection_readiness": {
                                "rfq_ready_eligible": False,
                                "blocking_reasons": ["audit_gate_not_passed"],
                                "max_specificity_level": "compound_required",
                            }
                        }
                    },
                }
            ],
            "selection": {
                "selection_status": "winner_selected",
                "candidates": [{"candidate_id": "ptfe::g461", "material_family": "PTFE"}],
                "winner_candidate_id": "ptfe::g461",
                "recommendation_artifact": {
                    "selection_status": "winner_selected",
                    "winner_candidate_id": "ptfe::g461",
                    "candidate_ids": ["ptfe::g461"],
                    "viable_candidate_ids": ["ptfe::g461"],
                    "blocked_candidates": [],
                    "evidence_basis": ["fc-audit"],
                    "release_status": "manufacturer_validation_required",
                    "rfq_admissibility": "provisional",
                    "specificity_level": "subfamily",
                    "output_blocked": True,
                    "trace_provenance_refs": ["fc-audit", "session_test_7"],
                },
                "release_status": "manufacturer_validation_required",
                "rfq_admissibility": "provisional",
                "specificity_level": "subfamily",
                "output_blocked": True,
                "viable_candidate_ids": ["ptfe::g461"],
                "blocked_candidates": [],
            },
        },
    }

    async def run_test():
        with patch("app.agent.api.router.execute_agent", return_value=mock_updated_state):
            return await chat_endpoint(ChatRequest(message="Audit block", session_id="audit_block"))

    response = asyncio.run(run_test())
    assert response.reply == (
        "Technischer Eignungsraum vorbereitet. Hersteller-Validierung ist erforderlich; "
        "keine Material- oder Compound-Freigabe wird ausgegeben."
    )
    assert response.sealing_state["governance"]["release_status"] == "manufacturer_validation_required"
    assert response.sealing_state["relevant_evidence"][0]["normalized_evidence"]["datasheet_contract"]["selection_readiness"]["blocking_reasons"] == ["audit_gate_not_passed"]


def test_chat_returns_safeguarded_reply_when_artifact_missing_even_if_ai_message_exists():
    mock_updated_state = {
        "messages": [
            HumanMessage(content="Unsafe"),
            AIMessage(content="Unsafe pre-gate recommendation text."),
        ],
        "sealing_state": {
            "cycle": {"state_revision": 3, "analysis_cycle_id": "session_test_3"},
            "selection": {
                "selection_status": "winner_selected",
                "candidates": [{"candidate_id": "ptfe"}],
                "viable_candidate_ids": ["ptfe"],
                "blocked_candidates": [],
                "winner_candidate_id": "ptfe",
                "recommendation_artifact": None,
                "release_status": "rfq_ready",
                "rfq_admissibility": "ready",
                "specificity_level": "family_only",
                "output_blocked": False,
            },
        },
    }

    async def run_test():
        with patch("app.agent.api.router.execute_agent", return_value=mock_updated_state):
            return await chat_endpoint(ChatRequest(message="Unsafe", session_id="missing_artifact"))

    response = asyncio.run(run_test())
    assert response.reply == SAFEGUARDED_WITHHELD_REPLY


def test_chat_withholds_when_governance_is_inadmissible_even_if_candidate_exists():
    mock_updated_state = {
        "messages": [
            HumanMessage(content="Blocked"),
            AIMessage(content="Unsafe pre-gate recommendation text."),
        ],
        "sealing_state": {
            "cycle": {"state_revision": 4, "analysis_cycle_id": "session_test_4"},
            "governance": {"release_status": "inadmissible", "conflicts": []},
            "selection": {
                "selection_status": "winner_selected",
                "candidates": [{"candidate_id": "ptfe"}],
                "winner_candidate_id": "ptfe",
                "recommendation_artifact": {
                    "selection_status": "winner_selected",
                    "winner_candidate_id": "ptfe",
                    "candidate_ids": ["ptfe"],
                    "viable_candidate_ids": [],
                    "blocked_candidates": [{"candidate_id": "ptfe", "block_reason": "blocked_missing_required_inputs"}],
                    "evidence_basis": ["fc-1"],
                    "release_status": "inadmissible",
                    "rfq_admissibility": "inadmissible",
                    "specificity_level": "family_only",
                    "output_blocked": True,
                    "trace_provenance_refs": ["fc-1", "session_test_4"],
                },
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "output_blocked": True,
                "viable_candidate_ids": [],
                "blocked_candidates": [{"candidate_id": "ptfe", "block_reason": "blocked_missing_required_inputs"}],
            },
        },
    }

    async def run_test():
        with patch("app.agent.api.router.execute_agent", return_value=mock_updated_state):
            return await chat_endpoint(ChatRequest(message="Blocked", session_id="blocked_inadmissible"))

    response = asyncio.run(run_test())
    assert response.reply == SAFEGUARDED_WITHHELD_REPLY


def test_chat_returns_no_viable_candidates_reply_when_all_candidates_fail_limits():
    mock_updated_state = {
        "messages": [
            HumanMessage(content="Blocked by limits"),
            AIMessage(content="Unsafe pre-gate recommendation text."),
        ],
        "sealing_state": {
            "cycle": {"state_revision": 5, "analysis_cycle_id": "session_test_5"},
            "selection": {
                "selection_status": "blocked_no_viable_candidates",
                "candidates": [{"candidate_id": "ptfe"}],
                "winner_candidate_id": None,
                "recommendation_artifact": {
                    "selection_status": "blocked_no_viable_candidates",
                    "winner_candidate_id": None,
                    "candidate_ids": ["ptfe"],
                    "viable_candidate_ids": [],
                    "blocked_candidates": [{"candidate_id": "ptfe", "block_reason": "blocked_temperature_conflict"}],
                    "evidence_basis": ["fc-1"],
                    "release_status": "inadmissible",
                    "rfq_admissibility": "inadmissible",
                    "specificity_level": "family_only",
                    "output_blocked": True,
                    "trace_provenance_refs": ["fc-1", "session_test_5"],
                },
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "output_blocked": True,
                "viable_candidate_ids": [],
                "blocked_candidates": [{"candidate_id": "ptfe", "block_reason": "blocked_temperature_conflict"}],
            },
        },
    }

    async def run_test():
        with patch("app.agent.api.router.execute_agent", return_value=mock_updated_state):
            return await chat_endpoint(ChatRequest(message="Blocked by limits", session_id="no_viable"))

    response = asyncio.run(run_test())
    assert response.reply == "No governed recommendation can be released because no viable candidate remains after deterministic checks."


def test_api_chat_empty_message():
    with pytest.raises(Exception):
        ChatRequest(message="", session_id="bad")


def test_stream_does_not_emit_pre_gate_tokens():
    async def mock_astream_events(state, version):
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": AIMessage(content="Stream")},
        }
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {
                "output": {
                    "messages": state["messages"] + [
                        AIMessage(content="Unsafe pre-gate recommendation text.")
                    ],
                    "sealing_state": {
                        "cycle": {"state_revision": 10},
                        "selection": {
                            "selection_status": "blocked_missing_required_inputs",
                            "candidates": [{"candidate_id": "ptfe"}],
                            "winner_candidate_id": None,
                            "recommendation_artifact": {
                                "selection_status": "blocked_missing_required_inputs",
                                "winner_candidate_id": None,
                                "candidate_ids": ["ptfe"],
                                "viable_candidate_ids": [],
                                "blocked_candidates": [{"candidate_id": "ptfe", "block_reason": "blocked_missing_required_inputs"}],
                                "evidence_basis": ["fc-1"],
                                "release_status": "inadmissible",
                                "rfq_admissibility": "inadmissible",
                                "specificity_level": "family_only",
                                "output_blocked": True,
                                "trace_provenance_refs": ["fc-1", "stream_test"],
                            },
                            "release_status": "inadmissible",
                            "rfq_admissibility": "inadmissible",
                            "specificity_level": "family_only",
                            "output_blocked": True,
                            "viable_candidate_ids": [],
                            "blocked_candidates": [{"candidate_id": "ptfe", "block_reason": "blocked_missing_required_inputs"}],
                        },
                    },
                }
            },
        }

    async def collect_events():
        with patch("app.agent.api.router.app.astream_events", side_effect=mock_astream_events):
            events = []
            async for event in event_generator(ChatRequest(message="Starte Stream", session_id="stream_test")):
                events.append(event)
            return "".join(events)

    content = asyncio.run(collect_events())
    assert "Stream" not in content
    assert "Unsafe pre-gate recommendation text." not in content
    assert "required engineering inputs are missing" in content
    assert '"state"' in content
    assert "[DONE]" in content


def test_chat_stream_route_emits_only_gated_reply_and_state():
    async def mock_event_generator(_request):
        yield f"data: {json.dumps({'reply': SAFEGUARDED_WITHHELD_REPLY})}\n\n"
        yield f"data: {json.dumps({'state': {'selection': {'release_status': 'inadmissible'}}, 'working_profile': {}})}\n\n"
        yield "data: [DONE]\n\n"

    async def collect_response():
        with patch("app.agent.api.router.event_generator", side_effect=mock_event_generator):
            response = await chat_stream_endpoint(
                ChatRequest(message="Starte Stream", session_id="route_stream_test")
            )
            chunks = []
            async for chunk in response.body_iterator:
                if isinstance(chunk, bytes):
                    chunks.append(chunk.decode())
                else:
                    chunks.append(chunk)
            return response, "".join(chunks)

    response, content = asyncio.run(collect_response())

    assert response.media_type == "text/event-stream"
    assert SAFEGUARDED_WITHHELD_REPLY in content
    assert '"release_status": "inadmissible"' in content
    assert '"state"' in content
    assert "[DONE]" in content
