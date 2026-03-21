# backend/app/langgraph_v2/projections/case_workspace.py
"""Deterministic projection from internal SealAIState to UI-facing CaseWorkspaceProjection.

All logic here is pure — no I/O, no LLM, no DB calls.
Input: a dict of state_values (as returned by LangGraph checkpoint snapshot.values).
Output: a CaseWorkspaceProjection ready for JSON serialization.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from app.api.v1.schemas.case_workspace import (
    ArtifactStatus,
    CandidateClusterSummary,
    CaseSummary,
    CaseWorkspaceProjection,
    ClaimItem,
    ClaimsSummary,
    CompletenessStatus,
    ConflictSummary,
    CycleInfo,
    ElevationHint,
    GovernanceStatus,
    ManufacturerQuestions,
    MaterialFitItem,
    PartnerMatchingSummary,
    RFQPackageSummary,
    RFQStatus,
    SpecificityInfo,
)


def _pillar(state: Dict[str, Any], pillar: str) -> Dict[str, Any]:
    raw = state.get(pillar)
    if hasattr(raw, "model_dump"):
        return raw.model_dump(exclude_none=True)
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _field(state: Dict[str, Any], pillar: str, key: str, default: Any = None) -> Any:
    pillar_data = _pillar(state, pillar)
    if key in pillar_data:
        return pillar_data[key]
    return state.get(key, default)


def project_case_workspace(state_values: Dict[str, Any]) -> CaseWorkspaceProjection:
    """Build a CaseWorkspaceProjection from raw checkpoint state_values."""
    conv = _pillar(state_values, "conversation")
    wp = _pillar(state_values, "working_profile")
    reasoning = _pillar(state_values, "reasoning")
    system = _pillar(state_values, "system")

    intent = conv.get("intent") or {}
    if isinstance(intent, str):
        intent = {"goal": intent}

    candidate_clusters = _build_candidate_clusters(system)
    rfq_status = _build_rfq_status(system, reasoning)
    rfq_package = _build_rfq_package(system)
    mfr_questions = _build_manufacturer_questions(system, reasoning)
    completeness = _build_completeness(wp, reasoning, system)
    specificity = _build_specificity(system, reasoning, completeness, candidate_clusters)
    cycle_info = _build_cycle_info(reasoning, wp, system)

    return CaseWorkspaceProjection(
        case_summary=_build_case_summary(conv, reasoning, intent),
        completeness=completeness,
        governance_status=_build_governance_status(system, reasoning),
        specificity=specificity,
        candidate_clusters=candidate_clusters,
        conflicts=_build_conflicts(system),
        claims_summary=_build_claims_summary(reasoning, system),
        manufacturer_questions=mfr_questions,
        rfq_status=rfq_status,
        artifact_status=_build_artifact_status(wp, system),
        rfq_package=rfq_package,
        partner_matching=_build_partner_matching(
            candidate_clusters, rfq_status, rfq_package, mfr_questions,
            specificity, cycle_info, reasoning, system,
        ),
        cycle_info=cycle_info,
    )


def _build_case_summary(
    conv: Dict[str, Any], reasoning: Dict[str, Any], intent: Dict[str, Any]
) -> CaseSummary:
    return CaseSummary(
        thread_id=conv.get("thread_id"),
        user_id=conv.get("user_id"),
        phase=reasoning.get("phase"),
        intent_goal=intent.get("goal"),
        application_category=conv.get("application_category"),
        seal_family=conv.get("seal_family"),
        motion_type=conv.get("motion_type"),
        user_persona=conv.get("user_persona"),
        turn_count=reasoning.get("turn_count", 0),
        max_turns=reasoning.get("max_turns", 12),
    )


def _build_completeness(
    wp: Dict[str, Any], reasoning: Dict[str, Any], system: Dict[str, Any]
) -> CompletenessStatus:
    # missing_critical_parameters from requirement_spec in answer_contract or system
    missing_critical: List[str] = []
    answer_contract = system.get("answer_contract") or {}
    if isinstance(answer_contract, dict):
        req_spec = answer_contract.get("requirement_spec") or {}
        if isinstance(req_spec, dict):
            missing_critical = req_spec.get("missing_critical_parameters", [])

    # Fall back to sealing_requirement_spec
    if not missing_critical:
        srs = system.get("sealing_requirement_spec") or {}
        if isinstance(srs, dict):
            missing_critical = srs.get("missing_critical_parameters", [])

    return CompletenessStatus(
        coverage_score=reasoning.get("coverage_score", 0.0),
        coverage_gaps=reasoning.get("coverage_gaps", []),
        completeness_depth=reasoning.get("completeness_depth", "precheck"),
        missing_critical_parameters=missing_critical,
        discovery_missing=reasoning.get("discovery_missing", []),
        analysis_complete=wp.get("analysis_complete", False),
        recommendation_ready=reasoning.get("recommendation_ready", False),
    )


def _build_governance_status(
    system: Dict[str, Any], reasoning: Dict[str, Any]
) -> GovernanceStatus:
    # Primary source: answer_contract governance
    answer_contract = system.get("answer_contract") or {}
    gov_meta = system.get("governance_metadata") or {}
    if isinstance(gov_meta, dict):
        pass
    elif hasattr(gov_meta, "model_dump"):
        gov_meta = gov_meta.model_dump(exclude_none=True)
    else:
        gov_meta = {}

    # answer_contract level governance
    ac_gov = {}
    release_status = "inadmissible"
    required_disclaimers: List[str] = []
    if isinstance(answer_contract, dict):
        ac_gov = answer_contract.get("governance_metadata") or {}
        if hasattr(ac_gov, "model_dump"):
            ac_gov = ac_gov.model_dump(exclude_none=True)
        elif not isinstance(ac_gov, dict):
            ac_gov = {}
        release_status = answer_contract.get("release_status", "inadmissible")
        required_disclaimers = answer_contract.get("required_disclaimers", [])

    # Merge: answer_contract governance takes precedence, system governance as fallback
    merged_gov = {**gov_meta, **{k: v for k, v in ac_gov.items() if v}}

    return GovernanceStatus(
        release_status=release_status,
        scope_of_validity=merged_gov.get("scope_of_validity", []),
        assumptions_active=merged_gov.get("assumptions_active", []),
        unknowns_release_blocking=merged_gov.get("unknowns_release_blocking", []),
        unknowns_manufacturer_validation=merged_gov.get("unknowns_manufacturer_validation", []),
        gate_failures=merged_gov.get("gate_failures", []),
        governance_notes=merged_gov.get("governance_notes", []),
        required_disclaimers=required_disclaimers,
        verification_passed=system.get("verification_passed", True),
    )


def _build_specificity(
    system: Dict[str, Any], 
    reasoning: Dict[str, Any],
    completeness: CompletenessStatus,
    clusters: CandidateClusterSummary,
) -> SpecificityInfo:
    srs = system.get("sealing_requirement_spec") or {}
    if hasattr(srs, "model_dump"):
        srs = srs.model_dump(exclude_none=True)
    elif not isinstance(srs, dict):
        srs = {}

    req_spec = srs.get("material_specificity_required", "family_only")
    comp_depth = reasoning.get("completeness_depth", "precheck")

    elevation_hints: List[ElevationHint] = []
    
    # Gap 1: Missing technical data (Priority 1-5)
    if completeness.missing_critical_parameters:
        for p in completeness.missing_critical_parameters:
            label = p.replace("_", " ").replace("c", "C").capitalize()
            # Core technical params have higher priority
            prio = 1 if p in ("medium", "pressure_bar", "temperature_c") else 2
            elevation_hints.append(ElevationHint(
                label=f"Define {label}",
                field_key=p,
                reason="Enables technical compound matching",
                priority=prio,
                action_type="provide_data"
            ))

    # Gap 2: Material name is too generic (Priority 10)
    # If no viable candidates exist but we have manufacturer validation items (likely families)
    if not clusters.plausibly_viable and clusters.manufacturer_validation_required:
        elevation_hints.append(ElevationHint(
            label="Specify exact compound",
            field_key="seal_material",
            reason="Required for authoritative release",
            priority=10,
            action_type="specify_material"
        ))

    # Sort hints by priority
    elevation_hints.sort(key=lambda x: x.priority)

    elevation_possible = len(elevation_hints) > 0
    elevation_target = "compound_required" if elevation_possible else None

    return SpecificityInfo(
        material_specificity_required=req_spec,
        completeness_depth=comp_depth,
        elevation_possible=elevation_possible,
        elevation_hints=elevation_hints,
        elevation_target=elevation_target,
    )


def _build_candidate_clusters(system: Dict[str, Any]) -> CandidateClusterSummary:
    answer_contract = system.get("answer_contract") or {}
    if not isinstance(answer_contract, dict):
        return CandidateClusterSummary()

    clusters = answer_contract.get("candidate_clusters") or {}
    if not isinstance(clusters, dict):
        return CandidateClusterSummary()

    viable = clusters.get("plausibly_viable", [])
    mfr_val = clusters.get("viable_only_with_manufacturer_validation", [])
    excluded = clusters.get("inadmissible_or_excluded", [])

    return CandidateClusterSummary(
        plausibly_viable=viable if isinstance(viable, list) else [],
        manufacturer_validation_required=mfr_val if isinstance(mfr_val, list) else [],
        inadmissible_or_excluded=excluded if isinstance(excluded, list) else [],
        total_candidates=(
            len(viable if isinstance(viable, list) else [])
            + len(mfr_val if isinstance(mfr_val, list) else [])
            + len(excluded if isinstance(excluded, list) else [])
        ),
    )


def _build_conflicts(system: Dict[str, Any]) -> ConflictSummary:
    answer_contract = system.get("answer_contract") or {}
    verification_report = system.get("verification_report") or {}

    conflicts: List[Dict[str, Any]] = []
    if isinstance(verification_report, dict):
        raw = verification_report.get("conflicts", [])
        if isinstance(raw, list):
            conflicts = [
                c if isinstance(c, dict) else (c.model_dump() if hasattr(c, "model_dump") else {})
                for c in raw
            ]

    open_count = sum(1 for c in conflicts if c.get("resolution_status") == "OPEN")
    resolved_count = sum(1 for c in conflicts if c.get("resolution_status") == "RESOLVED")

    severity_counts: Dict[str, int] = {}
    for c in conflicts:
        sev = c.get("severity", "UNKNOWN")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Project only UI-relevant fields per conflict item
    items = [
        {
            "conflict_type": c.get("conflict_type", "UNKNOWN"),
            "severity": c.get("severity", "UNKNOWN"),
            "summary": c.get("summary", ""),
            "resolution_status": c.get("resolution_status", "OPEN"),
        }
        for c in conflicts
    ]

    return ConflictSummary(
        total=len(conflicts),
        open=open_count,
        resolved=resolved_count,
        by_severity=severity_counts,
        items=items,
    )


def _build_claims_summary(
    reasoning: Dict[str, Any], system: Dict[str, Any]
) -> ClaimsSummary:
    # Claims from answer_contract (primary) and reasoning.claims (fallback)
    answer_contract = system.get("answer_contract") or {}
    claims: List[Any] = []
    if isinstance(answer_contract, dict):
        claims = answer_contract.get("claims", [])
    if not claims:
        claims = reasoning.get("claims", [])
    if not isinstance(claims, list):
        claims = []

    by_type: Dict[str, int] = {}
    by_origin: Dict[str, int] = {}
    projected_items: List[ClaimItem] = []
    for claim in claims:
        if isinstance(claim, dict):
            ct = claim.get("claim_type", "unknown")
            co = claim.get("claim_origin", "unknown")
            cv = claim.get("value")
        elif hasattr(claim, "claim_type"):
            ct = getattr(claim, "claim_type", "unknown")
            co = getattr(claim, "claim_origin", "unknown")
            cv = getattr(claim, "value", None)
        else:
            continue
        by_type[ct] = by_type.get(ct, 0) + 1
        by_origin[co] = by_origin.get(co, 0) + 1
        if len(projected_items) < 8:
            projected_items.append(ClaimItem(
                value=str(cv) if cv is not None else None,
                claim_type=ct,
                claim_origin=co,
            ))

    return ClaimsSummary(
        total=len(claims),
        by_type=by_type,
        by_origin=by_origin,
        items=projected_items,
    )


def _build_manufacturer_questions(
    system: Dict[str, Any], reasoning: Dict[str, Any]
) -> ManufacturerQuestions:
    rfq_draft = system.get("rfq_draft") or {}
    if hasattr(rfq_draft, "model_dump"):
        rfq_draft = rfq_draft.model_dump(exclude_none=True)
    elif not isinstance(rfq_draft, dict):
        rfq_draft = {}

    mandatory = rfq_draft.get("manufacturer_questions_mandatory", [])

    # Open questions from reasoning
    open_questions_raw = reasoning.get("open_questions", [])
    open_questions = []
    for q in (open_questions_raw if isinstance(open_questions_raw, list) else []):
        if isinstance(q, dict):
            item = q
        elif hasattr(q, "model_dump"):
            item = q.model_dump(exclude_none=True)
        else:
            continue
        if item.get("status", "open") == "open":
            open_questions.append({
                "id": item.get("id", ""),
                "question": item.get("question", ""),
                "reason": item.get("reason", ""),
                "priority": item.get("priority", "medium"),
                "category": item.get("category", "clarification_gap"),
            })

    return ManufacturerQuestions(
        mandatory=mandatory if isinstance(mandatory, list) else [],
        open_questions=open_questions,
        total_open=len(open_questions),
    )


def _build_rfq_status(
    system: Dict[str, Any], reasoning: Dict[str, Any]
) -> RFQStatus:
    rfq_adm = system.get("rfq_admissibility") or {}
    if hasattr(rfq_adm, "model_dump"):
        rfq_adm = rfq_adm.model_dump(exclude_none=True)
    elif not isinstance(rfq_adm, dict):
        rfq_adm = {}

    rfq_confirmed = system.get("rfq_confirmed", False)
    has_html_report = bool(system.get("rfq_html_report"))
    selected_partner_id = reasoning.get("selected_partner_id")
    
    # Handover is ready when RFQ is confirmed, document generated, partner selected,
    # and case is not stale or inadmissible.
    stale = reasoning.get("derived_artifacts_stale", False) or system.get("derived_artifacts_stale", False)
    release_status = rfq_adm.get("release_status", "inadmissible")
    
    handover_ready = (
        rfq_confirmed 
        and has_html_report 
        and selected_partner_id is not None
        and not stale
        and release_status != "inadmissible"
    )

    return RFQStatus(
        admissibility_status=rfq_adm.get("status", "inadmissible"),
        release_status=release_status,
        rfq_confirmed=rfq_confirmed,
        rfq_ready=reasoning.get("rfq_ready", False),
        handover_ready=handover_ready,
        handover_initiated=system.get("rfq_handover_initiated", False),
        blockers=rfq_adm.get("blockers", []),
        open_points=rfq_adm.get("open_points", []),
        has_pdf=bool(system.get("rfq_pdf_base64") or system.get("rfq_pdf_url")),
        has_html_report=has_html_report,
    )


def _build_artifact_status(
    wp: Dict[str, Any], system: Dict[str, Any]
) -> ArtifactStatus:
    answer_contract = system.get("answer_contract") or {}
    has_ac = bool(answer_contract)
    contract_id = ""
    contract_obsolete = False
    if isinstance(answer_contract, dict):
        contract_id = answer_contract.get("contract_id", "")
        contract_obsolete = answer_contract.get("obsolete", False)

    live_calc = wp.get("live_calc_tile") or {}
    if hasattr(live_calc, "model_dump"):
        live_calc = live_calc.model_dump(exclude_none=True)
    elif not isinstance(live_calc, dict):
        live_calc = {}

    return ArtifactStatus(
        has_answer_contract=has_ac,
        contract_id=contract_id or None,
        contract_obsolete=contract_obsolete,
        has_verification_report=bool(system.get("verification_report")),
        has_sealing_requirement_spec=bool(system.get("sealing_requirement_spec")),
        has_rfq_draft=bool(system.get("rfq_draft")),
        has_recommendation=bool(wp.get("recommendation")),
        has_live_calc_tile=bool(live_calc and live_calc.get("status") != "insufficient_data"),
        live_calc_status=live_calc.get("status", "insufficient_data"),
    )


def _build_partner_matching(
    cc: CandidateClusterSummary,
    rfq: RFQStatus,
    pkg: RFQPackageSummary,
    mfr_q: ManufacturerQuestions,
    spec: SpecificityInfo,
    cycle: CycleInfo,
    reasoning: Dict[str, Any],
    system: Dict[str, Any],
) -> PartnerMatchingSummary:
    # Gate: matching is only ready when RFQ is confirmed, draft exists,
    # not inadmissible, and not stale.
    not_ready: List[str] = []
    if not rfq.rfq_confirmed:
        not_ready.append("RFQ package not yet confirmed.")
    if not pkg.has_draft:
        not_ready.append("No RFQ draft available.")
    effective_status = rfq.release_status or "inadmissible"
    if effective_status == "inadmissible":
        not_ready.append("Case is inadmissible.")
    if cycle.derived_artifacts_stale:
        not_ready.append("Artifacts are stale — recalculation required.")

    matching_ready = len(not_ready) == 0

    # Build material fit items from viable + mfr_validation candidates
    fit_items: List[MaterialFitItem] = []
    specificity_label = spec.material_specificity_required

    for candidate in cc.plausibly_viable:
        if not isinstance(candidate, dict):
            continue
        material = str(candidate.get("value") or candidate.get("kind") or "")
        if not material:
            continue
        cand_spec = str(candidate.get("specificity") or specificity_label)
        fit_items.append(MaterialFitItem(
            material=material,
            cluster="viable",
            specificity=cand_spec,
            requires_validation=False,
            fit_basis=f"{material} viable at {cand_spec} level",
            grounded_facts=candidate.get("grounded_facts", []),
        ))

    for candidate in cc.manufacturer_validation_required:
        if not isinstance(candidate, dict):
            continue
        material = str(candidate.get("value") or candidate.get("kind") or "")
        if not material:
            continue
        cand_spec = str(candidate.get("specificity") or specificity_label)
        fit_items.append(MaterialFitItem(
            material=material,
            cluster="manufacturer_validation",
            specificity=cand_spec,
            requires_validation=True,
            fit_basis=f"{material} requires manufacturer validation ({cand_spec})",
            grounded_facts=candidate.get("grounded_facts", []),
        ))

    # Collect open manufacturer questions
    open_questions: List[str] = list(pkg.manufacturer_questions_mandatory)
    for q in mfr_q.mandatory:
        if q not in open_questions:
            open_questions.append(q)

    return PartnerMatchingSummary(
        matching_ready=matching_ready,
        not_ready_reasons=not_ready,
        material_fit_items=fit_items,
        open_manufacturer_questions=open_questions,
        selected_partner_id=reasoning.get("selected_partner_id"),
        data_source="candidate_derived",
    )


def _build_rfq_package(system: Dict[str, Any]) -> RFQPackageSummary:
    rfq_draft = system.get("rfq_draft") or {}
    if hasattr(rfq_draft, "model_dump"):
        rfq_draft = rfq_draft.model_dump(exclude_none=True)
    elif not isinstance(rfq_draft, dict):
        rfq_draft = {}

    has_draft = bool(rfq_draft)
    if not has_draft:
        return RFQPackageSummary()

    conflicts_visible = rfq_draft.get("conflicts_visible", [])

    return RFQPackageSummary(
        has_draft=True,
        rfq_id=rfq_draft.get("rfq_id") or None,
        rfq_basis_status=rfq_draft.get("rfq_basis_status", "inadmissible"),
        operating_context_redacted=rfq_draft.get("operating_context_redacted", {}),
        manufacturer_questions_mandatory=rfq_draft.get("manufacturer_questions_mandatory", []),
        conflicts_visible_count=len(conflicts_visible) if isinstance(conflicts_visible, list) else 0,
        buyer_assumptions_acknowledged=rfq_draft.get("buyer_assumptions_acknowledged", []),
    )


def _build_cycle_info(
    reasoning: Dict[str, Any], wp: Dict[str, Any], system: Dict[str, Any]
) -> CycleInfo:
    # Staleness can be set on any pillar; reasoning is primary
    stale = (
        reasoning.get("derived_artifacts_stale", False)
        or wp.get("derived_artifacts_stale", False)
        or system.get("derived_artifacts_stale", False)
    )
    stale_reason = (
        reasoning.get("derived_artifacts_stale_reason")
        or wp.get("derived_artifacts_stale_reason")
        or system.get("derived_artifacts_stale_reason")
    )

    return CycleInfo(
        current_assertion_cycle_id=reasoning.get("current_assertion_cycle_id", 0),
        state_revision=reasoning.get("state_revision", 0),
        asserted_profile_revision=reasoning.get("asserted_profile_revision", 0),
        derived_artifacts_stale=stale,
        stale_reason=stale_reason,
    )
