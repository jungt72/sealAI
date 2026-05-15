"""Deterministic V9.2 engineering orchestration.

The functions here intentionally do not call an LLM and do not perform I/O.
They adapt the existing V9.1 governed state into the richer V9.2 engineering
ledger: seal-system ontology, guarded calculations, evidence graph, standards
metadata, compound/product separation and RFQ dossier.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from typing import Any, Iterable, Mapping

from app.agent.v92.models import (
    CalculationInputSnapshot,
    CalculationResult,
    CalculationState,
    CompoundCandidate,
    CompoundState,
    DocumentEvidenceState,
    DossierSection,
    DossierState,
    EngineeringAssumption,
    EngineeringDecision,
    EngineeringState,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    EvidenceGraphState,
    FailureObservationState,
    MaterialFamilyCandidate,
    ProductCandidate,
    ReviewState,
    SealSystemComponent,
    SealSystemState,
    StandardsRegistryEntry,
    StandardsState,
)
from app.domain.seal_type import (
    SealFamily,
    SealType,
    normalize_seal_type,
    seal_family_for_type,
)
from app.mcp.calculations.oring_groove import lookup_nut


_RWDR_REQUIRED_FIELDS = (
    "sealing_type",
    "medium",
    "temperature_c",
    "pressure_bar",
    "shaft_diameter_mm",
    "speed_rpm",
)
_ORING_REQUIRED_FIELDS = (
    "sealing_type",
    "medium",
    "temperature_c",
    "pressure_bar",
    "oring_cross_section_mm",
    "groove_depth_mm",
    "groove_width_mm",
)
_HYDRAULIC_REQUIRED_FIELDS = (
    "sealing_type",
    "medium",
    "temperature_c",
    "pressure_bar",
    "rod_diameter_mm",
    "stroke_speed_mm_s",
)

_MATERIAL_FAMILY_FIELDS = (
    "material",
    "material_family",
    "sealing_material_family",
    "compound_family",
)
_COMPOUND_FIELDS = ("compound", "compound_name", "compound_designation", "grade_name")
_PRODUCT_FIELDS = ("product", "product_id", "article_ref", "article_number", "part_number")


def _claim_value(state: Any, field_name: str) -> Any:
    claim = getattr(getattr(state, "asserted", None), "assertions", {}).get(field_name)
    if claim is None:
        return None
    return getattr(claim, "asserted_value", None)


def _asserted_inputs(state: Any) -> dict[str, Any]:
    assertions = getattr(getattr(state, "asserted", None), "assertions", {}) or {}
    result: dict[str, Any] = {}
    for field_name, claim in assertions.items():
        value = getattr(claim, "asserted_value", None)
        if value is not None:
            result[str(field_name)] = value
    return result


def _string_value(state: Any, *field_names: str) -> str:
    for field_name in field_names:
        value = _claim_value(state, field_name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _float_value(state: Any, *field_names: str) -> float | None:
    for field_name in field_names:
        value = _claim_value(state, field_name)
        if value is None:
            continue
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            continue
    return None


def _is_missing(value: Any) -> bool:
    return value is None or value == ""


def _stable_hash(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _required_fields_for(seal_type: str, seal_family: str) -> tuple[str, ...]:
    if seal_type in {
        SealType.radial_shaft_seal.value,
        SealType.rotary_lip_seal.value,
        SealType.cassette_seal.value,
        SealType.v_ring.value,
    } or seal_family == SealFamily.rotary_shaft.value:
        return _RWDR_REQUIRED_FIELDS
    if seal_type in {SealType.o_ring.value, SealType.x_ring.value, SealType.backup_ring.value}:
        return _ORING_REQUIRED_FIELDS
    if seal_family in {SealFamily.hydraulic.value, SealFamily.pneumatic.value}:
        return _HYDRAULIC_REQUIRED_FIELDS
    return ("sealing_type", "medium", "temperature_c", "pressure_bar")


def build_seal_system_state(state: Any) -> SealSystemState:
    inputs = _asserted_inputs(state)
    text = " ".join(
        str(item)
        for item in (
            inputs.get("sealing_type"),
            inputs.get("seal_type"),
            inputs.get("application_pattern"),
            inputs.get("motion_type"),
            getattr(state, "pending_message", ""),
        )
        if item
    )
    normalization = normalize_seal_type(
        text,
        context={
            "engineering_path": inputs.get("engineering_path"),
            "routing": {"engineering_path": inputs.get("engineering_path")},
        },
    )
    seal_type = normalization.seal_type.value
    seal_family = normalization.seal_family.value
    if seal_type == SealType.unknown_seal.value and inputs.get("sealing_type"):
        raw = str(inputs.get("sealing_type")).strip().lower()
        if raw in {"rwdr", "radialwellendichtring"}:
            seal_type = SealType.radial_shaft_seal.value
            seal_family = seal_family_for_type(seal_type).value
        elif raw in {"o-ring", "oring", "o_ring"}:
            seal_type = SealType.o_ring.value
            seal_family = seal_family_for_type(seal_type).value

    required = _required_fields_for(seal_type, seal_family)
    missing = [field for field in required if _is_missing(inputs.get(field))]
    status = "ready" if required and not missing else ("partial" if inputs else "pending")
    component = SealSystemComponent(
        component_id="primary_seal",
        role="primary_sealing_function",
        seal_family=seal_family,
        seal_type=seal_type,
        confidence=normalization.confidence,
        known_fields={key: inputs[key] for key in required if key in inputs},
        missing_fields=missing,
    )
    assumptions: list[str] = []
    if normalization.ambiguous:
        assumptions.append("Seal type is still ambiguous and must be confirmed.")
    if not inputs.get("sealing_type"):
        assumptions.append("Seal system type is not confirmed.")
    return SealSystemState(
        status=status,
        seal_family=seal_family,
        seal_type=seal_type,
        motion_type=str(inputs.get("motion_type") or "") or None,
        application_pattern=str(inputs.get("application_pattern") or "") or None,
        components=[component],
        system_edges=[
            {
                "from": "primary_seal",
                "to": "medium",
                "relationship": "seals_against",
            }
        ]
        if inputs.get("medium")
        else [],
        required_fields=list(required),
        missing_fields=missing,
        assumptions=assumptions,
        validity_boundaries=[
            "Seal-system classification is a governed prequalification model, not a product release."
        ],
    )


def _calculation_result_from_compute(
    result: Mapping[str, Any],
    *,
    snapshot_hash: str,
) -> CalculationResult:
    records = list(result.get("calculation_records") or [])
    dependencies: list[str] = []
    for record in records:
        if isinstance(record, Mapping):
            dependencies.extend(str(key) for key in dict(record.get("inputs_used") or {}).keys())
    notes = [str(item) for item in list(result.get("notes") or []) if item]
    status = str(result.get("status") or "ok")
    if status not in {"ok", "warning", "insufficient_data", "stale", "blocked"}:
        status = "warning"
    return CalculationResult(
        calculation_id=str(result.get("calc_type") or "calculation"),
        version="v9_2_adapter_1",
        calculator=str(result.get("calculation_engine") or "unknown_calculator"),
        status=status,  # type: ignore[arg-type]
        input_snapshot_hash=snapshot_hash,
        outputs={
            key: value
            for key, value in dict(result).items()
            if key
            not in {
                "calculation_records",
                "notes",
                "provenance",
                "calculation_engine",
            }
            and value is not None
        },
        dependencies=list(dict.fromkeys(dependencies)),
        notes=notes,
    )


def _oring_calculation(state: Any, *, snapshot_hash: str) -> CalculationResult | None:
    cross_section = _float_value(
        state,
        "oring_cross_section_mm",
        "cord_diameter_mm",
        "schnurdurchmesser_mm",
        "cross_section_mm",
    )
    pressure = _float_value(state, "pressure_bar")
    if cross_section is None:
        return None
    missing = []
    if pressure is None:
        missing.append("pressure_bar")
        pressure = 0.0
    motion = _string_value(state, "motion_type", "dynamic_type").lower()
    situation = "dynamisch" if any(marker in motion for marker in ("dynam", "rot", "hub", "rezip")) else "statisch"
    output = asdict(lookup_nut(cross_section, situation, pressure))
    status = "insufficient_data" if missing else "ok"
    notes = [
        "O-ring groove result is a screening calculation; tolerances and installation details still require review."
    ]
    if output.get("hinweis"):
        notes.append(str(output["hinweis"]))
    return CalculationResult(
        calculation_id="oring.groove_screening",
        version="din3770_iso3601_2_metadata_v1",
        calculator="lookup_nut",
        status=status,  # type: ignore[arg-type]
        input_snapshot_hash=snapshot_hash,
        outputs=output,
        missing_inputs=missing,
        dependencies=["oring_cross_section_mm", "pressure_bar", "motion_type"],
        notes=notes,
    )


def build_calculation_state(state: Any) -> CalculationState:
    inputs = _asserted_inputs(state)
    snapshot_hash = _stable_hash(inputs)
    snapshot = CalculationInputSnapshot(
        snapshot_hash=snapshot_hash,
        case_revision=int(
            getattr(getattr(state, "persistence_marker", None), "postgres_case_revision", None)
            or 0
        ),
        inputs=inputs,
    )
    results = [
        _calculation_result_from_compute(result, snapshot_hash=snapshot_hash)
        for result in list(getattr(state, "compute_results", []) or [])
        if isinstance(result, Mapping)
    ]
    oring_result = _oring_calculation(state, snapshot_hash=snapshot_hash)
    if oring_result is not None:
        results.append(oring_result)

    blocked: list[str] = []
    seal_system = build_seal_system_state(state)
    if seal_system.seal_family == SealFamily.rotary_shaft.value and not any(
        item.calculation_id == "rwdr" for item in results
    ):
        missing = [
            field
            for field in ("shaft_diameter_mm", "speed_rpm")
            if _is_missing(inputs.get(field))
        ]
        blocked.append("rwdr.surface_speed_missing:" + ",".join(missing or ["unknown"]))
        results.append(
            CalculationResult(
                calculation_id="rwdr.surface_speed",
                version="v9_2_missing_input_guard",
                calculator="CascadingCalculationEngine",
                status="insufficient_data",
                input_snapshot_hash=snapshot_hash,
                missing_inputs=missing,
                dependencies=["shaft_diameter_mm", "speed_rpm"],
            )
        )
    status = "ready" if results and not blocked else ("partial" if results or inputs else "pending")
    return CalculationState(
        status=status,
        input_snapshot=snapshot,
        results=results,
        blocked_calculations=blocked,
    )


def build_engineering_state(
    *,
    seal_system: SealSystemState,
    calculation: CalculationState,
) -> EngineeringState:
    blockers = list(dict.fromkeys(seal_system.missing_fields + calculation.blocked_calculations))
    assumptions = [
        EngineeringAssumption(
            assumption_id=f"seal_system.assumption.{index}",
            text=text,
            affected_fields=seal_system.missing_fields,
            invalidates_calculations=[item.calculation_id for item in calculation.results],
        )
        for index, text in enumerate(seal_system.assumptions)
    ]
    ready_calcs = [
        item.calculation_id
        for item in calculation.results
        if item.status in {"ok", "warning"}
    ]
    next_action = "review_engineering_dossier" if not blockers and ready_calcs else "collect_missing_inputs"
    if blockers and "sealing_type" in blockers:
        next_action = "identify_seal_system"
    elif blockers and any("shaft_diameter" in item or "speed_rpm" in item for item in blockers):
        next_action = "collect_geometry_and_motion_inputs"
    decision = EngineeringDecision(
        decision_id="engineering_orchestrator.primary",
        decision_type="prequalification_readiness",
        status="ready" if not blockers and ready_calcs else ("partial" if seal_system.status != "pending" else "pending"),
        rationale="Deterministic V9.2 orchestration over seal-system and calculation state.",
        next_action=next_action,
        blockers=blockers,
        related_calculations=ready_calcs,
    )
    return EngineeringState(
        status=decision.status,
        route=seal_system.seal_type,
        decisions=[decision],
        assumptions=assumptions,
        blockers=blockers,
        next_best_engineering_action=next_action,
    )


def build_evidence_graph_state(state: Any) -> EvidenceGraphState:
    nodes: list[EvidenceGraphNode] = []
    edges: list[EvidenceGraphEdge] = []
    for index, item in enumerate(list(getattr(state, "rag_evidence", []) or [])):
        if not isinstance(item, Mapping):
            continue
        source_ref = str(
            item.get("source_id")
            or item.get("id")
            or item.get("document_id")
            or f"rag_evidence.{index}"
        )
        title = str(item.get("title") or item.get("source_title") or source_ref)
        node_id = f"evidence.{index}"
        nodes.append(
            EvidenceGraphNode(
                node_id=node_id,
                evidence_type=str(item.get("type") or item.get("source_type") or "rag_card"),
                title=title,
                source_ref=source_ref,
                claim_level="L2_screening",
                applicability="indirect",
                limitations=["Retrieved evidence requires applicability review."],
            )
        )
        edges.append(EvidenceGraphEdge(from_node_id=node_id, to_target_id="engineering_prequalification"))
    evidence_state = getattr(state, "evidence", None)
    for index, finding in enumerate(list(getattr(evidence_state, "source_backed_findings", []) or [])):
        node_id = f"source_finding.{index}"
        nodes.append(
            EvidenceGraphNode(
                node_id=node_id,
                evidence_type="source_backed_finding",
                title=str(finding),
                claim_level="L2_screening",
                applicability="direct",
                supports=["technical_screening"],
            )
        )
    gaps = list(getattr(evidence_state, "evidence_gaps", []) or [])
    status = "ready" if nodes and not gaps else ("partial" if nodes else "pending")
    return EvidenceGraphState(status=status, nodes=nodes, edges=edges, unresolved_gaps=[str(item) for item in gaps])


def build_compound_state(state: Any) -> CompoundState:
    families: list[MaterialFamilyCandidate] = []
    compounds: list[CompoundCandidate] = []
    products: list[ProductCandidate] = []
    inputs = _asserted_inputs(state)

    for field_name in _MATERIAL_FAMILY_FIELDS:
        value = inputs.get(field_name)
        if value:
            families.append(
                MaterialFamilyCandidate(
                    family=str(value),
                    basis=[field_name],
                )
            )
    for field_name in _COMPOUND_FIELDS:
        value = inputs.get(field_name)
        if value:
            family = str(families[0].family if families else "")
            compounds.append(
                CompoundCandidate(
                    compound_id=str(value),
                    family=family,
                    designation=str(value),
                    evidence_refs=[],
                )
            )
    for field_name in _PRODUCT_FIELDS:
        value = inputs.get(field_name)
        if value:
            products.append(ProductCandidate(product_id=str(value), article_ref=str(value)))

    violations: list[str] = []
    if products and not compounds:
        violations.append("product_candidate_without_compound_layer")
    if compounds and not families:
        violations.append("compound_candidate_without_material_family_layer")
    status = "ready" if families and not violations else ("partial" if families or compounds or products else "pending")
    return CompoundState(
        status=status,
        material_family_candidates=families,
        compound_candidates=compounds,
        product_candidates=products,
        separation_violations=violations,
    )


def build_document_evidence_state(state: Any) -> DocumentEvidenceState:
    docs: list[dict[str, Any]] = []
    for index, item in enumerate(list(getattr(state, "rag_evidence", []) or [])):
        if isinstance(item, Mapping):
            docs.append(
                {
                    "document_ref": str(item.get("document_id") or item.get("source_id") or f"evidence.{index}"),
                    "title": str(item.get("title") or item.get("source_title") or ""),
                    "claim_level": "L1_normalized",
                }
            )
    status = "partial" if docs else "pending"
    return DocumentEvidenceState(
        status=status,
        documents_seen=docs,
        extraction_gaps=[] if docs else ["no_structured_document_evidence"],
    )


def build_failure_observation_state(state: Any) -> FailureObservationState:
    text = " ".join(
        str(item)
        for item in (
            getattr(state, "pending_message", ""),
            _string_value(state, "failure_description", "damage_pattern", "complaint"),
        )
        if item
    ).lower()
    indicators: list[str] = []
    patterns = {
        "leakage": r"\b(leck|leckage|undicht|leak)\b",
        "wear": r"\b(verschleiss|verschleiß|abrieb|wear)\b",
        "extrusion": r"\b(extrusion|spalt|ausgepresst)\b",
        "thermal_damage": r"\b(hitze|verbrannt|thermal|temperatur)\b",
        "chemical_attack": r"\b(quellung|aufgequollen|chemisch|riss)\b",
    }
    for key, pattern in patterns.items():
        if re.search(pattern, text):
            indicators.append(key)
    possible = []
    if "leakage" in indicators:
        possible.append("installation_gap_or_surface_or_pressure_boundary")
    if "chemical_attack" in indicators:
        possible.append("medium_material_incompatibility")
    status = "partial" if indicators else "pending"
    return FailureObservationState(
        status=status,
        morphology_indicators=indicators,
        possible_causes=possible,
    )


def build_engineering_update(state: Any) -> dict[str, Any]:
    seal_system = build_seal_system_state(state)
    calculation = build_calculation_state(state)
    engineering = build_engineering_state(seal_system=seal_system, calculation=calculation)
    return {
        "seal_system": seal_system,
        "engineering": engineering,
        "calculation": calculation,
        "evidence_graph": build_evidence_graph_state(state),
        "compound_state": build_compound_state(state),
        "document_evidence": build_document_evidence_state(state),
        "failure_observation": build_failure_observation_state(state),
    }


def _standard_entry_from_check(check: Mapping[str, Any]) -> StandardsRegistryEntry:
    module_id = str(check.get("module_id") or "unknown_standard_module")
    title = module_id.replace("norm_", "").replace("_", " ").upper()
    return StandardsRegistryEntry(
        standard_id=module_id,
        title=title,
        version=str(check.get("version") or "metadata_only"),
        scope=str(check.get("scope") or check.get("status") or ""),
        region=None,
        source_module_id=module_id,
        conformity_claim_allowed=False,
    )


def build_standards_state(state: Any) -> StandardsState:
    norm_checks = [
        item
        for item in list(getattr(getattr(state, "sealai_norm", None), "norm_checks", []) or [])
        if isinstance(item, Mapping)
    ]
    entries = [_standard_entry_from_check(check) for check in norm_checks]
    blocking: list[str] = []
    for check in norm_checks:
        status = str(check.get("status") or "")
        if status in {"insufficient_data", "fail"}:
            module_id = str(check.get("module_id") or "standard")
            for field in list(check.get("missing_required_fields") or []):
                blocking.append(f"{module_id}:{field}")
    status = "ready" if entries and not blocking else ("partial" if entries else "pending")
    return StandardsState(
        status=status,
        applicable_entries=entries,
        check_results=[dict(check) for check in norm_checks],
        blocking_gaps=list(dict.fromkeys(blocking)),
    )


def build_review_state(state: Any) -> ReviewState:
    rfq = getattr(state, "rfq", None)
    blocking = [str(item) for item in list(getattr(rfq, "blocking_findings", []) or []) if item]
    soft = [str(item) for item in list(getattr(rfq, "soft_findings", []) or []) if item]
    corrections = [str(item) for item in list(getattr(rfq, "required_corrections", []) or []) if item]
    if blocking:
        status = "blocked"
    elif corrections:
        status = "changes_required"
    elif getattr(rfq, "critical_review_passed", False):
        status = "approved_scope"
    elif getattr(rfq, "critical_review_status", "") not in {"", "not_run"}:
        status = "pending"
    else:
        status = "not_started"
    return ReviewState(
        status=status,  # type: ignore[arg-type]
        scope=["rfq_handover", "claim_boundary", "manufacturer_review"],
        decision_summary=str(getattr(rfq, "critical_review_status", "") or ""),
        blocking_findings=blocking,
        soft_findings=soft,
        required_corrections=corrections,
    )


def _facts_from_assertions(state: Any) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for field_name, value in sorted(_asserted_inputs(state).items()):
        facts.append(
            {
                "field": field_name,
                "value": value,
                "claim_level": "L1_normalized",
                "source": "asserted_state",
            }
        )
    return facts


def _calculation_items(calculation: CalculationState) -> list[dict[str, Any]]:
    return [
        {
            "calculation_id": result.calculation_id,
            "status": result.status,
            "claim_level": result.claim_level,
            "outputs": dict(result.outputs),
            "missing_inputs": list(result.missing_inputs),
            "notes": list(result.notes),
        }
        for result in calculation.results
    ]


def _candidate_items(state: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    compound = getattr(state, "compound_state", None)
    for item in list(getattr(compound, "material_family_candidates", []) or []):
        candidates.append(
            {
                "candidate_type": "material_family",
                "id": item.family,
                "claim_level": item.claim_level,
                "requires_review": True,
            }
        )
    for item in list(getattr(compound, "compound_candidates", []) or []):
        candidates.append(
            {
                "candidate_type": "compound",
                "id": item.compound_id,
                "family": item.family,
                "claim_level": item.claim_level,
                "requires_datasheet": item.requires_datasheet,
            }
        )
    for item in list(getattr(compound, "product_candidates", []) or []):
        candidates.append(
            {
                "candidate_type": "product",
                "id": item.product_id,
                "claim_level": item.claim_level,
                "requires_manufacturer_review": item.requires_manufacturer_review,
            }
        )
    return candidates


def _allowed_claims(state: Any) -> list[str]:
    claims = [
        "technische Vorqualifikation",
        "prüfbare Richtung",
        "offene Punkte für Herstellerprüfung",
    ]
    if getattr(getattr(state, "review_state", None), "status", "") == "approved_scope":
        claims.append("reviewed RFQ scope")
    return claims


def build_dossier_state(state: Any) -> DossierState:
    facts = _facts_from_assertions(state)
    calculation_items = _calculation_items(getattr(state, "calculation", CalculationState()))
    candidates = _candidate_items(state)
    blockers: list[str] = []
    blockers.extend(str(item) for item in list(getattr(getattr(state, "engineering", None), "blockers", []) or []) if item)
    blockers.extend(str(item) for item in list(getattr(getattr(state, "standards", None), "blocking_gaps", []) or []) if item)
    blockers.extend(str(item) for item in list(getattr(getattr(state, "compound_state", None), "separation_violations", []) or []) if item)
    blockers.extend(str(item) for item in list(getattr(getattr(state, "rfq", None), "blocking_findings", []) or []) if item)
    blockers = list(dict.fromkeys(blockers))
    status = "ready" if facts and not blockers else ("partial" if facts or calculation_items or candidates else "pending")
    sections = [
        DossierSection(section_id="facts", title="Governed Facts", items=facts),
        DossierSection(section_id="calculations", title="Deterministic Calculations", items=calculation_items),
        DossierSection(section_id="candidates", title="Screening Candidates", items=candidates),
        DossierSection(
            section_id="blockers",
            title="Open Blockers",
            items=[{"blocker": blocker} for blocker in blockers],
        ),
    ]
    session_id = str(getattr(state, "session_id", "") or "")
    return DossierState(
        status=status,
        dossier_id=f"rfq-dossier-v92-{session_id}" if session_id else None,
        facts=facts,
        calculations=calculation_items,
        candidates=candidates,
        blockers=blockers,
        allowed_claims=_allowed_claims(state),
        sections=sections,
    )


def build_dossier_update(state: Any) -> dict[str, Any]:
    standards = build_standards_state(state)
    state_with_standards = state.model_copy(update={"standards": standards})
    review_state = build_review_state(state_with_standards)
    state_with_review = state_with_standards.model_copy(update={"review_state": review_state})
    dossier = build_dossier_state(state_with_review)
    return {
        "standards": standards,
        "review_state": review_state,
        "dossier": dossier,
    }


__all__ = [
    "build_calculation_state",
    "build_compound_state",
    "build_dossier_state",
    "build_dossier_update",
    "build_engineering_state",
    "build_engineering_update",
    "build_evidence_graph_state",
    "build_seal_system_state",
    "build_standards_state",
]
