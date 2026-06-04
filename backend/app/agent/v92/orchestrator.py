"""Deterministic V9.2 engineering orchestration.

The functions here intentionally do not call an LLM and do not perform I/O.
They adapt the existing V9.1 governed state into the richer V9.2 engineering
ledger: seal-system ontology, guarded calculations, evidence graph, standards
metadata, compound/product separation and RFQ dossier.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

from app.agent.v92.calculator_registry import get_calculator_registry
from app.agent.v92.models import (
    CalculationGuardResult,
    CalculationInputSnapshot,
    CalculationResult,
    CalculationState,
    CompletenessMatrix,
    CompoundCandidate,
    CompoundState,
    DocumentEvidenceState,
    DossierSection,
    DossierState,
    EngineeringAssumption,
    EngineeringDecision,
    EngineeringRiskFinding,
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

# P1-1: required fields come from the domain pack seam (RWDR pack + shallow stubs),
# never from a core per-type branch.
from app.domain.seal_packs import required_fields_for as _required_fields_for

# P1-4 / C9: O-Ring screening geometry lives in its own domain module; the core
# injects its generic calc primitives (no O-Ring engineering depth in the core).
from app.agent.domain.oring_calc import oring_calculations


_MATERIAL_FAMILY_FIELDS = (
    "material",
    "material_family",
    "sealing_material_family",
    "compound_family",
)
_COMPOUND_FIELDS = ("compound", "compound_name", "compound_designation", "grade_name")
_PRODUCT_FIELDS = (
    "product",
    "product_id",
    "article_ref",
    "article_number",
    "part_number",
)

_PROMPT_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "system prompt",
    "developer message",
    "ignoriere alle vorherigen",
    "ignoriere vorherige",
    "folge nicht den bisherigen",
)

_SDS_MARKERS = (
    "safety data sheet",
    "sicherheitsdatenblatt",
    "sds",
    "msds",
)

_CERTIFICATE_MARKERS = (
    "certificate",
    "zertifikat",
    "certificate of analysis",
    "coa",
)

_STANDARD_METADATA = {
    "norm_din_3760_iso_6194": {
        "standard_id": "norm_din_3760_iso_6194",
        "title": "DIN 3760 / ISO 6194 metadata",
        "publisher": "DIN / ISO",
        "edition": "metadata_only",
        "applies_to_seal_types": ["radial_shaft_seal", "rotary_lip_seal"],
        "relevant_fields": ["shaft_diameter_mm", "housing_bore_mm", "seal_width_mm"],
        "scope": "Rotary shaft lip-type seal metadata reference; no licensed dimension table embedded.",
        "source_url": "https://www.iso.org/standard/34678.html",
    },
    "iso_3601_2": {
        "standard_id": "ISO_3601_2_2025",
        "title": "ISO 3601-2 metadata",
        "publisher": "ISO",
        "edition": "2025",
        "applies_to_seal_types": ["o_ring", "x_ring", "backup_ring"],
        "relevant_fields": [
            "oring_cross_section_mm",
            "groove_depth_mm",
            "groove_width_mm",
        ],
        "scope": "O-ring housing/gland metadata reference; no licensed dimension table embedded.",
        "source_url": "https://www.iso.org/standard/85921.html",
    },
    "iso_3601_1": {
        "standard_id": "ISO_3601_1_2012_AMD1_2019",
        "title": "ISO 3601-1 metadata",
        "publisher": "ISO",
        "edition": "2012+Amd1:2019",
        "applies_to_seal_types": ["o_ring", "x_ring"],
        "relevant_fields": ["oring_inner_diameter_mm", "oring_cross_section_mm"],
        "scope": "O-ring size/designation metadata reference; no licensed dimension table embedded.",
        "source_url": "https://www.iso.org/standard/58043.html",
    },
}

_OPTIONAL_FIELDS_BY_FAMILY = {
    SealFamily.rotary_shaft.value: [
        "counterface_surface_condition",
        "shaft_roughness_ra_um",
        "shaft_hardness_hrc",
        "runout_mm",
        "eccentricity_mm",
        "axial_movement_mm",
        "lubrication_condition",
        "contamination_condition",
        "dust_lip_required",
        "installation_space",
        "installation_space_summary",
    ],
    SealFamily.static_elastomer.value: [
        "tolerance_stack",
        "hardness_shore_a",
        "surface_finish",
        "installation_conditions",
        "pressure_direction",
        "radial_gap_mm",
    ],
    SealFamily.hydraulic.value: ["seal_profile", "surface_finish", "extrusion_gap_mm"],
    SealFamily.pneumatic.value: ["seal_profile", "lubrication", "surface_finish"],
}


def _document_text(item: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "title",
        "source_title",
        "text",
        "content",
        "snippet",
        "summary",
        "excerpt",
    ):
        value = item.get(key)
        if value:
            parts.append(str(value))
    return "\n".join(parts)


def _document_type(item: Mapping[str, Any], text: str) -> str:
    explicit = str(
        item.get("document_type") or item.get("type") or item.get("source_type") or ""
    ).lower()
    haystack = f"{explicit}\n{text.lower()}"
    if any(marker in haystack for marker in _SDS_MARKERS):
        return "sds"
    if any(marker in haystack for marker in _CERTIFICATE_MARKERS):
        return "certificate"
    if any(
        marker in haystack for marker in ("drawing", "zeichnung", "technical drawing")
    ):
        return "drawing"
    if any(marker in haystack for marker in ("datasheet", "datenblatt", "tds")):
        return "datasheet"
    return explicit or "rag_card"


def _unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if item))


def _output_hash(outputs: Mapping[str, Any]) -> str:
    return _stable_hash(outputs)


def _units_present(units: Mapping[str, str], outputs: Mapping[str, Any]) -> bool:
    return all(key in units for key in outputs.keys())


def _calculation_guard(
    result: CalculationResult, stale_result_ids: Iterable[str] = ()
) -> CalculationGuardResult:
    stale_ids = set(stale_result_ids)
    violations: list[str] = []
    required_present = not result.missing_inputs and result.status not in {
        "insufficient_data",
        "blocked",
    }
    units_ok = _units_present(result.units, result.outputs)
    formula_ok = bool(result.version and result.formula_refs)
    if not required_present:
        violations.append("required_inputs_missing")
    if result.outputs and not units_ok:
        violations.append("output_units_missing")
    if not formula_ok:
        violations.append("formula_version_missing")
    if result.claim_level in {"L6_expert_approved", "L5_document_backed"}:
        violations.append("calculation_claim_level_too_high")
    if result.calculation_id in stale_ids or result.status == "stale":
        violations.append("stale_inputs_detected")
    return CalculationGuardResult(
        calculation_id=result.calculation_id,
        required_inputs_present=required_present,
        units_normalized=units_ok,
        formula_version_present=formula_ok,
        output_units_present=units_ok,
        stale_inputs_detected=result.calculation_id in stale_ids
        or result.status == "stale",
        no_final_claim_from_calculation=result.claim_level
        not in {"L5_document_backed", "L6_expert_approved"},
        allowed_user_facing=required_present
        and units_ok
        and formula_ok
        and result.validity_status
        in {
            "valid_for_screening",
            "valid_with_assumptions",
        },
        violations=violations,
    )


def _has_positive_marker(text: str, patterns: Iterable[str]) -> bool:
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            prefix = text[max(0, match.start() - 18) : match.start()].lower()
            if any(
                marker in prefix
                for marker in ("kein ", "keine ", "no ", "not ", "ohne ")
            ):
                continue
            return True
    return False


def _extract_first(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return next(
        (group.strip() for group in match.groups() if group and group.strip()), None
    )


def _extract_cas_components(text: str) -> list[dict[str, str]]:
    components: list[dict[str, str]] = []
    for match in re.finditer(r"\b(\d{2,7}-\d{2}-\d)\b", text):
        components.append({"cas": match.group(1), "source": "sds_text"})
    return components


def _document_metadata(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_owner": item.get("source_owner")
        or item.get("owner")
        or item.get("manufacturer"),
        "version": item.get("version") or item.get("revision"),
        "issue_date": item.get("issue_date") or item.get("publication_date"),
        "valid_until": item.get("valid_until"),
        "retrieved_at": item.get("retrieved_at") or item.get("source_checked_at"),
        "region": item.get("region"),
        "manufacturer": item.get("manufacturer"),
        "compound_id": item.get("compound_id"),
        "source_scope": item.get("source_scope") or item.get("scope"),
    }


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
    status = (
        "ready" if required and not missing else ("partial" if inputs else "pending")
    )
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
            dependencies.extend(
                str(key) for key in dict(record.get("inputs_used") or {}).keys()
            )
    notes = [str(item) for item in list(result.get("notes") or []) if item]
    status = str(result.get("status") or "ok")
    if status not in {"ok", "warning", "insufficient_data", "stale", "blocked"}:
        status = "warning"
    outputs = {
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
    }
    units = {
        "v_surface_m_s": "m/s",
        "pv_value_mpa_m_s": "MPa*m/s",
        "dn_value": "mm*rpm",
        "temperature_headroom_c": "degC",
        "pressure_window": "text",
        "calc_type": "text",
        "status": "text",
    }
    return CalculationResult(
        calculation_id=str(result.get("calc_type") or "calculation"),
        version="v9_2_adapter_1",
        calculator=str(result.get("calculation_engine") or "unknown_calculator"),
        status=status,  # type: ignore[arg-type]
        claim_level="L3_deterministic_calculation",
        input_snapshot_hash=snapshot_hash,
        outputs=outputs,
        units={key: value for key, value in units.items() if key in outputs},
        formula_refs=[
            str(record.get("calc_id") or "calculation_engine")
            for record in records
            if isinstance(record, Mapping)
        ],
        output_snapshot_hash=_output_hash(outputs),
        validity_status="valid_for_screening"
        if status in {"ok", "warning"}
        else "input_missing",
        engineering_signals=["deterministic_intermediate_value"],
        limitations=[
            "Calculated value is a screening intermediate, not a final technical release."
        ],
        dependencies=list(dict.fromkeys(dependencies)),
        notes=notes,
    )


def _calc_result(
    *,
    calculation_id: str,
    version: str,
    calculator: str,
    snapshot_hash: str,
    outputs: Mapping[str, Any],
    units: Mapping[str, str],
    dependencies: Iterable[str],
    formula_refs: Iterable[str],
    status: str = "ok",
    validity_status: str = "valid_for_screening",
    missing_inputs: Iterable[str] = (),
    notes: Iterable[str] = (),
    engineering_signals: Iterable[str] = (),
    assumptions: Iterable[dict[str, Any]] = (),
    limitations: Iterable[str] = (),
) -> CalculationResult:
    clean_outputs = {
        key: value for key, value in dict(outputs).items() if value is not None
    }
    return CalculationResult(
        calculation_id=calculation_id,
        version=version,
        calculator=calculator,
        status=status,  # type: ignore[arg-type]
        claim_level="L3_deterministic_calculation",
        input_snapshot_hash=snapshot_hash,
        outputs=clean_outputs,
        units={
            key: value for key, value in dict(units).items() if key in clean_outputs
        },
        formula_refs=list(formula_refs),
        assumptions=list(assumptions),
        output_snapshot_hash=_output_hash(clean_outputs),
        validity_status=validity_status,  # type: ignore[arg-type]
        engineering_signals=list(engineering_signals),
        limitations=list(limitations)
        or ["Screening calculation only; no final technical release."],
        missing_inputs=list(missing_inputs),
        dependencies=list(dict.fromkeys(str(item) for item in dependencies)),
        notes=list(notes),
    )


def build_calculation_state(state: Any) -> CalculationState:
    inputs = _asserted_inputs(state)
    snapshot_hash = _stable_hash(inputs)
    snapshot = CalculationInputSnapshot(
        snapshot_hash=snapshot_hash,
        case_revision=int(
            getattr(
                getattr(state, "persistence_marker", None),
                "postgres_case_revision",
                None,
            )
            or 0
        ),
        inputs=inputs,
    )
    results = [
        _calculation_result_from_compute(result, snapshot_hash=snapshot_hash)
        for result in list(getattr(state, "compute_results", []) or [])
        if isinstance(result, Mapping)
    ]
    results.extend(
        oring_calculations(
            state,
            snapshot_hash=snapshot_hash,
            float_value=_float_value,
            string_value=_string_value,
            calc_result=_calc_result,
        )
    )
    registry = get_calculator_registry()

    blocked: list[str] = []
    stale_result_ids = [
        str(item)
        for item in list(
            getattr(getattr(state, "derived", None), "stale_derived_value_ids", [])
            or []
        )
        if item
    ]
    seal_system = build_seal_system_state(state)
    if any(
        not _is_missing(inputs.get(field))
        for field in ("material", "material_family", "temperature_c")
    ):
        temp_screening = registry.calculate(
            "temperature_window_screening",
            inputs=inputs,
            case_revision=snapshot.case_revision,
        )
        results.append(temp_screening)
        if temp_screening.missing_inputs:
            blocked.append(
                "material.temperature_missing:"
                + ",".join(temp_screening.missing_inputs)
            )
    if any(
        not _is_missing(inputs.get(field))
        for field in ("material", "material_family", "medium")
    ):
        resistance = registry.calculate(
            "material_family_counterindication_check",
            inputs=inputs,
            case_revision=snapshot.case_revision,
        )
        results.append(resistance)
        if resistance.missing_inputs:
            blocked.append(
                "material.chemical_resistance_missing:"
                + ",".join(resistance.missing_inputs)
            )
    if seal_system.seal_family == SealFamily.rotary_shaft.value:
        existing_calculations = {item.calculation_id for item in results} | {
            item.calculator for item in results
        }
        if not existing_calculations.intersection(
            {"rwdr", "rwdr.surface_speed", "surface_speed_from_rpm_and_diameter"}
        ):
            surface_speed = registry.calculate(
                "surface_speed_from_rpm_and_diameter",
                inputs=inputs,
                case_revision=snapshot.case_revision,
            )
            results.append(surface_speed)
            if surface_speed.missing_inputs:
                blocked.append(
                    "rwdr.surface_speed_missing:"
                    + ",".join(surface_speed.missing_inputs)
                )
    guard_results = [_calculation_guard(result, stale_result_ids) for result in results]
    guardrail_violations = _unique(
        f"{guard.calculation_id}:{violation}"
        for guard in guard_results
        for violation in guard.violations
        if violation != "required_inputs_missing"
    )
    status = (
        "ready"
        if results and not blocked
        else ("partial" if results or inputs else "pending")
    )
    return CalculationState(
        status=status,
        input_snapshot=snapshot,
        results=results,
        stale_result_ids=stale_result_ids,
        blocked_calculations=blocked,
        guardrail_violations=guardrail_violations,
        guard_results=guard_results,
    )


def _readiness_band(
    *,
    seal_system: SealSystemState,
    calculation: CalculationState,
    blockers: Iterable[str],
) -> str:
    blocker_list = list(blockers)
    if seal_system.missing_fields:
        return "blocked_missing_core_data"
    if blocker_list:
        return (
            "review_ready_with_open_items"
            if calculation.results
            else "engineering_checks_partial"
        )
    if calculation.results:
        return "rfq_ready_for_expert_review"
    if seal_system.status in {"partial", "ready"}:
        return "screening_possible"
    return "intake_started"


def _completeness_matrix(
    *,
    seal_system: SealSystemState,
    inputs: Mapping[str, Any],
    readiness_band: str,
) -> CompletenessMatrix:
    optional = _OPTIONAL_FIELDS_BY_FAMILY.get(seal_system.seal_family, [])
    missing_optional = [field for field in optional if _is_missing(inputs.get(field))]
    return CompletenessMatrix(
        seal_type=seal_system.seal_type,
        required_fields=[
            {
                "field": field,
                "present": not _is_missing(inputs.get(field)),
                "blocking": field in seal_system.missing_fields,
            }
            for field in seal_system.required_fields
        ],
        present_fields=[
            field
            for field in seal_system.required_fields
            if not _is_missing(inputs.get(field))
        ],
        missing_fields=list(seal_system.missing_fields),
        blocking_missing_fields=list(seal_system.missing_fields),
        optional_but_useful_fields=missing_optional,
        readiness_band=readiness_band,  # type: ignore[arg-type]
        next_best_blocker=next(iter(seal_system.missing_fields), None),
    )


def _risk_findings(
    *,
    seal_system: SealSystemState,
    calculation: CalculationState,
    compound_state: CompoundState,
    document_evidence: DocumentEvidenceState,
    failure_observation: FailureObservationState,
) -> list[EngineeringRiskFinding]:
    findings: list[EngineeringRiskFinding] = []
    for field in seal_system.missing_fields:
        category = (
            "geometry"
            if any(
                marker in field for marker in ("diameter", "groove", "width", "depth")
            )
            else "medium"
        )
        findings.append(
            EngineeringRiskFinding(
                finding_id=f"missing_core.{field}",
                category=category,  # type: ignore[arg-type]
                severity="blocking",
                title=f"Missing core input: {field}",
                technical_reason=f"{field} is required for the classified seal system.",
                user_facing_reason=f"Für diesen Dichtungsfall fehlt noch: {field}.",
                affected_calculations=[
                    item.calculation_id for item in calculation.results
                ],
                affected_claims=["technical_screening", "rfq_dossier"],
                required_next_evidence=[field],
                claim_id=f"deterministic_rule.missing_core.{field}",
                claim_type="missing_input_risk",
                subject_field=field,
                missing_fields=[field],
                blocked_reason="missing_core_input",
                allowed_user_wording=f"Für diesen Dichtungsfall fehlt noch: {field}.",
                forbidden_user_wording=[
                    f"{field} ist fachlich bewertet.",
                    "Der Fall ist freigegeben.",
                ],
            )
        )
    for violation in compound_state.separation_violations:
        findings.append(
            EngineeringRiskFinding(
                finding_id=f"compound.{violation}",
                category="compound",
                severity="blocking",
                title="Compound/Product layer boundary",
                technical_reason="Material family, compound and product/article are separate evidence layers.",
                user_facing_reason="Ein Produkt- oder Compound-Hinweis ersetzt keine Datenblatt- oder Herstellerprüfung.",
                affected_claims=["material_fit", "product_release"],
                required_next_evidence=["compound_datasheet", "manufacturer_review"],
                claim_id=f"deterministic_rule.compound.{violation}",
                claim_type="blocked_claim",
                subject_field="compound",
                missing_fields=["compound_datasheet", "manufacturer_review"],
                blocked_reason="compound_product_layer_boundary",
                allowed_user_wording=(
                    "Ein Produkt- oder Compound-Hinweis ersetzt keine Datenblatt- oder Herstellerpruefung."
                ),
                forbidden_user_wording=[
                    "Das Produkt ist geeignet.",
                    "Das Compound ist freigegeben.",
                ],
            )
        )
    for gap in document_evidence.extraction_gaps + document_evidence.sds_limitations:
        findings.append(
            EngineeringRiskFinding(
                finding_id=f"document.{_stable_hash({'gap': gap})}",
                category="document",
                severity="high" if "prompt_instruction_marker" in gap else "medium",
                title="Document evidence limitation",
                technical_reason=gap,
                user_facing_reason="Dokumentdaten bleiben begrenzt prüfbare Evidenz, bis die relevanten Felder strukturiert bestätigt sind.",
                affected_claims=["document_backed_claim", "medium_compatibility"],
                required_next_evidence=["structured_document_fields"],
                claim_id=f"deterministic_rule.document.{_stable_hash({'gap': gap})}",
                claim_type="blocked_claim",
                subject_field="document_evidence",
                missing_fields=["structured_document_fields"],
                blocked_reason="document_evidence_limitation",
                allowed_user_wording=(
                    "Dokumentdaten bleiben begrenzt pruefbare Evidenz, bis relevante Felder strukturiert bestaetigt sind."
                ),
                forbidden_user_wording=["Das Dokument beweist die Freigabe."],
            )
        )
    if failure_observation.morphology_indicators:
        findings.append(
            EngineeringRiskFinding(
                finding_id="failure.requires_diagnostics",
                category="failure",
                severity="high",
                title="Failure observation requires diagnostics",
                technical_reason="Failure morphology can indicate hypotheses but cannot prove root cause.",
                user_facing_reason="Das Schadbild ist ein Indiz. Für eine Ursache brauchen wir Diagnose- und Vergleichsdaten.",
                affected_claims=["root_cause"],
                required_next_evidence=list(failure_observation.required_diagnostics),
                claim_id="deterministic_rule.failure.requires_diagnostics",
                claim_type="context_advisory",
                subject_field="failure_observation",
                evidence_fields=["failure_observation"],
                missing_fields=list(failure_observation.required_diagnostics),
                allowed_user_wording=(
                    "Das Schadbild ist ein Indiz; fuer eine Ursache brauchen wir Diagnose- und Vergleichsdaten."
                ),
                forbidden_user_wording=["Die eindeutige Schadensursache ist bewiesen."],
            )
        )
    return findings


def build_engineering_state(
    *,
    seal_system: SealSystemState,
    calculation: CalculationState,
    compound_state: CompoundState | None = None,
    document_evidence: DocumentEvidenceState | None = None,
    failure_observation: FailureObservationState | None = None,
    inputs: Mapping[str, Any] | None = None,
) -> EngineeringState:
    blockers = list(
        dict.fromkeys(seal_system.missing_fields + calculation.blocked_calculations)
    )
    compound_state = compound_state or CompoundState()
    document_evidence = document_evidence or DocumentEvidenceState()
    failure_observation = failure_observation or FailureObservationState()
    blockers.extend(compound_state.separation_violations)
    blockers.extend(document_evidence.prompt_injection_findings)
    blockers = _unique(blockers)
    readiness_band = _readiness_band(
        seal_system=seal_system, calculation=calculation, blockers=blockers
    )
    completeness = _completeness_matrix(
        seal_system=seal_system,
        inputs=inputs or {},
        readiness_band=readiness_band,
    )
    risks = _risk_findings(
        seal_system=seal_system,
        calculation=calculation,
        compound_state=compound_state,
        document_evidence=document_evidence,
        failure_observation=failure_observation,
    )
    assumptions = [
        EngineeringAssumption(
            assumption_id=f"seal_system.assumption.{index}",
            text=text,
            affected_fields=seal_system.missing_fields,
            invalidates_calculations=[
                item.calculation_id for item in calculation.results
            ],
        )
        for index, text in enumerate(seal_system.assumptions)
    ]
    ready_calcs = [
        item.calculation_id
        for item in calculation.results
        if item.status in {"ok", "warning"}
    ]
    next_action = (
        "review_engineering_dossier"
        if not blockers and ready_calcs
        else "collect_missing_inputs"
    )
    if blockers and "sealing_type" in blockers:
        next_action = "identify_seal_system"
    elif blockers and any(
        "shaft_diameter" in item or "speed_rpm" in item for item in blockers
    ):
        next_action = "collect_geometry_and_motion_inputs"
    decision = EngineeringDecision(
        decision_id="engineering_orchestrator.primary",
        decision_type="prequalification_readiness",
        status="ready"
        if not blockers and ready_calcs
        else ("partial" if seal_system.status != "pending" else "pending"),
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
        risk_findings=risks,
        completeness_matrix=completeness,
        next_best_engineering_action=next_action,
    )


def build_evidence_graph_state(state: Any) -> EvidenceGraphState:
    nodes: list[EvidenceGraphNode] = []
    edges: list[EvidenceGraphEdge] = []
    lifecycle_gaps: list[str] = []
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
        metadata = _document_metadata(item)
        evidence_type = str(
            item.get("type")
            or item.get("document_type")
            or item.get("source_type")
            or "rag_card"
        )
        permitted = ["L2_screening"]
        if evidence_type in {
            "datasheet",
            "manufacturer_datasheet",
            "certificate",
            "test_report",
        }:
            permitted.append("L5_document_backed")
        if not metadata.get("retrieved_at"):
            lifecycle_gaps.append(f"{source_ref}:retrieved_at_missing")
        if evidence_type in {"certificate", "test_report"} and not metadata.get(
            "valid_until"
        ):
            lifecycle_gaps.append(f"{source_ref}:valid_until_missing")
        nodes.append(
            EvidenceGraphNode(
                node_id=node_id,
                evidence_type=evidence_type,
                title=title,
                source_ref=source_ref,
                claim_level="L2_screening",
                applicability=str(item.get("applicability") or "indirect"),  # type: ignore[arg-type]
                source_owner=metadata.get("source_owner"),
                version=metadata.get("version"),
                issue_date=metadata.get("issue_date"),
                valid_until=metadata.get("valid_until"),
                retrieved_at=metadata.get("retrieved_at"),
                region=metadata.get("region"),
                manufacturer=metadata.get("manufacturer"),
                compound_id=metadata.get("compound_id"),
                source_scope=metadata.get("source_scope"),
                permitted_claim_levels=permitted,  # type: ignore[arg-type]
                confidence=float(item.get("confidence"))
                if item.get("confidence") is not None
                else None,
                limitations=[
                    "Retrieved evidence requires applicability review.",
                    "Source lifecycle metadata limits claim strength until version/date/scope are complete.",
                ],
            )
        )
        edges.append(
            EvidenceGraphEdge(
                from_node_id=node_id, to_target_id="engineering_prequalification"
            )
        )
    evidence_state = getattr(state, "evidence", None)
    for index, finding in enumerate(
        list(getattr(evidence_state, "source_backed_findings", []) or [])
    ):
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
    gaps = list(getattr(evidence_state, "evidence_gaps", []) or []) + lifecycle_gaps
    status = "ready" if nodes and not gaps else ("partial" if nodes else "pending")
    return EvidenceGraphState(
        status=status,
        nodes=nodes,
        edges=edges,
        unresolved_gaps=[str(item) for item in gaps],
    )


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
            products.append(
                ProductCandidate(product_id=str(value), article_ref=str(value))
            )

    violations: list[str] = []
    if products and not compounds:
        violations.append("product_candidate_without_compound_layer")
    if compounds and not families:
        violations.append("compound_candidate_without_material_family_layer")
    status = (
        "ready"
        if families and not violations
        else ("partial" if families or compounds or products else "pending")
    )
    return CompoundState(
        status=status,
        material_family_candidates=families,
        compound_candidates=compounds,
        product_candidates=products,
        separation_violations=violations,
    )


def build_document_evidence_state(state: Any) -> DocumentEvidenceState:
    docs: list[dict[str, Any]] = []
    prompt_findings: list[str] = []
    sds_limitations: list[str] = []
    drawing_fields: dict[str, Any] = {}
    sds_fields: dict[str, Any] = {}
    medium_exposures: list[dict[str, Any]] = []
    candidate_facts: list[dict[str, Any]] = []

    for index, item in enumerate(list(getattr(state, "rag_evidence", []) or [])):
        if not isinstance(item, Mapping):
            continue
        text = _document_text(item)
        lower_text = text.lower()
        document_ref = str(
            item.get("document_id") or item.get("source_id") or f"evidence.{index}"
        )
        doc_type = _document_type(item, text)
        docs.append(
            {
                "document_ref": document_ref,
                "title": str(item.get("title") or item.get("source_title") or ""),
                "document_type": doc_type,
                "claim_level": "L1_normalized",
                "accepted_as_instruction": False,
                **{
                    key: value
                    for key, value in _document_metadata(item).items()
                    if value
                },
            }
        )
        if item.get("field") and item.get("value") is not None:
            candidate_facts.append(
                {
                    "field": str(item.get("field")),
                    "value": item.get("value"),
                    "source_ref": document_ref,
                    "claim_level": "L1_normalized",
                    "requires_user_confirmation": True,
                }
            )
        for marker in _PROMPT_INJECTION_MARKERS:
            if marker in lower_text:
                prompt_findings.append(
                    f"{document_ref}:prompt_instruction_marker:{marker}"
                )
        if doc_type == "sds":
            product_name = item.get("product_name") or _extract_first(
                r"(?:product|produkt|name)\s*[:=]\s*([^\n;]+)", text
            )
            manufacturer = item.get("manufacturer") or _extract_first(
                r"(?:manufacturer|hersteller)\s*[:=]\s*([^\n;]+)", text
            )
            revision = item.get("revision") or _extract_first(
                r"(?:revision|version|ausgabedatum|revision date)\s*[:=]\s*([0-9A-Za-z_.:/ -]+)",
                text,
            )
            cas_components = item.get("cas_components") or _extract_cas_components(text)
            composition_present = _has_positive_marker(
                text,
                (
                    r"\bcomposition\b",
                    r"\bzusammensetzung\b",
                    r"\bsection\s*3\b",
                    r"\babschnitt\s*3\b",
                ),
            )
            if any(
                marker in lower_text
                for marker in (
                    "nicht strukturiert",
                    "not structured",
                    "not disclosed",
                    "nicht offengelegt",
                )
            ):
                composition_present = False
            composition_status = (
                "partly_known"
                if cas_components or composition_present
                else "product_name_only"
            )
            sds_payload = {
                "source_ref": document_ref,
                "claim_level": "L1_normalized",
                "product_name": product_name,
                "manufacturer": manufacturer,
                "revision": revision,
                "cas_components": cas_components,
                "composition_status": composition_status,
                "limitations": ["SDS is not a complete formulation document."],
            }
            sds_fields[document_ref] = {
                key: value
                for key, value in sds_payload.items()
                if value not in (None, [], "")
            }
            medium_exposures.append(
                {
                    "exposure_id": f"medium_exposure.{document_ref}",
                    "medium_role": "process_or_cleaning_medium",
                    "display_name": str(
                        product_name or item.get("title") or document_ref
                    ),
                    "product_name": product_name,
                    "cas_components": cas_components,
                    "unknown_components": []
                    if cas_components
                    else ["composition_not_fully_disclosed"],
                    "source_refs": [document_ref],
                    "composition_status": composition_status,
                }
            )
            if not revision:
                sds_limitations.append(f"{document_ref}:missing_revision_metadata")
            if not composition_present and not cas_components:
                sds_limitations.append(f"{document_ref}:composition_not_structured")
        if doc_type == "drawing":
            extracted: dict[str, Any] = {
                "source_ref": document_ref,
                "claim_level": "L1_normalized",
            }
            drawing_patterns = {
                "shaft_diameter_mm": r"(?:shaft|welle|wellendurchmesser)\D{0,16}(\d+(?:[,.]\d+)?)\s*mm",
                "groove_depth_mm": r"(?:groove depth|nuttiefe)\D{0,16}(\d+(?:[,.]\d+)?)\s*mm",
                "groove_width_mm": r"(?:groove width|nutbreite)\D{0,16}(\d+(?:[,.]\d+)?)\s*mm",
                "surface_ra_um": r"(?:ra|rauheit)\D{0,8}(\d+(?:[,.]\d+)?)\s*(?:um|µm)",
            }
            for field, pattern in drawing_patterns.items():
                value = _extract_first(pattern, text)
                if value:
                    extracted[field] = value.replace(",", ".")
                    candidate_facts.append(
                        {
                            "field": field,
                            "value": value.replace(",", "."),
                            "source_ref": document_ref,
                            "claim_level": "L1_normalized",
                            "requires_user_confirmation": True,
                            "affects_calculators": [
                                "rwdr.surface_speed",
                                "oring.geometry_screening",
                            ],
                        }
                    )
            drawing_fields[document_ref] = extracted

    extraction_gaps: list[str] = []
    if not docs:
        extraction_gaps.append("no_structured_document_evidence")
    elif not drawing_fields and not sds_fields:
        extraction_gaps.append("no_governed_drawing_or_sds_fields")
    extraction_gaps.extend(prompt_findings)
    status = (
        "ready"
        if docs and not extraction_gaps and not sds_limitations
        else ("partial" if docs else "pending")
    )
    return DocumentEvidenceState(
        status=status,
        documents_seen=docs,
        drawing_fields=drawing_fields,
        sds_fields=sds_fields,
        medium_exposures=medium_exposures,
        candidate_facts=candidate_facts,
        prompt_injection_findings=_unique(prompt_findings),
        sds_limitations=_unique(sds_limitations),
        extraction_gaps=_unique(extraction_gaps),
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
        "abrasion": r"\b(verschleiss|verschleiß|abrieb|wear|abrasion)\b",
        "extrusion_nibbling": r"\b(extrusion|spaltextrusion|nibbling|spalt|ausgepresst)\b",
        "thermal_degradation": r"\b(hitze|verbrannt|thermal|temperatur|verhaertet|verhärtet)\b",
        "chemical_swelling": r"\b(quellung|aufgequollen|chemisch|riss|swelling)\b",
        "compression_set": r"\b(compression set|bleibende verformung|setzerscheinung)\b",
        "assembly_damage": r"\b(montageschaden|schnitt|cut|assembly)\b",
    }
    for key, pattern in patterns.items():
        if re.search(pattern, text):
            indicators.append(key)
    possible: list[str] = []
    diagnostics: list[str] = []
    if "leakage" in indicators:
        possible.append("installation_gap_or_surface_or_pressure_boundary")
        diagnostics.extend(
            [
                "installation_review",
                "surface_finish_measurement",
                "pressure_profile_check",
            ]
        )
    if "abrasion" in indicators:
        possible.append("friction_or_lubrication_or_surface_boundary")
        diagnostics.extend(
            [
                "wear_track_inspection",
                "lubrication_review",
                "counterface_hardness_check",
            ]
        )
    if "extrusion_nibbling" in indicators:
        possible.append("gap_or_pressure_or_hardness_boundary")
        diagnostics.extend(
            ["extrusion_gap_measurement", "pressure_peak_review", "hardness_check"]
        )
    if "thermal_degradation" in indicators:
        possible.append("thermal_or_speed_boundary")
        diagnostics.extend(
            ["temperature_history_review", "surface_speed_recalculation"]
        )
    if "chemical_swelling" in indicators:
        possible.append("medium_material_incompatibility")
        diagnostics.extend(
            ["medium_analysis", "compound_datasheet_review", "sds_review"]
        )
    morphology_tags = [
        {
            "tag_id": indicator,
            "label": indicator.replace("_", " "),
            "possible_indications": possible,
            "required_diagnostics": _unique(diagnostics),
            "forbidden_claims": [
                "definitive_root_cause",
                "final_failure_cause_from_image",
            ],
        }
        for indicator in _unique(indicators)
    ]
    status = "partial" if indicators else "pending"
    return FailureObservationState(
        status=status,
        morphology_indicators=_unique(indicators),
        morphology_tags=morphology_tags,
        possible_causes=_unique(possible),
        required_diagnostics=_unique(diagnostics),
    )


def build_engineering_update(state: Any) -> dict[str, Any]:
    inputs = _asserted_inputs(state)
    seal_system = build_seal_system_state(state)
    calculation = build_calculation_state(state)
    evidence_graph = build_evidence_graph_state(state)
    compound_state = build_compound_state(state)
    document_evidence = build_document_evidence_state(state)
    failure_observation = build_failure_observation_state(state)
    engineering = build_engineering_state(
        seal_system=seal_system,
        calculation=calculation,
        compound_state=compound_state,
        document_evidence=document_evidence,
        failure_observation=failure_observation,
        inputs=inputs,
    )
    return {
        "seal_system": seal_system,
        "engineering": engineering,
        "calculation": calculation,
        "evidence_graph": evidence_graph,
        "compound_state": compound_state,
        "document_evidence": document_evidence,
        "failure_observation": failure_observation,
    }


def _standard_entry_from_check(check: Mapping[str, Any]) -> StandardsRegistryEntry:
    module_id = str(check.get("module_id") or "unknown_standard_module")
    metadata = (
        _STANDARD_METADATA.get(module_id)
        or _STANDARD_METADATA.get(module_id.lower())
        or {}
    )
    if not metadata and "3601" in module_id:
        metadata = _STANDARD_METADATA["iso_3601_2"]
    title = str(
        metadata.get("title")
        or module_id.replace("norm_", "").replace("_", " ").upper()
    )
    return StandardsRegistryEntry(
        standard_id=str(metadata.get("standard_id") or module_id),
        title=title,
        publisher=str(metadata.get("publisher") or check.get("publisher") or "unknown"),
        version=str(check.get("version") or metadata.get("edition") or "metadata_only"),
        edition=str(metadata.get("edition") or check.get("edition") or "metadata_only"),
        publication_date=check.get("publication_date")
        or metadata.get("publication_date"),
        scope=str(
            check.get("scope") or metadata.get("scope") or check.get("status") or ""
        ),
        region=check.get("region"),
        applies_to_seal_types=list(
            metadata.get("applies_to_seal_types")
            or check.get("applies_to_seal_types")
            or []
        ),
        relevant_fields=list(
            metadata.get("relevant_fields") or check.get("relevant_fields") or []
        ),
        licensed_content_available=bool(
            check.get("licensed_content_available") or False
        ),
        source_url=check.get("source_url") or metadata.get("source_url"),
        source_checked_at=check.get("source_checked_at") or "2026-05-14",
        source_module_id=module_id,
        conformity_claim_allowed=False,
    )


def build_standards_state(state: Any) -> StandardsState:
    norm_checks = [
        item
        for item in list(
            getattr(getattr(state, "sealai_norm", None), "norm_checks", []) or []
        )
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
    status = (
        "ready" if entries and not blocking else ("partial" if entries else "pending")
    )
    return StandardsState(
        status=status,
        applicable_entries=entries,
        check_results=[dict(check) for check in norm_checks],
        blocking_gaps=list(dict.fromkeys(blocking)),
    )


def build_review_state(state: Any) -> ReviewState:
    rfq = getattr(state, "rfq", None)
    blocking = [
        str(item) for item in list(getattr(rfq, "blocking_findings", []) or []) if item
    ]
    soft = [str(item) for item in list(getattr(rfq, "soft_findings", []) or []) if item]
    corrections = [
        str(item)
        for item in list(getattr(rfq, "required_corrections", []) or [])
        if item
    ]
    required_reviews = ["rfq_scope_review", "claim_boundary_review"]
    dossier_modules = ["facts", "calculations", "candidates", "blockers"]

    compound_state = getattr(state, "compound_state", None)
    document_evidence = getattr(state, "document_evidence", None)
    failure_observation = getattr(state, "failure_observation", None)
    standards = getattr(state, "standards", None)

    if list(getattr(compound_state, "product_candidates", []) or []):
        required_reviews.append("manufacturer_product_review")
    if list(getattr(compound_state, "compound_candidates", []) or []) or list(
        getattr(compound_state, "material_family_candidates", []) or []
    ):
        required_reviews.append("compound_datasheet_review")
    if list(getattr(standards, "applicable_entries", []) or []):
        required_reviews.append("licensed_standards_review")
    if dict(getattr(document_evidence, "sds_fields", {}) or {}):
        required_reviews.append("sds_review")
    if list(getattr(document_evidence, "prompt_injection_findings", []) or []):
        required_reviews.append("document_security_review")
    if list(getattr(failure_observation, "morphology_indicators", []) or []):
        required_reviews.append("failure_diagnostics_review")

    blocking.extend(
        str(item)
        for item in list(getattr(standards, "blocking_gaps", []) or [])
        if item
    )
    blocking.extend(
        str(item)
        for item in list(
            getattr(document_evidence, "prompt_injection_findings", []) or []
        )
        if item
    )
    blocking.extend(
        str(item)
        for item in list(getattr(compound_state, "separation_violations", []) or [])
        if item
    )
    blocking = _unique(blocking)

    reviewer_id = getattr(rfq, "critical_review_reviewer_id", None) or getattr(
        rfq, "reviewer_id", None
    )
    decision_value = (
        getattr(rfq, "critical_review_decision", None)
        or getattr(rfq, "review_decision", None)
        or (
            "accepted_for_rfq"
            if getattr(rfq, "critical_review_passed", False)
            else None
        )
    )
    if blocking:
        status = "blocked"
    elif corrections:
        status = "changes_required"
    elif (
        getattr(rfq, "critical_review_passed", False) and reviewer_id and decision_value
    ):
        status = "approved_scope"
    elif getattr(rfq, "critical_review_passed", False):
        status = "pending"
        soft.append("critical_review_passed_without_reviewer_or_decision")
    elif getattr(rfq, "critical_review_status", "") not in {"", "not_run"}:
        status = "pending"
    else:
        status = "not_started"
    decisions: list[dict[str, Any]] = []
    approved_claim_level = None
    if status == "approved_scope" and reviewer_id and decision_value:
        approved_claim_level = "L6_expert_approved"
        decisions.append(
            {
                "decision_id": f"review.{_stable_hash({'reviewer_id': reviewer_id, 'decision': decision_value})}",
                "review_type": "rfq_review",
                "reviewer_id": str(reviewer_id),
                "decision": str(decision_value),
                "approved_claim_level": approved_claim_level,
                "scope": ["rfq_handover", "screening_dossier"],
                "source_refs": [],
            }
        )
    return ReviewState(
        status=status,  # type: ignore[arg-type]
        reviewer_id=str(reviewer_id) if reviewer_id else None,
        scope=["rfq_handover", "claim_boundary", "manufacturer_review"],
        required_review_types=_unique(required_reviews),
        review_guard_notes=[
            "No expert-review status without reviewer_id and decision.",
            "No approved_claim_level is created by AI.",
            "Certificate claims require certificate evidence.",
            "Overrides must be logged before scoped claims change.",
        ],
        dossier_modules=dossier_modules,
        decisions=decisions,
        approved_claim_level=approved_claim_level,  # type: ignore[arg-type]
        decision_summary=str(getattr(rfq, "critical_review_status", "") or ""),
        blocking_findings=blocking,
        soft_findings=_unique(soft),
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
            "validity_status": result.validity_status,
            "outputs": dict(result.outputs),
            "units": dict(result.units),
            "formula_refs": list(result.formula_refs),
            "input_snapshot_hash": result.input_snapshot_hash,
            "output_snapshot_hash": result.output_snapshot_hash,
            "missing_inputs": list(result.missing_inputs),
            "notes": list(result.notes),
            "limitations": list(result.limitations),
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
    calculation_state = getattr(state, "calculation", CalculationState())
    calculation_items = _calculation_items(calculation_state)
    candidates = _candidate_items(state)
    compound_state = getattr(state, "compound_state", CompoundState())
    seal_system = getattr(state, "seal_system", SealSystemState())
    engineering = getattr(state, "engineering", EngineeringState())
    standards = getattr(state, "standards", StandardsState())
    evidence_graph = getattr(state, "evidence_graph", EvidenceGraphState())
    document_evidence = getattr(state, "document_evidence", DocumentEvidenceState())
    review_state = getattr(state, "review_state", ReviewState())
    blockers: list[str] = []
    blockers.extend(
        str(item) for item in list(getattr(engineering, "blockers", []) or []) if item
    )
    blockers.extend(
        str(item)
        for item in list(getattr(standards, "blocking_gaps", []) or [])
        if item
    )
    blockers.extend(
        str(item)
        for item in list(getattr(compound_state, "separation_violations", []) or [])
        if item
    )
    blockers.extend(
        str(item)
        for item in list(getattr(document_evidence, "extraction_gaps", []) or [])
        if item
    )
    blockers.extend(
        str(item)
        for item in list(getattr(document_evidence, "sds_limitations", []) or [])
        if item
    )
    blockers.extend(
        str(item)
        for item in list(getattr(evidence_graph, "unresolved_gaps", []) or [])
        if item
    )
    blockers.extend(
        str(item)
        for item in list(
            getattr(getattr(state, "rfq", None), "blocking_findings", []) or []
        )
        if item
    )
    failure = getattr(state, "failure_observation", None)
    if list(getattr(failure, "morphology_indicators", []) or []):
        blockers.append("failure_observation_requires_diagnostics_review")
    blockers = _unique(blockers)
    status = (
        "ready"
        if facts and not blockers
        else ("partial" if facts or calculation_items or candidates else "pending")
    )
    if seal_system.missing_fields:
        readiness_band = "blocked_missing_core_data"
    elif status == "ready" and review_state.status == "approved_scope":
        readiness_band = "rfq_ready_for_expert_review"
    elif facts and calculation_items and not blockers:
        readiness_band = "review_ready_with_open_items"
    elif facts or calculation_items or candidates:
        readiness_band = "engineering_checks_partial"
    else:
        readiness_band = "not_ready"
    allowed_next_actions = [
        "collect_missing_inputs",
        "request_datasheets",
        "request_manufacturer_review",
    ]
    if calculation_items:
        allowed_next_actions.append("export_screening_rfq_dossier")
    if list(getattr(failure, "required_diagnostics", []) or []):
        allowed_next_actions.append("run_failure_diagnostics_review")
    sections = [
        DossierSection(section_id="facts", title="Governed Facts", items=facts),
        DossierSection(
            section_id="calculations",
            title="Deterministic Calculations",
            items=calculation_items,
        ),
        DossierSection(
            section_id="candidates", title="Screening Candidates", items=candidates
        ),
        DossierSection(
            section_id="blockers",
            title="Open Blockers",
            items=[{"blocker": blocker} for blocker in blockers],
        ),
    ]
    session_id = str(getattr(state, "session_id", "") or "")
    material_family_candidates = [
        {
            "family": item.family,
            "claim_level": item.claim_level,
            "basis": list(item.basis),
        }
        for item in list(compound_state.material_family_candidates)
    ]
    compound_candidates = [
        {
            "compound_id": item.compound_id,
            "family": item.family,
            "designation": item.designation,
            "claim_level": item.claim_level,
            "requires_datasheet": item.requires_datasheet,
        }
        for item in list(compound_state.compound_candidates)
    ]
    product_candidates = [
        {
            "product_id": item.product_id,
            "manufacturer": item.manufacturer,
            "article_ref": item.article_ref,
            "compound_id": item.compound_id,
            "claim_level": item.claim_level,
            "requires_manufacturer_review": item.requires_manufacturer_review,
        }
        for item in list(compound_state.product_candidates)
    ]
    return DossierState(
        status=status,
        dossier_id=f"rfq-dossier-v92-{session_id}" if session_id else None,
        case_revision=int(
            getattr(calculation_state.input_snapshot, "case_revision", 0)
            if calculation_state.input_snapshot
            else 0
        ),
        seal_system_summary={
            "seal_family": seal_system.seal_family,
            "seal_type": seal_system.seal_type,
            "required_fields": list(seal_system.required_fields),
            "missing_fields": list(seal_system.missing_fields),
        },
        facts=facts,
        calculations=calculation_items,
        candidates=candidates,
        material_family_candidates=material_family_candidates,
        compound_candidates=compound_candidates,
        product_candidates=product_candidates,
        blockers=blockers,
        risk_findings=[
            item.model_dump()
            for item in list(getattr(engineering, "risk_findings", []) or [])
        ],
        document_refs=list(document_evidence.documents_seen),
        evidence_summary=[
            {
                "node_id": node.node_id,
                "evidence_type": node.evidence_type,
                "source_ref": node.source_ref,
                "applicability": node.applicability,
                "permitted_claim_levels": list(node.permitted_claim_levels),
            }
            for node in list(evidence_graph.nodes)
        ],
        standards_refs=[
            entry.model_dump() for entry in list(standards.applicable_entries)
        ],
        compliance_notes=[
            {
                "note": "No compliance or certificate claim without certificate evidence and expert review.",
                "claim_level": "L2_screening",
            }
        ],
        expert_review_status=review_state.status,
        allowed_claims=_allowed_claims(state),
        readiness_band=readiness_band,  # type: ignore[arg-type]
        allowed_next_actions=_unique(allowed_next_actions),
        sections=sections,
    )


def build_dossier_update(state: Any) -> dict[str, Any]:
    standards = build_standards_state(state)
    state_with_standards = state.model_copy(update={"standards": standards})
    review_state = build_review_state(state_with_standards)
    state_with_review = state_with_standards.model_copy(
        update={"review_state": review_state}
    )
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
    "build_document_evidence_state",
    "build_dossier_update",
    "build_engineering_state",
    "build_engineering_update",
    "build_evidence_graph_state",
    "build_failure_observation_state",
    "build_seal_system_state",
    "build_standards_state",
]
