from __future__ import annotations

from sqlalchemy import select

import sealai_v2.db.models  # noqa: F401
from sealai_v2.core.case_state import (
    CaseField,
    CaseFieldSource,
    CaseFieldStatus,
    CaseStateV2,
)
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.interview import (
    InProcessInterviewRepository,
    PostgresInterviewRepository,
)
from sealai_v2.db.models import V2InterviewShadowDecision
from sealai_v2.knowledge.domain_packs import load_rwdr_v1_pack
from sealai_v2.pipeline.adaptive_interview import AdaptiveInterviewService


def _state(*, revision: int, rpm: str = "1000 U/min") -> CaseStateV2:
    return CaseStateV2(
        case_id="rwdr-session",
        revision=revision,
        fields=(
            CaseField(
                key="dichtungstyp",
                value="rwdr",
                status=CaseFieldStatus.CONFIRMED,
                source=CaseFieldSource(kind="user_form"),
            ),
            CaseField(
                key="drehzahl",
                value=rpm,
                status=CaseFieldStatus.CONFIRMED,
                source=CaseFieldSource(kind="user_form"),
            ),
        ),
    )


def test_postgres_repository_persists_pending_and_privacy_safe_shadow(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'interview.db'}")
    Base.metadata.create_all(engine)
    sf = make_sessionmaker(engine)
    repo = PostgresInterviewRepository(sf)
    service = AdaptiveInterviewService(pack=load_rwdr_v1_pack(), repository=repo)

    evaluation = service.evaluate(
        tenant_id="tenant-a",
        session_id="rwdr-session",
        case_state=_state(revision=1),
        legacy_answer_text="**Noch erforderlich**\n- Welches Medium liegt an?",
        persist_shadow=True,
    )

    assert evaluation is not None
    stored = repo.load(
        tenant_id="tenant-a", session_id="rwdr-session", topic_id="rwdr.default"
    )
    assert stored.pack_id == "rwdr.v1"
    assert stored.pack_version == "1.0.0"
    assert stored.state_revision == 1
    assert (
        len(
            [item for item in stored.pending_questions if item.status.value == "active"]
        )
        == 1
    )

    with sf() as session:
        shadow = session.scalar(select(V2InterviewShadowDecision))
        assert shadow is not None
        assert shadow.case_reference != "rwdr-session"
        assert len(shadow.case_reference) == 24
        assert shadow.legacy_question_fingerprint is not None
        assert "Medium" not in shadow.legacy_question_fingerprint
        assert shadow.completeness_json["additional_llm_calls_by_controller"] == 0


def test_correction_is_retained_as_conflict_across_revisions(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'conflict.db'}")
    Base.metadata.create_all(engine)
    sf = make_sessionmaker(engine)
    repo = PostgresInterviewRepository(sf)
    service = AdaptiveInterviewService(pack=load_rwdr_v1_pack(), repository=repo)

    service.evaluate(
        tenant_id="tenant-a",
        session_id="rwdr-session",
        case_state=_state(revision=1, rpm="1000 U/min"),
        persist_shadow=False,
    )
    evaluation = service.evaluate(
        tenant_id="tenant-a",
        session_id="rwdr-session",
        case_state=_state(revision=2, rpm="1500 U/min"),
        persist_shadow=True,
    )

    assert evaluation is not None
    assert evaluation.decision.directives[0].type.value == "clarify_conflict"
    stored = repo.load(
        tenant_id="tenant-a", session_id="rwdr-session", topic_id="rwdr.default"
    )
    assert stored.conflicts[0].candidate_values == ("1000 U/min", "1500 U/min")
    assert stored.conflicts[0].created_from_state_revision == 2


def test_clear_removes_pending_state_but_retains_hashed_audit_log(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'clear.db'}")
    Base.metadata.create_all(engine)
    sf = make_sessionmaker(engine)
    repo = PostgresInterviewRepository(sf)
    service = AdaptiveInterviewService(pack=load_rwdr_v1_pack(), repository=repo)
    service.evaluate(
        tenant_id="tenant-a",
        session_id="rwdr-session",
        case_state=_state(revision=1),
        persist_shadow=True,
    )

    service.clear(tenant_id="tenant-a", session_id="rwdr-session")

    state = repo.load(
        tenant_id="tenant-a", session_id="rwdr-session", topic_id="rwdr.default"
    )
    assert state.pack_id == "legacy_unversioned"
    with sf() as session:
        assert session.scalar(select(V2InterviewShadowDecision)) is not None


def test_out_of_scope_case_is_decided_but_not_persisted_as_rwdr_shadow() -> None:
    repo = InProcessInterviewRepository()
    service = AdaptiveInterviewService(pack=load_rwdr_v1_pack(), repository=repo)
    case_state = CaseStateV2(
        case_id="glrd-session",
        revision=1,
        fields=(
            CaseField(
                key="dichtungstyp",
                value="gleitringdichtung",
                status=CaseFieldStatus.CONFIRMED,
                source=CaseFieldSource(kind="user_form"),
            ),
        ),
    )

    evaluation = service.evaluate(
        tenant_id="tenant-a",
        session_id="glrd-session",
        case_state=case_state,
        persist_shadow=True,
    )

    assert evaluation is not None
    assert evaluation.decision.directives[0].reason_code == "out_of_scope_primary_case"
    assert repo.shadow_records() == ()
    stored = repo.load(
        tenant_id="tenant-a", session_id="glrd-session", topic_id="rwdr.default"
    )
    assert stored.pack_id == "legacy_unversioned"
