import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.agent.agent.knowledge import load_fact_cards, retrieve_rag_context
from app.agent.agent.logic import process_cycle_update
from app.agent.cli import create_initial_state
from app.agent.domain.material import normalize_fact_card_evidence


_BUNDLED_KB_PATH = Path("backend/app/data/kb/SEALAI_KB_PTFE_factcards_gates_v1_3.json")


def test_load_fact_cards_enriches_document_metadata_from_source_registry(tmp_path: Path):
    kb_path = tmp_path / "kb.json"
    kb_path.write_text(
        json.dumps(
            {
                "schema_version": "1.3",
                "sources": {
                    "SRC-G461": {
                        "title": "Acme G461 PTFE Datasheet",
                        "url": "https://example.invalid/acme-g461.pdf",
                        "type": "manufacturer_datasheet",
                        "rank": 2,
                        "published_at": "2024-01-15",
                        "document_revision": "Rev. 3",
                        "manufacturer_name": "Acme",
                        "product_line": "G-Series",
                        "material_family": "PTFE",
                        "evidence_scope": ["grade_identity"],
                    }
                },
                "factcards": [
                    {
                        "id": "FC-G461-001",
                        "source": "SRC-G461",
                        "source_type": "manufacturer_datasheet",
                        "source_rank": 2,
                        "topic": "Acme G461",
                        "property": "temperature_max_c",
                        "value": 260,
                        "units": "C",
                        "metadata": {
                            "grade_name": "G461",
                            "manufacturer_name": "Acme",
                            "material_family": "PTFE",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cards = load_fact_cards(kb_path)

    assert len(cards) == 1
    card = cards[0]
    assert card.source_ref == "SRC-G461"
    assert card.metadata["published_at"] == "2024-01-15"
    assert card.metadata["document_revision"] == "Rev. 3"
    assert card.normalized_evidence["document_metadata"]["product_line"] == "G-Series"
    assert card.normalized_evidence["document_metadata_quality"] == "complete"
    assert card.normalized_evidence["temporal_quality"] == "sufficient"
    assert card.normalized_evidence["authority_quality"] == "sufficient"


def test_normalized_evidence_marks_incomplete_manufacturer_datasheet_metadata():
    normalized = normalize_fact_card_evidence(
        {
            "evidence_id": "fc-1",
            "source_ref": "doc-1",
            "source_type": "manufacturer_datasheet",
            "source_rank": 2,
            "topic": "Acme G461",
            "content": "PTFE grade G461 fuer Acme.",
            "metadata": {
                "material_family": "PTFE",
                "grade_name": "G461",
                "manufacturer_name": "Acme",
            },
        }
    )

    assert normalized["document_metadata_quality"] == "incomplete"
    assert "revision_or_publication_metadata" in normalized["document_metadata_missing"]
    assert normalized["temporal_quality"] == "unknown"
    assert normalized["temporal_reason"] == "temporal_document_metadata_missing"
    contract = normalized["datasheet_contract"]
    assert contract["document_identity"]["document_class"] == "manufacturer_datasheet"
    assert contract["document_metadata"]["grade_name"] == "G461"
    assert contract["audit"]["audit_gate_passed"] is False
    assert contract["selection_readiness"]["rfq_ready_eligible"] is False
    assert "audit_gate_not_passed" in contract["selection_readiness"]["blocking_reasons"]


def test_retrieve_rag_context_preserves_minimum_provenance_fields():
    hits = [
        {
            "id": "hit-1",
            "source": "doc-1",
            "text": "PTFE data",
            "score": 0.88,
            "metadata": {"topic": "PTFE", "manufacturer": "Acme"},
        }
    ]

    async def run_retrieval():
        with patch("app.agent.agent.knowledge.asyncio.to_thread", new=AsyncMock(return_value=hits)):
            return await retrieve_rag_context("ptfe")

    cards = asyncio.run(run_retrieval())

    assert len(cards) == 1
    card = cards[0]
    assert card.evidence_id == "hit-1"
    assert card.source_ref == "doc-1"
    assert card.topic == "PTFE"
    assert card.content == "PTFE data"
    assert card.retrieval_rank == 1
    assert card.retrieval_score == 0.88
    assert card.metadata == {"topic": "PTFE", "manufacturer": "Acme"}
    assert card.normalized_evidence["evidence_id"] == "hit-1"


def test_normalized_evidence_prefers_metadata_for_identity_and_limits():
    normalized = normalize_fact_card_evidence(
        {
            "evidence_id": "fc-1",
            "source_ref": "doc-1",
            "topic": "NBR sheet",
            "content": "NBR hat ein Temperaturlimit von max. 260 C und einen maximalen Druck von 80 bar.",
            "metadata": {
                "material_family": "PTFE",
                "grade_name": "G25",
                "manufacturer_name": "Acme",
                "temperature_max_c": 180,
                "pressure_max_bar": 40,
            },
        }
    )

    assert normalized["material_family"] == "PTFE"
    assert normalized["grade_name"] == "G25"
    assert normalized["manufacturer_name"] == "Acme"
    assert normalized["candidate_kind"] == "manufacturer_grade"
    assert normalized["normalized_temp_max"] == 180.0
    assert normalized["normalized_pressure_max"] == 40.0


def test_retrieve_rag_context_exposes_normalized_evidence_from_document_metadata():
    hits = [
        {
            "id": "hit-2",
            "source": "doc-2",
            "text": "PTFE grade G461 fuer Acme.",
            "score": 0.91,
            "metadata": {
                "topic": "Acme G461 sheet",
                "material_family": "PTFE",
                "grade_name": "G461",
                "manufacturer_name": "Acme",
                "source_type": "manufacturer_datasheet",
                "source_rank": 2,
                "source_version": "Rev. 4",
                "effective_date": "2025-03-01",
                "additional_metadata": {
                    "product_line": "G-Series",
                    "evidence_scope": ["grade_identity"],
                },
            },
        }
    ]

    async def run_retrieval():
        with patch("app.agent.agent.knowledge.asyncio.to_thread", new=AsyncMock(return_value=hits)):
            return await retrieve_rag_context("g461")

    cards = asyncio.run(run_retrieval())

    assert len(cards) == 1
    normalized = cards[0].normalized_evidence
    assert normalized["document_metadata"]["document_revision"] == "Rev. 4"
    assert normalized["document_metadata"]["published_at"] == "2025-03-01"
    assert normalized["document_metadata"]["product_line"] == "G-Series"
    assert normalized["temporal_quality"] == "sufficient"
    assert normalized["datasheet_contract"]["audit"]["audit_gate_passed"] is True
    assert normalized["datasheet_contract"]["selection_readiness"]["rfq_ready_eligible"] is True


def test_normalized_evidence_exposes_contract_blockers_for_distributor_and_marketing_sources():
    normalized = normalize_fact_card_evidence(
        {
            "evidence_id": "fc-2",
            "source_ref": "dist-1",
            "source_type": "distributor_sheet",
            "source_rank": 2,
            "topic": "Acme G461 distributor sheet",
            "content": "PTFE grade G461 fuer Acme.",
            "metadata": {
                "material_family": "PTFE",
                "grade_name": "G461",
                "manufacturer_name": "Acme",
                "published_at": "2024-01-15",
                "data_origin_type": "marketing_estimate",
            },
        }
    )

    contract = normalized["datasheet_contract"]
    blockers = contract["selection_readiness"]["blocking_reasons"]
    assert contract["document_identity"]["document_class"] == "distributor_sheet"
    assert contract["selection_readiness"]["max_specificity_level"] == "subfamily"
    assert contract["selection_readiness"]["compound_level_allowed"] is False
    assert "distributor_sheet_ceiling_without_manufacturer_grade_sheet" in blockers
    assert "marketing_estimate_never_release_relevant" in blockers


def test_bundled_kb_pilot_s7_exposes_real_document_metadata_but_remains_temporally_incomplete():
    cards = load_fact_cards(_BUNDLED_KB_PATH)
    pilot = next(card for card in cards if card.id == "PTFE-F-059")
    normalized = pilot.normalized_evidence

    assert normalized["document_metadata"]["source_ref"] == "S7"
    assert normalized["document_metadata"]["source_type"] == "manufacturer_datasheet"
    assert normalized["document_metadata"]["manufacturer_name"] == "Chemours"
    assert normalized["document_metadata"]["product_line"] == "Teflon PTFE 62 X"
    assert normalized["document_metadata"]["material_family"] == "PTFE"
    assert normalized["document_metadata_quality"] == "complete"
    assert normalized["temporal_quality"] == "unknown"


def test_bundled_kb_pilot_s7_stays_manufacturer_validation_required_in_agent_path():
    data = json.loads(_BUNDLED_KB_PATH.read_text(encoding="utf-8"))
    pilot = next(card for card in data["factcards"] if card["id"] == "PTFE-F-059")

    new_state = process_cycle_update(
        old_state=create_initial_state(),
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params={"temperature": 120.0},
        raw_claims=[
            {
                "statement": "Material ist PTFE, Grade 62 X, Hersteller Chemours. Medium ist Wasser.",
                "claim_type": "fact_observed",
                "confidence": 1.0,
                "source": "llm_submit_claim",
                "source_fact_ids": ["PTFE-F-059"],
            }
        ],
        relevant_fact_cards=[pilot],
    )

    assert new_state["normalized"]["identity_records"]["material_family"]["identity_class"] == "identity_unresolved"
    assert new_state["normalized"]["identity_records"]["material_family"]["mapping_reason"] == "temporal_metadata_missing"
    assert new_state["normalized"]["identity_records"]["manufacturer_name"]["identity_class"] == "identity_unresolved"
    assert new_state["normalized"]["identity_records"]["grade_name"]["identity_class"] == "identity_unresolved"
    assert new_state["governance"]["specificity_level"] == "family_only"
    assert new_state["governance"]["release_status"] == "manufacturer_validation_required"
    assert new_state["governance"]["rfq_admissibility"] == "provisional"
