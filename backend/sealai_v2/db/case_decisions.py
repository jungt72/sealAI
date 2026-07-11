"""Postgres system-of-record for cases, snapshots, decisions, and approvals."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.core.decision_records import (
    APPROVAL_STATUSES,
    RISK_CLASSES,
    CaseDecisionError,
    CaseRecord,
    CaseSnapshot,
    DecisionApproval,
    DecisionRecord,
    _validate_decision,
    _aggregate_review_status,
    _validate_approval,
    snapshot_digest,
)
from sealai_v2.db.models import (
    V2CaseRecord,
    V2CaseSnapshot,
    V2DecisionApproval,
    V2DecisionRecord,
)


def _case(row: V2CaseRecord) -> CaseRecord:
    return CaseRecord(
        tenant_id=row.tenant_id,
        case_id=row.case_id,
        title=row.title,
        status=row.status,
        risk_class=row.risk_class,
        owner_subject=row.owner_subject,
        current_revision=row.current_revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _snapshot(row: V2CaseSnapshot) -> CaseSnapshot:
    return CaseSnapshot(
        id=row.id,
        tenant_id=row.tenant_id,
        case_id=row.case_id,
        revision=row.revision,
        state=dict(row.state_json or {}),
        evidence_refs=tuple(row.evidence_refs_json or ()),
        open_points=tuple(row.open_points_json or ()),
        content_sha256=row.content_sha256,
        created_by=row.created_by,
        created_at=row.created_at,
    )


def _decision(row: V2DecisionRecord) -> DecisionRecord:
    return DecisionRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        case_id=row.case_id,
        snapshot_id=row.snapshot_id,
        decision_type=row.decision_type,
        status=row.status,
        conclusion=row.conclusion,
        rationale=row.rationale,
        evidence_refs=tuple(row.evidence_refs_json or ()),
        uncertainty=row.uncertainty,
        responsibilities=dict(row.responsibilities_json or {}),
        approvals_required=tuple(row.approvals_required_json or ()),
        supersedes_decision_id=row.supersedes_decision_id or "",
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _approval(row: V2DecisionApproval) -> DecisionApproval:
    return DecisionApproval(
        id=row.id,
        tenant_id=row.tenant_id,
        decision_id=row.decision_id,
        approval_kind=row.approval_kind,
        status=row.status,
        actor_subject=row.actor_subject,
        actor_role=row.actor_role,
        scope=row.scope,
        note=row.note,
        created_at=row.created_at,
    )


class PostgresCaseDecisionStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def create_case(self, *, tenant_id, title, risk_class, owner_subject, now):
        if not tenant_id or not title.strip() or not owner_subject:
            raise CaseDecisionError("tenant, title, and owner are required")
        if risk_class not in RISK_CLASSES:
            raise CaseDecisionError("invalid risk class")
        row = V2CaseRecord(
            tenant_id=tenant_id,
            case_id=str(uuid.uuid4()),
            title=title.strip(),
            status="active",
            risk_class=risk_class,
            owner_subject=owner_subject,
            current_revision=0,
            created_at=now,
            updated_at=now,
        )
        with self._sf() as session:
            session.add(row)
            session.commit()
            return _case(row)

    def get_case(self, *, tenant_id, case_id):
        with self._sf() as session:
            row = session.get(V2CaseRecord, (tenant_id, case_id))
            return _case(row) if row is not None else None

    def create_snapshot(
        self,
        *,
        tenant_id,
        case_id,
        state,
        evidence_refs,
        open_points,
        actor,
        now,
    ):
        with self._sf() as session:
            case = session.scalar(
                select(V2CaseRecord)
                .where(
                    V2CaseRecord.tenant_id == tenant_id,
                    V2CaseRecord.case_id == case_id,
                )
                .with_for_update()
            )
            if case is None:
                raise CaseDecisionError("case not found")
            if not state or not actor.strip():
                raise CaseDecisionError("snapshot state and actor are required")
            revision = case.current_revision + 1
            row = V2CaseSnapshot(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                case_id=case_id,
                revision=revision,
                state_json=dict(state),
                evidence_refs_json=list(evidence_refs),
                open_points_json=list(open_points),
                content_sha256=snapshot_digest(
                    state=state,
                    evidence_refs=evidence_refs,
                    open_points=open_points,
                ),
                created_by=actor,
                created_at=now,
            )
            case.current_revision = revision
            case.updated_at = now
            session.add(row)
            session.commit()
            return _snapshot(row)

    def create_decision(
        self,
        *,
        tenant_id,
        case_id,
        snapshot_id,
        decision_type,
        conclusion,
        rationale,
        evidence_refs,
        uncertainty,
        responsibilities,
        approvals_required,
        actor,
        now,
        supersedes_decision_id="",
    ):
        _validate_decision(
            evidence_refs=evidence_refs,
            uncertainty=uncertainty,
            conclusion=conclusion,
            rationale=rationale,
            decision_type=decision_type,
            responsibilities=responsibilities,
            approvals_required=approvals_required,
            actor=actor,
        )
        with self._sf() as session:
            snapshot = session.scalar(
                select(V2CaseSnapshot).where(
                    V2CaseSnapshot.id == snapshot_id,
                    V2CaseSnapshot.tenant_id == tenant_id,
                    V2CaseSnapshot.case_id == case_id,
                )
            )
            if snapshot is None:
                raise CaseDecisionError("snapshot not found in case")
            if not set(evidence_refs).issubset(set(snapshot.evidence_refs_json or ())):
                raise CaseDecisionError(
                    "decision evidence must belong to the case snapshot"
                )
            if supersedes_decision_id:
                superseded = session.scalar(
                    select(V2DecisionRecord).where(
                        V2DecisionRecord.id == supersedes_decision_id,
                        V2DecisionRecord.tenant_id == tenant_id,
                        V2DecisionRecord.case_id == case_id,
                    )
                )
                if superseded is None:
                    raise CaseDecisionError("superseded decision not found in case")
            row = V2DecisionRecord(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                case_id=case_id,
                snapshot_id=snapshot_id,
                decision_type=decision_type,
                status="review_required",
                conclusion=conclusion,
                rationale=rationale,
                evidence_refs_json=list(evidence_refs),
                uncertainty=uncertainty,
                responsibilities_json=dict(responsibilities),
                approvals_required_json=list(approvals_required),
                supersedes_decision_id=supersedes_decision_id or None,
                created_by=actor,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.commit()
            return _decision(row)

    def add_approval(
        self,
        *,
        tenant_id,
        decision_id,
        status,
        actor_subject,
        actor_role,
        scope,
        note,
        now,
    ):
        if status not in APPROVAL_STATUSES:
            raise CaseDecisionError("invalid approval status")
        with self._sf() as session:
            decision = session.scalar(
                select(V2DecisionRecord)
                .where(
                    V2DecisionRecord.id == decision_id,
                    V2DecisionRecord.tenant_id == tenant_id,
                )
                .with_for_update()
            )
            if decision is None:
                raise CaseDecisionError("decision not found")
            domain_decision = _decision(decision)
            _validate_approval(
                decision=domain_decision,
                status=status,
                actor_subject=actor_subject,
                actor_role=actor_role,
                scope=scope,
                note=note,
            )
            existing = session.scalars(
                select(V2DecisionApproval).where(
                    V2DecisionApproval.tenant_id == tenant_id,
                    V2DecisionApproval.decision_id == decision_id,
                )
            ).all()
            if any(row.actor_subject == actor_subject for row in existing):
                raise CaseDecisionError("reviewer already recorded a decision review")
            row = V2DecisionApproval(
                tenant_id=tenant_id,
                decision_id=decision_id,
                approval_kind="technical_review",
                status=status,
                actor_subject=actor_subject,
                actor_role=actor_role,
                scope=scope,
                note=note,
                created_at=now,
            )
            decision.status = _aggregate_review_status(
                tuple([*(item.status for item in existing), status])
            )
            decision.updated_at = now
            session.add(row)
            session.commit()
            return _approval(row)

    def case_bundle(self, *, tenant_id, case_id):
        with self._sf() as session:
            case = session.get(V2CaseRecord, (tenant_id, case_id))
            if case is None:
                raise CaseDecisionError("case not found")
            snapshots = session.scalars(
                select(V2CaseSnapshot)
                .where(
                    V2CaseSnapshot.tenant_id == tenant_id,
                    V2CaseSnapshot.case_id == case_id,
                )
                .order_by(V2CaseSnapshot.revision)
            ).all()
            decisions = session.scalars(
                select(V2DecisionRecord)
                .where(
                    V2DecisionRecord.tenant_id == tenant_id,
                    V2DecisionRecord.case_id == case_id,
                )
                .order_by(V2DecisionRecord.created_at)
            ).all()
            decision_ids = [row.id for row in decisions]
            approvals = (
                session.scalars(
                    select(V2DecisionApproval)
                    .where(
                        V2DecisionApproval.tenant_id == tenant_id,
                        V2DecisionApproval.decision_id.in_(decision_ids),
                    )
                    .order_by(V2DecisionApproval.id)
                ).all()
                if decision_ids
                else []
            )
            return {
                "case": _case(case),
                "snapshots": tuple(_snapshot(row) for row in snapshots),
                "decisions": tuple(_decision(row) for row in decisions),
                "approvals": tuple(_approval(row) for row in approvals),
            }
