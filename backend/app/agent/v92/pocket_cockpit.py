"""V1.6 Pocket Cockpit projection (Blueprint §4.3, §11.3, §11.4).

Mobile turns must *compress* the desktop cockpit into four things only:
``recognized`` / ``critical`` / ``next_step`` / ``rfq_status`` (§3.3, §4.3) plus
optional :class:`ActionChip` affordances (§4.5).

This is an **additive, pure projection** built on top of the already-existing
:class:`V92DashboardContract` (the canonical dashboard projection). It does not
touch dispatch, streaming or the desktop cockpit, and it mutates nothing —
action chips are UI affordances here; their State-Gate handling lands in Patch 5.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.agent.v92.contracts import ActionChip, PocketCockpitPatch, V92DashboardContract

MAX_RECOGNIZED = 4
MAX_CRITICAL = 3

# Coarse mapping until the full RFQ readiness model lands in Patch 9.
_READINESS_TO_RFQ_STATUS: dict[str, str] = {
    "not_ready": "DRAFT",
    "screening_possible": "DRAFT",
    "rfq_ready_for_expert_review": "MANUFACTURER_REVIEW_READY",
}


def _recognized(contract: V92DashboardContract, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fact in contract.current_facts:
        label = str(fact.get("field_name") or "").strip()
        value = fact.get("value")
        if not label or value is None:
            continue
        unit = fact.get("unit")
        display: Any = f"{value} {unit}".strip() if unit else value
        confidence = str(fact.get("confidence") or "").lower()
        status = "confirmed" if confidence == "confirmed" else "candidate"
        out.append({"label": label, "value": display, "status": status})
        if len(out) >= limit:
            break
    return out


def _critical(contract: V92DashboardContract, limit: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for risk in contract.risk_matrix:
        label = str(
            risk.get("label")
            or risk.get("title")
            or risk.get("name")
            or risk.get("risk")
            or ""
        ).strip()
        if not label:
            continue
        severity = str(risk.get("severity") or "").lower() or "high"
        items.append({"label": label, "severity": severity})
        if len(items) >= limit:
            break
    if len(items) < limit:
        for missing in contract.blocking_missing_fields:
            label = str(missing.get("label") or missing.get("key") or "").strip()
            if not label:
                continue
            items.append({"label": label, "severity": "high"})
            if len(items) >= limit:
                break
    return items[:limit]


def _rfq_status(contract: V92DashboardContract) -> str:
    band = str(contract.readiness_band or "not_ready")
    return _READINESS_TO_RFQ_STATUS.get(band, "DRAFT")


def _next_step(
    contract: V92DashboardContract,
    pending_question: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if pending_question:
        question = str(
            pending_question.get("text") or pending_question.get("question") or ""
        ).strip()
        step: dict[str, Any] = {}
        if question:
            step["question"] = question
        field = pending_question.get("field")
        if field:
            step["field"] = field
        return step or None
    card = contract.recommendation_card or {}
    action = str(card.get("next_action") or "").strip()
    if action:
        return {"action": action}
    return None


def build_pocket_cockpit_patch(
    contract: V92DashboardContract,
    *,
    pending_question: Mapping[str, Any] | None = None,
    max_recognized: int = MAX_RECOGNIZED,
    max_critical: int = MAX_CRITICAL,
) -> PocketCockpitPatch:
    """Project a :class:`V92DashboardContract` into a compressed pocket patch."""
    return PocketCockpitPatch(
        recognized=_recognized(contract, max_recognized),
        critical=_critical(contract, max_critical),
        next_step=_next_step(contract, pending_question),
        rfq_status=_rfq_status(contract),
        details_available=True,
        collapsed_by_default=True,
    )


def build_action_chips(
    pending_question: Mapping[str, Any] | None = None,
) -> list[ActionChip]:
    """Derive limited-answer affordances for the active question (§4.5).

    Chips are UI affordances only; selecting one emits an event but does not
    mutate case state (State-Gate handling is Patch 5).
    """
    if not pending_question:
        return []
    field = pending_question.get("field")
    answer_type = str(pending_question.get("answer_type") or "").lower()
    options: Sequence[Any] = pending_question.get("options") or []

    if answer_type in {"yes_no", "boolean", "bool"}:
        return [
            ActionChip(label="Ja", value="yes", field=field),
            ActionChip(label="Nein", value="no", field=field),
            ActionChip(label="Weiß ich nicht", value="unknown", field=field),
            ActionChip(label="Foto senden", action="upload_photo"),
        ]
    if options:
        chips = [
            ActionChip(
                label=str(opt.get("label") if isinstance(opt, Mapping) else opt),
                value=str(opt.get("value") if isinstance(opt, Mapping) else opt),
                field=field,
            )
            for opt in options
        ]
        chips.append(ActionChip(label="Weiß ich nicht", value="unknown", field=field))
        return chips
    return [
        ActionChip(label="Weiß ich nicht", value="unknown", field=field),
        ActionChip(label="Foto senden", action="upload_photo"),
    ]


def build_pocket_cockpit(
    contract: V92DashboardContract,
    *,
    pending_question: Mapping[str, Any] | None = None,
) -> tuple[PocketCockpitPatch, list[ActionChip]]:
    """Convenience: pocket patch + action chips for a turn."""
    return (
        build_pocket_cockpit_patch(contract, pending_question=pending_question),
        build_action_chips(pending_question),
    )
