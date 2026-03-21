from __future__ import annotations

from typing import Any, Dict, List

from app._legacy_v2.state.sealai_state import RFQAdmissibilityContract


def _as_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dumped
    return {}



def derive_release_status(
    *,
    blockers: List[str],
    governed_ready: bool,
    status: str,
    manufacturer_validation_items: List[str],
    requires_human_review: bool,
    open_points: List[str],
) -> str:
    """Derive Blueprint-compliant release_status from concrete governance signals.

    Precedence (each check is a hard gate, not a heuristic):
    1. blockers non-empty                                         → inadmissible
    2. governed_ready=True, status=="ready", no blockers          → rfq_ready
    3. manufacturer_validation_items non-empty, no blockers       → manufacturer_validation_required
    4. open_points non-empty or requires_human_review, no blockers → precheck_only
    5. default                                                     → inadmissible
    """
    if blockers:
        return "inadmissible"
    if governed_ready and status == "ready":
        return "rfq_ready"
    if manufacturer_validation_items:
        return "manufacturer_validation_required"
    if open_points or requires_human_review:
        return "precheck_only"
    return "inadmissible"


def default_rfq_admissibility_contract(
    *,
    cycle_id: int | None = None,
    revision: int | None = None,
    status: str = "inadmissible",
    reason: str = "rfq_contract_missing",
    open_points: list[str] | None = None,
    blockers: list[str] | None = None,
    manufacturer_validation_items: list[str] | None = None,
    requires_human_review: bool = False,
) -> Dict[str, Any]:
    resolved_status = status if status in {"inadmissible", "provisional", "ready"} else "inadmissible"
    resolved_blockers = list(blockers or [])
    resolved_open_points = list(open_points or [])
    governed = resolved_status == "ready"
    release_status = derive_release_status(
        blockers=resolved_blockers,
        governed_ready=governed,
        status=resolved_status,
        manufacturer_validation_items=list(manufacturer_validation_items or []),
        requires_human_review=requires_human_review,
        open_points=resolved_open_points,
    )
    contract = RFQAdmissibilityContract(
        status=resolved_status,
        release_status=release_status,
        reason=reason,
        open_points=resolved_open_points,
        blockers=resolved_blockers,
        manufacturer_validation_items=list(manufacturer_validation_items or []),
        governed_ready=governed,
        derived_from_assertion_cycle_id=cycle_id,
        derived_from_assertion_revision=revision,
    )
    return contract.model_dump(exclude_none=False)


def normalize_rfq_admissibility_contract(state: Any) -> Dict[str, Any]:
    values = _as_dict(state)
    system = _as_dict(values.get("system"))
    reasoning = _as_dict(values.get("reasoning"))

    # Collect hard blockers from governance signals (already-computed upstream results).
    sys_gov = _as_dict(system.get("governance_metadata"))
    sys_blockers = list(sys_gov.get("unknowns_release_blocking") or [])
    ans_contract = _as_dict(system.get("answer_contract"))
    ans_gov = _as_dict(ans_contract.get("governance_metadata"))
    ans_blockers = list(ans_gov.get("unknowns_release_blocking") or [])

    # Collect BLOCKING_UNKNOWN conflicts from verification_report (post-check results).
    verify_report = _as_dict(system.get("verification_report"))
    report_conflicts = list(verify_report.get("conflicts") or [])
    conflict_blockers = [
        str(c.get("summary") or c.get("scope_note") or "Blocking unknown").strip()
        for item in report_conflicts
        for c in [_as_dict(item)]
        if c.get("severity") in ("BLOCKING_UNKNOWN", "CRITICAL")
    ]

    active_blockers = list(dict.fromkeys(
        str(b).strip() for b in (sys_blockers + ans_blockers + conflict_blockers) if str(b).strip()
    ))

    # Collect manufacturer-validation items from governance metadata.
    mfr_conflict_items = [
        str(c.get("summary") or c.get("scope_note") or "Manufacturer validation required").strip()
        for item in report_conflicts
        for c in [_as_dict(item)]
        if c.get("severity") == "RESOLUTION_REQUIRES_MANUFACTURER_SCOPE"
    ]

    mfr_items = list(dict.fromkeys(
        str(item).strip()
        for item in list(ans_gov.get("unknowns_manufacturer_validation") or [])
        + list(sys_gov.get("unknowns_manufacturer_validation") or [])
        + mfr_conflict_items
        if str(item).strip()
    ))

    requires_human_review = bool(system.get("requires_human_review"))

    contract = _as_dict(system.get("rfq_admissibility"))
    if contract:
        normalized = default_rfq_admissibility_contract(
            cycle_id=contract.get("derived_from_assertion_cycle_id"),
            revision=contract.get("derived_from_assertion_revision"),
            status=str(contract.get("status") or "inadmissible"),
            reason=str(contract.get("reason") or "rfq_contract_missing"),
            open_points=list(contract.get("open_points") or []),
            blockers=list(contract.get("blockers") or []),
            manufacturer_validation_items=mfr_items,
            requires_human_review=requires_human_review,
        )
        normalized["governed_ready"] = bool(contract.get("governed_ready")) and normalized["status"] == "ready"
        if active_blockers:
            merged_blockers = list(dict.fromkeys(normalized["blockers"] + active_blockers))
            normalized["status"] = "inadmissible"
            normalized["governed_ready"] = False
            normalized["reason"] = "blocking_unknowns"
            normalized["blockers"] = merged_blockers
            normalized["release_status"] = "inadmissible"
        return normalized

    legacy_ready = bool(reasoning.get("rfq_ready") or values.get("rfq_ready"))
    cycle_id = reasoning.get("current_assertion_cycle_id")
    revision = reasoning.get("asserted_profile_revision")
    base = default_rfq_admissibility_contract(
        cycle_id=cycle_id if isinstance(cycle_id, int) else None,
        revision=revision if isinstance(revision, int) else None,
        status="inadmissible",
        reason="legacy_rfq_ready_ignored_without_contract" if legacy_ready else "rfq_contract_missing",
        blockers=["rfq_contract_missing"] if legacy_ready else [],
        manufacturer_validation_items=mfr_items,
        requires_human_review=requires_human_review,
    )
    if active_blockers:
        merged_blockers = list(dict.fromkeys(base["blockers"] + active_blockers))
        base["status"] = "inadmissible"
        base["governed_ready"] = False
        base["reason"] = "blocking_unknowns"
        base["blockers"] = merged_blockers
        base["release_status"] = "inadmissible"
    return base


def invalidate_rfq_admissibility_contract(
    *,
    cycle_id: int | None,
    revision: int | None,
    reason: str,
) -> Dict[str, Any]:
    return default_rfq_admissibility_contract(
        cycle_id=cycle_id,
        revision=revision,
        status="inadmissible",
        reason=reason,
        blockers=[reason],
    )


def rfq_contract_is_ready(contract: Dict[str, Any] | Any) -> bool:
    data = _as_dict(contract)
    return (
        str(data.get("status") or "") == "ready"
        and bool(data.get("governed_ready"))
        and not bool(data.get("blockers"))
    )


__all__ = [
    "default_rfq_admissibility_contract",
    "derive_release_status",
    "invalidate_rfq_admissibility_contract",
    "normalize_rfq_admissibility_contract",
    "rfq_contract_is_ready",
]
