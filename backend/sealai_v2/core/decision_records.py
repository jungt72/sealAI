"""Pure contracts for durable, reviewable sealing-case decisions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
import uuid

UNCERTAINTY_STATES = frozenset(
    {"bounded", "conditional", "conflicted", "not_sufficiently_supported"}
)
RISK_CLASSES = frozenset({"A", "B", "C", "D", "E"})
APPROVAL_STATUSES = frozenset({"approved", "rejected", "conditional"})


class CaseDecisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class CaseRecord:
    tenant_id: str
    case_id: str
    title: str
    status: str
    risk_class: str
    owner_subject: str
    current_revision: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class CaseSnapshot:
    id: str
    tenant_id: str
    case_id: str
    revision: int
    state: dict
    evidence_refs: tuple[str, ...]
    open_points: tuple[str, ...]
    content_sha256: str
    created_by: str
    created_at: str


@dataclass(frozen=True)
class DecisionRecord:
    id: str
    tenant_id: str
    case_id: str
    snapshot_id: str
    decision_type: str
    status: str
    conclusion: str
    rationale: str
    evidence_refs: tuple[str, ...]
    uncertainty: str
    responsibilities: dict
    approvals_required: tuple[str, ...]
    supersedes_decision_id: str
    created_by: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DecisionApproval:
    id: int
    tenant_id: str
    decision_id: str
    approval_kind: str
    status: str
    actor_subject: str
    actor_role: str
    scope: str
    note: str
    created_at: str


def snapshot_digest(
    *, state: dict, evidence_refs: tuple[str, ...], open_points: tuple[str, ...]
) -> str:
    payload = json.dumps(
        {
            "state": state,
            "evidence_refs": evidence_refs,
            "open_points": open_points,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


class InProcessCaseDecisionStore:
    def __init__(self) -> None:
        self.cases: dict[tuple[str, str], CaseRecord] = {}
        self.snapshots: dict[str, CaseSnapshot] = {}
        self.decisions: dict[str, DecisionRecord] = {}
        self.approvals: list[DecisionApproval] = []

    def create_case(
        self,
        *,
        tenant_id: str,
        title: str,
        risk_class: str,
        owner_subject: str,
        now: str,
    ) -> CaseRecord:
        if not tenant_id or not title.strip() or not owner_subject:
            raise CaseDecisionError("tenant, title, and owner are required")
        if risk_class not in RISK_CLASSES:
            raise CaseDecisionError("invalid risk class")
        record = CaseRecord(
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
        self.cases[(tenant_id, record.case_id)] = record
        return record

    def get_case(self, *, tenant_id: str, case_id: str) -> CaseRecord | None:
        return self.cases.get((tenant_id, case_id))

    def create_snapshot(
        self,
        *,
        tenant_id: str,
        case_id: str,
        state: dict,
        evidence_refs: tuple[str, ...],
        open_points: tuple[str, ...],
        actor: str,
        now: str,
    ) -> CaseSnapshot:
        case = self.get_case(tenant_id=tenant_id, case_id=case_id)
        if case is None:
            raise CaseDecisionError("case not found")
        if not state or not actor.strip():
            raise CaseDecisionError("snapshot state and actor are required")
        revision = case.current_revision + 1
        snapshot = CaseSnapshot(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            case_id=case_id,
            revision=revision,
            state=dict(state),
            evidence_refs=evidence_refs,
            open_points=open_points,
            content_sha256=snapshot_digest(
                state=state,
                evidence_refs=evidence_refs,
                open_points=open_points,
            ),
            created_by=actor,
            created_at=now,
        )
        self.snapshots[snapshot.id] = snapshot
        self.cases[(tenant_id, case_id)] = replace(
            case, current_revision=revision, updated_at=now
        )
        return snapshot

    def create_decision(
        self,
        *,
        tenant_id: str,
        case_id: str,
        snapshot_id: str,
        decision_type: str,
        conclusion: str,
        rationale: str,
        evidence_refs: tuple[str, ...],
        uncertainty: str,
        responsibilities: dict,
        approvals_required: tuple[str, ...],
        actor: str,
        now: str,
        supersedes_decision_id: str = "",
    ) -> DecisionRecord:
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
        snapshot = self.snapshots.get(snapshot_id)
        if (
            snapshot is None
            or snapshot.tenant_id != tenant_id
            or snapshot.case_id != case_id
        ):
            raise CaseDecisionError("snapshot not found in case")
        if not set(evidence_refs).issubset(set(snapshot.evidence_refs)):
            raise CaseDecisionError(
                "decision evidence must belong to the case snapshot"
            )
        if supersedes_decision_id:
            superseded = self.decisions.get(supersedes_decision_id)
            if (
                superseded is None
                or superseded.tenant_id != tenant_id
                or superseded.case_id != case_id
            ):
                raise CaseDecisionError("superseded decision not found in case")
        decision = DecisionRecord(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            case_id=case_id,
            snapshot_id=snapshot_id,
            decision_type=decision_type,
            status="review_required",
            conclusion=conclusion,
            rationale=rationale,
            evidence_refs=evidence_refs,
            uncertainty=uncertainty,
            responsibilities=dict(responsibilities),
            approvals_required=approvals_required,
            supersedes_decision_id=supersedes_decision_id,
            created_by=actor,
            created_at=now,
            updated_at=now,
        )
        self.decisions[decision.id] = decision
        return decision

    def add_approval(
        self,
        *,
        tenant_id: str,
        decision_id: str,
        status: str,
        actor_subject: str,
        actor_role: str,
        scope: str,
        note: str,
        now: str,
    ) -> DecisionApproval:
        if status not in APPROVAL_STATUSES:
            raise CaseDecisionError("invalid approval status")
        decision = self.decisions.get(decision_id)
        if decision is None or decision.tenant_id != tenant_id:
            raise CaseDecisionError("decision not found")
        _validate_approval(
            decision=decision,
            status=status,
            actor_subject=actor_subject,
            actor_role=actor_role,
            scope=scope,
            note=note,
        )
        if any(
            item.tenant_id == tenant_id
            and item.decision_id == decision_id
            and item.actor_subject == actor_subject
            for item in self.approvals
        ):
            raise CaseDecisionError("reviewer already recorded a decision review")
        approval = DecisionApproval(
            id=len(self.approvals) + 1,
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
        self.approvals.append(approval)
        statuses = tuple(
            item.status
            for item in self.approvals
            if item.tenant_id == tenant_id and item.decision_id == decision_id
        )
        self.decisions[decision_id] = replace(
            decision,
            status=_aggregate_review_status(statuses),
            updated_at=now,
        )
        return approval

    def case_bundle(self, *, tenant_id: str, case_id: str) -> dict:
        case = self.get_case(tenant_id=tenant_id, case_id=case_id)
        if case is None:
            raise CaseDecisionError("case not found")
        snapshots = tuple(
            item
            for item in self.snapshots.values()
            if item.tenant_id == tenant_id and item.case_id == case_id
        )
        decisions = tuple(
            item
            for item in self.decisions.values()
            if item.tenant_id == tenant_id and item.case_id == case_id
        )
        decision_ids = {item.id for item in decisions}
        approvals = tuple(
            item
            for item in self.approvals
            if item.tenant_id == tenant_id and item.decision_id in decision_ids
        )
        return {
            "case": case,
            "snapshots": snapshots,
            "decisions": decisions,
            "approvals": approvals,
        }


def _validate_decision(
    *,
    evidence_refs: tuple[str, ...],
    uncertainty: str,
    conclusion: str,
    rationale: str,
    decision_type: str,
    responsibilities: dict,
    approvals_required: tuple[str, ...],
    actor: str,
) -> None:
    if not evidence_refs or any(not reference.strip() for reference in evidence_refs):
        raise CaseDecisionError("a decision requires evidence references")
    if uncertainty not in UNCERTAINTY_STATES:
        raise CaseDecisionError("invalid uncertainty state")
    if not conclusion.strip() or not rationale.strip():
        raise CaseDecisionError("decision conclusion and rationale are required")
    if not decision_type.strip() or not actor.strip():
        raise CaseDecisionError("decision type and actor are required")
    if not responsibilities:
        raise CaseDecisionError("decision responsibilities are required")
    if not approvals_required or any(not item.strip() for item in approvals_required):
        raise CaseDecisionError("decision approval requirements are required")


def _validate_approval(
    *,
    decision: DecisionRecord,
    status: str,
    actor_subject: str,
    actor_role: str,
    scope: str,
    note: str,
) -> None:
    if not actor_subject.strip() or not actor_role.strip() or not scope.strip():
        raise CaseDecisionError("review actor, role, and scope are required")
    if actor_subject == decision.created_by:
        raise CaseDecisionError("a decision author cannot review their own decision")
    if status in {"rejected", "conditional"} and not note.strip():
        raise CaseDecisionError("conditional or rejected review requires a note")


def _aggregate_review_status(statuses: tuple[str, ...]) -> str:
    if "rejected" in statuses:
        return "rejected"
    if "conditional" in statuses:
        return "conditional"
    return "approved"
