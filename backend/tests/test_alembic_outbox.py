"""Tests for Sprint 1 Patch 1.3 migration: create_outbox."""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


def test_migration_upgrades_cleanly(alembic_config, test_db_engine):
    """Migration applies without error."""
    from alembic import command

    command.upgrade(alembic_config, "head")


def test_migration_downgrades_cleanly(alembic_config, test_db_engine):
    """Migration reverses; outbox table gone after downgrade."""
    from alembic import command

    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "-1")
    inspector = inspect(test_db_engine)
    assert "outbox" not in inspector.get_table_names()


def test_outbox_table_structure(test_db_engine_at_head):
    """All 14 columns exist."""
    inspector = inspect(test_db_engine_at_head)
    assert "outbox" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("outbox")}
    expected = {
        "outbox_id",
        "case_id",
        "mutation_id",
        "tenant_id",
        "task_type",
        "payload",
        "status",
        "priority",
        "attempts",
        "max_attempts",
        "next_attempt_at",
        "last_error",
        "created_at",
        "completed_at",
    }
    missing = expected - columns
    assert not missing, f"Missing columns: {missing}"
    assert len(expected) == 14
    assert columns == expected


def test_indexes_created(test_db_engine_at_head):
    """All 3 indexes exist."""
    inspector = inspect(test_db_engine_at_head)
    indexes = {index["name"] for index in inspector.get_indexes("outbox")}
    expected = {
        "idx_outbox_status_priority",
        "idx_outbox_case_id",
        "idx_outbox_tenant_id",
    }
    missing = expected - indexes
    assert not missing, f"Missing indexes: {missing}"


def test_status_priority_index_order(test_db_engine_at_head):
    """Worker index keeps status, priority DESC, next_attempt_at order."""
    inspector = inspect(test_db_engine_at_head)
    indexes = {index["name"]: index for index in inspector.get_indexes("outbox")}
    index = indexes["idx_outbox_status_priority"]
    assert index["column_names"] == ["status", "priority", "next_attempt_at"]

    with test_db_engine_at_head.begin() as conn:
        index_definition = conn.execute(
            text(
                """
                SELECT indexdef
                FROM pg_indexes
                WHERE tablename = 'outbox'
                  AND indexname = 'idx_outbox_status_priority'
                """
            )
        ).scalar_one()
    assert "(status, priority DESC, next_attempt_at)" in index_definition


def test_valid_status_insert_succeeds(test_db_engine_at_head):
    """Insert with each valid status value succeeds."""
    statuses = [
        "pending",
        "in_progress",
        "completed",
        "failed_retryable",
        "failed_permanent",
    ]
    with test_db_engine_at_head.begin() as conn:
        for status in statuses:
            conn.execute(
                text(
                    """
                    INSERT INTO outbox (outbox_id, task_type, payload, status)
                    VALUES (
                        :outbox_id, 'risk_score_recompute',
                        '{}'::jsonb, :status
                    )
                    """
                ),
                {"outbox_id": f"obx-{status}", "status": status},
            )
            result = conn.execute(
                text("SELECT status FROM outbox WHERE outbox_id = :outbox_id"),
                {"outbox_id": f"obx-{status}"},
            ).scalar()
            assert result == status
        conn.execute(text("DELETE FROM outbox WHERE outbox_id LIKE 'obx-%'"))


def test_invalid_status_rejected(test_db_engine_at_head):
    """CHECK constraint rejects invalid status."""
    with test_db_engine_at_head.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO outbox (outbox_id, task_type, payload, status)
                    VALUES (
                        'obx-bad', 'risk_score_recompute',
                        '{}'::jsonb, 'not_a_real_status'
                    )
                    """
                )
            )


def test_defaults_applied(test_db_engine_at_head):
    """Server defaults applied on minimal insert."""
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO outbox (outbox_id, task_type, payload)
                VALUES ('obx-defaults', 'notify_audit_log', '{}'::jsonb)
                """
            )
        )
        row = conn.execute(
            text(
                "SELECT status, priority, attempts, max_attempts "
                "FROM outbox WHERE outbox_id = 'obx-defaults'"
            )
        ).mappings().one()
        assert row["status"] == "pending"
        assert row["priority"] == 0
        assert row["attempts"] == 0
        assert row["max_attempts"] == 5
        conn.execute(text("DELETE FROM outbox WHERE outbox_id = 'obx-defaults'"))


def test_fk_cascade_on_case_delete(test_db_engine_at_head):
    """Deleting a case cascades to its outbox tasks."""
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cases (id, case_number, user_id) "
                "VALUES ('case-cascade-outbox', 'CASE-1-3', 'user-test')"
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO outbox (outbox_id, case_id, task_type, payload)
                VALUES ('obx-cascade', 'case-cascade-outbox',
                        'risk_score_recompute', '{}'::jsonb)
                """
            )
        )
        conn.execute(text("DELETE FROM cases WHERE id = 'case-cascade-outbox'"))
        count = conn.execute(
            text("SELECT COUNT(*) FROM outbox WHERE outbox_id = 'obx-cascade'")
        ).scalar()
        assert count == 0


def test_fk_no_cascade_on_mutation_delete(test_db_engine_at_head):
    """The mutation_id FK exists and does not declare ON DELETE CASCADE."""
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cases (id, case_number, user_id) "
                "VALUES ('case-mut-1', 'CASE-1-3-MUT', 'user-test')"
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO mutation_events (
                    mutation_id, case_id, event_type, payload,
                    case_revision_before, case_revision_after,
                    actor, actor_type
                ) VALUES (
                    'mut-1-3-outbox', 'case-mut-1', 'case_created',
                    '{}'::jsonb, 0, 1, 'test', 'system'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO outbox (outbox_id, mutation_id, task_type, payload)
                VALUES ('obx-no-cascade', 'mut-1-3-outbox',
                        'notify_audit_log', '{}'::jsonb)
                """
            )
        )

        inspector = inspect(test_db_engine_at_head)
        fks = inspector.get_foreign_keys("outbox")
        mutation_fk = next(
            (
                fk
                for fk in fks
                if fk["name"] == "fk_outbox_mutation_id"
                and fk["referred_table"] == "mutation_events"
            ),
            None,
        )
        assert mutation_fk is not None
        assert mutation_fk["constrained_columns"] == ["mutation_id"]
        assert mutation_fk["referred_columns"] == ["mutation_id"]
        assert mutation_fk.get("options", {}).get("ondelete") != "CASCADE"

        conn.execute(text("DELETE FROM outbox WHERE outbox_id = 'obx-no-cascade'"))
        conn.execute(text("DELETE FROM cases WHERE id = 'case-mut-1'"))
