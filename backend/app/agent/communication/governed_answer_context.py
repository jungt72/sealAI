from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.communication.context import human_label
from app.agent.state.models import PendingQuestion, SlotAnswerBinding
from app.agent.v91.contracts import FinalAnswerContext, QuestionPlan
from app.agent.v91.final_answer_context import build_v91_final_answer_context
from app.agent.v91.question_planner import build_question_plan_from_strategy

AnswerMarkdownSource = Literal["not_composed_yet"]

_SAFETY_BOUNDARIES = [
    "do_not_approve_material_suitability",
    "do_not_create_rfq_readiness",
    "do_not_set_risk_readiness_or_calculation_truth",
    "do_not_invent_missing_values",
    "ask_at_most_one_main_clarification_question",
    "mention_uncertainty_for_ambiguous_values",
]

_FORBIDDEN_CLAIMS = [
    "final_engineering_approval",
    "final_material_suitability",
    "manufacturer_acceptance",
    "rfq_readiness_without_backend_state",
    "compliance_approval",
    "invented_evidence",
]


class GovernedAnswerUpdate(BaseModel):
    field_key: str
    label: str
    value: Any = None
    unit: str | None = None
    source: str = "backend"
    status: str = "accepted"
    confidence: str | None = None

    model_config = ConfigDict(extra="forbid")


class GovernedAmbiguousValue(BaseModel):
    field_key: str
    label: str
    raw_value: Any = None
    normalized_value: Any = None
    reason: str = "needs_clarification"
    clarification_question: str | None = None

    model_config = ConfigDict(extra="forbid")


class GovernedRejectedUpdate(BaseModel):
    field_key: str
    label: str
    value: Any = None
    reason: str = "not_accepted"

    model_config = ConfigDict(extra="forbid")


class GovernedFact(BaseModel):
    field_key: str
    label: str
    value: Any = None
    unit: str | None = None
    confidence: str = "confirmed"
    source: str = "asserted_state"
    status: str = "confirmed"

    model_config = ConfigDict(extra="forbid")


class GovernedCalculationFact(BaseModel):
    calculation_id: str
    label: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    status: str = "unknown"
    claim_level: str = "L3_deterministic_calculation"
    validity_status: str = "unknown"
    limitation: str = "Berechneter Screening-Zwischenwert, keine technische Freigabe."

    model_config = ConfigDict(extra="forbid")


class GovernedAnswerContext(BaseModel):
    latest_user_message: str | None = None
    pending_question: PendingQuestion | None = None
    slot_answer_bindings: list[SlotAnswerBinding] = Field(default_factory=list)
    accepted_updates: list[GovernedAnswerUpdate] = Field(default_factory=list)
    ambiguous_values: list[GovernedAmbiguousValue] = Field(default_factory=list)
    rejected_updates: list[GovernedRejectedUpdate] = Field(default_factory=list)
    confirmed_facts: list[GovernedFact] = Field(default_factory=list)
    calculation_results: list[GovernedCalculationFact] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    open_points: list[str] = Field(default_factory=list)
    challenge_findings: list[dict[str, Any]] = Field(default_factory=list)
    challenge_hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    next_best_question: str | None = None
    v91_question_plan: QuestionPlan | None = None
    v91_final_answer_context: FinalAnswerContext | None = None
    response_class: str | None = None
    allowed_claims: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=lambda: list(_FORBIDDEN_CLAIMS))
    safety_boundaries: list[str] = Field(default_factory=lambda: list(_SAFETY_BOUNDARIES))
    answer_goal: str = "acknowledge valid newly supplied information, clarify ambiguous values, and ask the next best required question"
    answer_markdown_source: AnswerMarkdownSource = "not_composed_yet"

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item).strip() for item in items if str(item or "").strip()))


def _latest_user_message(state: Any) -> str | None:
    pending = str(getattr(state, "pending_message", "") or "").strip()
    if pending:
        return pending
    for message in reversed(list(getattr(state, "conversation_messages", []) or [])):
        if str(getattr(message, "role", "") or "") == "user":
            text = str(getattr(message, "content", "") or "").strip()
            if text:
                return text
    return None


def _field_unit(state: Any, field_key: str) -> str | None:
    normalized = getattr(getattr(state, "normalized", None), "parameters", {}) or {}
    parameter = dict(normalized).get(field_key)
    return getattr(parameter, "unit", None) if parameter is not None else None


def _confirmed_facts(state: Any) -> list[GovernedFact]:
    facts: list[GovernedFact] = []
    assertions = dict(getattr(getattr(state, "asserted", None), "assertions", {}) or {})
    for field_key, claim in assertions.items():
        value = getattr(claim, "asserted_value", None)
        confidence = str(getattr(claim, "confidence", "") or "")
        status = str(getattr(claim, "status", "") or "")
        if value in (None, ""):
            continue
        if confidence != "confirmed" or status not in {"confirmed", "user_stated"}:
            continue
        facts.append(
            GovernedFact(
                field_key=str(field_key),
                label=human_label(str(field_key)),
                value=value,
                unit=_field_unit(state, str(field_key)),
                confidence=confidence,
                status=status,
            )
        )
    return facts


def _missing_fields(state: Any, output_public: dict[str, Any] | None) -> list[str]:
    if isinstance(output_public, dict) and isinstance(output_public.get("missing_fields"), list):
        return _unique([str(item) for item in output_public.get("missing_fields") or []])
    raw: list[str] = []
    raw.extend(str(item) for item in list(getattr(getattr(state, "asserted", None), "blocking_unknowns", []) or []) if item)
    governance = getattr(state, "governance", None)
    for attr in ("preselection_blockers", "compliance_blockers", "type_sensitive_required"):
        raw.extend(str(item) for item in list(getattr(governance, attr, []) or []) if item)
    return _unique(raw)


def _open_points(state: Any, output_public: dict[str, Any] | None) -> list[str]:
    if isinstance(output_public, dict) and isinstance(output_public.get("open_points"), list):
        return _unique([str(item) for item in output_public.get("open_points") or []])
    governance = getattr(state, "governance", None)
    return _unique([str(item) for item in list(getattr(governance, "open_validation_points", []) or []) if item])


def _challenge_findings(state: Any) -> list[dict[str, Any]]:
    challenge = getattr(state, "challenge", None)
    findings: list[dict[str, Any]] = []
    for item in list(getattr(challenge, "findings", []) or [])[:6]:
        if hasattr(item, "model_dump"):
            payload = item.model_dump(mode="json")
        elif isinstance(item, dict):
            payload = dict(item)
        else:
            continue
        findings.append(
            {
                "title": str(payload.get("title") or ""),
                "summary": str(payload.get("summary") or ""),
                "severity": str(payload.get("severity") or ""),
                "related_fields": list(payload.get("related_fields") or [])[:5],
                "claim_id": str(payload.get("claim_id") or ""),
                "claim_type": str(payload.get("claim_type") or ""),
                "subject_field": str(payload.get("subject_field") or ""),
                "evidence_fields": list(payload.get("evidence_fields") or [])[:5],
                "missing_fields": list(payload.get("missing_fields") or [])[:5],
                "allowed_user_wording": str(payload.get("allowed_user_wording") or ""),
                "forbidden_user_wording": list(payload.get("forbidden_user_wording") or [])[:5],
            }
        )
    return findings


def _challenge_hypotheses(state: Any) -> list[dict[str, Any]]:
    challenge = getattr(state, "challenge", None)
    hypotheses: list[dict[str, Any]] = []
    for item in list(getattr(challenge, "hypotheses", []) or [])[:6]:
        if hasattr(item, "model_dump"):
            payload = item.model_dump(mode="json")
        elif isinstance(item, dict):
            payload = dict(item)
        else:
            continue
        hypotheses.append(
            {
                "label": str(payload.get("label") or ""),
                "plausibility_class": str(payload.get("plausibility_class") or ""),
                "status": str(payload.get("status") or ""),
                "basis": list(payload.get("basis") or [])[:5],
                "counterindicators": list(payload.get("counterindicators") or [])[:5],
                "blocking_unknowns": list(payload.get("blocking_unknowns") or [])[:5],
                "required_checks": list(payload.get("required_checks") or [])[:5],
            }
        )
    return hypotheses


_CALCULATION_LABELS = {
    "rwdr.surface_speed": "Umfangsgeschwindigkeit",
    "surface_speed_from_rpm_and_diameter": "Umfangsgeschwindigkeit",
    "material.temperature_window_screening": "Temperaturfenster-Screening",
    "material_family_counterindication_check": "Werkstofffamilien-Screening",
}


def _calculation_results(state: Any) -> list[GovernedCalculationFact]:
    calculation = getattr(state, "calculation", None)
    results = list(getattr(calculation, "results", []) or [])
    facts: list[GovernedCalculationFact] = []
    for item in results:
        status = str(getattr(item, "status", "") or "")
        if status not in {"ok", "warning"}:
            continue
        validity_status = str(getattr(item, "validity_status", "") or "unknown")
        if validity_status == "stale":
            continue
        outputs = dict(getattr(item, "outputs", {}) or {})
        if not outputs:
            continue
        calculation_id = str(getattr(item, "calculation_id", "") or "")
        calculator = str(getattr(item, "calculator", "") or "")
        label = (
            _CALCULATION_LABELS.get(calculation_id)
            or _CALCULATION_LABELS.get(calculator)
            or human_label(calculation_id or calculator)
        )
        limitations = list(getattr(item, "limitations", []) or [])
        facts.append(
            GovernedCalculationFact(
                calculation_id=calculation_id or calculator,
                label=label,
                outputs=outputs,
                units=dict(getattr(item, "units", {}) or {}),
                status=status,
                claim_level=str(
                    getattr(item, "claim_level", "")
                    or "L3_deterministic_calculation"
                ),
                validity_status=validity_status,
                limitation=(
                    str(limitations[0])
                    if limitations
                    else "Berechneter Screening-Zwischenwert, keine technische Freigabe."
                ),
            )
        )
    return facts[:6]


def _slot_answer_bindings(state: Any) -> list[SlotAnswerBinding]:
    binding = getattr(state, "last_slot_answer_binding", None)
    return [binding] if isinstance(binding, SlotAnswerBinding) else []


def _accepted_updates(state: Any, bindings: list[SlotAnswerBinding]) -> list[GovernedAnswerUpdate]:
    updates: list[GovernedAnswerUpdate] = []
    assertions = dict(getattr(getattr(state, "asserted", None), "assertions", {}) or {})
    for binding in bindings:
        claim = assertions.get(binding.target_field)
        normalized_value = getattr(claim, "asserted_value", None) if claim is not None else binding.normalized_value
        updates.append(
            GovernedAnswerUpdate(
                field_key=binding.target_field,
                label=human_label(binding.target_field),
                value=normalized_value,
                unit=_field_unit(state, binding.target_field),
                source=binding.source,
                status="candidate_needs_clarification" if binding.needs_clarification else "accepted",
                confidence=(
                    str(getattr(claim, "confidence", "") or "")
                    if claim is not None
                    else "proposed"
                ),
            )
        )
    return updates


def _medium_clarification_question(state: Any) -> str | None:
    classification = getattr(state, "medium_classification", None)
    question = str(getattr(classification, "followup_question", "") or "").strip()
    return question or None


def _ambiguous_values(state: Any, bindings: list[SlotAnswerBinding]) -> list[GovernedAmbiguousValue]:
    values: list[GovernedAmbiguousValue] = []
    for binding in bindings:
        if not (binding.ambiguity or binding.needs_clarification):
            continue
        values.append(
            GovernedAmbiguousValue(
                field_key=binding.target_field,
                label=human_label(binding.target_field),
                raw_value=binding.raw_value,
                normalized_value=binding.normalized_value,
                clarification_question=(
                    _medium_clarification_question(state)
                    if binding.target_field == "medium"
                    else None
                ),
            )
        )
    return values


def _rejected_updates(state: Any) -> list[GovernedRejectedUpdate]:
    rejected: list[GovernedRejectedUpdate] = []
    asserted = getattr(state, "asserted", None)
    for field_key in list(getattr(asserted, "conflict_flags", []) or []):
        rejected.append(
            GovernedRejectedUpdate(
                field_key=str(field_key),
                label=human_label(str(field_key)),
                reason="conflict_unresolved",
            )
        )
    return rejected


def _next_best_question(strategy: Any | None, ambiguous_values: list[GovernedAmbiguousValue]) -> str | None:
    for item in ambiguous_values:
        if item.clarification_question:
            return item.clarification_question
    primary = str(getattr(strategy, "primary_question", "") or "").strip() if strategy is not None else ""
    if primary:
        return primary
    return None


def _allowed_claims(
    *,
    confirmed_facts: list[GovernedFact],
    missing_fields: list[str],
    ambiguous_values: list[GovernedAmbiguousValue],
    next_best_question: str | None,
) -> list[str]:
    claims: list[str] = []
    for fact in confirmed_facts:
        claims.append(f"confirmed_field:{fact.field_key}")
    for field in missing_fields:
        claims.append(f"missing_field:{field}")
    for item in ambiguous_values:
        claims.append(f"ambiguous_value:{item.field_key}")
    if next_best_question:
        claims.append("next_best_question")
    return _unique(claims)


def build_governed_answer_context(
    state: Any,
    *,
    output_public: dict[str, Any] | None = None,
    output_reply: str | None = None,
    response_class: str | None = None,
    strategy: Any | None = None,
    pending_question: PendingQuestion | None = None,
) -> GovernedAnswerContext:
    """Build a read-only context for a future governed answer composer.

    The context is intentionally non-authoritative: it mirrors already governed
    state and output strategy, but it never computes engineering truth or changes
    the visible reply.
    """

    bindings = _slot_answer_bindings(state)
    ambiguous = _ambiguous_values(state, bindings)
    confirmed = _confirmed_facts(state)
    calculations = _calculation_results(state)
    missing = _missing_fields(state, output_public)
    open_points = _open_points(state, output_public)
    challenge_findings = _challenge_findings(state)
    challenge_hypotheses = _challenge_hypotheses(state)
    next_question = _next_best_question(strategy, ambiguous)
    question_plan = build_question_plan_from_strategy(
        strategy=strategy,
        state=state,
        override_question=next_question,
        override_target_field=(
            ambiguous[0].field_key if ambiguous else None
        ),
        override_reason=(
            "Der zuletzt genannte Wert ist noch mehrdeutig und braucht eine klare Einordnung."
            if ambiguous
            else None
        ),
    )
    context = GovernedAnswerContext(
        latest_user_message=_latest_user_message(state),
        pending_question=pending_question if pending_question is not None else getattr(state, "pending_question", None),
        slot_answer_bindings=bindings,
        accepted_updates=_accepted_updates(state, bindings),
        ambiguous_values=ambiguous,
        rejected_updates=_rejected_updates(state),
        confirmed_facts=confirmed,
        calculation_results=calculations,
        missing_fields=missing,
        open_points=open_points,
        challenge_findings=challenge_findings,
        challenge_hypotheses=challenge_hypotheses,
        next_best_question=next_question,
        v91_question_plan=question_plan,
        response_class=response_class or str(getattr(state, "output_response_class", "") or "") or None,
        allowed_claims=_allowed_claims(
            confirmed_facts=confirmed,
            missing_fields=missing,
            ambiguous_values=ambiguous,
            next_best_question=next_question,
        ),
        answer_goal=(
            "acknowledge the supplied slot answer, clarify the ambiguity, and ask the next best required question"
            if ambiguous
            else "acknowledge valid newly supplied information and ask the next best required question"
        ),
    )
    return context.model_copy(
        update={
            "v91_final_answer_context": build_v91_final_answer_context(
                state=state,
                governed_context=context,
            )
        }
    )
