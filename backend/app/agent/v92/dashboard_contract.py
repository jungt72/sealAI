"""Canonical V9.2 dashboard projection helpers."""

from __future__ import annotations

from typing import Any

from app.agent.state.models import GovernedSessionState
from app.agent.v92.contracts import V92DashboardContract, TurnRoute


def _dump(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return dict(value) if isinstance(value, dict) else {}


def _case_revision(state: GovernedSessionState | None) -> int | None:
    if state is None:
        return None
    marker = getattr(state, "persistence_marker", None)
    for value in (
        getattr(marker, "postgres_case_revision", None),
        getattr(marker, "postgres_snapshot_revision", None),
        getattr(getattr(state, "dossier", None), "case_revision", None),
        getattr(getattr(getattr(state, "calculation", None), "input_snapshot", None), "case_revision", None),
    ):
        if isinstance(value, int) and value > 0:
            return value
    case_events = list(getattr(state, "case_events", []) or [])
    revisions = [
        int(getattr(event, "case_revision_after", 0) or getattr(event, "state_revision_after", 0) or 0)
        for event in case_events
    ]
    if revisions:
        return max(revisions)
    for value in (
        getattr(state, "user_turn_index", None),
        getattr(state, "analysis_cycle", None),
    ):
        if isinstance(value, int) and value > 0:
            return value
    return None


def extract_case_revision(state: GovernedSessionState | None) -> int | None:
    return _case_revision(state)


def _string_items(items: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in items:
        text = str(item or "").strip()
        if text:
            result.append({"key": text, "label": text, "status": "missing"})
    return result


def _current_facts(state: GovernedSessionState | None) -> list[dict[str, Any]]:
    if state is None:
        return []
    facts: list[dict[str, Any]] = []
    for key, assertion in (getattr(getattr(state, "asserted", None), "assertions", {}) or {}).items():
        value = getattr(assertion, "asserted_value", None)
        if value is None:
            continue
        facts.append(
            {
                "field_name": str(key),
                "value": value,
                "confidence": getattr(assertion, "confidence", None),
                "source": "asserted_state",
            }
        )
    for key, parameter in (getattr(getattr(state, "normalized", None), "parameters", {}) or {}).items():
        if any(fact.get("field_name") == key for fact in facts):
            continue
        facts.append(
            {
                "field_name": str(key),
                "value": getattr(parameter, "value", None),
                "unit": getattr(parameter, "unit", None),
                "confidence": getattr(parameter, "confidence", None),
                "source": "normalized_state",
            }
        )
    return facts


def _risk_matrix(state: GovernedSessionState | None) -> list[dict[str, Any]]:
    if state is None:
        return []
    risks: list[dict[str, Any]] = []
    for finding in list(getattr(getattr(state, "engineering", None), "risk_findings", []) or []):
        item = _dump(finding)
        if item:
            risks.append(item)
    challenge = getattr(state, "challenge", None)
    for finding in list(getattr(challenge, "findings", []) or []):
        item = _dump(finding)
        if item:
            risks.append(item)
    return risks


def _calculation_items(state: GovernedSessionState | None) -> list[dict[str, Any]]:
    if state is None:
        return []
    items = [_dump(result) for result in list(getattr(getattr(state, "calculation", None), "results", []) or [])]
    for result in list(getattr(state, "compute_results", []) or []):
        if isinstance(result, dict):
            items.append(dict(result))
    return [item for item in items if item]


def _stale_items(state: GovernedSessionState | None) -> list[dict[str, Any]]:
    if state is None:
        return []
    calculation = getattr(state, "calculation", None)
    stale_ids = list(getattr(calculation, "stale_result_ids", []) or [])
    items = [{"item_id": str(item_id), "kind": "calculation", "status": "stale"} for item_id in stale_ids]
    for result in list(getattr(calculation, "results", []) or []):
        dumped = _dump(result)
        if dumped.get("status") == "stale" or dumped.get("validity_status") == "stale":
            items.append(
                {
                    "item_id": dumped.get("calculation_id") or dumped.get("calculator") or "calculation",
                    "kind": "calculation",
                    "status": "stale",
                }
            )
    return items


def _readiness_band(state: GovernedSessionState | None) -> str:
    if state is None:
        return "not_ready"
    for value in (
        getattr(getattr(state, "dossier", None), "readiness_band", None),
        getattr(getattr(getattr(state, "engineering", None), "completeness_matrix", None), "readiness_band", None),
    ):
        if value:
            return str(value)
    if getattr(getattr(state, "governance", None), "rfq_admissible", False):
        return "rfq_ready_for_expert_review"
    if _current_facts(state):
        return "screening_possible"
    return "not_ready"


def _review_status(state: GovernedSessionState | None) -> dict[str, Any]:
    review = getattr(state, "review_state", None) if state is not None else None
    status = str(getattr(review, "status", "not_started") or "not_started")
    required_review_types = list(getattr(review, "required_review_types", []) or [])
    blocking_findings = list(getattr(review, "blocking_findings", []) or [])
    required_corrections = list(getattr(review, "required_corrections", []) or [])
    human_review_required = bool(blocking_findings or required_corrections)
    if status != "approved_scope":
        human_review_required = bool(
            human_review_required
            or required_review_types
            or status in {"pending", "changes_required", "blocked"}
        )
    return {
        "status": status,
        "scope": list(getattr(review, "scope", []) or []),
        "required_review_types": required_review_types,
        "blocking_findings": blocking_findings,
        "required_corrections": required_corrections,
        "approved_claim_level": getattr(review, "approved_claim_level", None),
        "decisions": list(getattr(review, "decisions", []) or []),
        "review_guard_notes": list(getattr(review, "review_guard_notes", []) or []),
        "human_review_required": human_review_required,
    }


def _active_question(state: GovernedSessionState | None) -> dict[str, Any] | None:
    """Project the existing governed ``PendingQuestion`` (not a new concept)."""
    pending = getattr(state, "pending_question", None) if state is not None else None
    if pending is None:
        return None
    if str(getattr(pending, "status", "open") or "open") != "open":
        return None
    field = str(getattr(pending, "target_field", "") or "").strip()
    text = str(getattr(pending, "question_text", "") or "").strip()
    if not field and not text:
        return None
    return {
        "field": field or None,
        "question": text or None,
        "expected_answer_type": str(getattr(pending, "expected_answer_type", "") or "") or None,
        "status": str(getattr(pending, "status", "open") or "open"),
    }


def _conflicts(state: GovernedSessionState | None) -> list[dict[str, Any]]:
    """Project detected ``ConflictRef`` items from normalized state."""
    if state is None:
        return []
    out: list[dict[str, Any]] = []
    for conflict in list(getattr(getattr(state, "normalized", None), "conflicts", []) or []):
        dumped = _dump(conflict)
        if dumped:
            out.append(dumped)
    return out


def _knowledge_notes(state: GovernedSessionState | None) -> list[dict[str, Any]]:
    """RAG-supported knowledge notes (§14.5/§19.6).

    No first-class knowledge-note state exists yet; the populating source lands
    with the Knowledge contract (Patch 7). Read tolerantly so any already-present
    notes surface, otherwise empty.
    """
    if state is None:
        return []
    context = getattr(state, "governed_answer_context", {}) or {}
    notes = context.get("knowledge_notes") if isinstance(context, dict) else None
    if not isinstance(notes, list):
        return []
    return [dict(note) for note in notes if isinstance(note, dict)]


def build_v92_dashboard_contract(
    state: GovernedSessionState | None,
    *,
    turn_id: str,
    route: TurnRoute,
    case_id: str | None = None,
    challenge_card: dict[str, Any] | None = None,
) -> V92DashboardContract:
    seal_system = getattr(state, "seal_system", None) if state is not None else None
    engineering = getattr(state, "engineering", None) if state is not None else None
    calculation = getattr(state, "calculation", None) if state is not None else None
    evidence = getattr(state, "evidence_graph", None) if state is not None else None
    standards = getattr(state, "standards", None) if state is not None else None
    compound = getattr(state, "compound_state", None) if state is not None else None
    dossier = getattr(state, "dossier", None) if state is not None else None
    current_facts = _current_facts(state)
    calculations = _calculation_items(state)

    completeness = getattr(engineering, "completeness_matrix", None)
    missing_fields = _string_items(list(getattr(seal_system, "missing_fields", []) or []))
    if completeness is not None:
        missing_fields.extend(_string_items(list(getattr(completeness, "missing_fields", []) or [])))
    blocking_missing = _string_items(
        list(getattr(completeness, "blocking_missing_fields", []) or [])
        or list(getattr(engineering, "blockers", []) or [])
    )

    recommendation_card = None
    next_action = str(getattr(engineering, "next_best_engineering_action", "") or "").strip()
    if next_action or _readiness_band(state) != "not_ready":
        recommendation_card = {
            "status": str(getattr(engineering, "status", "pending") or "pending"),
            "allowed_claim_level": str(
                getattr(getattr(state, "review_state", None), "approved_claim_level", None)
                or "L2_screening"
            ),
            "next_action": next_action or "collect_missing_inputs",
            "no_final_technical_release": True,
        }

    return V92DashboardContract(
        case_id=case_id,
        case_revision=_case_revision(state),
        turn_id=turn_id,
        route=route,
        readiness_band=_readiness_band(state),
        seal_system=_dump(seal_system) or None,
        current_facts=current_facts,
        missing_fields=missing_fields,
        blocking_missing_fields=blocking_missing,
        calculations=calculations,
        stale_items=_stale_items(state),
        material_family_screening=[
            _dump(item)
            for item in list(getattr(compound, "material_family_candidates", []) or [])
            if _dump(item)
        ],
        compound_candidates=[
            _dump(item)
            for item in list(getattr(compound, "compound_candidates", []) or [])
            if _dump(item)
        ],
        product_candidates=[
            _dump(item)
            for item in list(getattr(compound, "product_candidates", []) or [])
            if _dump(item)
        ],
        evidence_summary={
            "status": str(getattr(evidence, "status", "pending") or "pending"),
            "node_count": len(list(getattr(evidence, "nodes", []) or [])),
            "unresolved_gaps": list(getattr(evidence, "unresolved_gaps", []) or []),
            "claim_boundary": str(getattr(evidence, "claim_boundary", "") or ""),
        },
        standards_summary={
            "status": str(getattr(standards, "status", "pending") or "pending"),
            "registry_version": str(getattr(standards, "registry_version", "") or ""),
            "applicable_count": len(list(getattr(standards, "applicable_entries", []) or [])),
            "blocking_gaps": list(getattr(standards, "blocking_gaps", []) or []),
            "claim_boundary": str(getattr(standards, "claim_boundary", "") or ""),
        },
        risk_matrix=_risk_matrix(state),
        recommendation_card=recommendation_card,
        challenge_card=challenge_card,
        review_status=_review_status(state),
        rfq_dossier_preview={
            "status": str(getattr(dossier, "status", "pending") or "pending"),
            "dossier_id": getattr(dossier, "dossier_id", None),
            "case_revision": int(getattr(dossier, "case_revision", 0) or 0),
            "blockers": list(getattr(dossier, "blockers", []) or []),
            "open_blockers": list(getattr(dossier, "blockers", []) or []),
            "accepted_facts": current_facts,
            "calculated_values": calculations,
            "evidence_summary": list(getattr(dossier, "evidence_summary", []) or []),
            "forbidden_claims": list(getattr(dossier, "forbidden_claims", []) or []),
            "allowed_next_actions": list(getattr(dossier, "allowed_next_actions", []) or []),
            "no_final_technical_release": bool(getattr(dossier, "no_final_technical_release", True)),
        }
        if dossier is not None
        else None,
        allowed_next_actions=list(getattr(dossier, "allowed_next_actions", []) or [])
        or ["collect_missing_inputs"],
        active_question=_active_question(state),
        conflicts=_conflicts(state),
        knowledge_notes=_knowledge_notes(state),
        # Visual/sketch candidates remain empty until Patch 6 (vision).
        visual_candidates=[],
        sketch_candidates=[],
    )


def build_legacy_v92_ui_tile(state: GovernedSessionState | None) -> dict[str, Any]:
    """Compatibility tile for existing frontend `ui.v92` consumers."""

    contract = build_v92_dashboard_contract(
        state,
        turn_id="projection-only",
        route="engineering_case_update",
        case_id=None,
    )
    return {
        "seal_system": {
            "status": (contract.seal_system or {}).get("status", "pending"),
            "seal_family": (contract.seal_system or {}).get("seal_family", "unknown"),
            "seal_type": (contract.seal_system or {}).get("seal_type", "unknown_seal"),
            "missing_fields": [
                str(item.get("key") or item.get("label") or "")
                for item in contract.missing_fields
                if item
            ],
            "validity_boundaries": (contract.seal_system or {}).get("validity_boundaries", []),
        },
        "engineering": {
            "status": str(getattr(getattr(state, "engineering", None), "status", "pending") or "pending"),
            "route": str(getattr(getattr(state, "engineering", None), "route", "unknown") or "unknown"),
            "next_best_engineering_action": str(
                getattr(
                    getattr(state, "engineering", None),
                    "next_best_engineering_action",
                    "identify_seal_system",
                )
                or "identify_seal_system"
            ),
            "blockers": list(getattr(getattr(state, "engineering", None), "blockers", []) or []),
        },
        "calculations": {
            "status": str(getattr(getattr(state, "calculation", None), "status", "pending") or "pending"),
            "result_count": len(contract.calculations),
            "blocked_calculations": list(getattr(getattr(state, "calculation", None), "blocked_calculations", []) or []),
            "guardrail_violations": list(getattr(getattr(state, "calculation", None), "guardrail_violations", []) or []),
        },
        "standards": {
            "status": contract.standards_summary.get("status", "pending"),
            "registry_version": contract.standards_summary.get("registry_version", "standards_registry_metadata_v1"),
            "applicable_count": contract.standards_summary.get("applicable_count", 0),
            "blocking_gaps": contract.standards_summary.get("blocking_gaps", []),
            "claim_boundary": contract.standards_summary.get("claim_boundary", ""),
        },
        "evidence_graph": {
            "status": contract.evidence_summary.get("status", "pending"),
            "node_count": contract.evidence_summary.get("node_count", 0),
            "unresolved_gaps": contract.evidence_summary.get("unresolved_gaps", []),
        },
        "compound": {
            "status": str(getattr(getattr(state, "compound_state", None), "status", "pending") or "pending"),
            "material_family_count": len(contract.material_family_screening),
            "compound_count": len(contract.compound_candidates),
            "product_count": len(contract.product_candidates),
            "separation_violations": list(getattr(getattr(state, "compound_state", None), "separation_violations", []) or []),
        },
        "review": {
            "status": contract.review_status.get("status", "not_started"),
            "blocking_findings": contract.review_status.get("blocking_findings", []),
            "required_corrections": contract.review_status.get("required_corrections", []),
        },
        "dossier": {
            "status": (contract.rfq_dossier_preview or {}).get("status", "pending"),
            "dossier_id": (contract.rfq_dossier_preview or {}).get("dossier_id"),
            "fact_count": len(getattr(getattr(state, "dossier", None), "facts", []) or []),
            "calculation_count": len(getattr(getattr(state, "dossier", None), "calculations", []) or []),
            "candidate_count": len(getattr(getattr(state, "dossier", None), "candidates", []) or []),
            "blockers": (contract.rfq_dossier_preview or {}).get("blockers", []),
            "no_final_technical_release": (contract.rfq_dossier_preview or {}).get("no_final_technical_release", True),
        },
    }
