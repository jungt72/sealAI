from __future__ import annotations

from typing import Any, Literal

from app.agent.v91.contracts import CandidateFact, FieldGovernanceDecision

ExtractionMethod = Literal["llm", "regex", "form", "document", "manual"]


def candidate_fact_from_observed_extraction(
    extraction: Any,
    *,
    source_message: str | None = None,
    source_message_id: str | None = None,
    extraction_method: ExtractionMethod | None = None,
) -> CandidateFact:
    """Project an existing ObservedExtraction into the V9.1 CandidateFact shape.

    This is an adapter, not a new authority layer. The governed reducers remain
    the only path from observed candidates to normalized/asserted case truth.
    """

    method = extraction_method or _method_from_source(getattr(extraction, "source", None))
    confidence = _bounded_confidence(getattr(extraction, "confidence", 0.5))
    return CandidateFact(
        field_id=str(getattr(extraction, "field_name", "") or "").strip(),
        value=getattr(extraction, "raw_value", None),
        unit=_clean_optional(getattr(extraction, "raw_unit", None), limit=32),
        source_message_id=source_message_id,
        source_quote=_source_quote(
            source_message=source_message,
            raw_value=getattr(extraction, "raw_value", None),
        ),
        extraction_method=method,
        confidence=confidence,
        requires_user_confirmation=confidence < 0.95 or method != "manual",
    )


def append_candidate_facts(
    existing: list[CandidateFact] | list[dict[str, Any]] | None,
    candidates: list[CandidateFact],
) -> list[CandidateFact]:
    """Append candidates while avoiding exact duplicates from the same turn."""

    merged: list[CandidateFact] = [
        item if isinstance(item, CandidateFact) else CandidateFact.model_validate(item)
        for item in (existing or [])
    ]
    seen = {_candidate_key(item) for item in merged}
    for candidate in candidates:
        key = _candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        merged.append(candidate)
    return merged


def build_field_governance_decisions(
    *,
    candidates: list[CandidateFact] | list[dict[str, Any]] | None,
    normalized: Any,
    asserted: Any,
    previous_asserted: Any | None = None,
) -> list[FieldGovernanceDecision]:
    """Project reducer outcomes into explicit V9.1 field-governance decisions.

    The function does not promote facts and does not write case truth. It only
    explains how the deterministic reducer chain treated already observed
    candidates in this run.
    """

    normalized_parameters = dict(getattr(normalized, "parameters", {}) or {})
    normalized_conflicts = {
        str(getattr(conflict, "field_name", "") or "")
        for conflict in list(getattr(normalized, "conflicts", []) or [])
    }
    assertions = dict(getattr(asserted, "assertions", {}) or {})
    previous_assertions = dict(getattr(previous_asserted, "assertions", {}) or {})
    blocking_unknowns = {
        str(field_name)
        for field_name in list(getattr(asserted, "blocking_unknowns", []) or [])
    }
    conflict_flags = {
        str(field_name)
        for field_name in list(getattr(asserted, "conflict_flags", []) or [])
    }

    decisions: list[FieldGovernanceDecision] = []
    for raw_candidate in candidates or []:
        candidate = (
            raw_candidate
            if isinstance(raw_candidate, CandidateFact)
            else CandidateFact.model_validate(raw_candidate)
        )
        field_id = candidate.field_id
        normalized_parameter = normalized_parameters.get(field_id)
        assertion = assertions.get(field_id)
        previous_assertion = previous_assertions.get(field_id)

        if field_id in normalized_conflicts or field_id in conflict_flags:
            decisions.append(
                _field_decision(
                    candidate,
                    decision="conflict_requires_confirmation",
                    provenance="inferred",
                    normalized_status=_status(normalized_parameter),
                    case_status=None,
                    case_revision_event_type="conflict",
                    requires_user_confirmation=True,
                    requires_recompute=False,
                    reason="deterministic reducer detected a conflicting value for this field",
                )
            )
            continue

        if assertion is not None:
            event_type = (
                "correction"
                if previous_assertion is not None
                and _canonical_compare_value(getattr(previous_assertion, "asserted_value", None))
                != _canonical_compare_value(getattr(assertion, "asserted_value", None))
                else "new_value"
            )
            decisions.append(
                _field_decision(
                    candidate,
                    decision="accepted_to_case_state",
                    provenance=str(getattr(assertion, "provenance", None) or "confirmed"),
                    normalized_status=_status(normalized_parameter),
                    case_status=str(getattr(assertion, "status", "") or "confirmed"),
                    case_revision_event_type=event_type,
                    requires_user_confirmation=False,
                    requires_recompute=True,
                    reason="candidate passed reducer chain into asserted case state",
                )
            )
            continue

        if normalized_parameter is not None:
            needs_confirmation = (
                candidate.requires_user_confirmation
                or str(getattr(normalized_parameter, "confidence", "") or "")
                == "requires_confirmation"
            )
            decisions.append(
                _field_decision(
                    candidate,
                    decision=(
                        "held_for_confirmation"
                        if field_id in blocking_unknowns or needs_confirmation
                        else "normalized_candidate"
                    ),
                    provenance=str(getattr(normalized_parameter, "provenance", None) or "inferred"),
                    normalized_status=_status(normalized_parameter),
                    case_status=None,
                    requires_user_confirmation=needs_confirmation,
                    requires_recompute=False,
                    reason=(
                        "candidate is normalized but not asserted as governed truth yet"
                    ),
                )
            )
            continue

        decisions.append(
            _field_decision(
                candidate,
                decision="observed_only",
                provenance="inferred",
                requires_user_confirmation=True,
                requires_recompute=False,
                reason="candidate remains in observed intake only",
            )
        )

    return _dedupe_field_decisions(decisions)


def _method_from_source(source: Any) -> ExtractionMethod:
    if str(source or "").strip() == "user":
        return "manual"
    return "llm"


def _candidate_key(candidate: CandidateFact) -> tuple[str, str, str | None, str]:
    return (
        candidate.field_id,
        str(candidate.value),
        candidate.source_message_id,
        candidate.extraction_method,
    )


def _field_decision(
    candidate: CandidateFact,
    *,
    decision: str,
    provenance: str,
    normalized_status: str | None = None,
    case_status: str | None = None,
    case_revision_event_type: str = "none",
    requires_user_confirmation: bool,
    requires_recompute: bool,
    reason: str,
) -> FieldGovernanceDecision:
    return FieldGovernanceDecision(
        field_id=candidate.field_id,
        candidate_value=candidate.value,
        candidate_unit=candidate.unit,
        source_message_id=candidate.source_message_id,
        source_quote=candidate.source_quote,
        decision=decision,  # type: ignore[arg-type]
        provenance=provenance,  # type: ignore[arg-type]
        normalized_status=normalized_status,
        case_status=case_status,
        case_revision_event_type=case_revision_event_type,  # type: ignore[arg-type]
        requires_user_confirmation=requires_user_confirmation,
        requires_recompute=requires_recompute,
        reason=reason,
    )


def _dedupe_field_decisions(
    decisions: list[FieldGovernanceDecision],
) -> list[FieldGovernanceDecision]:
    seen: set[tuple[str, str, str | None, str]] = set()
    result: list[FieldGovernanceDecision] = []
    for decision in decisions:
        key = (
            decision.field_id,
            str(decision.candidate_value),
            decision.source_message_id,
            decision.decision,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(decision)
    return result


def _status(value: Any) -> str | None:
    status = str(getattr(value, "status", "") or "").strip()
    return status or None


def _canonical_compare_value(value: Any) -> str:
    return " ".join(str(value if value is not None else "").split()).casefold()


def _source_quote(*, source_message: str | None, raw_value: Any) -> str | None:
    message = " ".join(str(source_message or "").split())
    value = " ".join(str(raw_value if raw_value is not None else "").split())
    if value and value.casefold() in message.casefold():
        return _clean_optional(value, limit=240)
    return _clean_optional(message, limit=240)


def _bounded_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, number))


def _clean_optional(value: Any, *, limit: int) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."
