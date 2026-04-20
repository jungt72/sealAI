"""Tests for Sprint 1 Patch 1.2 migration: create_mutation_events."""

import pytest
from sqlalchemy import inspect, text


def test_migration_upgrades_cleanly(alembic_config, test_db_engine):
    """Migration applies without error."""
    from alembic import command

    command.upgrade(alembic_config, "head")


def test_migration_downgrades_cleanly(alembic_config, test_db_engine):
    """Migration reverses; mutation_events table gone after downgrade."""
    from alembic import command

    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "6d8f1b3a9c20")
    inspector = inspect(test_db_engine)
    assert "mutation_events" not in inspector.get_table_names()


def test_mutation_events_table_exists(test_db_engine_at_head):
    """Table exists with correct columns after upgrade."""
    inspector = inspect(test_db_engine_at_head)
    assert "mutation_events" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("mutation_events")}
    expected = {
        "mutation_id",
        "case_id",
        "tenant_id",
        "event_type",
        "payload",
        "case_revision_before",
        "case_revision_after",
        "actor",
        "actor_type",
        "created_at",
    }
    missing = expected - columns
    assert not missing, f"Missing columns: {missing}"


def test_indexes_created(test_db_engine_at_head):
    """All 4 indexes exist."""
    inspector = inspect(test_db_engine_at_head)
    indexes = {index["name"] for index in inspector.get_indexes("mutation_events")}
    expected = {
        "idx_mutation_events_case_id",
        "idx_mutation_events_tenant_id",
        "idx_mutation_events_event_type",
        "idx_mutation_events_created_at",
    }
    missing = expected - indexes
    assert not missing, f"Missing indexes: {missing}"


def test_valid_insert_succeeds(test_db_engine_at_head):
    """Valid insert with a referenced case succeeds."""
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cases (id, case_number, user_id, tenant_id) "
                "VALUES ('case-test-1.2', 'CASE-TEST-1-2', 'user-test', 'tenant-test')"
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO mutation_events (
                    mutation_id, case_id, tenant_id, event_type, payload,
                    case_revision_before, case_revision_after,
                    actor, actor_type
                ) VALUES (
                    'mut-test-001', 'case-test-1.2', 'tenant-test', 'case_created',
                    '{}'::jsonb, 0, 1, 'test-user', 'user'
                )
                """
            )
        )
        result = conn.execute(
            text(
                "SELECT event_type FROM mutation_events "
                "WHERE mutation_id = 'mut-test-001'"
            )
        ).scalar()
        assert result == "case_created"
        conn.execute(text("DELETE FROM cases WHERE id = 'case-test-1.2'"))


def test_insert_missing_required_column_fails(test_db_engine_at_head):
    """INSERT omitting a NOT NULL column fails."""
    from sqlalchemy.exc import IntegrityError

    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cases (id, case_number, user_id, tenant_id) "
                "VALUES ('case-test-1.2b', 'CASE-TEST-1-2B', 'user-test', 'tenant-test')"
            )
        )
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO mutation_events (
                        mutation_id, case_id, event_type, payload,
                        actor, actor_type
                    ) VALUES (
                        'mut-fail-001', 'case-test-1.2b', 'case_created',
                        '{}'::jsonb, 'test-user', 'user'
                    )
                    """
                )
            )


def test_fk_cascade_on_case_delete(test_db_engine_at_head):
    """Deleting a case cascades to its mutation events."""
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cases (id, case_number, user_id, tenant_id) "
                "VALUES ('case-cascade-test', 'CASE-CASCADE', 'user-test', 'tenant-test')"
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO mutation_events (
                    mutation_id, case_id, tenant_id, event_type, payload,
                    case_revision_before, case_revision_after,
                    actor, actor_type
                ) VALUES (
                    'mut-cascade-001', 'case-cascade-test', 'tenant-test', 'field_updated',
                    '{"field":"x"}'::jsonb, 1, 2, 'test', 'system'
                )
                """
            )
        )
        conn.execute(text("DELETE FROM cases WHERE id = 'case-cascade-test'"))
        result = conn.execute(
            text(
                "SELECT COUNT(*) FROM mutation_events "
                "WHERE mutation_id = 'mut-cascade-001'"
            )
        ).scalar()
        assert result == 0, "FK CASCADE did not delete mutation event"
