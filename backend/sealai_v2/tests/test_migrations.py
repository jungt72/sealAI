from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import inspect, select

import sealai_v2.db.models  # noqa: F401
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.migrate import _upgrade_engine, migration_status, up, validate_schema
from sealai_v2.db.models import (
    V2HerstellerPartner,
    V2InterviewShadowDecision,
    V2InterviewState,
    V2ManufacturerCapabilityProfile,
    V2ManufacturerCapabilityReview,
)


def test_alembic_upgrade_creates_fresh_schema(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'fresh.db'}")

    tables = set(up(engine))

    assert set(Base.metadata.tables) <= tables
    assert "alembic_version" in tables
    current, head = migration_status(engine)
    assert current == head == "20260718_0017"
    indexes = {
        item["name"]
        for item in inspect(engine).get_indexes("v2_interview_shadow_decisions")
    }
    assert "ix_v2_interview_shadow_scope_created" in indexes
    validate_schema(engine)


def test_rwdr_pack_cutover_clears_only_1_0_0_ephemeral_state(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'rwdr-cutover.db'}")
    _upgrade_engine(engine, "20260713_0009")
    sf = make_sessionmaker(engine)
    base = {
        "tenant_id": "tenant-a",
        "topic_id": "rwdr.default",
        "pack_id": "rwdr.v1",
        "policy_version": "adaptive-interview.lexicographic.1.0.0",
        "case_schema_version": 2,
        "state_revision": 1,
        "pending_questions_json": [],
        "need_status_overrides_json": {},
        "conflicts_json": [],
        "fact_snapshots_json": [],
        "calculator_version_refs_json": [],
        "updated_at": "2026-07-14T10:00:00Z",
    }
    with sf() as session:
        session.add_all(
            [
                V2InterviewState(
                    **base,
                    session_id="old-case",
                    pack_version="1.0.0",
                    question_catalog_version="rwdr.questions.1.0.0",
                ),
                V2InterviewState(
                    **base,
                    session_id="current-case",
                    pack_version="1.0.1",
                    question_catalog_version="rwdr.questions.1.0.1",
                ),
                V2InterviewShadowDecision(
                    id="shadow-old-pack",
                    tenant_id="tenant-a",
                    case_reference="opaque-case-ref",
                    state_revision=1,
                    pack_id="rwdr.v1",
                    pack_version="1.0.0",
                    policy_version="adaptive-interview.lexicographic.1.0.0",
                    legacy_question_present=True,
                    legacy_question_fingerprint="opaque-fingerprint",
                    legacy_need_id="rwdr.medium.primary",
                    controller_directive="ask",
                    controller_question_id="rwdr.q.application_goal",
                    rule_refs_json=["AI-T4-REQUIRED-001"],
                    divergence_type="different_need",
                    decision_duration_ms=0.1,
                    completeness_json={},
                    created_at="2026-07-14T10:00:00Z",
                ),
            ]
        )
        session.commit()

    _upgrade_engine(engine)

    with sf() as session:
        states = session.scalars(select(V2InterviewState)).all()
        shadow = session.scalar(select(V2InterviewShadowDecision))
    assert [(item.session_id, item.pack_version) for item in states] == [
        ("current-case", "1.0.1")
    ]
    assert shadow is not None
    assert shadow.id == "shadow-old-pack"
    assert shadow.pack_version == "1.0.0"


def test_alembic_baseline_adopts_complete_legacy_schema(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    legacy_tables = [
        table
        for table in Base.metadata.sorted_tables
        if not table.name.startswith(("v2_material_", "v2_medium_catalog"))
    ]
    Base.metadata.create_all(engine, tables=legacy_tables)
    assert "alembic_version" not in inspect(engine).get_table_names()

    up(engine)

    assert "alembic_version" in inspect(engine).get_table_names()
    validate_schema(engine)


def test_alembic_baseline_adopts_known_legacy_schema_without_legal_table(
    tmp_path,
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'legacy-before-legal.db'}")
    legacy_tables = [
        table
        for table in Base.metadata.sorted_tables
        if not table.name.startswith(("v2_material_", "v2_medium_catalog"))
    ]
    Base.metadata.create_all(engine, tables=legacy_tables)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE v2_legal_acceptance")

    up(engine)

    assert "v2_legal_acceptance" in inspect(engine).get_table_names()
    validate_schema(engine)


def test_alembic_baseline_rejects_partial_legacy_schema(tmp_path) -> None:
    path = tmp_path / "partial.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE v2_sessions (tenant_id TEXT NOT NULL, session_id TEXT NOT NULL, "
            "turns INTEGER NOT NULL, PRIMARY KEY (tenant_id, session_id))"
        )

    engine = make_engine(f"sqlite:///{path}")
    with pytest.raises(RuntimeError, match="partial V2 schema"):
        up(engine)


def test_knowledge_migration_rejects_partial_precreated_ledger(tmp_path) -> None:
    path = tmp_path / "partial-knowledge.db"
    engine = make_engine(f"sqlite:///{path}")
    up(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE v2_knowledge_outbox")
        connection.exec_driver_sql(
            "UPDATE alembic_version SET version_num='20260710_0002'"
        )

    with pytest.raises(RuntimeError, match="partial technical-knowledge ledger"):
        up(engine)


def test_legacy_partner_capabilities_become_unverified_submissions(tmp_path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'legacy-capabilities.db'}")
    _upgrade_engine(engine, "20260711_0004")
    sf = make_sessionmaker(engine)
    with sf() as session:
        session.add(
            V2HerstellerPartner(
                hersteller="acme",
                firmenname="ACME",
                aktiv=True,
                lead_email="leads@example.test",
                werkstoffe=["FKM"],
                bauformen=["RWDR"],
                groessen="10-200 mm",
                zertifikate=["ISO 9001"],
            )
        )
        session.commit()

    _upgrade_engine(engine)

    with sf() as session:
        profile = session.scalar(select(V2ManufacturerCapabilityProfile))
        review = session.scalar(select(V2ManufacturerCapabilityReview))
        assert profile.status == "submitted"
        assert profile.materials_json == ["FKM"]
        assert profile.seal_types_json == ["RWDR"]
        assert profile.evidence_json == []
        assert review.from_status == "legacy_partner_metadata"
        assert review.to_status == "submitted"
