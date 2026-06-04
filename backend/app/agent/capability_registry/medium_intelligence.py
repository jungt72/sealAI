from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.agent.capability_registry.contracts import (
    CapabilityDescriptor,
    CapabilityId,
    CapabilityInput,
    CapabilityKind,
    CapabilityResult,
    assert_capability_output_safe,
)
from app.services.medium_intelligence_service import (
    MediumIntelligenceResult,
    MediumIntelligenceService,
    ProvenanceTier,
    PropertyWithProvenance,
)


@dataclass(frozen=True, slots=True)
class MediumIntelligenceCapability:
    service: MediumIntelligenceService = field(
        default_factory=MediumIntelligenceService
    )

    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            capability_id=CapabilityId.MEDIUM_INTELLIGENCE,
            kind=CapabilityKind.DOMAIN_CONTEXT,
            name="Medium Intelligence",
            version="medium_intelligence_capability_v1",
            description=(
                "Read-only medium context adapter for candidate facts, risk notes, "
                "and Anfragebasis relevance hints."
            ),
        )

    def run(self, capability_input: CapabilityInput) -> CapabilityResult:
        payload = dict(capability_input.payload)
        medium_query = str(
            payload.get("medium_query") or payload.get("medium") or ""
        ).strip()
        if not medium_query:
            result = CapabilityResult(
                capability_id=CapabilityId.MEDIUM_INTELLIGENCE,
                capability_kind=CapabilityKind.DOMAIN_CONTEXT,
                input_summary="medium_query missing",
                risk_notes=("medium_query_missing",),
                missing_field_hints=("medium_query",),
                rfq_relevance_notes=(
                    "Medium context can only support the Anfragebasis after a medium is provided.",
                ),
                confidence="low",
                validation_status="missing_input",
            )
            assert_capability_output_safe(result)
            return result

        service_result = self.service.get_medium_intelligence(
            medium_query=medium_query,
            temperature_c=_optional_float(payload.get("temperature_c")),
            application_context=_optional_text(payload.get("application_context")),
        )
        result = _adapt_medium_result(medium_query, service_result)
        assert_capability_output_safe(result)
        return result


def _adapt_medium_result(
    medium_query: str,
    service_result: MediumIntelligenceResult,
) -> CapabilityResult:
    candidate_facts = _candidate_facts(service_result)
    context_notes = tuple(
        note
        for note in (
            _safe_note(service_result.medium_summary),
            _safe_note(service_result.material_selection_rationale),
        )
        if note
    )
    missing_field_hints: tuple[str, ...] = ()
    if service_result.provenance_tier is not ProvenanceTier.REGISTRY:
        missing_field_hints = ("registry_or_datasheet_evidence",)

    return CapabilityResult(
        capability_id=CapabilityId.MEDIUM_INTELLIGENCE,
        capability_kind=CapabilityKind.DOMAIN_CONTEXT,
        input_summary=f"medium_query={medium_query}",
        candidate_facts=candidate_facts,
        context_notes=context_notes,
        risk_notes=tuple(str(note) for note in service_result.risk_notes if note),
        missing_field_hints=missing_field_hints,
        rfq_relevance_notes=(
            "Medium context may inform open points in a manufacturer-review Anfragebasis.",
            "Consent remains required before any RFQ export or external sharing.",
        ),
        evidence_refs=(),
        confidence=service_result.confidence_level,
        validation_status=_validation_status(service_result.provenance_tier),
    )


def _candidate_facts(result: MediumIntelligenceResult) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    entry = result.matched_registry_entry
    if entry is not None:
        facts.update(
            {
                "matched_registry_entry_id": entry.medium_id,
                "canonical_name": entry.canonical_name,
                "display_name": dict(entry.display_name),
                "registry_version": entry.version,
            }
        )
    for key, prop in result.llm_synthesized_properties.items():
        facts[str(key)] = _property_payload(prop)
    recommendations = [
        {
            "compound_family": item.compound_family,
            "rationale": _safe_note(item.rationale),
            "confidence": item.confidence,
        }
        for item in result.compound_recommendations
    ]
    if recommendations:
        facts["compound_recommendations"] = recommendations
    return facts


def _property_payload(prop: PropertyWithProvenance) -> dict[str, Any]:
    return {
        "value": _jsonable(prop.value),
        "provenance_tier": prop.provenance_tier.value,
        "confidence": prop.confidence,
        "disclaimer": _safe_note(prop.disclaimer),
    }


def _validation_status(provenance_tier: ProvenanceTier) -> str:
    if provenance_tier is ProvenanceTier.REGISTRY:
        return "registry_grounded"
    if provenance_tier is ProvenanceTier.LLM_SYNTHESIS:
        return "unvalidated"
    return "candidate"


def _jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _safe_note(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text.replace(
        "final manufacturer review remains required",
        "manufacturer review remains required",
    )


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
