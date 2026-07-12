from __future__ import annotations

import asyncio
import json

import pytest

from sealai_v2.core.contracts import Flags, GroundingFact, ModelConfig
from sealai_v2.core.engineering_answer import (
    EngineeringAnswerValidationError,
    EngineeringKnowledgeAnswer,
    validate_engineering_answer,
)
from sealai_v2.core.l1_generator import L1Generator, _fact_subjects
from sealai_v2.knowledge.material_parameters import lookup
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.render.engineering_answer import render_engineering_answer
from sealai_v2.tests._fakes import FakeLlmClient


def _answer(*, subject: str = "NBR", statement: str = "NBR ist ein Elastomer."):
    return EngineeringKnowledgeAnswer.model_validate(
        {
            "schema_version": 2,
            "profile": "material_comparison",
            "case_revision": 4,
            "conclusion": "Die Werkstoffklassen lösen unterschiedliche Dichtaufgaben.",
            "claims": [
                {
                    "subject": subject,
                    "facet": "definition",
                    "statement": statement,
                    "evidence_ids": ["E1"],
                    "criticality": "context",
                }
            ],
            "assumptions": [],
            "missing_information": ["Konkrete Bauform und Betriebsbedingungen"],
        }
    )


def _validate(answer: EngineeringKnowledgeAnswer) -> None:
    validate_engineering_answer(
        answer,
        profile="material_comparison",
        case_revision=4,
        allowed_subjects=("NBR", "PTFE"),
        evidence_facets={"E1": frozenset({"definition"})},
        evidence_subjects={"E1": frozenset({"NBR"})},
        evidence_texts={"E1": "NBR ist ein Elastomer."},
    )


def test_subject_bound_claim_is_accepted() -> None:
    _validate(_answer())


def test_cross_material_evidence_is_rejected() -> None:
    with pytest.raises(
        EngineeringAnswerValidationError, match="subject_evidence_mismatch"
    ):
        _validate(_answer(subject="PTFE", statement="PTFE ist ein Thermoplast."))


def test_subject_binding_does_not_treat_hnbr_as_nbr() -> None:
    fact = GroundingFact("HNBR-Fakt", "ledger", card_id="FK-HNBR-UEBERBLICK")
    assert _fact_subjects(fact, ("NBR", "PTFE")) == frozenset()


def test_unreviewed_number_is_rejected() -> None:
    with pytest.raises(
        EngineeringAnswerValidationError, match="unsupported_numeric_content"
    ):
        _validate(_answer(statement="NBR ist bis 177 °C einsetzbar."))


def test_renderer_owns_aligned_comparison_and_parameter_tables() -> None:
    answer = _answer()
    plan = {
        "comparison": True,
        "subjects": ["NBR", "PTFE"],
        "sections": [
            {"heading": "Vergleichsbasis", "facets": ["definition"]},
            {"heading": "Grenzen", "facets": ["limits"]},
        ],
    }
    rendered = render_engineering_answer(
        answer,
        knowledge_answer_plan=plan,
        material_params=[lookup("NBR"), lookup("PTFE")],
    )
    assert "| Vergleichsachse | NBR | PTFE |" in rendered
    assert "| Vergleichsbasis | NBR ist ein Elastomer. | Nicht belegt |" in rendered
    assert "| Parameter | NBR | PTFE |" in rendered
    assert "Druckverformungsrest" in rendered
    assert "Typ-, Mindest- und Referenzwerte" in rendered


def test_l1_uses_v2_schema_for_knowledge_answer() -> None:
    payload = {
        "schema_version": 2,
        "profile": "material_overview",
        "case_revision": 7,
        "conclusion": "NBR ist eine compoundabhängige Elastomerfamilie.",
        "claims": [
            {
                "subject": "NBR",
                "facet": "definition",
                "statement": "NBR ist eine Elastomerfamilie.",
                "evidence_ids": ["E1"],
                "criticality": "context",
            }
        ],
        "assumptions": [],
        "missing_information": [],
    }
    client = FakeLlmClient(json.dumps(payload))
    generator = L1Generator(
        client,
        PromptAssembler(),
        ModelConfig("standard"),
        structured_output_enabled=True,
    )
    answer = asyncio.run(
        generator.generate(
            "Details zu NBR",
            flags=Flags(),
            grounding_facts=(
                GroundingFact(
                    "NBR ist eine Elastomerfamilie.",
                    "ledger",
                    card_id="FK-NBR-UEBERBLICK",
                    claim_id="claim-nbr-definition",
                    answer_facets=("definition",),
                    subject_type="material",
                ),
            ),
            knowledge_answer_plan={
                "profile": "material_overview",
                "subjects": ["NBR"],
                "comparison": False,
                "evidence_status": "complete",
                "evidence_fact_count": 1,
                "evidence_document_count": 1,
                "subject_coverage": [
                    {
                        "subject": "NBR",
                        "covered_facets": ["definition"],
                        "missing_facets": [],
                    }
                ],
                "sections": [
                    {
                        "heading": "Einordnung",
                        "instruction": "Werkstoffklasse einordnen.",
                        "facets": ["definition"],
                        "covered_facets": ["definition"],
                        "missing_facets": [],
                    }
                ],
            },
            case_revision=7,
        )
    )
    assert answer.finish_reason != "deterministic_engineering_fallback"
    assert "**Einordnung**" in answer.text
    assert "NBR ist eine Elastomerfamilie." in answer.text
