"""Tests for the create_outcome_records migration (V1.8 §6.5, d1e2f3a4b5c6)."""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


def test_migration_upgrades_cleanly(alembic_config, test_db_engine):
    from alembic import command

    command.upgrade(alembic_config, "head")


def test_migration_downgrades_cleanly(alembic_config, test_db_engine):
    from alembic import command

    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "c7d8e9f0a1b2")
    inspector = inspect(test_db_engine)
    assert "outcome_records" not in inspector.get_table_names()


def test_table_structure(test_db_engine_at_head):
    inspector = inspect(test_db_engine_at_head)
    assert "outcome_records" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("outcome_records")}
    expected = {
        "outcome_id",
        "case_id",
        "tenant_id",
        "position_id",
        "solution_ref",
        "event",
        "installed_at",
        "runtime_hours_estimate",
        "outcome_pattern",
        "suspected_cause",
        "evidence_refs",
        "confidence",
        "created_at",
    }
    assert columns == expected


def test_indexes_created(test_db_engine_at_head):
    inspector = inspect(test_db_engine_at_head)
    indexes = {i["name"] for i in inspector.get_indexes("outcome_records")}
    expected = {
        "idx_outcome_records_tenant_id",
        "idx_outcome_records_case_id",
        "idx_outcome_records_pattern",
    }
    assert expected <= indexes


def test_tenant_id_is_not_nullable(test_db_engine_at_head):
    """Raw outcomes are tenant-scoped — tenant_id NOT NULL is enforced."""
    with test_db_engine_at_head.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO outcome_records (outcome_id, event, confidence) "
                    "VALUES ('oc-no-tenant', 'incident', 'medium')"
                )
            )


def test_defaults_applied(test_db_engine_at_head):
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO outcome_records (outcome_id, tenant_id) "
                "VALUES ('oc-defaults', 'tenant-test')"
            )
        )
        row = (
            conn.execute(
                text(
                    "SELECT position_id, event, confidence, evidence_refs "
                    "FROM outcome_records WHERE outcome_id = 'oc-defaults'"
                )
            )
            .mappings()
            .one()
        )
        assert row["position_id"] == "pos_1"
        assert row["event"] == "incident"
        assert row["confidence"] == "medium"
        conn.execute(
            text("DELETE FROM outcome_records WHERE outcome_id = 'oc-defaults'")
        )


def test_invalid_event_and_confidence_rejected(test_db_engine_at_head):
    with test_db_engine_at_head.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO outcome_records (outcome_id, tenant_id, event) "
                    "VALUES ('oc-bad-event', 'tenant-test', 'exploded')"
                )
            )
    with test_db_engine_at_head.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO outcome_records (outcome_id, tenant_id, confidence) "
                    "VALUES ('oc-bad-conf', 'tenant-test', 'certain')"
                )
            )
