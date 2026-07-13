"""Persistence adapters for pending questions and privacy-safe shadow decisions."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from threading import RLock

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from sealai_v2.core.interview.contracts import (
    FactSnapshot,
    InterviewConflict,
    InterviewDirectiveType,
    InterviewRuntimeState,
    InterviewShadowRecord,
    NeedStatus,
    PendingQuestion,
    PendingQuestionStatus,
)
from sealai_v2.db.models import V2InterviewShadowDecision, V2InterviewState
from sealai_v2.security.tenant import TenantContext, require_tenant


class StaleInterviewState(RuntimeError):
    pass


def _pending(raw: dict) -> PendingQuestion:
    return PendingQuestion(
        pending_question_id=raw["pending_question_id"],
        question_id=raw["question_id"],
        primary_need_id=raw["primary_need_id"],
        related_need_ids=tuple(raw.get("related_need_ids", ())),
        topic_id=raw["topic_id"],
        pack_id=raw["pack_id"],
        pack_version=raw["pack_version"],
        policy_version=raw["policy_version"],
        created_at=raw.get("created_at", ""),
        created_from_state_revision=int(raw["created_from_state_revision"]),
        dependency_snapshot=dict(raw.get("dependency_snapshot", {})),
        status=PendingQuestionStatus(raw.get("status", "active")),
        invalidated_reason=raw.get("invalidated_reason", ""),
        answered_at=raw.get("answered_at", ""),
        directive_type=InterviewDirectiveType(raw.get("directive_type", "ask")),
    )


def _conflict(raw: dict) -> InterviewConflict:
    return InterviewConflict(
        conflict_id=raw["conflict_id"],
        field_key=raw["field_key"],
        need_id=raw["need_id"],
        candidate_values=tuple(raw.get("candidate_values", ())),
        created_from_state_revision=int(raw["created_from_state_revision"]),
        status=raw.get("status", "active"),
        reason_code=raw.get("reason_code", "corrected_decision_critical_fact"),
    )


def _snapshot(raw: dict) -> FactSnapshot:
    return FactSnapshot(
        field_key=raw["field_key"],
        value=raw["value"],
        unit=raw.get("unit", ""),
        state_revision=int(raw["state_revision"]),
        status=raw.get("status", "stated"),
    )


def _runtime(row: V2InterviewState) -> InterviewRuntimeState:
    return InterviewRuntimeState(
        topic_id=row.topic_id,
        pack_id=row.pack_id,
        pack_version=row.pack_version,
        policy_version=row.policy_version,
        question_catalog_version=row.question_catalog_version,
        case_schema_version=row.case_schema_version,
        state_revision=row.state_revision,
        pending_questions=tuple(_pending(item) for item in row.pending_questions_json),
        need_status_overrides={
            key: NeedStatus(value)
            for key, value in row.need_status_overrides_json.items()
        },
        conflicts=tuple(_conflict(item) for item in row.conflicts_json),
        fact_snapshots=tuple(_snapshot(item) for item in row.fact_snapshots_json),
        calculator_version_refs=tuple(row.calculator_version_refs_json),
    )


def _jsonable(value):
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value.value if hasattr(value, "value") else value


def _state_values(state: InterviewRuntimeState, *, updated_at: str) -> dict:
    return {
        "pack_id": state.pack_id,
        "pack_version": state.pack_version,
        "policy_version": state.policy_version,
        "question_catalog_version": state.question_catalog_version,
        "case_schema_version": state.case_schema_version,
        "state_revision": state.state_revision,
        "pending_questions_json": _jsonable(
            [asdict(item) for item in state.pending_questions]
        ),
        "need_status_overrides_json": {
            key: value.value for key, value in state.need_status_overrides.items()
        },
        "conflicts_json": _jsonable([asdict(item) for item in state.conflicts]),
        "fact_snapshots_json": _jsonable(
            [asdict(item) for item in state.fact_snapshots]
        ),
        "calculator_version_refs_json": list(state.calculator_version_refs),
        "updated_at": updated_at,
    }


class InProcessInterviewRepository:
    def __init__(self) -> None:
        self._states: dict[tuple[str, str, str], InterviewRuntimeState] = {}
        self._logs: list[InterviewShadowRecord] = []
        self._lock = RLock()

    def load(
        self, *, tenant_id: str, session_id: str, topic_id: str
    ) -> InterviewRuntimeState:
        require_tenant(TenantContext(tenant_id))
        with self._lock:
            return self._states.get(
                (tenant_id, session_id, topic_id),
                InterviewRuntimeState(topic_id=topic_id),
            )

    def save_evaluation(
        self,
        *,
        tenant_id: str,
        session_id: str,
        state: InterviewRuntimeState,
        updated_at: str,
        shadow: InterviewShadowRecord | None,
    ) -> None:
        require_tenant(TenantContext(tenant_id))
        key = (tenant_id, session_id, state.topic_id)
        with self._lock:
            current = self._states.get(key)
            if current is not None and current.state_revision > state.state_revision:
                raise StaleInterviewState("newer interview state is already persisted")
            self._states[key] = state
            if shadow is not None:
                self._logs.append(shadow)

    def shadow_records(self) -> tuple[InterviewShadowRecord, ...]:
        with self._lock:
            return tuple(self._logs)

    def clear(self, *, tenant_id: str, session_id: str) -> None:
        require_tenant(TenantContext(tenant_id))
        with self._lock:
            for key in tuple(self._states):
                if key[:2] == (tenant_id, session_id):
                    del self._states[key]


class PostgresInterviewRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def load(
        self, *, tenant_id: str, session_id: str, topic_id: str
    ) -> InterviewRuntimeState:
        require_tenant(TenantContext(tenant_id))
        with self._sf() as session:
            row = session.get(V2InterviewState, (tenant_id, session_id, topic_id))
            return (
                _runtime(row)
                if row is not None
                else InterviewRuntimeState(topic_id=topic_id)
            )

    def save_evaluation(
        self,
        *,
        tenant_id: str,
        session_id: str,
        state: InterviewRuntimeState,
        updated_at: str,
        shadow: InterviewShadowRecord | None,
    ) -> None:
        require_tenant(TenantContext(tenant_id))
        with self._sf.begin() as session:
            row = session.scalar(
                select(V2InterviewState)
                .where(
                    V2InterviewState.tenant_id == tenant_id,
                    V2InterviewState.session_id == session_id,
                    V2InterviewState.topic_id == state.topic_id,
                )
                .with_for_update()
            )
            if row is not None and row.state_revision > state.state_revision:
                raise StaleInterviewState("newer interview state is already persisted")
            values = _state_values(state, updated_at=updated_at)
            if row is None:
                session.add(
                    V2InterviewState(
                        tenant_id=tenant_id,
                        session_id=session_id,
                        topic_id=state.topic_id,
                        **values,
                    )
                )
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            if shadow is not None:
                session.add(
                    V2InterviewShadowDecision(
                        id=shadow.record_id or uuid.uuid4().hex,
                        tenant_id=shadow.tenant_id,
                        case_reference=shadow.case_reference,
                        state_revision=shadow.state_revision,
                        pack_id=shadow.pack_id,
                        pack_version=shadow.pack_version,
                        policy_version=shadow.policy_version,
                        legacy_question_present=shadow.legacy_question_present,
                        legacy_question_fingerprint=shadow.legacy_question_fingerprint,
                        controller_directive=shadow.controller_directive,
                        controller_question_id=shadow.controller_question_id,
                        rule_refs_json=list(shadow.rule_refs),
                        divergence_type=shadow.divergence_type,
                        decision_duration_ms=shadow.decision_duration_ms,
                        completeness_json=dict(shadow.completeness),
                        created_at=shadow.created_at,
                    )
                )

    def clear(self, *, tenant_id: str, session_id: str) -> None:
        require_tenant(TenantContext(tenant_id))
        with self._sf.begin() as session:
            session.execute(
                delete(V2InterviewState).where(
                    V2InterviewState.tenant_id == tenant_id,
                    V2InterviewState.session_id == session_id,
                )
            )
