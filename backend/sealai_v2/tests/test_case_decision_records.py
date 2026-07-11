from __future__ import annotations

import pytest

import sealai_v2.db.models  # noqa: F401
from sealai_v2.core.decision_records import CaseDecisionError
from sealai_v2.db.case_decisions import PostgresCaseDecisionStore
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker

NOW = "2026-07-11T20:00:00Z"


def _store(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'decisions.db'}")
    Base.metadata.create_all(engine)
    return PostgresCaseDecisionStore(make_sessionmaker(engine))


def test_case_snapshot_decision_and_approval_are_tenant_scoped(tmp_path) -> None:
    store = _store(tmp_path)
    case = store.create_case(
        tenant_id="tenant-a",
        title="RWDR Heißlauf",
        risk_class="D",
        owner_subject="engineer-a",
        now=NOW,
    )
    snapshot = store.create_snapshot(
        tenant_id="tenant-a",
        case_id=case.case_id,
        state={"seal_type": "RWDR", "temperature_c": 140},
        evidence_refs=("claim:123",),
        open_points=("shaft hardness",),
        actor="engineer-a",
        now=NOW,
    )
    decision = store.create_decision(
        tenant_id="tenant-a",
        case_id=case.case_id,
        snapshot_id=snapshot.id,
        decision_type="technical_orientation",
        conclusion="Further manufacturer validation required",
        rationale="Temperature and shaft hardness remain coupled constraints.",
        evidence_refs=("claim:123",),
        uncertainty="conditional",
        responsibilities={"manufacturer": "component validation"},
        approvals_required=("technical_review",),
        actor="engineer-a",
        now=NOW,
    )
    approval = store.add_approval(
        tenant_id="tenant-a",
        decision_id=decision.id,
        status="approved",
        actor_subject="reviewer-a",
        actor_role="decision_reviewer",
        scope="technical review only",
        note="Evidence trace checked",
        now=NOW,
    )

    assert snapshot.revision == 1
    assert len(snapshot.content_sha256) == 64
    assert decision.status == "review_required"
    assert approval.approval_kind == "technical_review"
    bundle = store.case_bundle(tenant_id="tenant-a", case_id=case.case_id)
    assert bundle["decisions"][0].status == "approved"
    with pytest.raises(CaseDecisionError, match="case not found"):
        store.case_bundle(tenant_id="tenant-b", case_id=case.case_id)


def test_decision_without_evidence_is_rejected(tmp_path) -> None:
    store = _store(tmp_path)
    case = store.create_case(
        tenant_id="tenant-a",
        title="Case",
        risk_class="C",
        owner_subject="user-a",
        now=NOW,
    )
    snapshot = store.create_snapshot(
        tenant_id="tenant-a",
        case_id=case.case_id,
        state={"topic": "test"},
        evidence_refs=(),
        open_points=(),
        actor="user-a",
        now=NOW,
    )

    with pytest.raises(CaseDecisionError, match="requires evidence"):
        store.create_decision(
            tenant_id="tenant-a",
            case_id=case.case_id,
            snapshot_id=snapshot.id,
            decision_type="orientation",
            conclusion="x",
            rationale="y",
            evidence_refs=(),
            uncertainty="not_sufficiently_supported",
            responsibilities={},
            approvals_required=("technical_review",),
            actor="user-a",
            now=NOW,
        )


def test_author_cannot_review_own_decision(tmp_path) -> None:
    store = _store(tmp_path)
    case = store.create_case(
        tenant_id="tenant-a",
        title="Case",
        risk_class="C",
        owner_subject="engineer-a",
        now=NOW,
    )
    snapshot = store.create_snapshot(
        tenant_id="tenant-a",
        case_id=case.case_id,
        state={"seal_type": "RWDR"},
        evidence_refs=("claim:123",),
        open_points=(),
        actor="engineer-a",
        now=NOW,
    )
    decision = store.create_decision(
        tenant_id="tenant-a",
        case_id=case.case_id,
        snapshot_id=snapshot.id,
        decision_type="technical_orientation",
        conclusion="Review required",
        rationale="Evidence must be checked independently.",
        evidence_refs=("claim:123",),
        uncertainty="conditional",
        responsibilities={"manufacturer": "component validation"},
        approvals_required=("technical_review",),
        actor="engineer-a",
        now=NOW,
    )

    with pytest.raises(CaseDecisionError, match="own decision"):
        store.add_approval(
            tenant_id="tenant-a",
            decision_id=decision.id,
            status="approved",
            actor_subject="engineer-a",
            actor_role="decision_reviewer",
            scope="technical review only",
            note="",
            now=NOW,
        )
