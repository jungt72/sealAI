from __future__ import annotations

"""Blueprint Sections 02/06/08/12: deterministic material qualification core.

This foundation keeps the critical material gate path outside LLM and UI
projection logic. It produces an auditable suitability-space assessment only;
it never emits a silent final material release.
"""

from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.agent.domain.material import MaterialPhysicalProfile, MaterialValidator, normalize_fact_card_evidence
from app.agent.domain.parameters import PhysicalParameter

TRANSITION_SOURCE_ADAPTER = "material_candidate_source_adapter_v1"
TRANSITION_SOURCE_ORIGIN = "retrieval_fact_card_transition_adapter"
PROMOTED_SOURCE_ADAPTER = "promoted_candidate_registry_provider_v1"
PROMOTED_SOURCE_ORIGIN = "promoted_candidate_registry_v1"
_PROMOTED_REGISTRY_PATH = Path(__file__).with_name("promoted_candidate_registry_v1.json")


class MaterialCoreCandidateDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    candidate_kind: str | None = None
    material_family: str
    filler_hint: str | None = None
    grade_name: str | None = None
    manufacturer_name: str | None = None
    evidence_refs: List[str] = Field(default_factory=list)


class MaterialCandidateAssessmentDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    viability_status: str
    block_reason: str | None = None
    candidate_source_class: str
    candidate_source_quality: str
    qualified_eligible: bool
    supporting_evidence_refs: List[str] = Field(default_factory=list)
    source_gate_reasons: List[str] = Field(default_factory=list)
    open_points: List[str] = Field(default_factory=list)


class MaterialCandidateSourceAssessmentDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    candidate_source_class: str
    candidate_source_quality: str
    identity_specificity: str
    source_origin: str
    source_adapter: str
    registry_record_id: str | None = None
    promotion_state: str | None = None
    qualified_eligible: bool
    evidence_refs: List[str] = Field(default_factory=list)
    source_gate_reasons: List[str] = Field(default_factory=list)


class MaterialCandidateSourceRecordDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    candidate_kind: str | None = None
    material_family: str
    filler_hint: str | None = None
    grade_name: str | None = None
    manufacturer_name: str | None = None
    evidence_refs: List[str] = Field(default_factory=list)
    source_refs: List[str] = Field(default_factory=list)
    source_adapter: str
    source_origin: str
    candidate_source_class: str
    candidate_source_quality: str
    identity_specificity: str
    authority_quality: str
    evidence_quality: str
    registry_record_id: str | None = None
    promotion_state: str | None = None
    qualified_eligible: bool
    source_gate_reasons: List[str] = Field(default_factory=list)


class PromotedQualifiedCandidateRecordDTO(MaterialCandidateSourceRecordDTO):
    """Blueprint Sections 06/08/12: explicit governed candidate source contract for qualified path input."""

    source_adapter: str = Field(default=PROMOTED_SOURCE_ADAPTER)
    source_origin: str = Field(default=PROMOTED_SOURCE_ORIGIN)
    registry_record_id: str
    promotion_state: str = Field(default="promoted")
    qualified_eligible: bool = Field(default=True)


class PromotedCandidateRegistryRecordDTO(BaseModel):
    """Blueprint Sections 06/08/12: governed promoted candidate source record.

    registry_authority governs whether this entry may act as a promoted trust anchor
    in qualification-relevant paths. Intended values:
      "governed"  — real registry entry with verified manufacturer provenance; eligible
                    for trust-granting promotion via resolve_promoted_candidate_records_for_material_case()
      "demo_only" — placeholder / non-production entry; loaded for auditability but
                    excluded from all trust-granting and qualification paths

    Default is "demo_only" — explicit opt-in is required to reach governed status.
    """

    model_config = ConfigDict(extra="forbid")

    registry_record_id: str
    material_family: str
    grade_name: str
    manufacturer_name: str
    candidate_kind: str = Field(default="manufacturer_grade")
    filler_hint: str | None = None
    promotion_state: str = Field(default="promoted")
    # 0B.1: governance authority — safe default is "demo_only" (explicit opt-in required)
    registry_authority: str = Field(
        default="demo_only",
        description="0B.1: 'governed' = real entry; 'demo_only' = non-production placeholder.",
    )
    source_refs: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)

    @property
    def candidate_id(self) -> str:
        return _candidate_id(
            self.material_family,
            self.filler_hint,
            self.grade_name,
            self.manufacturer_name,
        )


class MaterialProviderContractSnapshotDTO(BaseModel):
    """Blueprint Sections 02/08/12: auditable provider contract snapshot for case invalidation."""

    model_config = ConfigDict(extra="forbid")

    provider_source_adapter: str = Field(default=PROMOTED_SOURCE_ADAPTER)
    provider_source_origin: str = Field(default=PROMOTED_SOURCE_ORIGIN)
    matched_registry_record_ids: List[str] = Field(default_factory=list)
    matched_promoted_registry_record_ids: List[str] = Field(default_factory=list)
    matched_candidate_ids: List[str] = Field(default_factory=list)
    matched_promoted_candidate_ids: List[str] = Field(default_factory=list)
    registry_records: List[Dict[str, Any]] = Field(default_factory=list)
    has_promoted_registry_match: bool = False


class MaterialCandidateSourceAdapterOutputDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_adapter: str
    source_origin: str
    source_origins: List[str] = Field(default_factory=list)
    candidate_source_records: List[MaterialCandidateSourceRecordDTO] = Field(default_factory=list)
    qualified_candidate_records: List[MaterialCandidateSourceRecordDTO] = Field(default_factory=list)
    exploratory_candidate_records: List[MaterialCandidateSourceRecordDTO] = Field(default_factory=list)
    promoted_candidate_records: List[MaterialCandidateSourceRecordDTO] = Field(default_factory=list)
    transition_candidate_records: List[MaterialCandidateSourceRecordDTO] = Field(default_factory=list)
    evidence_basis: List[str] = Field(default_factory=list)


class MaterialQualificationCoreOutputDTO(BaseModel):
    model_config = ConfigDict(extra="ignore")

    qualification_status: str
    release_status: str
    rfq_admissibility: str
    specificity_level: str
    output_blocked: bool
    viable_candidate_ids: List[str] = Field(default_factory=list)
    qualified_viable_candidate_ids: List[str] = Field(default_factory=list)
    exploratory_candidate_ids: List[str] = Field(default_factory=list)
    promoted_candidate_ids: List[str] = Field(default_factory=list)
    transition_candidate_ids: List[str] = Field(default_factory=list)
    candidate_source_origins: List[str] = Field(default_factory=list)
    has_promoted_candidate_source: bool = False
    blocked_by_candidate_source: List[Dict[str, str]] = Field(default_factory=list)
    blocked_candidates: List[Dict[str, str]] = Field(default_factory=list)
    candidate_source_assessments: List[MaterialCandidateSourceAssessmentDTO] = Field(default_factory=list)
    candidate_source_records: List[MaterialCandidateSourceRecordDTO] = Field(default_factory=list)
    candidate_assessments: List[MaterialCandidateAssessmentDTO] = Field(default_factory=list)
    missing_required_inputs: List[str] = Field(default_factory=list)
    open_points: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    deterministic_gate_summary: Dict[str, Any] = Field(default_factory=dict)


def evaluate_material_qualification_core(
    *,
    candidates: Optional[List[Dict[str, Any]]] = None,
    candidate_source_records: Optional[List[Dict[str, Any] | MaterialCandidateSourceRecordDTO]] = None,
    relevant_fact_cards: List[Dict[str, Any]],
    asserted_state: Optional[Dict[str, Any]] = None,
    governance_state: Optional[Dict[str, Any]] = None,
) -> MaterialQualificationCoreOutputDTO:
    asserted_state = asserted_state or {}
    governance_state = governance_state or {}

    cards_by_evidence_id = _index_fact_cards(relevant_fact_cards)
    adapter_output: MaterialCandidateSourceAdapterOutputDTO | None = None
    if candidate_source_records is not None:
        typed_source_records = [
            record
            if isinstance(record, MaterialCandidateSourceRecordDTO)
            else MaterialCandidateSourceRecordDTO.model_validate(record)
            for record in candidate_source_records
        ]
    else:
        adapter_output = build_material_candidate_source_adapter(
            relevant_fact_cards=relevant_fact_cards,
            seed_candidates=candidates or [],
        )
        typed_source_records = list(adapter_output.candidate_source_records)

    typed_candidates = [
        MaterialCoreCandidateDTO(
            candidate_id=record.candidate_id,
            candidate_kind=record.candidate_kind,
            material_family=record.material_family,
            filler_hint=record.filler_hint,
            grade_name=record.grade_name,
            manufacturer_name=record.manufacturer_name,
            evidence_refs=list(record.evidence_refs),
        )
        for record in typed_source_records
    ]
    source_boundary = [
        MaterialCandidateSourceAssessmentDTO(
            candidate_id=record.candidate_id,
            candidate_source_class=record.candidate_source_class,
            candidate_source_quality=record.candidate_source_quality,
            identity_specificity=record.identity_specificity,
            source_origin=record.source_origin,
            source_adapter=record.source_adapter,
            qualified_eligible=record.qualified_eligible,
            evidence_refs=list(record.evidence_refs),
            source_gate_reasons=list(record.source_gate_reasons),
        )
        for record in typed_source_records
    ]
    source_by_candidate_id = {
        assessment.candidate_id: assessment for assessment in source_boundary
    }
    temperature = _normalize_temperature(asserted_state)
    pressure = _normalize_pressure(asserted_state)

    candidate_assessments: List[MaterialCandidateAssessmentDTO] = []
    viable_candidate_ids: List[str] = []
    qualified_viable_candidate_ids: List[str] = []
    exploratory_candidate_ids: List[str] = []
    promoted_candidate_ids = [
        record.candidate_id for record in typed_source_records if record.source_origin == PROMOTED_SOURCE_ORIGIN
    ]
    transition_candidate_ids = [
        record.candidate_id for record in typed_source_records if record.source_origin == TRANSITION_SOURCE_ORIGIN
    ]
    candidate_source_origins = list(dict.fromkeys(record.source_origin for record in typed_source_records))
    blocked_by_candidate_source: List[Dict[str, str]] = []
    blocked_candidates: List[Dict[str, str]] = []
    evidence_refs: List[str] = []
    missing_required_inputs: List[str] = []
    open_points: List[str] = []

    for candidate in typed_candidates:
        assessment = _assess_candidate(
            candidate=candidate,
            cards_by_evidence_id=cards_by_evidence_id,
            temperature=temperature,
            pressure=pressure,
            source_assessment=source_by_candidate_id.get(candidate.candidate_id),
        )
        candidate_assessments.append(assessment)
        evidence_refs.extend(assessment.supporting_evidence_refs)
        open_points.extend(assessment.open_points)
        if assessment.viability_status == "viable":
            viable_candidate_ids.append(candidate.candidate_id)
            if assessment.qualified_eligible:
                qualified_viable_candidate_ids.append(candidate.candidate_id)
            else:
                exploratory_candidate_ids.append(candidate.candidate_id)
                blocked_by_candidate_source.append(
                    {
                        "candidate_id": candidate.candidate_id,
                        "block_reason": "blocked_candidate_source_boundary",
                    }
                )
        else:
            blocked_candidates.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "block_reason": assessment.block_reason or assessment.viability_status,
                }
            )
        if assessment.block_reason == "blocked_missing_required_inputs" and assessment.qualified_eligible:
            if temperature is None:
                missing_required_inputs.append("temperature_c")
            if pressure is None and any(
                _profile_requires_pressure(cards_by_evidence_id.get(ref))
                for ref in candidate.evidence_refs
            ):
                missing_required_inputs.append("pressure_bar")

    qualification_status = "no_evidence_bound_candidates"
    release_status = "inadmissible"
    rfq_admissibility = "inadmissible"
    specificity_level = str(governance_state.get("specificity_level") or "family_only")
    output_blocked = True

    if not typed_candidates:
        qualification_status = "no_evidence_bound_candidates"
    elif not source_boundary:
        qualification_status = "no_evidence_bound_candidates"
    elif not any(assessment.qualified_eligible for assessment in source_boundary):
        qualification_status = "exploratory_candidate_source_only"
    elif missing_required_inputs:
        qualification_status = "insufficient_input"
    elif not qualified_viable_candidate_ids:
        qualification_status = "no_viable_candidates"
    else:
        release_status = str(governance_state.get("release_status") or "inadmissible")
        rfq_admissibility = str(governance_state.get("rfq_admissibility") or "inadmissible")

        if _governance_has_hard_block(governance_state):
            qualification_status = "governance_blocked"
        elif specificity_level != "compound_required":
            qualification_status = "manufacturer_validation_required"
            output_blocked = True
            open_points.append("compound_or_manufacturer_grade_not_deterministically_confirmed")
        elif release_status == "rfq_ready" and rfq_admissibility == "ready":
            qualification_status = "neutral_rfq_basis_ready"
            output_blocked = False
        else:
            qualification_status = "manufacturer_validation_required"
            output_blocked = True

    if qualification_status in {
        "no_evidence_bound_candidates",
        "exploratory_candidate_source_only",
        "insufficient_input",
        "no_viable_candidates",
        "governance_blocked",
    }:
        output_blocked = True
        if qualification_status == "insufficient_input":
            release_status = "inadmissible"
            rfq_admissibility = "inadmissible"
        elif qualification_status == "governance_blocked":
            release_status = str(governance_state.get("release_status") or "inadmissible")
            rfq_admissibility = str(governance_state.get("rfq_admissibility") or "inadmissible")
        elif qualification_status == "exploratory_candidate_source_only":
            release_status = "manufacturer_validation_required"
            rfq_admissibility = "provisional"
            open_points.append("candidate_source_boundary_requires_manufacturer_grade")
        else:
            release_status = "inadmissible"
            rfq_admissibility = "inadmissible"

    return MaterialQualificationCoreOutputDTO(
        qualification_status=qualification_status,
        release_status=release_status,
        rfq_admissibility=rfq_admissibility,
        specificity_level=specificity_level,
        output_blocked=output_blocked,
        viable_candidate_ids=list(dict.fromkeys(viable_candidate_ids)),
        qualified_viable_candidate_ids=list(dict.fromkeys(qualified_viable_candidate_ids)),
        exploratory_candidate_ids=list(dict.fromkeys(exploratory_candidate_ids)),
        promoted_candidate_ids=list(dict.fromkeys(promoted_candidate_ids)),
        transition_candidate_ids=list(dict.fromkeys(transition_candidate_ids)),
        candidate_source_origins=candidate_source_origins,
        has_promoted_candidate_source=bool(promoted_candidate_ids),
        blocked_by_candidate_source=blocked_by_candidate_source,
        blocked_candidates=blocked_candidates,
        candidate_source_assessments=source_boundary,
        candidate_source_records=typed_source_records,
        candidate_assessments=candidate_assessments,
        missing_required_inputs=list(dict.fromkeys(missing_required_inputs)),
        open_points=list(dict.fromkeys(open_points)),
        evidence_refs=list(dict.fromkeys(evidence_refs)),
        deterministic_gate_summary={
            "candidate_count": len(typed_candidates),
            "viable_candidate_count": len(viable_candidate_ids),
            "qualified_viable_candidate_count": len(qualified_viable_candidate_ids),
            "exploratory_candidate_count": len(exploratory_candidate_ids),
            "promoted_candidate_count": len(promoted_candidate_ids),
            "transition_candidate_count": len(transition_candidate_ids),
            "candidate_source_origins": candidate_source_origins,
            "temperature_input_present": temperature is not None,
            "pressure_input_present": pressure is not None,
            "governance_release_status": governance_state.get("release_status"),
            "governance_rfq_admissibility": governance_state.get("rfq_admissibility"),
            "governance_specificity_level": specificity_level,
            "candidate_source_adapter": (
                adapter_output.source_adapter
                if adapter_output is not None
                else TRANSITION_SOURCE_ADAPTER
            ),
        },
    )


def build_material_candidate_source_adapter(
    *,
    relevant_fact_cards: List[Dict[str, Any]],
    seed_candidates: Optional[List[Dict[str, Any]]] = None,
) -> MaterialCandidateSourceAdapterOutputDTO:
    """Blueprint Sections 02/06/08/12: adapter between retrieval evidence and governed candidate input."""

    aggregated = _aggregate_candidate_inputs_from_evidence(
        relevant_fact_cards=relevant_fact_cards,
        seed_candidates=seed_candidates or [],
    )
    source_assessments = classify_material_candidate_sources(
        candidates=aggregated,
        relevant_fact_cards=relevant_fact_cards,
    )
    source_by_candidate_id = {assessment.candidate_id: assessment for assessment in source_assessments}
    cards_by_evidence_id = _index_fact_cards(relevant_fact_cards)

    candidate_source_records: List[MaterialCandidateSourceRecordDTO] = []
    for candidate in aggregated:
        assessment = source_by_candidate_id[candidate.candidate_id]
        supporting_cards = [
            cards_by_evidence_id[evidence_ref]
            for evidence_ref in candidate.evidence_refs
            if evidence_ref in cards_by_evidence_id
        ]
        source_refs = list(
            dict.fromkeys(str(card.get("source_ref")) for card in supporting_cards if card.get("source_ref"))
        )
        record_kwargs = dict(
            candidate_id=candidate.candidate_id,
            candidate_kind=candidate.candidate_kind,
            material_family=candidate.material_family,
            filler_hint=candidate.filler_hint,
            grade_name=candidate.grade_name,
            manufacturer_name=candidate.manufacturer_name,
            evidence_refs=list(candidate.evidence_refs),
            source_refs=source_refs,
            source_adapter=assessment.source_adapter,
            source_origin=assessment.source_origin,
            candidate_source_class=assessment.candidate_source_class,
            candidate_source_quality=assessment.candidate_source_quality,
            identity_specificity=assessment.identity_specificity,
            authority_quality=_rollup_normalized_quality(supporting_cards, "authority_quality"),
            evidence_quality=_rollup_normalized_quality(supporting_cards, "evidence_quality"),
            registry_record_id=assessment.registry_record_id,
            promotion_state=assessment.promotion_state,
            qualified_eligible=assessment.qualified_eligible,
            source_gate_reasons=list(assessment.source_gate_reasons),
        )
        if assessment.source_origin == PROMOTED_SOURCE_ORIGIN and record_kwargs["registry_record_id"]:
            candidate_source_records.append(PromotedQualifiedCandidateRecordDTO(**record_kwargs))
        else:
            candidate_source_records.append(MaterialCandidateSourceRecordDTO(**record_kwargs))

    qualified_records = [record for record in candidate_source_records if record.qualified_eligible]
    exploratory_records = [record for record in candidate_source_records if not record.qualified_eligible]
    promoted_records = [record for record in candidate_source_records if record.source_origin == PROMOTED_SOURCE_ORIGIN]
    transition_records = [record for record in candidate_source_records if record.source_origin == TRANSITION_SOURCE_ORIGIN]
    evidence_basis = list(
        dict.fromkeys(
            evidence_ref
            for record in candidate_source_records
            for evidence_ref in record.evidence_refs
        )
    )
    source_origins = list(dict.fromkeys(record.source_origin for record in candidate_source_records))
    return MaterialCandidateSourceAdapterOutputDTO(
        source_adapter=(
            PROMOTED_SOURCE_ADAPTER if source_origins == [PROMOTED_SOURCE_ORIGIN] else TRANSITION_SOURCE_ADAPTER
        ),
        source_origin=source_origins[0] if len(source_origins) == 1 else "mixed_candidate_source_boundary_v1",
        source_origins=source_origins,
        candidate_source_records=candidate_source_records,
        qualified_candidate_records=qualified_records,
        exploratory_candidate_records=exploratory_records,
        promoted_candidate_records=promoted_records,
        transition_candidate_records=transition_records,
        evidence_basis=evidence_basis,
    )


def _assess_candidate(
    *,
    candidate: MaterialCoreCandidateDTO,
    cards_by_evidence_id: Dict[str, Dict[str, Any]],
    temperature: PhysicalParameter | None,
    pressure: PhysicalParameter | None,
    source_assessment: MaterialCandidateSourceAssessmentDTO | None,
) -> MaterialCandidateAssessmentDTO:
    source_assessment = source_assessment or MaterialCandidateSourceAssessmentDTO(
        candidate_id=candidate.candidate_id,
        candidate_source_class="exploratory_candidate_input",
        candidate_source_quality="insufficient",
        identity_specificity=candidate.candidate_kind or "family",
        source_origin=TRANSITION_SOURCE_ORIGIN,
        source_adapter=TRANSITION_SOURCE_ADAPTER,
        qualified_eligible=False,
        evidence_refs=list(candidate.evidence_refs),
        source_gate_reasons=["candidate_source_boundary_missing"],
    )
    supporting_profiles: List[tuple[str, MaterialPhysicalProfile]] = []
    for evidence_ref in candidate.evidence_refs:
        card = cards_by_evidence_id.get(evidence_ref)
        if not card:
            continue
        profile = MaterialPhysicalProfile.from_fact_card(card)
        if profile and profile.material_id.upper() == candidate.material_family.upper():
            supporting_profiles.append((evidence_ref, profile))

    if not supporting_profiles:
        return MaterialCandidateAssessmentDTO(
            candidate_id=candidate.candidate_id,
            viability_status="blocked_no_evidence",
            block_reason="blocked_no_evidence",
            candidate_source_class=source_assessment.candidate_source_class,
            candidate_source_quality=source_assessment.candidate_source_quality,
            qualified_eligible=source_assessment.qualified_eligible,
            supporting_evidence_refs=[],
            source_gate_reasons=list(source_assessment.source_gate_reasons),
            open_points=["no_evidence_bound_material_profile"],
        )

    requires_pressure = any(getattr(profile, "pressure_max", None) is not None for _, profile in supporting_profiles)
    if temperature is None or (requires_pressure and pressure is None):
        missing = ["temperature_c"] if temperature is None else []
        if requires_pressure and pressure is None:
            missing.append("pressure_bar")
        return MaterialCandidateAssessmentDTO(
            candidate_id=candidate.candidate_id,
            viability_status="blocked_missing_required_inputs",
            block_reason="blocked_missing_required_inputs",
            candidate_source_class=source_assessment.candidate_source_class,
            candidate_source_quality=source_assessment.candidate_source_quality,
            qualified_eligible=source_assessment.qualified_eligible,
            supporting_evidence_refs=[ref for ref, _ in supporting_profiles],
            source_gate_reasons=list(source_assessment.source_gate_reasons),
            open_points=missing,
        )

    if any(not MaterialValidator(profile).validate_temperature(temperature) for _, profile in supporting_profiles):
        return MaterialCandidateAssessmentDTO(
            candidate_id=candidate.candidate_id,
            viability_status="blocked_temperature_conflict",
            block_reason="blocked_temperature_conflict",
            candidate_source_class=source_assessment.candidate_source_class,
            candidate_source_quality=source_assessment.candidate_source_quality,
            qualified_eligible=source_assessment.qualified_eligible,
            supporting_evidence_refs=[ref for ref, _ in supporting_profiles],
            source_gate_reasons=list(source_assessment.source_gate_reasons),
            open_points=["temperature_outside_evidence_bound_limit"],
        )

    if any(
        getattr(profile, "pressure_max", None) is not None
        and not MaterialValidator(profile).validate_pressure(pressure)
        for _, profile in supporting_profiles
    ):
        return MaterialCandidateAssessmentDTO(
            candidate_id=candidate.candidate_id,
            viability_status="blocked_pressure_conflict",
            block_reason="blocked_pressure_conflict",
            candidate_source_class=source_assessment.candidate_source_class,
            candidate_source_quality=source_assessment.candidate_source_quality,
            qualified_eligible=source_assessment.qualified_eligible,
            supporting_evidence_refs=[ref for ref, _ in supporting_profiles],
            source_gate_reasons=list(source_assessment.source_gate_reasons),
            open_points=["pressure_outside_evidence_bound_limit"],
        )

    open_points: List[str] = []
    if candidate.candidate_kind != "manufacturer_grade":
        open_points.append("compound_identity_not_confirmed")
    if not candidate.manufacturer_name:
        open_points.append("manufacturer_name_not_confirmed")

    return MaterialCandidateAssessmentDTO(
        candidate_id=candidate.candidate_id,
        viability_status="viable",
        block_reason=None,
        candidate_source_class=source_assessment.candidate_source_class,
        candidate_source_quality=source_assessment.candidate_source_quality,
        qualified_eligible=source_assessment.qualified_eligible,
        supporting_evidence_refs=[ref for ref, _ in supporting_profiles],
        source_gate_reasons=list(source_assessment.source_gate_reasons),
        open_points=open_points,
    )


def classify_material_candidate_sources(
    *,
    candidates: List[MaterialCoreCandidateDTO | Dict[str, Any]],
    relevant_fact_cards: List[Dict[str, Any]],
) -> List[MaterialCandidateSourceAssessmentDTO]:
    cards_by_evidence_id = _index_fact_cards(relevant_fact_cards)
    promoted_registry = resolve_promoted_candidate_records_for_material_case(candidates)
    assessments: List[MaterialCandidateSourceAssessmentDTO] = []

    for raw_candidate in candidates:
        candidate = (
            raw_candidate
            if isinstance(raw_candidate, MaterialCoreCandidateDTO)
            else MaterialCoreCandidateDTO.model_validate(raw_candidate)
        )
        supporting_cards = []
        reasons: List[str] = []
        for evidence_ref in candidate.evidence_refs:
            card = cards_by_evidence_id.get(evidence_ref)
            if not card:
                continue
            normalized = card.get("normalized_evidence") or {}
            if normalized.get("material_family", "").upper() == candidate.material_family.upper():
                supporting_cards.append(card)

        if not supporting_cards:
            reasons.append("no_matching_evidence_bound_candidate_source")

        promoted_registry_record = promoted_registry.get(candidate.candidate_id)
        source_origin = PROMOTED_SOURCE_ORIGIN if promoted_registry_record else TRANSITION_SOURCE_ORIGIN
        source_adapter = _resolve_candidate_source_adapter(source_origin)
        if source_origin != PROMOTED_SOURCE_ORIGIN:
            reasons.append("candidate_source_not_promoted_registry")
        elif not promoted_registry_record:
            reasons.append("candidate_registry_record_missing")

        identity_specificity = candidate.candidate_kind or "family"
        if identity_specificity != "manufacturer_grade":
            reasons.append("candidate_specificity_below_qualified_boundary")

        if any(not card.get("source_ref") for card in supporting_cards):
            reasons.append("candidate_source_ref_missing")

        if any((card.get("normalized_evidence") or {}).get("authority_quality") != "sufficient" for card in supporting_cards):
            reasons.append("candidate_authority_insufficient")

        if any((card.get("normalized_evidence") or {}).get("evidence_quality") != "qualified_identity" for card in supporting_cards):
            reasons.append("candidate_identity_not_qualified")

        if identity_specificity == "manufacturer_grade":
            if any(
                (card.get("normalized_evidence") or {}).get("identity_quality", {}).get("grade_name", {}).get("quality") != "qualified"
                for card in supporting_cards
            ):
                reasons.append("grade_identity_not_evidence_bound")
            if any(
                (card.get("normalized_evidence") or {}).get("identity_quality", {}).get("manufacturer_name", {}).get("quality") != "qualified"
                for card in supporting_cards
            ):
                reasons.append("manufacturer_identity_not_evidence_bound")

        qualified_eligible = bool(supporting_cards) and not reasons
        assessments.append(
            MaterialCandidateSourceAssessmentDTO(
                candidate_id=candidate.candidate_id,
                candidate_source_class=(
                    "qualified_candidate_input" if qualified_eligible else "exploratory_candidate_input"
                ),
                candidate_source_quality=(
                    "promoted_registry"
                    if qualified_eligible
                    else "transition_only" if source_origin == TRANSITION_SOURCE_ORIGIN else "promoted_but_blocked"
                ),
                identity_specificity=identity_specificity,
                source_origin=source_origin,
                source_adapter=source_adapter,
                registry_record_id=(
                    promoted_registry_record.registry_record_id if promoted_registry_record is not None else None
                ),
                promotion_state=(
                    promoted_registry_record.promotion_state if promoted_registry_record is not None else None
                ),
                qualified_eligible=qualified_eligible,
                evidence_refs=list(candidate.evidence_refs),
                source_gate_reasons=list(dict.fromkeys(reasons)),
            )
        )

    return assessments


def _resolve_candidate_source_adapter(source_origin: str) -> str:
    if source_origin == PROMOTED_SOURCE_ORIGIN:
        return PROMOTED_SOURCE_ADAPTER
    return TRANSITION_SOURCE_ADAPTER


@lru_cache(maxsize=1)
def load_promoted_candidate_registry_records() -> tuple[PromotedCandidateRegistryRecordDTO, ...]:
    """Load governed promoted candidate records from the read-only provider source."""

    if not _PROMOTED_REGISTRY_PATH.exists():
        return ()
    raw_payload = json.loads(_PROMOTED_REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw_payload, list):
        return ()
    return tuple(
        PromotedCandidateRegistryRecordDTO.model_validate(entry)
        for entry in raw_payload
    )


def resolve_promoted_candidate_records_for_material_case(
    candidates: List[MaterialCoreCandidateDTO | Dict[str, Any]],
) -> Dict[str, PromotedCandidateRegistryRecordDTO]:
    """Return provider-backed promoted records that match the current material candidates.

    0B.1: Only entries with promotion_state == "promoted" AND registry_authority == "governed"
    may act as promoted trust anchors. "demo_only" entries are loaded (auditable) but excluded
    from all trust-granting and qualification paths.
    """

    resolved = resolve_candidate_registry_records_for_material_case(candidates)
    return {
        candidate_id: record
        for candidate_id, record in resolved.items()
        if record.promotion_state == "promoted" and record.registry_authority == "governed"
    }


def resolve_candidate_registry_records_for_material_case(
    candidates: List[MaterialCoreCandidateDTO | Dict[str, Any]],
) -> Dict[str, PromotedCandidateRegistryRecordDTO]:
    """Return provider-backed registry records that match the current material candidates."""

    promoted_by_candidate_id = {
        record.candidate_id: record
        for record in load_promoted_candidate_registry_records()
    }
    resolved: Dict[str, PromotedCandidateRegistryRecordDTO] = {}
    for raw_candidate in candidates:
        candidate = (
            raw_candidate
            if isinstance(raw_candidate, MaterialCoreCandidateDTO)
            else MaterialCoreCandidateDTO.model_validate(raw_candidate)
        )
        promoted = promoted_by_candidate_id.get(candidate.candidate_id)
        if promoted is not None:
            resolved[candidate.candidate_id] = promoted
    return resolved


def build_material_provider_contract_snapshot(
    *,
    relevant_fact_cards: List[Dict[str, Any]],
    seed_candidates: Optional[List[Dict[str, Any]]] = None,
) -> MaterialProviderContractSnapshotDTO:
    """Blueprint Sections 02/08/12: deterministic provider provenance snapshot for resume and invalidation."""

    aggregated = _aggregate_candidate_inputs_from_evidence(
        relevant_fact_cards=relevant_fact_cards,
        seed_candidates=seed_candidates or [],
    )
    matched_registry = resolve_candidate_registry_records_for_material_case(aggregated)
    matched_records = sorted(
        matched_registry.values(),
        key=lambda record: (record.registry_record_id, record.candidate_id),
    )
    promoted_records = [record for record in matched_records if record.promotion_state == "promoted"]
    return MaterialProviderContractSnapshotDTO(
        matched_registry_record_ids=[record.registry_record_id for record in matched_records],
        matched_promoted_registry_record_ids=[record.registry_record_id for record in promoted_records],
        matched_candidate_ids=[record.candidate_id for record in matched_records],
        matched_promoted_candidate_ids=[record.candidate_id for record in promoted_records],
        registry_records=[
            {
                "registry_record_id": record.registry_record_id,
                "candidate_id": record.candidate_id,
                "material_family": record.material_family,
                "grade_name": record.grade_name,
                "manufacturer_name": record.manufacturer_name,
                "promotion_state": record.promotion_state,
                "source_refs": list(record.source_refs),
                "evidence_refs": list(record.evidence_refs),
            }
            for record in matched_records
        ],
        has_promoted_registry_match=bool(promoted_records),
    )


def _aggregate_candidate_inputs_from_evidence(
    *,
    relevant_fact_cards: List[Dict[str, Any]],
    seed_candidates: List[Dict[str, Any]],
) -> List[MaterialCoreCandidateDTO]:
    candidates_by_id: Dict[str, Dict[str, Any]] = {}

    for seed in seed_candidates:
        candidate = MaterialCoreCandidateDTO.model_validate(seed)
        candidates_by_id[candidate.candidate_id] = candidate.model_dump()

    for card in relevant_fact_cards:
        normalized_evidence = card.get("normalized_evidence") or normalize_fact_card_evidence(card)
        family = normalized_evidence.get("material_family")
        evidence_id = card.get("evidence_id") or card.get("id")
        if not family or not evidence_id:
            continue

        filler_hint = normalized_evidence.get("filler_hint")
        grade_name = normalized_evidence.get("grade_name")
        manufacturer_name = normalized_evidence.get("manufacturer_name")
        candidate_kind = normalized_evidence.get("candidate_kind")
        candidate_id = _candidate_id(family, filler_hint, grade_name, manufacturer_name)

        existing = candidates_by_id.get(candidate_id)
        if not existing:
            existing = MaterialCoreCandidateDTO(
                candidate_id=candidate_id,
                candidate_kind=candidate_kind,
                material_family=family,
                filler_hint=filler_hint,
                grade_name=grade_name,
                manufacturer_name=manufacturer_name,
                evidence_refs=[],
            ).model_dump()
            candidates_by_id[candidate_id] = existing

        if evidence_id not in existing["evidence_refs"]:
            existing["evidence_refs"].append(str(evidence_id))

    return [
        MaterialCoreCandidateDTO.model_validate(candidate)
        for candidate in sorted(candidates_by_id.values(), key=lambda item: item["candidate_id"])
    ]


def _index_fact_cards(relevant_fact_cards: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    cards_by_evidence_id: Dict[str, Dict[str, Any]] = {}
    for card in relevant_fact_cards:
        evidence_id = card.get("evidence_id") or card.get("id")
        if not evidence_id:
            continue
        normalized_card = dict(card)
        normalized_card["normalized_evidence"] = card.get("normalized_evidence") or normalize_fact_card_evidence(card)
        cards_by_evidence_id[str(evidence_id)] = normalized_card
    return cards_by_evidence_id


def _candidate_id(
    family: str,
    filler_hint: Optional[str],
    grade_name: Optional[str],
    manufacturer_name: Optional[str],
) -> str:
    parts = [
        family.lower(),
        (filler_hint or "").lower(),
        (grade_name or "").lower(),
        (manufacturer_name or "").lower(),
    ]
    return "::".join(part for part in parts if part)


def _rollup_normalized_quality(supporting_cards: List[Dict[str, Any]], field_name: str) -> str:
    if not supporting_cards:
        return "unknown"
    values = {
        str((card.get("normalized_evidence") or {}).get(field_name) or "unknown")
        for card in supporting_cards
    }
    if len(values) == 1:
        return next(iter(values))
    if "conflicted_identity" in values:
        return "conflicted_identity"
    if "insufficient" in values or "unqualified_identity" in values:
        return "mixed_insufficient"
    return "mixed"


def _normalize_temperature(asserted_state: Dict[str, Any]) -> PhysicalParameter | None:
    temperature_value = (asserted_state or {}).get("operating_conditions", {}).get("temperature")
    if temperature_value is None:
        return None
    try:
        return PhysicalParameter(value=float(temperature_value), unit="C")
    except Exception:
        return None


def _normalize_pressure(asserted_state: Dict[str, Any]) -> PhysicalParameter | None:
    pressure_value = (asserted_state or {}).get("operating_conditions", {}).get("pressure")
    if pressure_value is None:
        return None
    try:
        return PhysicalParameter(value=float(pressure_value), unit="bar")
    except Exception:
        return None


def _profile_requires_pressure(card: Dict[str, Any] | None) -> bool:
    if not card:
        return False
    profile = MaterialPhysicalProfile.from_fact_card(card)
    return bool(profile and getattr(profile, "pressure_max", None) is not None)


def _governance_has_hard_block(governance_state: Dict[str, Any]) -> bool:
    if governance_state.get("gate_failures"):
        return True
    if governance_state.get("unknowns_release_blocking"):
        return True
    return any(
        str(conflict.get("severity") or "").upper() in {"CRITICAL", "BLOCKING_UNKNOWN"}
        for conflict in governance_state.get("conflicts", [])
    )
