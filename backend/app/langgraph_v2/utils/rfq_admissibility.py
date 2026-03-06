from __future__ import annotations

from typing import Any, Dict

from app.langgraph_v2.state.sealai_state import RFQAdmissibilityContract


def _as_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=False)
        if isinstance(dumped, dict):
            return dumped
    return {}


def default_rfq_admissibility_contract(
    *,
    cycle_id: int | None = None,
    revision: int | None = None,
    status: str = "inadmissible",
    reason: str = "rfq_contract_missing",
    open_points: list[str] | None = None,
    blockers: list[str] | None = None,
) -> Dict[str, Any]:
    contract = RFQAdmissibilityContract(
        status=status if status in {"inadmissible", "provisional", "ready"} else "inadmissible",
        reason=reason,
        open_points=list(open_points or []),
        blockers=list(blockers or []),
        governed_ready=(status == "ready"),
        derived_from_assertion_cycle_id=cycle_id,
        derived_from_assertion_revision=revision,
    )
    return contract.model_dump(exclude_none=False)


def normalize_rfq_admissibility_contract(state: Any) -> Dict[str, Any]:
    values = _as_dict(state)
    system = _as_dict(values.get("system"))
    reasoning = _as_dict(values.get("reasoning"))

    contract = _as_dict(system.get("rfq_admissibility"))
    if contract:
        normalized = default_rfq_admissibility_contract(
            cycle_id=contract.get("derived_from_assertion_cycle_id"),
            revision=contract.get("derived_from_assertion_revision"),
            status=str(contract.get("status") or "inadmissible"),
            reason=str(contract.get("reason") or "rfq_contract_missing"),
            open_points=list(contract.get("open_points") or []),
            blockers=list(contract.get("blockers") or []),
        )
        normalized["governed_ready"] = bool(contract.get("governed_ready")) and normalized["status"] == "ready"
        return normalized

    legacy_ready = bool(reasoning.get("rfq_ready") or values.get("rfq_ready"))
    cycle_id = reasoning.get("current_assertion_cycle_id")
    revision = reasoning.get("asserted_profile_revision")
    if legacy_ready:
        return default_rfq_admissibility_contract(
            cycle_id=cycle_id if isinstance(cycle_id, int) else None,
            revision=revision if isinstance(revision, int) else None,
            status="inadmissible",
            reason="legacy_rfq_ready_ignored_without_contract",
            blockers=["rfq_contract_missing"],
        )
    return default_rfq_admissibility_contract(
        cycle_id=cycle_id if isinstance(cycle_id, int) else None,
        revision=revision if isinstance(revision, int) else None,
    )


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
    return str(data.get("status") or "") == "ready" and bool(data.get("governed_ready"))


__all__ = [
    "default_rfq_admissibility_contract",
    "invalidate_rfq_admissibility_contract",
    "normalize_rfq_admissibility_contract",
    "rfq_contract_is_ready",
]
