from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PROMOTED_SOURCE_ORIGIN = "promoted_candidate_registry_v1"
TRANSITION_SOURCE_ORIGIN = "retrieval_fact_card_transition_adapter"


@dataclass(frozen=True)
class PromotedCandidateRegistryRecordDTO:
    registry_record_id: str
    material_family: str
    grade_name: str | None = None
    manufacturer_name: str | None = None
    candidate_kind: str = "manufacturer_grade"
    promotion_state: str = "promoted"
    registry_authority: str = "demo_only"
    source_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.registry_authority not in {"demo_only", "governed"}:
            raise ValueError("registry_authority must be demo_only or governed")


@dataclass(frozen=True)
class CandidateSourceAssessment:
    candidate_id: str
    source_origin: str
    qualified_eligible: bool
    source_gate_reasons: list[str]
    candidate_source_class: str
    registry_record: PromotedCandidateRegistryRecordDTO | None = None


@dataclass(frozen=True)
class MaterialQualificationCoreOutput:
    has_promoted_candidate_source: bool
    promoted_candidate_ids: list[str]
    qualified_candidate_ids: list[str]
    exploratory_candidate_ids: list[str]
    qualification_status: str
    output_blocked: bool


def load_promoted_candidate_registry_records() -> tuple[PromotedCandidateRegistryRecordDTO, ...]:
    return (
        PromotedCandidateRegistryRecordDTO(
            registry_record_id="registry-ptfe-g25-acme",
            material_family="PTFE",
            grade_name="G25",
            manufacturer_name="Acme",
            candidate_kind="manufacturer_grade",
            promotion_state="promoted",
            registry_authority="demo_only",
            source_refs=["registry:ptfe:g25:acme"],
            evidence_refs=[],
        ),
    )


def _candidate_key(candidate: dict[str, Any]) -> tuple[str, str | None, str | None]:
    return (
        str(candidate.get("material_family") or "").upper(),
        (str(candidate.get("grade_name")) if candidate.get("grade_name") else None),
        (str(candidate.get("manufacturer_name")) if candidate.get("manufacturer_name") else None),
    )


def resolve_candidate_registry_records_for_material_case(
    candidates: list[dict[str, Any]],
) -> dict[str, PromotedCandidateRegistryRecordDTO]:
    records = load_promoted_candidate_registry_records()
    resolved: dict[str, PromotedCandidateRegistryRecordDTO] = {}
    for candidate in candidates:
        ckey = _candidate_key(candidate)
        for record in records:
            rkey = (record.material_family.upper(), record.grade_name, record.manufacturer_name)
            if ckey == rkey:
                resolved[str(candidate.get("candidate_id"))] = record
    return resolved


def resolve_promoted_candidate_records_for_material_case(
    candidates: list[dict[str, Any]],
) -> dict[str, PromotedCandidateRegistryRecordDTO]:
    return {
        candidate_id: record
        for candidate_id, record in resolve_candidate_registry_records_for_material_case(candidates).items()
        if record.registry_authority == "governed" and record.promotion_state == "promoted"
    }


def classify_material_candidate_sources(
    *,
    candidates: list[dict[str, Any]],
    relevant_fact_cards: list[dict[str, Any]],
) -> list[CandidateSourceAssessment]:
    del relevant_fact_cards
    all_records = resolve_candidate_registry_records_for_material_case(candidates)
    promoted_records = resolve_promoted_candidate_records_for_material_case(candidates)
    assessments: list[CandidateSourceAssessment] = []
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id"))
        promoted_record = promoted_records.get(candidate_id)
        record = promoted_record or all_records.get(candidate_id)
        if promoted_record:
            assessments.append(
                CandidateSourceAssessment(
                    candidate_id=candidate_id,
                    source_origin=PROMOTED_SOURCE_ORIGIN,
                    qualified_eligible=True,
                    source_gate_reasons=[],
                    candidate_source_class="promoted_candidate_input",
                    registry_record=promoted_record,
                )
            )
        else:
            assessments.append(
                CandidateSourceAssessment(
                    candidate_id=candidate_id,
                    source_origin=TRANSITION_SOURCE_ORIGIN,
                    qualified_eligible=False,
                    source_gate_reasons=["candidate_source_not_promoted_registry"],
                    candidate_source_class="exploratory_candidate_input",
                    registry_record=record,
                )
            )
    return assessments


def evaluate_material_qualification_core(
    *,
    relevant_fact_cards: list[dict[str, Any]],
    asserted_state: dict[str, Any],
    governance_state: dict[str, Any],
) -> MaterialQualificationCoreOutput:
    del asserted_state, governance_state
    candidates: list[dict[str, Any]] = []
    for card in relevant_fact_cards:
        metadata = card.get("metadata") or {}
        family = metadata.get("material_family")
        if not family:
            continue
        candidates.append(
            {
                "candidate_id": "::".join(
                    part.lower()
                    for part in [family, metadata.get("grade_name"), metadata.get("manufacturer_name")]
                    if part
                ),
                "material_family": family,
                "grade_name": metadata.get("grade_name"),
                "manufacturer_name": metadata.get("manufacturer_name"),
                "candidate_kind": "manufacturer_grade" if metadata.get("grade_name") and metadata.get("manufacturer_name") else "family",
                "evidence_refs": [card.get("evidence_id") or card.get("id")] if card.get("evidence_id") or card.get("id") else [],
            }
        )
    assessments = classify_material_candidate_sources(candidates=candidates, relevant_fact_cards=relevant_fact_cards)
    promoted_candidate_ids = [item.candidate_id for item in assessments if item.source_origin == PROMOTED_SOURCE_ORIGIN]
    exploratory_candidate_ids = [item.candidate_id for item in assessments if item.source_origin != PROMOTED_SOURCE_ORIGIN]
    qualified_candidate_ids = [item.candidate_id for item in assessments if item.qualified_eligible]
    has_promoted_candidate_source = bool(promoted_candidate_ids)
    return MaterialQualificationCoreOutput(
        has_promoted_candidate_source=has_promoted_candidate_source,
        promoted_candidate_ids=promoted_candidate_ids,
        qualified_candidate_ids=qualified_candidate_ids,
        exploratory_candidate_ids=exploratory_candidate_ids,
        qualification_status="qualified_candidate_source_available" if has_promoted_candidate_source else "exploratory_candidate_source_only",
        output_blocked=not has_promoted_candidate_source,
    )


def build_material_provider_contract_snapshot(
    *,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    all_records = resolve_candidate_registry_records_for_material_case(candidates)
    promoted_records = resolve_promoted_candidate_records_for_material_case(candidates)
    return {
        "registry_records": [
            {
                "candidate_id": candidate_id,
                "registry_record_id": record.registry_record_id,
                "registry_authority": record.registry_authority,
            }
            for candidate_id, record in all_records.items()
        ],
        "matched_promoted_registry_record_ids": [record.registry_record_id for record in promoted_records.values()],
    }
