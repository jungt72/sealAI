from __future__ import annotations

import asyncio
import json

import pytest

from sealai_v2.core.contracts import (
    CalcResult,
    ComputedValue,
    Flags,
    GroundingFact,
    ModelConfig,
)
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
    assert "quellengebunden" in answer.text
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
            grounding_facts=(GroundingFact("PTFE fact", "ledger", card_id="EV-1"),),
            case_revision=7,
        )
    )
    assert "quellengebunden" in answer.text
    assert "EV-1" not in answer.text
    assert len(client.calls) == 2


def test_knowledge_answer_falls_back_without_a_second_paid_call():
    client = FakeLlmClient(_payload(evidence_ids=[]))
    answer = asyncio.run(
        _generator(client).generate(
            "Was ist PTFE?",
            flags=Flags(),
            grounding_facts=(GroundingFact("PTFE fact", "ledger", card_id="EV-1"),),
            knowledge_answer_plan=_knowledge_plan(),
            case_revision=7,
        )
    )

    assert "Weitere quellengebundene Einordnung" in answer.text
    assert "- PTFE fact" in answer.text
    assert "geprüft belegt" not in answer.text
    assert answer.finish_reason == "deterministic_engineering_fallback"
    assert len(client.calls) == 1


def test_evidence_bound_technical_answer_falls_back_without_second_paid_call():
    client = FakeLlmClient(_payload(evidence_ids=[]))
    answer = asyncio.run(
        _generator(client).generate(
            "Welcher Dichtungsaufbau passt?",
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "Geprüfter technischer Zusammenhang.",
                    "ledger",
                    card_id="EV-1",
                ),
            ),
            require_evidence_for_all_claims=True,
            work_solution_candidate=True,
            case_revision=7,
        )
    )

    assert "Geprüfter technischer Zusammenhang" in answer.text
    assert answer.finish_reason == "deterministic_evidence_fallback"
    assert len(client.calls) == 1
    assert "one primary provisional candidate" in client.calls[0]["system"]


def test_rwdr_fallback_surfaces_kernel_value_and_discriminating_inputs():
    client = FakeLlmClient(_payload(evidence_ids=[]))
    calc = CalcResult(
        computed=(
            ComputedValue(
                calc_id="umfangsgeschwindigkeit",
                name="v_m_s",
                value=3.534,
                unit="m/s",
                stage=1,
                derivation_depth=1,
                formula="pi*d*n/60",
            ),
        )
    )
    answer = asyncio.run(
        _generator(client).generate(
            "RWDR 45 mm bei 1500 U/min technisch vorprüfen",
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "Ein RWDR benötigt einen tragfähigen Schmierfilm.",
                    "ledger",
                    card_id="FK-RWDR-ENGINEERING-PROFILE",
                ),
            ),
            calc=calc,
            require_evidence_for_all_claims=True,
            case_revision=7,
        )
    )
    assert "v_m_s = 3.534 m/s" in answer.text
    assert "Wellenhärte, Rauheit und Drallfreiheit" in answer.text
    assert "Druckdifferenz einschließlich Druckspitzen" in answer.text
    assert answer.finish_reason == "deterministic_evidence_fallback"
    assert len(client.calls) == 1


def test_compact_technical_answer_caps_first_turn_density_deterministically():
    payload = json.loads(_payload())
    payload["assumptions"] = ["a", "b"]
    payload["missing_information"] = ["m1", "m2", "m3", "m4", "m5"]
    payload["claims"] = [
        {
            "text": f"claim {index}",
            "evidence_ids": ["EV-1"],
            "criticality": "decision_relevant" if index == 4 else "supporting",
        }
        for index in range(5)
    ]
    payload["recommendation"] = {
        "summary": "Prüfpfad",
        "status": "conditional",
        "conditions": ["c1", "c2", "c3", "c4"],
    }
    client = FakeLlmClient(json.dumps(payload))

    answer = asyncio.run(
        _generator(client).generate(
            "RWDR-Fall",
            flags=Flags(),
            grounding_facts=(GroundingFact("fact", "ledger", card_id="EV-1"),),
            require_evidence_for_all_claims=True,
            compact_technical_answer=True,
            case_revision=7,
        )
    )

    assert "claim 4" in answer.text
    assert answer.text.count("quellengebunden") == 3
    assert "m4" not in answer.text and "m5" not in answer.text
    assert "c3" not in answer.text and "c4" not in answer.text
    assert "**Annahmen**" not in answer.text


def test_knowledge_answer_drops_redundant_recommendation_block():
    payload = json.loads(_payload(evidence_ids=["E1"]))
    payload["recommendation"] = {
        "summary": "PTFE nur nach Prüfung einsetzen.",
        "status": "provisional",
        "conditions": ["Herstellerprüfung"],
    }
    payload["needs_human_review"] = True
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
    assert "Fachprüfung erforderlich" not in answer.text


def test_knowledge_answer_supplements_missing_claim_level_facet_coverage():
    plan = _knowledge_plan()
    plan["sections"] = [
        {
            "heading": "Kennwerte",
            "instruction": "Definition und Parameter abdecken.",
            "facets": ["definition", "parameters"],
            "covered_facets": ["definition", "parameters"],
            "missing_facets": [],
        }
    ]
    client = FakeLlmClient(_payload(evidence_ids=["E1"]))
    facts = (
        GroundingFact(
            "PTFE definition",
            "ledger",
            card_id="FK-PTFE",
            answer_facets=("definition",),
            claim_id="claim-definition",
        ),
        GroundingFact(
            "PTFE parameter",
            "ledger",
            card_id="FK-PTFE",
            answer_facets=("parameters",),
            claim_id="claim-parameters",
        ),
    )

    answer = asyncio.run(
        _generator(client).generate(
            "Was ist PTFE?",
            flags=Flags(),
            grounding_facts=facts,
            knowledge_answer_plan=plan,
            case_revision=7,
        )
    )

    assert len(client.calls) == 1
    assert (
        "Evidence ownership: E1=>subject[PTFE];facets[definition]"
        in client.calls[0]["system"]
    )
    assert "[Evidenz-ID: E1]" in client.calls[0]["system"]
    assert "claim-definition" not in client.calls[0]["system"]
    assert "EV-1" not in client.calls[0]["system"]
    assert "PTFE definition" in answer.text
    assert "PTFE parameter" in answer.text


def test_knowledge_answer_hides_canonical_uuid_behind_short_alias():
    canonical_id = "7cf25557-4816-5ec1-b8f7-03cf5346e587"
    client = FakeLlmClient(_payload(evidence_ids=["E1"]))
    fact = GroundingFact(
        "PTFE definition",
        "ledger",
        card_id="FK-PTFE-ENGINEERING-PROFILE",
        claim_id=canonical_id,
    )

    answer = asyncio.run(
        _generator(client).generate(
            "Erkläre PTFE.",
            flags=Flags(),
            grounding_facts=(fact,),
            knowledge_answer_plan=_knowledge_plan(),
            case_revision=7,
        )
    )

    assert (
        "Evidence ownership: E1=>subject[PTFE];facets[none]"
        in client.calls[0]["system"]
    )
    assert canonical_id not in client.calls[0]["system"]
    assert answer.grounding_facts == (fact,)


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
