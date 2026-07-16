"""Pure lexicographic interview policy for versioned domain packs."""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import replace

from sealai_v2.core.case_state import CaseField, CaseFieldStatus, CaseStateV2
from sealai_v2.core.contracts import DerivedFact
from sealai_v2.core.interview.contracts import (
    DomainPack,
    EpistemicStatus,
    FactOrigin,
    FactSemantics,
    FactSnapshot,
    InterviewCompletenessMetrics,
    InterviewConflict,
    InterviewDecision,
    InterviewDirective,
    InterviewDirectiveType,
    InterviewRuntimeState,
    InterviewStatePatch,
    InterviewStatePatchType,
    NeedDefinition,
    NeedState,
    NeedStatus,
    NextQuestionPayload,
    PendingQuestion,
    PendingQuestionStatus,
    VerificationStatus,
)

_UNKNOWN_VALUES = {"", "unknown", "unbekannt", "nicht bekannt", "n/a"}
_SUPPORTED_SCOPE = "supported"
_UNSUPPORTED_SCOPE = "unsupported"
_UNKNOWN_SCOPE = "unknown"


class InterviewContractError(RuntimeError):
    """Controlled fail-closed error for an invalid interview catalog/runtime."""


def _normalized(value: str | None) -> str:
    return " ".join((value or "").strip().casefold().split())


def _origin(field: CaseField) -> FactOrigin:
    kind = field.source.kind.casefold()
    reference = field.source.reference.casefold()
    if kind == "kernel":
        return FactOrigin.KERNEL
    if kind == "document":
        return FactOrigin.DOCUMENT
    if kind == "expert":
        return FactOrigin.EXPERT
    if kind == "import":
        return FactOrigin.IMPORT
    if "form" in kind or "user-form" in reference:
        return FactOrigin.USER_FORM
    return FactOrigin.USER_TEXT


def _verification(field: CaseField) -> VerificationStatus:
    if field.status is CaseFieldStatus.CONFIRMED:
        return VerificationStatus.USER_CONFIRMED
    if field.status is CaseFieldStatus.DERIVED:
        return VerificationStatus.SYSTEM_VALIDATED
    if field.status is CaseFieldStatus.DOCUMENT_EXTRACTED:
        return VerificationStatus.NORMALIZED
    if field.status is CaseFieldStatus.CONFLICT:
        return VerificationStatus.REJECTED
    return VerificationStatus.CANDIDATE


def _epistemic(field: CaseField) -> EpistemicStatus:
    if field.status is CaseFieldStatus.DERIVED:
        return EpistemicStatus.DERIVED
    if field.status is CaseFieldStatus.CONFLICT:
        return EpistemicStatus.CONFLICTING
    if field.status is CaseFieldStatus.DOCUMENT_EXTRACTED:
        return EpistemicStatus.OBSERVED
    if field.value is None or _normalized(field.value) in _UNKNOWN_VALUES:
        return EpistemicStatus.UNKNOWN
    return EpistemicStatus.STATED


def _semantics(field: CaseField) -> FactSemantics:
    return FactSemantics(
        origin=_origin(field),
        verification_status=_verification(field),
        epistemic_status=_epistemic(field),
        field_key=field.key,
        value=field.value,
        unit=field.unit,
        source_ref=field.source.reference,
    )


def classify_scope(case_state: CaseStateV2, pack: DomainPack) -> str:
    explicit = next(
        (
            field
            for key in ("dichtungstyp", "seal_type")
            if (field := case_state.field(key)) is not None and field.value
        ),
        None,
    )
    if explicit is not None:
        value = _normalized(explicit.value)
        if value in {_normalized(item) for item in pack.supported_seal_types}:
            return _SUPPORTED_SCOPE
        return _UNSUPPORTED_SCOPE
    if any(case_state.field(key) is not None for key in pack.rwdr_signal_fields):
        return _SUPPORTED_SCOPE
    return _UNKNOWN_SCOPE


def _need_for_field(pack: DomainPack, field_key: str) -> NeedDefinition | None:
    candidates = [
        need for need in pack.needs if need.active and field_key in need.field_keys
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda need: (
            not need.required,
            need.curated_order,
            need.need_id,
        ),
    )


def _conflict_id(
    *, case_id: str, field_key: str, old: FactSnapshot, new: CaseField, revision: int
) -> str:
    payload = "|".join(
        (
            case_id,
            field_key,
            str(old.state_revision),
            str(revision),
            old.value,
            new.value or "",
        )
    )
    return "icf_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def reconcile_runtime_facts(
    case_state: CaseStateV2,
    pack: DomainPack,
    runtime_state: InterviewRuntimeState,
) -> InterviewRuntimeState:
    """Record decision-critical value changes without modifying the canonical facts.

    The canonical V2 fact remains last-value-wins.  This coupled interview state keeps
    the preceding value and the revision that changed it so a correction is auditably
    surfaced as a conflict instead of disappearing.
    """
    previous = {item.field_key: item for item in runtime_state.fact_snapshots}
    conflicts = list(runtime_state.conflicts)
    snapshots: list[FactSnapshot] = []
    tracked_fields = {
        key for need in pack.needs if need.active for key in need.field_keys
    }
    for field in sorted(
        (item for item in case_state.fields if item.key in tracked_fields),
        key=lambda item: item.key,
    ):
        if field.value is None:
            continue
        old = previous.get(field.key)
        need = _need_for_field(pack, field.key)
        if (
            old is not None
            and need is not None
            and need.conflict_sensitive
            and (old.value, old.unit) != (field.value, field.unit)
            and not any(
                item.status == "active"
                and item.field_key == field.key
                and item.candidate_values == (old.value, field.value)
                for item in conflicts
            )
        ):
            conflicts.append(
                InterviewConflict(
                    conflict_id=_conflict_id(
                        case_id=case_state.case_id,
                        field_key=field.key,
                        old=old,
                        new=field,
                        revision=case_state.revision,
                    ),
                    field_key=field.key,
                    need_id=need.need_id,
                    candidate_values=(old.value, field.value),
                    created_from_state_revision=case_state.revision,
                )
            )
        snapshots.append(
            FactSnapshot(
                field_key=field.key,
                value=field.value,
                unit=field.unit,
                state_revision=case_state.revision,
                status=field.status.value,
            )
        )
    legacy = runtime_state.pack_id == "legacy_unversioned"
    return replace(
        runtime_state,
        pack_id=pack.pack_id if legacy else runtime_state.pack_id,
        pack_version=pack.version if legacy else runtime_state.pack_version,
        policy_version=pack.policy_version if legacy else runtime_state.policy_version,
        question_catalog_version=(
            pack.question_catalog_version
            if legacy
            else runtime_state.question_catalog_version
        ),
        case_schema_version=case_state.schema_version,
        state_revision=case_state.revision,
        conflicts=tuple(conflicts),
        fact_snapshots=tuple(snapshots),
        calculator_version_refs=(
            pack.calculator_version_refs
            if legacy
            else runtime_state.calculator_version_refs
        ),
    )


def resolve_need_states(
    case_state: CaseStateV2,
    pack: DomainPack,
    runtime_state: InterviewRuntimeState,
    *,
    derived_facts: tuple[DerivedFact, ...] = (),
) -> dict[str, NeedState]:
    by_calc = {item.calc_id: item for item in derived_facts}
    active_conflicts = {
        item.need_id for item in runtime_state.conflicts if item.status == "active"
    }
    for conflict in case_state.open_conflicts:
        if need := _need_for_field(pack, conflict.field_key):
            active_conflicts.add(need.need_id)

    overrides = {item.need_id: item for item in runtime_state.unobtainable_overrides}
    for record in overrides.values():
        if (record.pack_version, record.policy_version) != (
            pack.version,
            pack.policy_version,
        ):
            raise InterviewContractError("unobtainable override version mismatch")
        if pack.need(record.need_id) is None or not pack.allows_unobtainable(
            record.need_id
        ):
            raise InterviewContractError(
                "unobtainable override is not allowed for this primary need"
            )

    states: dict[str, NeedState] = {}
    for need in sorted(
        pack.needs, key=lambda item: (item.dependency_depth, item.need_id)
    ):
        if not need.active:
            states[need.need_id] = NeedState(
                need_id=need.need_id,
                status=NeedStatus.NOT_APPLICABLE,
                reason_code="inactive_in_pack_version",
            )
            continue
        if need.need_id in active_conflicts:
            states[need.need_id] = NeedState(
                need_id=need.need_id,
                status=NeedStatus.CONFLICTED,
                reason_code="active_conflict",
            )
            continue
        if need.need_id in overrides:
            states[need.need_id] = NeedState(
                need_id=need.need_id,
                status=NeedStatus.UNOBTAINABLE,
                reason_code="audited_unobtainable_override",
            )
            continue
        if need.derived_calc_id:
            derived = by_calc.get(need.derived_calc_id)
            if derived is not None:
                states[need.need_id] = NeedState(
                    need_id=need.need_id,
                    status=NeedStatus.SATISFIED,
                    facts=(
                        FactSemantics(
                            origin=FactOrigin.KERNEL,
                            verification_status=VerificationStatus.SYSTEM_VALIDATED,
                            epistemic_status=EpistemicStatus.DERIVED,
                            field_key=derived.name,
                            value=derived.value,
                            unit=derived.unit,
                            source_ref=derived.calc_id,
                        ),
                    ),
                    reason_code="kernel_derived",
                )
                continue
            dependencies = [states.get(ref) for ref in need.dependency_refs]
            reason = (
                "kernel_result_missing"
                if dependencies
                and all(
                    item is not None and item.status is NeedStatus.SATISFIED
                    for item in dependencies
                )
                else "dependencies_open"
            )
            states[need.need_id] = NeedState(
                need_id=need.need_id,
                status=NeedStatus.BLOCKED,
                reason_code=reason,
            )
            continue
        fields = tuple(
            field
            for key in need.field_keys
            if (field := case_state.field(key)) is not None
            and field.value is not None
            and _normalized(field.value) not in _UNKNOWN_VALUES
        )
        if not fields:
            status = NeedStatus.UNKNOWN
        elif len(fields) < max(1, need.min_present):
            status = NeedStatus.PARTIAL
        else:
            status = NeedStatus.SATISFIED
        states[need.need_id] = NeedState(
            need_id=need.need_id,
            status=status,
            facts=tuple(_semantics(field) for field in fields),
            reason_code="mapped_case_fields" if fields else "no_mapped_value",
        )
    return states


def completeness_metrics(
    pack: DomainPack, states: dict[str, NeedState]
) -> InterviewCompletenessMetrics:
    required = [item for item in pack.needs if item.active and item.required]
    counts = Counter(states[item.need_id].status for item in required)
    documented = sum(1 for item in required if states[item.need_id].is_documented)
    return InterviewCompletenessMetrics(
        active_required_needs=len(required),
        documented_required_needs=documented,
        satisfied=counts[NeedStatus.SATISFIED],
        conflicted=counts[NeedStatus.CONFLICTED],
        unobtainable=counts[NeedStatus.UNOBTAINABLE],
        not_applicable=counts[NeedStatus.NOT_APPLICABLE],
        blocked=counts[NeedStatus.BLOCKED],
    )


def _dependency_snapshot(
    question_id: str, pack: DomainPack, states: dict[str, NeedState]
) -> dict[str, str]:
    question = pack.question(question_id)
    if question is None:
        return {}
    refs = set(question.dependency_refs)
    if need := pack.need(question.primary_need_id):
        refs.update(need.dependency_refs)
    return {ref: states[ref].status.value for ref in sorted(refs) if ref in states}


def _pending_id(
    *,
    case_id: str,
    topic_id: str,
    question_id: str,
    directive_type: InterviewDirectiveType,
    state_revision: int,
) -> str:
    payload = (
        f"{case_id}|{topic_id}|{question_id}|{directive_type.value}|{state_revision}"
    )
    return "ipq_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _pending_for(
    *,
    case_state: CaseStateV2,
    runtime_state: InterviewRuntimeState,
    pack: DomainPack,
    states: dict[str, NeedState],
    question_id: str,
    directive_type: InterviewDirectiveType,
) -> PendingQuestion:
    question = pack.question(question_id)
    assert question is not None
    return PendingQuestion(
        pending_question_id=_pending_id(
            case_id=case_state.case_id,
            topic_id=runtime_state.topic_id,
            question_id=question_id,
            directive_type=directive_type,
            state_revision=case_state.revision,
        ),
        question_id=question_id,
        primary_need_id=question.primary_need_id,
        related_need_ids=question.related_need_ids,
        topic_id=runtime_state.topic_id,
        pack_id=pack.pack_id,
        pack_version=pack.version,
        policy_version=pack.policy_version,
        created_at="",
        created_from_state_revision=case_state.revision,
        dependency_snapshot=_dependency_snapshot(question_id, pack, states),
        directive_type=directive_type,
    )


def _validate_pending(
    pending: PendingQuestion,
    *,
    pack: DomainPack,
    states: dict[str, NeedState],
    active_conflict_ids: set[str],
    state_revision: int,
) -> tuple[bool, PendingQuestion | None, str]:
    if pending.status is not PendingQuestionStatus.ACTIVE:
        return False, None, "not_active"
    if (pending.pack_id, pending.pack_version, pending.policy_version) != (
        pack.pack_id,
        pack.version,
        pack.policy_version,
    ):
        return (
            False,
            replace(
                pending,
                status=PendingQuestionStatus.INVALIDATED,
                invalidated_reason="version_mismatch_continue_pinned",
            ),
            "version_mismatch",
        )
    if pending.created_from_state_revision > state_revision:
        return (
            False,
            replace(
                pending,
                status=PendingQuestionStatus.INVALIDATED,
                invalidated_reason="pending_from_future_state_revision",
            ),
            "future_state_revision",
        )
    question = pack.question(pending.question_id)
    if question is None:
        return (
            False,
            replace(
                pending,
                status=PendingQuestionStatus.INVALIDATED,
                invalidated_reason="question_missing_from_catalog",
            ),
            "question_missing",
        )
    current_snapshot = _dependency_snapshot(pending.question_id, pack, states)
    if current_snapshot != pending.dependency_snapshot:
        return (
            False,
            replace(
                pending,
                status=PendingQuestionStatus.INVALIDATED,
                invalidated_reason="dependency_snapshot_changed",
            ),
            "dependency_changed",
        )
    state = states[pending.primary_need_id]
    if pending.directive_type is InterviewDirectiveType.ASK:
        valid = state.status in {NeedStatus.UNKNOWN, NeedStatus.PARTIAL}
    elif pending.directive_type is InterviewDirectiveType.CONFIRM_CRITICAL_FACT:
        valid = state.status is NeedStatus.SATISFIED and any(
            fact.verification_status
            not in {
                VerificationStatus.USER_CONFIRMED,
                VerificationStatus.SYSTEM_VALIDATED,
                VerificationStatus.EXPERT_APPROVED,
            }
            for fact in state.facts
        )
    else:
        valid = state.status is NeedStatus.CONFLICTED and bool(active_conflict_ids)
    if valid:
        return True, None, "valid"
    status = (
        PendingQuestionStatus.ANSWERED
        if state.status is NeedStatus.SATISFIED
        else PendingQuestionStatus.INVALIDATED
    )
    return (
        False,
        replace(
            pending,
            status=status,
            invalidated_reason=(
                ""
                if status is PendingQuestionStatus.ANSWERED
                else "need_no_longer_open"
            ),
        ),
        "need_closed",
    )


def _decision(
    *,
    case_state: CaseStateV2,
    pack: DomainPack,
    directive: InterviewDirective,
    rule_refs: tuple[str, ...],
    patches: tuple[InterviewStatePatch, ...],
) -> InterviewDecision:
    return InterviewDecision(
        directives=(directive,),
        rule_refs=tuple(dict.fromkeys(rule_refs)),
        pack_id=pack.pack_id,
        pack_version=pack.version,
        policy_version=pack.policy_version,
        state_revision=case_state.revision,
        state_patches=patches,
    )


def decide_next_interview_step(
    case_state: CaseStateV2,
    domain_pack: DomainPack,
    *,
    runtime_state: InterviewRuntimeState | None = None,
    derived_facts: tuple[DerivedFact, ...] = (),
) -> InterviewDecision:
    """Return one deterministic primary user action using a strict tier order."""
    runtime = runtime_state or InterviewRuntimeState()
    patches: list[InterviewStatePatch] = []

    if runtime.pack_id not in {"legacy_unversioned", domain_pack.pack_id} or (
        runtime.pack_id == domain_pack.pack_id
        and runtime.pack_version not in {"legacy_unversioned", domain_pack.version}
    ):
        return _decision(
            case_state=case_state,
            pack=domain_pack,
            directive=InterviewDirective(
                type=InterviewDirectiveType.ESCALATE,
                reason_code="pinned_pack_version_unavailable",
            ),
            rule_refs=("AI-T0-VERSION-001",),
            patches=(),
        )

    scope = classify_scope(case_state, domain_pack)
    if scope == _UNSUPPORTED_SCOPE:
        return _decision(
            case_state=case_state,
            pack=domain_pack,
            directive=InterviewDirective(
                type=InterviewDirectiveType.ESCALATE,
                reason_code="out_of_scope_primary_case",
            ),
            rule_refs=("AI-T0-SCOPE-001",),
            patches=(),
        )
    if scope == _UNKNOWN_SCOPE:
        return InterviewDecision(
            directives=(),
            rule_refs=("AI-T0-NO-RWDR-CANDIDATE",),
            pack_id=domain_pack.pack_id,
            pack_version=domain_pack.version,
            policy_version=domain_pack.policy_version,
            state_revision=case_state.revision,
        )

    states = resolve_need_states(
        case_state, domain_pack, runtime, derived_facts=derived_facts
    )
    conflict_items = [item for item in runtime.conflicts if item.status == "active"]
    for conflict in case_state.open_conflicts:
        need = _need_for_field(domain_pack, conflict.field_key)
        if need is None:
            continue
        conflict_items.append(
            InterviewConflict(
                conflict_id="icf_"
                + hashlib.sha256(
                    (
                        f"{case_state.case_id}|{conflict.field_key}|"
                        f"{'|'.join(conflict.candidate_values)}"
                    ).encode("utf-8")
                ).hexdigest()[:24],
                field_key=conflict.field_key,
                need_id=need.need_id,
                candidate_values=conflict.candidate_values,
                created_from_state_revision=case_state.revision,
                reason_code=conflict.reason,
            )
        )
    active_conflicts = tuple(
        sorted(
            {item.conflict_id: item for item in conflict_items}.values(),
            key=lambda item: (item.created_from_state_revision, item.conflict_id),
        )
    )
    active_conflict_ids = {item.conflict_id for item in active_conflicts}

    valid_pending: list[PendingQuestion] = []
    for pending in sorted(
        runtime.pending_questions,
        key=lambda item: (item.created_from_state_revision, item.question_id),
    ):
        valid, update, _reason = _validate_pending(
            pending,
            pack=domain_pack,
            states=states,
            active_conflict_ids=active_conflict_ids,
            state_revision=case_state.revision,
        )
        if valid:
            valid_pending.append(pending)
        elif update is not None:
            patches.append(
                InterviewStatePatch(
                    type=InterviewStatePatchType.UPDATE_PENDING_STATUS,
                    pending_question=update,
                )
            )
    if len(valid_pending) > 1:
        for extra in valid_pending[1:]:
            patches.append(
                InterviewStatePatch(
                    type=InterviewStatePatchType.UPDATE_PENDING_STATUS,
                    pending_question=replace(
                        extra,
                        status=PendingQuestionStatus.SUPERSEDED,
                        invalidated_reason="single_active_question_invariant",
                    ),
                )
            )
        valid_pending = valid_pending[:1]

    # T2a: decision-critical conflicts dominate every normal question.
    if active_conflicts:
        conflict = active_conflicts[0]
        need = domain_pack.need(conflict.need_id)
        if need is not None and need.question_id:
            pending = _pending_for(
                case_state=case_state,
                runtime_state=runtime,
                pack=domain_pack,
                states=states,
                question_id=need.question_id,
                directive_type=InterviewDirectiveType.CLARIFY_CONFLICT,
            )
            patches.append(
                InterviewStatePatch(
                    type=InterviewStatePatchType.UPSERT_PENDING,
                    pending_question=pending,
                )
            )
            return _decision(
                case_state=case_state,
                pack=domain_pack,
                directive=InterviewDirective(
                    type=InterviewDirectiveType.CLARIFY_CONFLICT,
                    reason_code="decision_critical_conflict",
                    question_id=need.question_id,
                    primary_need_id=need.need_id,
                    conflict_id=conflict.conflict_id,
                    pending_question_id=pending.pending_question_id,
                ),
                rule_refs=("AI-T2-CONFLICT-001", *need.rule_refs),
                patches=tuple(patches),
            )

    # T2b: a critical value from text/document remains a candidate until confirmed.
    critical_unconfirmed = []
    for need in domain_pack.needs:
        state = states[need.need_id]
        if (
            need.active
            and need.required
            and need.criticality == "decision_critical"
            and need.question_id
            and state.status is NeedStatus.SATISFIED
            and any(
                fact.verification_status
                not in {
                    VerificationStatus.USER_CONFIRMED,
                    VerificationStatus.SYSTEM_VALIDATED,
                    VerificationStatus.EXPERT_APPROVED,
                }
                for fact in state.facts
            )
        ):
            critical_unconfirmed.append(need)
    if critical_unconfirmed:
        need = min(critical_unconfirmed, key=_need_order)
        pending = _pending_for(
            case_state=case_state,
            runtime_state=runtime,
            pack=domain_pack,
            states=states,
            question_id=need.question_id or "",
            directive_type=InterviewDirectiveType.CONFIRM_CRITICAL_FACT,
        )
        patches.append(
            InterviewStatePatch(
                type=InterviewStatePatchType.UPSERT_PENDING,
                pending_question=pending,
            )
        )
        return _decision(
            case_state=case_state,
            pack=domain_pack,
            directive=InterviewDirective(
                type=InterviewDirectiveType.CONFIRM_CRITICAL_FACT,
                reason_code="unconfirmed_decision_critical_fact",
                question_id=need.question_id,
                primary_need_id=need.need_id,
                pending_question_id=pending.pending_question_id,
            ),
            rule_refs=("AI-T2-CONFIRM-001", *need.rule_refs),
            patches=tuple(patches),
        )

    # T3: continue the one still-valid pending question.
    if valid_pending:
        pending = valid_pending[0]
        return _decision(
            case_state=case_state,
            pack=domain_pack,
            directive=InterviewDirective(
                type=pending.directive_type,
                reason_code="continue_valid_pending_question",
                question_id=pending.question_id,
                primary_need_id=pending.primary_need_id,
                pending_question_id=pending.pending_question_id,
            ),
            rule_refs=("AI-T3-PENDING-001",),
            patches=tuple(patches),
        )

    # T4: required askable needs, sorted lexicographically and never by a score.
    required_open = [
        need
        for need in domain_pack.needs
        if need.active
        and need.required
        and need.question_id
        and states[need.need_id].status in {NeedStatus.UNKNOWN, NeedStatus.PARTIAL}
        and all(
            states[ref].status
            in {
                NeedStatus.SATISFIED,
                NeedStatus.UNOBTAINABLE,
                NeedStatus.NOT_APPLICABLE,
            }
            for ref in need.dependency_refs
        )
    ]
    if required_open:
        need = min(required_open, key=_need_order)
        pending = _pending_for(
            case_state=case_state,
            runtime_state=runtime,
            pack=domain_pack,
            states=states,
            question_id=need.question_id or "",
            directive_type=InterviewDirectiveType.ASK,
        )
        patches.append(
            InterviewStatePatch(
                type=InterviewStatePatchType.UPSERT_PENDING,
                pending_question=pending,
            )
        )
        return _decision(
            case_state=case_state,
            pack=domain_pack,
            directive=InterviewDirective(
                type=InterviewDirectiveType.ASK,
                reason_code="next_required_need",
                question_id=need.question_id,
                primary_need_id=need.need_id,
                pending_question_id=pending.pending_question_id,
            ),
            rule_refs=("AI-T4-REQUIRED-001", *need.rule_refs),
            patches=tuple(patches),
        )

    missing_kernel = next(
        (
            need
            for need in domain_pack.needs
            if need.active
            and need.required
            and need.derived_calc_id
            and states[need.need_id].reason_code == "kernel_result_missing"
        ),
        None,
    )
    if missing_kernel is not None:
        return _decision(
            case_state=case_state,
            pack=domain_pack,
            directive=InterviewDirective(
                type=InterviewDirectiveType.ESCALATE,
                reason_code="required_kernel_result_missing",
                primary_need_id=missing_kernel.need_id,
            ),
            rule_refs=("AI-T6-KERNEL-001", *missing_kernel.rule_refs),
            patches=tuple(patches),
        )

    required_incomplete = next(
        (
            need
            for need in domain_pack.needs
            if need.active
            and need.required
            and not states[need.need_id].is_completion_satisfying
        ),
        None,
    )
    if required_incomplete is not None:
        return _decision(
            case_state=case_state,
            pack=domain_pack,
            directive=InterviewDirective(
                type=InterviewDirectiveType.ESCALATE,
                reason_code="required_need_not_completion_satisfying",
                primary_need_id=required_incomplete.need_id,
            ),
            rule_refs=("AI-T6-INCOMPLETE-001", *required_incomplete.rule_refs),
            patches=tuple(patches),
        )

    return _decision(
        case_state=case_state,
        pack=domain_pack,
        directive=InterviewDirective(
            type=InterviewDirectiveType.COMPLETE,
            reason_code="required_stop_profile_documented",
        ),
        rule_refs=("AI-T6-COMPLETE-001",),
        patches=tuple(patches),
    )


def _need_order(need: NeedDefinition) -> tuple[int, int, int, str]:
    return (
        need.dependency_depth,
        need.curated_order,
        -need.downstream_unlock_count,
        need.question_id or need.need_id,
    )


def apply_state_patches(
    runtime_state: InterviewRuntimeState,
    decision: InterviewDecision,
    *,
    created_at: str,
) -> InterviewRuntimeState:
    pending = {
        item.pending_question_id: item for item in runtime_state.pending_questions
    }
    for patch in decision.state_patches:
        item = patch.pending_question
        if patch.type is InterviewStatePatchType.UPSERT_PENDING:
            for key, current in tuple(pending.items()):
                if (
                    current.topic_id == item.topic_id
                    and current.status is PendingQuestionStatus.ACTIVE
                    and key != item.pending_question_id
                ):
                    pending[key] = replace(
                        current,
                        status=PendingQuestionStatus.SUPERSEDED,
                        invalidated_reason="new_canonical_pending_question",
                    )
            pending[item.pending_question_id] = replace(
                item, created_at=item.created_at or created_at
            )
        else:
            pending[item.pending_question_id] = (
                replace(item, answered_at=created_at)
                if item.status is PendingQuestionStatus.ANSWERED
                and not item.answered_at
                else item
            )
    return replace(
        runtime_state,
        state_revision=decision.state_revision,
        pending_questions=tuple(
            sorted(
                pending.values(),
                key=lambda item: (
                    item.created_from_state_revision,
                    item.pending_question_id,
                ),
            )
        ),
    )


def next_question_payload(
    *,
    case_id: str,
    topic_id: str,
    pack: DomainPack,
    decision: InterviewDecision,
) -> NextQuestionPayload | None:
    directive = decision.directives[0] if decision.directives else None
    if directive is None:
        return None
    expects_question = directive.type in {
        InterviewDirectiveType.ASK,
        InterviewDirectiveType.CLARIFY_CONFLICT,
        InterviewDirectiveType.CONFIRM_CRITICAL_FACT,
    }
    if expects_question and (
        not directive.question_id or not directive.pending_question_id
    ):
        raise InterviewContractError(
            "question directive requires question and pending references"
        )
    if not expects_question:
        if directive.question_id or directive.pending_question_id:
            raise InterviewContractError(
                "non-question directive cannot carry question references"
            )
        return None
    question = pack.question(directive.question_id)
    if question is None:
        raise InterviewContractError("directed question missing from catalog")
    return NextQuestionPayload(
        case_id=case_id,
        topic_id=topic_id,
        state_revision=decision.state_revision,
        pack_id=pack.pack_id,
        pack_version=pack.version,
        policy_version=pack.policy_version,
        question_id=question.question_id,
        primary_need_id=question.primary_need_id,
        related_need_ids=question.related_need_ids,
        question_text=question.canonical_text_de,
        question_type=question.question_type,
        answer_schema=question.answer_schema,
        allowed_unknown=question.allowed_unknown,
        allowed_unobtainable=question.allowed_unobtainable,
        criticality=question.criticality,
        rule_refs=tuple(dict.fromkeys((*decision.rule_refs, *question.rule_refs))),
        dependency_refs=question.dependency_refs,
        pending_question_id=directive.pending_question_id,
    )
