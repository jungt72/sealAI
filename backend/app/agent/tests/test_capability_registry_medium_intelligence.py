from __future__ import annotations

from typing import Any, Mapping

from app.agent.capability_registry import (
    CapabilityId,
    CapabilityInput,
    build_default_capability_registry,
)


FORBIDDEN_TERMS = (
    "final freigegeben",
    "freigegeben",
    "garantiert geeignet",
    "garantiert beständig",
    "garantiert bestaendig",
    "final approved",
    "approved solution",
    "certified recommendation",
    "zertifiziert",
    "beste Lösung",
    "beste Loesung",
)


def test_registry_lists_medium_intelligence() -> None:
    registry = build_default_capability_registry()

    descriptors = registry.list_capabilities()

    assert [descriptor.capability_id for descriptor in descriptors] == [
        CapabilityId.MEDIUM_INTELLIGENCE
    ]
    assert descriptors[0].as_dict()["capability_id"] == "medium_intelligence"


def test_known_hlp46_returns_registry_grounded_context() -> None:
    registry = build_default_capability_registry()

    result = registry.invoke("medium_intelligence", {"medium_query": "HLP46"})

    assert result.capability_id is CapabilityId.MEDIUM_INTELLIGENCE
    assert result.validation_status == "registry_grounded"
    assert result.confidence == "high"
    assert result.candidate_facts["matched_registry_entry_id"] == "med-hlp46"
    assert result.candidate_facts["chemical_class"]["value"] == "hydrocarbon_oil"
    assert result.context_notes
    assert any("Anfragebasis" in note for note in result.rfq_relevance_notes)


def test_unknown_medium_remains_low_confidence_and_unvalidated() -> None:
    registry = build_default_capability_registry()

    result = registry.invoke(
        CapabilityId.MEDIUM_INTELLIGENCE,
        CapabilityInput(
            capability_id=CapabilityId.MEDIUM_INTELLIGENCE,
            payload={"medium_query": "mystery medium"},
        ),
    )

    assert result.validation_status == "unvalidated"
    assert result.confidence == "low"
    assert "medium_not_registry_grounded" in result.risk_notes
    assert "registry_or_datasheet_evidence" in result.missing_field_hints


def test_output_is_bounded_and_not_answer_markdown() -> None:
    registry = build_default_capability_registry()

    result = registry.invoke("medium_intelligence", {"medium_query": "HLP46"})

    payload = result.as_dict()
    assert set(payload) == {
        "capability_id",
        "capability_kind",
        "input_summary",
        "candidate_facts",
        "context_notes",
        "risk_notes",
        "missing_field_hints",
        "rfq_relevance_notes",
        "evidence_refs",
        "confidence",
        "validation_status",
        "safety",
        "output_contract_version",
    }
    assert "answer_markdown" not in payload
    assert "reply" not in payload
    assert "proposed_case_delta" not in payload


def test_safety_flags_forbid_mutation_truth_dispatch_contact_and_export() -> None:
    registry = build_default_capability_registry()

    result = registry.invoke("medium_intelligence", {"medium_query": "HLP46"})
    safety = result.safety

    assert safety.mutates_case_state is False
    assert safety.creates_engineering_truth is False
    assert safety.final_approval_claim_allowed is False
    assert safety.dispatch_allowed is False
    assert safety.external_contact_allowed is False
    assert safety.export_allowed is False
    assert result.as_dict()["safety"] == {
        "mutates_case_state": False,
        "creates_engineering_truth": False,
        "final_approval_claim_allowed": False,
        "dispatch_allowed": False,
        "external_contact_allowed": False,
        "export_allowed": False,
    }


def test_capability_output_contains_no_forbidden_approval_or_suitability_wording() -> None:
    registry = build_default_capability_registry()

    known = registry.invoke("medium_intelligence", {"medium_query": "HLP46"})
    unknown = registry.invoke("medium_intelligence", {"medium_query": "mystery medium"})

    text = f"{_flatten_text(known.as_dict())} {_flatten_text(unknown.as_dict())}"
    lowered = text.casefold()
    for term in FORBIDDEN_TERMS:
        assert term.casefold() not in lowered


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return " ".join(
            f"{_flatten_text(key)} {_flatten_text(item)}"
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_text(item) for item in value)
    if value is None:
        return ""
    return str(value)
