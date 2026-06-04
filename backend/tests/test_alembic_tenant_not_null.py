"""Tests for Sprint 1 Patch 1.7 tenant_id NOT NULL hardening."""

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


def test_migration_has_correct_revision_id(alembic_config):
    script = ScriptDirectory.from_config(alembic_config)
    migration = script.get_revision("b8c4d6e2f901")

    assert migration is not None
    assert migration.revision == "b8c4d6e2f901"
    assert migration.down_revision == "4c2f8a9d1b73"


def test_tenant_not_null_migration_upgrades_cleanly(alembic_config, test_db_engine):
    from alembic import command

    command.upgrade(alembic_config, "head")


def test_tenant_columns_are_not_nullable_at_head(test_db_engine_at_head):
    inspector = inspect(test_db_engine_at_head)

    for table_name in ("cases", "mutation_events", "outbox"):
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        assert columns["tenant_id"]["nullable"] is False


def test_migration_fails_fast_when_existing_null_tenant_data_exists(
    alembic_config,
    test_db_engine,
):
    from alembic import command

    command.upgrade(alembic_config, "4c2f8a9d1b73")
    with test_db_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cases (id, case_number, user_id) "
                "VALUES ('case-null-tenant-1.7', 'CASE-NULL-1-7', 'user-test')"
            )
        )

    with pytest.raises(RuntimeError, match="found NULL tenant_id rows"):
        command.upgrade(alembic_config, "head")


def test_cases_insert_without_tenant_id_fails_at_db_level(test_db_engine_at_head):
    with test_db_engine_at_head.connect() as conn:
        transaction = conn.begin()
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO cases (id, case_number, user_id) "
                    "VALUES ('case-no-tenant-1.7', 'CASE-NO-TENANT-1-7', 'user-test')"
                )
            )
        transaction.rollback()


def test_mutation_events_insert_without_tenant_id_fails_at_db_level(
    test_db_engine_at_head,
):
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cases (id, case_number, user_id, tenant_id) "
                "VALUES ('case-mut-no-tenant-1.7', 'CASE-MUT-NO-TENANT-1-7', "
                "'user-test', 'tenant-test')"
            )
        )

    with test_db_engine_at_head.connect() as conn:
        transaction = conn.begin()
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO mutation_events (
                        mutation_id, case_id, event_type, payload,
                        case_revision_before, case_revision_after,
                        actor, actor_type
                    ) VALUES (
                        'mut-no-tenant-1.7', 'case-mut-no-tenant-1.7',
                        'field_updated', '{}'::jsonb, 0, 1, 'test', 'system'
                    )
                    """
                )
            )
        transaction.rollback()


def test_outbox_insert_without_tenant_id_fails_at_db_level(test_db_engine_at_head):
    with test_db_engine_at_head.connect() as conn:
        transaction = conn.begin()
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    """
                    INSERT INTO outbox (outbox_id, task_type, payload)
                    VALUES ('obx-no-tenant-1.7', 'notify_audit_log', '{}'::jsonb)
                    """
                )
            )
        transaction.rollback()


def test_valid_tenant_based_writes_still_succeed(test_db_engine_at_head):
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cases (id, case_number, user_id, tenant_id) "
                "VALUES ('case-valid-tenant-1.7', 'CASE-VALID-TENANT-1-7', "
                "'user-test', 'tenant-test')"
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO mutation_events (
                    mutation_id, case_id, tenant_id, event_type, payload,
                    case_revision_before, case_revision_after, actor, actor_type
                ) VALUES (
                    'mut-valid-tenant-1.7', 'case-valid-tenant-1.7',
                    'tenant-test', 'field_updated', '{}'::jsonb, 0, 1,
                    'test', 'system'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO outbox (
                    outbox_id, mutation_id, tenant_id, task_type, payload
                ) VALUES (
                    'obx-valid-tenant-1.7', 'mut-valid-tenant-1.7',
                    'tenant-test', 'project_case_snapshot', '{}'::jsonb
                )
                """
            )
        )

        counts = conn.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(*) FROM cases WHERE id = 'case-valid-tenant-1.7')
                    AS cases_count,
                    (SELECT COUNT(*) FROM mutation_events
                     WHERE mutation_id = 'mut-valid-tenant-1.7') AS mutation_count,
                    (SELECT COUNT(*) FROM outbox
                     WHERE outbox_id = 'obx-valid-tenant-1.7') AS outbox_count
                """
            )
        ).mappings().one()

    assert counts == {
        "cases_count": 1,
        "mutation_count": 1,
        "outbox_count": 1,
    }
