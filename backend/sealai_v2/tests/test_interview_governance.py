from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from sealai_v2.core.case_state import CaseField, CaseFieldSource, CaseStateV2
from sealai_v2.core.interview.contracts import (
    DomainPack,
    InterviewConflict,
    InterviewRuntimeState,
    NeedState,
    NeedDefinition,
    NeedStatus,
    UnobtainableOverrideAudit,
)
from sealai_v2.core.interview.policy import (
    InterviewContractError,
    decide_next_interview_step,
    reconcile_runtime_facts,
    resolve_need_states,
)
from sealai_v2.db.interview import _runtime, _state_values
from sealai_v2.knowledge.domain_packs import (
    DomainPackValidationError,
    _parse,
    load_rwdr_v1_pack,
)

PACK = load_rwdr_v1_pack()


def _record(need_id: str) -> UnobtainableOverrideAudit:
    return UnobtainableOverrideAudit(
        need_id=need_id,
        reason="value cannot be obtained after documented attempt",
        actor_ref="user:owner-1",
        created_at="2026-07-16T11:00:00Z",
        pack_version=PACK.version,
        policy_version=PACK.policy_version,
    )


def _state() -> CaseStateV2:
    return CaseStateV2(
        case_id="case-1",
        revision=1,
        fields=(
            CaseField(
                key="dichtungstyp",
                value="rwdr",
                source=CaseFieldSource(kind="user_form"),
            ),
        ),
    )


def test_documented_and_completion_satisfying_are_orthogonal() -> None:
    blocked = NeedState("need-1", NeedStatus.BLOCKED)
    assert blocked.is_documented is True
    assert blocked.is_completion_satisfying is False
    assert NeedState("need-1", NeedStatus.UNOBTAINABLE).is_completion_satisfying is True


def test_blocked_required_need_can_never_produce_complete() -> None:
    pack = DomainPack(
        pack_id="test-pack",
        version="1",
        question_catalog_version="1",
        case_schema_version=2,
        policy_version="1",
        stop_profile="required",
        supported_seal_types=("rwdr",),
        unsupported_primary_types=(),
        rwdr_signal_fields=(),
        needs=(
            NeedDefinition(
                need_id="inactive-dependency",
                field_keys=(),
                active=False,
                required=False,
                criticality="quality",
                question_id=None,
            ),
            NeedDefinition(
                need_id="required-kernel",
                field_keys=(),
                active=True,
                required=True,
                criticality="quality",
                question_id=None,
                dependency_refs=("inactive-dependency",),
                derived_calc_id="missing-calc",
            ),
        ),
        questions=(),
    )
    decision = decide_next_interview_step(_state(), pack)
    assert decision.directives[0].type.value == "escalate"
    assert (
        decision.directives[0].reason_code == "required_need_not_completion_satisfying"
    )


def test_active_conflict_dominates_valid_unobtainable_override() -> None:
    state = _state()
    need_id = "rwdr.medium.primary"
    runtime = reconcile_runtime_facts(state, PACK, InterviewRuntimeState())
    runtime = replace(
        runtime,
        unobtainable_overrides=(_record(need_id),),
        conflicts=(
            InterviewConflict(
                conflict_id="conflict-1",
                field_key="medium",
                need_id=need_id,
                candidate_values=("oil", "water"),
                created_from_state_revision=1,
            ),
        ),
    )
    assert (
        resolve_need_states(state, PACK, runtime)[need_id].status
        is NeedStatus.CONFLICTED
    )


def test_primary_override_does_not_override_related_needs() -> None:
    state = _state()
    primary = "rwdr.medium.primary"
    related = PACK.question("rwdr.q.medium_primary").related_need_ids[0]
    runtime = reconcile_runtime_facts(state, PACK, InterviewRuntimeState())
    runtime = replace(runtime, unobtainable_overrides=(_record(primary),))
    states = resolve_need_states(state, PACK, runtime)
    assert states[primary].status is NeedStatus.UNOBTAINABLE
    assert states[related].status is not NeedStatus.UNOBTAINABLE
    assert PACK.allows_unobtainable(related) is False
    with pytest.raises(InterviewContractError, match="not allowed"):
        resolve_need_states(
            state,
            PACK,
            replace(runtime, unobtainable_overrides=(_record(related),)),
        )


def test_typed_override_persistence_round_trip_and_legacy_rejection() -> None:
    state = InterviewRuntimeState(
        unobtainable_overrides=(_record("rwdr.medium.primary"),)
    )
    encoded = _state_values(state, updated_at="2026-07-16T11:01:00Z")
    base = {
        "topic_id": "rwdr.default",
        "pack_id": PACK.pack_id,
        "pack_version": PACK.version,
        "policy_version": PACK.policy_version,
        "question_catalog_version": PACK.question_catalog_version,
        "case_schema_version": 2,
        "state_revision": 0,
        "pending_questions_json": [],
        "conflicts_json": [],
        "fact_snapshots_json": [],
        "calculator_version_refs_json": [],
    }
    restored = _runtime(SimpleNamespace(**{**base, **encoded}))
    assert restored.unobtainable_overrides == state.unobtainable_overrides
    with pytest.raises(ValueError, match="legacy untyped"):
        _runtime(
            SimpleNamespace(
                **base,
                need_status_overrides_json={"rwdr.medium.primary": "unobtainable"},
            )
        )


def test_generic_status_override_cannot_be_constructed() -> None:
    with pytest.raises(TypeError, match="typed audit records"):
        InterviewRuntimeState(
            unobtainable_overrides=(
                {"need_id": "rwdr.medium.primary", "status": "satisfied"},
            )  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("section", "index", "key"),
    [
        ("needs", 0, "active"),
        ("needs", 0, "required"),
        ("needs", 0, "conflict_sensitive"),
        ("questions", 0, "allowed_unknown"),
        ("questions", 0, "allowed_unobtainable"),
    ],
)
def test_domain_pack_boolean_strings_are_rejected(section, index, key) -> None:
    path = Path(__file__).parents[1] / "knowledge" / "domain_packs" / "rwdr.v1.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    bad = copy.deepcopy(raw)
    bad[section][index][key] = "false"
    with pytest.raises(DomainPackValidationError, match="JSON boolean"):
        _parse(bad)


@pytest.mark.parametrize(
    "created_at",
    ["2026-07-16T11:00:00", "2026-07-16T13:00:00+02:00", "not-a-time"],
)
def test_override_requires_utc_audit_timestamp(created_at) -> None:
    with pytest.raises(ValueError, match="timestamp|UTC"):
        replace(_record("rwdr.medium.primary"), created_at=created_at)
