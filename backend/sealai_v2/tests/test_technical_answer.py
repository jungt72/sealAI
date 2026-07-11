from __future__ import annotations

import asyncio
import json

import pytest

from sealai_v2.core.contracts import Flags, GroundingFact, ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.core.technical_answer import (
    TechnicalAnswer,
    TechnicalAnswerValidationError,
    calibrate_technical_answer,
    validate_technical_answer,
)
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.tests._fakes import FakeLlmClient, ScriptedFakeLlmClient


def _payload(*, evidence_ids=None, revision=7):
    return json.dumps(
        {
            "schema_version": 1,
            "intent": "material_knowledge",
            "case_revision": revision,
            "conclusion": "PTFE ist ein thermoplastischer Dichtungswerkstoff.",
            "assumptions": [],
            "missing_information": [],
            "claims": [
                {
                    "text": "PTFE zeigt eine geringe Reibung.",
                    "evidence_ids": evidence_ids
                    if evidence_ids is not None
                    else ["EV-1"],
                    "criticality": "supporting",
                }
            ],
            "recommendation": {
                "summary": "",
                "status": "none",
                "conditions": [],
            },
            "needs_human_review": False,
        }
    )


def _generator(client):
    return L1Generator(
        client,
        PromptAssembler(),
        ModelConfig("standard"),
        structured_output_enabled=True,
    )


def _knowledge_plan() -> dict:
    return {
        "profile": "material_overview",
        "subjects": ["PTFE"],
        "comparison": False,
        "subject_coverage": [],
        "evidence_status": "complete",
        "evidence_fact_count": 1,
        "evidence_document_count": 1,
        "sections": [],
    }


def test_structured_answer_is_validated_and_rendered_deterministically():
    client = FakeLlmClient(_payload())
    answer = asyncio.run(
        _generator(client).generate(
            "Was ist PTFE?",
            flags=Flags(),
            grounding_facts=(
                GroundingFact("fact", "ledger", card_id="EV-1", sources=("DOC-1",)),
            ),
            case_revision=7,
        )
    )
    assert answer.model == "standard"
    assert answer.text.startswith("PTFE ist ein thermoplastischer Dichtungswerkstoff.")
    assert "geprüft belegt" in answer.text
    assert "EV-1" not in answer.text
    assert len(client.calls) == 1


def test_unknown_evidence_id_gets_exactly_one_semantic_repair():
    client = ScriptedFakeLlmClient(
        [_payload(evidence_ids=["INVENTED"]), _payload(evidence_ids=["EV-1"])]
    )
    answer = asyncio.run(
        _generator(client).generate(
            "Was ist PTFE?",
            flags=Flags(),
            grounding_facts=(GroundingFact("fact", "ledger", card_id="EV-1"),),
            case_revision=7,
        )
    )
    assert "geprüft belegt" in answer.text
    assert "EV-1" not in answer.text
    assert len(client.calls) == 2


def test_knowledge_answer_repairs_any_technical_claim_without_evidence():
    client = ScriptedFakeLlmClient(
        [_payload(evidence_ids=[]), _payload(evidence_ids=["EV-1"])]
    )
    answer = asyncio.run(
        _generator(client).generate(
            "Was ist PTFE?",
            flags=Flags(),
            grounding_facts=(GroundingFact("fact", "ledger", card_id="EV-1"),),
            knowledge_answer_plan=_knowledge_plan(),
            case_revision=7,
        )
    )

    assert "geprüft belegt" in answer.text
    assert len(client.calls) == 2


def test_knowledge_answer_drops_redundant_recommendation_block():
    payload = json.loads(_payload(evidence_ids=["EV-1"]))
    payload["recommendation"] = {
        "summary": "PTFE nur nach Prüfung einsetzen.",
        "status": "provisional",
        "conditions": ["Herstellerprüfung"],
    }
    client = FakeLlmClient(json.dumps(payload))

    answer = asyncio.run(
        _generator(client).generate(
            "Was ist PTFE?",
            flags=Flags(),
            grounding_facts=(GroundingFact("fact", "ledger", card_id="EV-1"),),
            knowledge_answer_plan=_knowledge_plan(),
            case_revision=7,
        )
    )

    assert "Vorläufige Orientierung" not in answer.text
    assert "PTFE nur nach Prüfung einsetzen" not in answer.text


def test_second_semantic_failure_stops_without_retry_loop():
    client = ScriptedFakeLlmClient(
        [_payload(evidence_ids=["BAD-1"]), _payload(evidence_ids=["BAD-2"])]
    )
    with pytest.raises(TechnicalAnswerValidationError):
        asyncio.run(
            _generator(client).generate(
                "Was ist PTFE?",
                flags=Flags(),
                grounding_facts=(GroundingFact("fact", "ledger", card_id="EV-1"),),
                case_revision=7,
            )
        )
    assert len(client.calls) == 2


def test_human_review_calibrates_unsupported_decisions_to_provisional():
    payload = json.loads(_payload(evidence_ids=[]))
    payload["claims"][0]["criticality"] = "decision_relevant"
    payload["recommendation"] = {
        "summary": "Werkstoff nur nach Prüfung einsetzen.",
        "status": "conditional",
        "conditions": ["Herstellerprüfung"],
    }
    payload["needs_human_review"] = True
    answer = TechnicalAnswer.model_validate(payload)

    calibrated = calibrate_technical_answer(answer)

    assert calibrated.claims[0].criticality == "supporting"
    assert calibrated.recommendation.status == "provisional"
    validate_technical_answer(
        calibrated, case_revision=7, allowed_evidence_ids=frozenset()
    )


def test_unsupported_decision_forces_conservative_human_review():
    payload = json.loads(_payload(evidence_ids=[]))
    payload["claims"][0]["criticality"] = "decision_relevant"
    answer = TechnicalAnswer.model_validate(payload)

    calibrated = calibrate_technical_answer(answer)

    assert calibrated.needs_human_review is True
    assert calibrated.claims[0].criticality == "supporting"
    assert calibrated.conclusion.startswith(
        "Vorläufige Einordnung ohne belastbaren Beleg:"
    )
    validate_technical_answer(
        calibrated, case_revision=7, allowed_evidence_ids=frozenset()
    )


def test_structured_answer_contract_caps_chat_density():
    schema = TechnicalAnswer.model_json_schema()
    props = schema["properties"]
    assert props["assumptions"]["maxItems"] == 6
    assert props["missing_information"]["maxItems"] == 6
    assert props["claims"]["maxItems"] == 8
