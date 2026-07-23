from __future__ import annotations

from dataclasses import replace

import pytest

from sealai_v2.core.case_state import (
    CaseField,
    CaseFieldSource,
    CaseFieldStatus,
    CaseStateV2,
)
from sealai_v2.core.contracts import DerivedFact, RememberedFact
from sealai_v2.core.interview.contracts import (
    InterviewDirectiveType,
    InterviewRuntimeState,
    NeedStatus,
    PendingQuestionStatus,
    UnobtainableOverrideAudit,
)
from sealai_v2.core.interview.policy import InterviewContractError
from sealai_v2.core.interview.policy import (
    apply_state_patches,
    compute_required_missing,
    decide_next_interview_step,
    reconcile_runtime_facts,
    resolve_need_states,
)
from sealai_v2.knowledge.domain_packs import load_rwdr_v1_pack

PACK = load_rwdr_v1_pack()


def _unobtainable(need_id: str) -> UnobtainableOverrideAudit:
    return UnobtainableOverrideAudit(
        need_id=need_id,
        reason="owner documented that the value cannot be obtained",
        actor_ref="user:owner-1",
        created_at="2026-07-16T10:00:00+00:00",
        pack_version=PACK.version,
        policy_version=PACK.policy_version,
    )


def _field(key: str, value: str, *, confirmed: bool = True) -> CaseField:
    return CaseField(
        key=key,
        value=value,
        status=(CaseFieldStatus.CONFIRMED if confirmed else CaseFieldStatus.STATED),
        source=CaseFieldSource(
            kind="user_form" if confirmed else "conversation_distilled"
        ),
    )


def _state(values: dict[str, str], *, revision: int = 1, confirmed: bool = True):
    values = {"dichtungstyp": "rwdr", **values}
    return CaseStateV2(
        case_id="case-rwdr",
        revision=revision,
        fields=tuple(
            _field(key, value, confirmed=confirmed) for key, value in values.items()
        ),
    )


def _runtime(state: CaseStateV2) -> InterviewRuntimeState:
    return reconcile_runtime_facts(state, PACK, InterviewRuntimeState())


def _directive(state, runtime=None, derived=()):
    return decide_next_interview_step(
        state,
        PACK,
        runtime_state=runtime or _runtime(state),
        derived_facts=derived,
    ).directives[0]


def _required_values() -> dict[str, str]:
    return {
        "anwendungsziel": "new_design",
        "medium": "Hydrauliköl HLP 46",
        "betriebstemperatur": "80 °C",
        "druck": "0,2 bar",
        "wellendurchmesser": "50 mm",
        "drehzahl": "1500 U/min",
    }


def _velocity() -> tuple[DerivedFact, ...]:
    return (
        DerivedFact(
            calc_id="umfangsgeschwindigkeit",
            name="v_m_s",
            value=3.927,
            unit="m/s",
            formula="pi*d*n/60000",
            parent_fields=("wellendurchmesser", "drehzahl"),
        ),
    )


def test_productive_rwdr_fields_map_to_stable_need_ids() -> None:
    mapping = {field: need.need_id for need in PACK.needs for field in need.field_keys}
    assert mapping["medium"] == "rwdr.medium.primary"
    assert mapping["wellendurchmesser"] == "rwdr.shaft.diameter"
    assert mapping["drehzahl"] == "rwdr.rotation.speed"
    assert mapping["gehäusebohrung"] == "rwdr.housing.diameter"
    assert mapping["einbaubreite"] == "rwdr.seal.width"
    assert mapping["rundlauf"] == "rwdr.shaft.runout"
    assert mapping["versatz"] == "rwdr.shaft.eccentricity"
    assert mapping["drall"] == "rwdr.shaft.lead_free_surface"
    assert mapping["staublippe"] == "rwdr.dust_lip.required"


def test_need_status_separates_user_form_semantics_and_unobtainable() -> None:
    state = _state({"wellendurchmesser": "50 mm"})
    runtime = replace(
        _runtime(state),
        unobtainable_overrides=(_unobtainable("rwdr.shaft.material"),),
    )
    needs = resolve_need_states(state, PACK, runtime)
    diameter = needs["rwdr.shaft.diameter"]
    assert diameter.status is NeedStatus.SATISFIED
    assert diameter.facts[0].origin.value == "user_form"
    assert diameter.facts[0].verification_status.value == "user_confirmed"
    assert needs["rwdr.shaft.material"].status is NeedStatus.UNOBTAINABLE


def test_real_case_state_conversion_preserves_user_form_origin() -> None:
    state = CaseStateV2.from_remembered_facts(
        case_id="case-rwdr",
        revision=1,
        facts=(
            RememberedFact(
                feld="dichtungstyp",
                wert="rwdr",
                provenance="user-form",
                status="confirmed",
            ),
            RememberedFact(
                feld="wellendurchmesser",
                wert="50 mm",
                provenance="user-form",
                status="confirmed",
            ),
        ),
    )
    needs = resolve_need_states(state, PACK, _runtime(state))
    diameter = needs["rwdr.shaft.diameter"]
    assert diameter.facts[0].origin.value == "user_form"
    assert state.to_remembered_facts()[1].provenance == "user-form"


def test_unobtainable_primary_need_is_not_asked_again() -> None:
    state = _state({})
    runtime = replace(
        _runtime(state),
        unobtainable_overrides=(_unobtainable("rwdr.medium.primary"),),
    )
    directive = _directive(state, runtime)
    assert directive.question_id == "rwdr.q.application_goal"
    assert directive.primary_need_id == "rwdr.application.goal"


def test_non_enabled_primary_need_cannot_be_marked_unobtainable() -> None:
    state = _state({})
    runtime = replace(
        _runtime(state),
        unobtainable_overrides=(_unobtainable("rwdr.application.goal"),),
    )
    with pytest.raises(InterviewContractError, match="not allowed"):
        resolve_need_states(state, PACK, runtime)


def test_scope_gate_dominates_normal_required_questions() -> None:
    state = CaseStateV2(
        case_id="glrd-case",
        revision=1,
        fields=(_field("dichtungstyp", "gleitringdichtung"),),
    )
    directive = _directive(state, InterviewRuntimeState())
    assert directive.type is InterviewDirectiveType.ESCALATE
    assert directive.reason_code == "out_of_scope_primary_case"


def test_unknown_non_case_does_not_start_rwdr_interview() -> None:
    state = CaseStateV2(case_id="knowledge-only", revision=0)
    decision = decide_next_interview_step(state, PACK)
    assert decision.directives == ()
    assert decision.rule_refs == ("AI-T0-NO-RWDR-CANDIDATE",)


def test_lexicographic_required_order_and_stable_tie_breaker() -> None:
    state = _state({})
    first = decide_next_interview_step(state, PACK, runtime_state=_runtime(state))
    second = decide_next_interview_step(state, PACK, runtime_state=_runtime(state))
    assert first == second
    assert first.directives[0].question_id == "rwdr.q.application_goal"
    assert first.directives[0].reason_code == "next_required_need"


def test_damage_pattern_does_not_infer_application_goal() -> None:
    state = _state({"schadensbild": "Leckage"})
    directive = _directive(state)
    assert directive.question_id == "rwdr.q.application_goal"
    assert directive.primary_need_id == "rwdr.application.goal"


def test_golden_case_missing_shaft_diameter_asks_for_shaft_diameter() -> None:
    values = _required_values()
    values.pop("wellendurchmesser")
    state = _state(values)
    directive = _directive(state)
    assert directive.type is InterviewDirectiveType.ASK
    assert directive.question_id == "rwdr.q.shaft_diameter"
    assert directive.primary_need_id == "rwdr.shaft.diameter"


def test_golden_case_missing_rotation_speed_asks_for_rotation_speed() -> None:
    values = _required_values()
    values.pop("drehzahl")
    state = _state(values)
    directive = _directive(state)
    assert directive.type is InterviewDirectiveType.ASK
    assert directive.question_id == "rwdr.q.rotation_speed"
    assert directive.primary_need_id == "rwdr.rotation.speed"


def test_unconfirmed_critical_fact_dominates_missing_required_need() -> None:
    state = _state(
        {"anwendungsziel": "new_design", "medium": "HLP 46"},
        confirmed=False,
    )
    directive = _directive(state)
    assert directive.type is InterviewDirectiveType.CONFIRM_CRITICAL_FACT
    assert directive.primary_need_id == "rwdr.application.goal"


def test_pending_question_is_created_continued_and_unique() -> None:
    state = _state({})
    runtime = _runtime(state)
    first = decide_next_interview_step(state, PACK, runtime_state=runtime)
    persisted = apply_state_patches(runtime, first, created_at="2026-07-13T20:00:00Z")
    active = [
        item
        for item in persisted.pending_questions
        if item.status is PendingQuestionStatus.ACTIVE
    ]
    assert len(active) == 1
    second = decide_next_interview_step(state, PACK, runtime_state=persisted)
    assert second.directives[0].pending_question_id == active[0].pending_question_id
    assert second.directives[0].reason_code == "continue_valid_pending_question"


def test_multiple_active_pending_questions_are_repaired_to_one_per_topic() -> None:
    state = _state({})
    runtime = _runtime(state)
    first = decide_next_interview_step(state, PACK, runtime_state=runtime)
    runtime = apply_state_patches(runtime, first, created_at="2026-07-13T20:00:00Z")
    canonical = runtime.pending_questions[0]
    duplicate = replace(canonical, pending_question_id="ipq_duplicate")
    corrupted = replace(runtime, pending_questions=(canonical, duplicate))

    repair = decide_next_interview_step(state, PACK, runtime_state=corrupted)
    repaired = apply_state_patches(
        corrupted,
        repair,
        created_at="2026-07-13T20:01:00Z",
    )

    active = [
        item
        for item in repaired.pending_questions
        if item.topic_id == canonical.topic_id
        and item.status is PendingQuestionStatus.ACTIVE
    ]
    assert len(active) == 1
    assert any(
        item.status is PendingQuestionStatus.SUPERSEDED
        and item.invalidated_reason == "single_active_question_invariant"
        for item in repaired.pending_questions
    )


def test_answered_pending_is_closed_and_next_required_need_selected() -> None:
    initial = _state({}, revision=1)
    runtime = _runtime(initial)
    first = decide_next_interview_step(initial, PACK, runtime_state=runtime)
    runtime = apply_state_patches(runtime, first, created_at="2026-07-13T20:00:00Z")
    answered = _state({"anwendungsziel": "new_design"}, revision=2)
    runtime = reconcile_runtime_facts(answered, PACK, runtime)
    decision = decide_next_interview_step(answered, PACK, runtime_state=runtime)
    assert decision.directives[0].question_id == "rwdr.q.medium_primary"
    assert any(
        patch.pending_question.status is PendingQuestionStatus.ANSWERED
        for patch in decision.state_patches
    )


def test_pending_question_from_future_state_revision_is_invalidated() -> None:
    state = _state({}, revision=1)
    runtime = _runtime(state)
    first = decide_next_interview_step(state, PACK, runtime_state=runtime)
    runtime = apply_state_patches(runtime, first, created_at="2026-07-13T20:00:00Z")
    future = replace(runtime.pending_questions[0], created_from_state_revision=2)
    runtime = replace(runtime, pending_questions=(future,))

    decision = decide_next_interview_step(state, PACK, runtime_state=runtime)

    assert decision.directives[0].question_id == "rwdr.q.application_goal"
    assert any(
        patch.pending_question.status is PendingQuestionStatus.INVALIDATED
        and patch.pending_question.invalidated_reason
        == "pending_from_future_state_revision"
        for patch in decision.state_patches
    )


def test_dependency_change_invalidates_pending_question() -> None:
    state = _state(_required_values(), revision=1)
    runtime = _runtime(state)
    # Build a pending question with a real dependency snapshot by temporarily asking a derived-like
    # catalog question through the shaft need.
    question = PACK.question("rwdr.q.shaft_diameter")
    assert question is not None
    first = decide_next_interview_step(
        _state({}, revision=1), PACK, runtime_state=_runtime(_state({}, revision=1))
    )
    pending = first.state_patches[-1].pending_question
    altered = replace(pending, dependency_snapshot={"rwdr.rotation.speed": "unknown"})
    runtime = replace(runtime, pending_questions=(altered,))
    decision = decide_next_interview_step(
        state, PACK, runtime_state=runtime, derived_facts=_velocity()
    )
    assert any(
        patch.pending_question.invalidated_reason == "dependency_snapshot_changed"
        for patch in decision.state_patches
    )


def test_corrected_rotation_speed_creates_auditable_conflict_and_priority() -> None:
    old = _state({"drehzahl": "1000 U/min"}, revision=1)
    runtime = _runtime(old)
    new = _state({"drehzahl": "1500 U/min"}, revision=2)
    runtime = reconcile_runtime_facts(new, PACK, runtime)
    assert runtime.conflicts[0].candidate_values == ("1000 U/min", "1500 U/min")
    directive = _directive(new, runtime)
    assert directive.type is InterviewDirectiveType.CLARIFY_CONFLICT
    assert directive.primary_need_id == "rwdr.rotation.speed"


def test_kernel_derived_velocity_is_system_validated_and_never_asked() -> None:
    state = _state(_required_values())
    runtime = _runtime(state)
    needs = resolve_need_states(state, PACK, runtime, derived_facts=_velocity())
    velocity = needs["rwdr.circumferential_speed"]
    assert velocity.status is NeedStatus.SATISFIED
    assert velocity.facts[0].origin.value == "kernel"
    assert velocity.facts[0].verification_status.value == "system_validated"
    decision = decide_next_interview_step(
        state, PACK, runtime_state=runtime, derived_facts=_velocity()
    )
    assert decision.directives[0].type is InterviewDirectiveType.COMPLETE
    assert all(
        directive.question_id != "rwdr.circumferential_speed"
        for directive in decision.directives
    )


def test_missing_kernel_result_escalates_instead_of_asking_user_for_velocity() -> None:
    state = _state(_required_values())
    directive = _directive(state, _runtime(state), derived=())
    assert directive.type is InterviewDirectiveType.ESCALATE
    assert directive.reason_code == "required_kernel_result_missing"


def test_pack_version_is_pinned_and_never_silently_migrated() -> None:
    state = _state({})
    runtime = replace(
        _runtime(state),
        pack_id=PACK.pack_id,
        pack_version="0.9.0",
    )
    directive = _directive(state, runtime)
    assert directive.type is InterviewDirectiveType.ESCALATE
    assert directive.reason_code == "pinned_pack_version_unavailable"


@pytest.mark.parametrize("field", ["haerte", "rauheit"])
def test_related_need_cannot_receive_primary_unobtainable_override(field: str) -> None:
    state = _state(_required_values())
    need_id = _need_id_for_field(field)
    runtime = replace(
        _runtime(state),
        unobtainable_overrides=(_unobtainable(need_id),),
    )
    with pytest.raises(InterviewContractError, match="not allowed"):
        decide_next_interview_step(
            state, PACK, runtime_state=runtime, derived_facts=_velocity()
        )


def test_pressure_boundary_fact_stays_documented_without_invented_material_limit() -> (
    None
):
    values = _required_values()
    values["druck"] = "0,6 bar"
    state = _state(values)
    needs = resolve_need_states(state, PACK, _runtime(state), derived_facts=_velocity())
    assert needs["rwdr.pressure.regime"].status is NeedStatus.SATISFIED


def _need_id_for_field(field: str) -> str:
    return next(need.need_id for need in PACK.needs if field in need.field_keys)


# -- compute_required_missing (case-intake fix, stage 2) --------------------------------
#
# Feeds CaseStateV2.required_missing, which the execution policy (orchestration/
# execution_policy.py) reads to decide ExecutionClass.D1/ModelTier.NONE and to render
# deterministic_response's "Für die technische Einordnung fehlen noch: {fields}." text.


def test_compute_required_missing_is_empty_for_unknown_scope() -> None:
    # No dichtungstyp/seal_type and no RWDR signal field at all -- classify_scope returns
    # "unknown". A blank/near-blank opener must never be reported as "missing fields": that
    # is exactly the case Stage 1's case_intake_invite route already handles separately.
    state = CaseStateV2(case_id="knowledge-only", revision=0)
    assert compute_required_missing(state, PACK) == ()


def test_compute_required_missing_is_empty_for_unsupported_scope() -> None:
    # An explicit, out-of-pack seal type (classify_scope == "unsupported") must not be
    # blocked on RWDR-specific required fields that do not even apply to it.
    state = CaseStateV2(
        case_id="glrd-case",
        revision=1,
        fields=(_field("dichtungstyp", "gleitringdichtung"),),
    )
    assert compute_required_missing(state, PACK) == ()


def test_compute_required_missing_is_empty_for_a_fully_specified_case() -> None:
    # _required_values() fills every askable required field. No derived_facts are (or ever
    # are) passed to compute_required_missing, so the kernel-derived, non-askable
    # rwdr.circumferential_speed need stays unresolved (BLOCKED) underneath -- proving that
    # exclusion of non-askable needs (no question_id) is load-bearing, not cosmetic: without
    # it, this fully-specified case would incorrectly still report something "missing".
    state = _state(_required_values())
    assert compute_required_missing(state, PACK) == ()


def test_compute_required_missing_lists_short_german_labels_in_curated_order() -> None:
    # Only medium + temperature are known (plus the implicit dichtungstyp="rwdr" the _state
    # fixture always injects) -- the rest of the required fields are open.
    state = _state({"medium": "Hydrauliköl HLP 46", "betriebstemperatur": "80 °C"})
    assert compute_required_missing(state, PACK) == (
        "Anwendungsziel",
        "Druck",
        "Wellendurchmesser",
        "Drehzahl",
    )


def test_compute_required_missing_accepts_legacy_distilled_temperature_key() -> None:
    state = _state({"medium": "Heißwasser", "temperatur": "90 °C"})

    assert "Betriebstemperatur" not in compute_required_missing(state, PACK)


def test_compute_required_missing_drops_a_field_once_it_is_answered() -> None:
    values = _required_values()
    values.pop("wellendurchmesser")
    state = _state(values)
    assert compute_required_missing(state, PACK) == ("Wellendurchmesser",)
    completed = _state(_required_values())
    assert compute_required_missing(completed, PACK) == ()


def test_compute_required_missing_feeds_the_deterministic_d1_response_text() -> None:
    from sealai_v2.orchestration.execution_policy import (
        ExecutionClass,
        ExecutionDecision,
        ModelTier,
        StreamingMode,
        VerificationMode,
        deterministic_response,
    )

    state = _state({"medium": "Hydrauliköl HLP 46", "betriebstemperatur": "80 °C"})
    missing = compute_required_missing(state, PACK)
    decision = ExecutionDecision(
        ExecutionClass.D1,
        ModelTier.NONE,
        None,
        VerificationMode.DETERMINISTIC,
        StreamingMode.ATOMIC,
        False,
        "deterministic_contract_clarification",
    )
    text = deterministic_response(
        decision, question="Bitte den RWDR-Fall fortsetzen", missing_fields=missing
    )
    assert text == (
        "Danke, den bisherigen Fallkontext habe ich berücksichtigt. Geht es um eine "
        "Neuauslegung, einen Austausch, eine Optimierung oder die Analyse eines Schadens? "
        "Das Ziel bestimmt, ob wir Bestand, Einbauraum oder Fehlerursachen zuerst betrachten."
    )
