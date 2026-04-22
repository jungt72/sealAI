"""Tests for Gate 3->4 remediation: inquiry extract dispatch scope."""

import importlib.util
from pathlib import Path

from sqlalchemy import inspect, text


REVISION = "f6a7b8c9d0e1"
DOWN_REVISION = "c4d7e8f9a0b1"
MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / f"{REVISION}_add_inquiry_extract_dispatch_scope.py"
)


def test_revision_exists_with_correct_down_revision():
    """Dispatch-scope migration follows the Sprint 3 ATEX capability head."""
    spec = importlib.util.spec_from_file_location(
        "inquiry_extract_dispatch_scope_migration",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == REVISION
    assert module.down_revision == DOWN_REVISION


def test_migration_upgrades_cleanly(alembic_config, test_db_engine):
    """Migration applies without error."""
    from alembic import command

    command.upgrade(alembic_config, "head")


def test_migration_downgrades_cleanly(alembic_config, test_db_engine):
    """Migration reverses; dispatch-scope column and index are removed."""
    from alembic import command

    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, DOWN_REVISION)

    inspector = inspect(test_db_engine)
    columns = {column["name"] for column in inspector.get_columns("inquiry_extracts")}
    indexes = {index["name"] for index in inspector.get_indexes("inquiry_extracts")}
    assert "dispatched_to_manufacturer_id" not in columns
    assert "ix_inquiry_extracts_dispatched_to_manufacturer_id" not in indexes


def test_dispatch_scope_column_and_index_exist(test_db_engine_at_head):
    """Manufacturer dispatch scope is explicitly modelled and filterable."""
    inspector = inspect(test_db_engine_at_head)
    columns = {column["name"] for column in inspector.get_columns("inquiry_extracts")}
    indexes = {index["name"] for index in inspector.get_indexes("inquiry_extracts")}

    assert "dispatched_to_manufacturer_id" in columns
    assert "ix_inquiry_extracts_dispatched_to_manufacturer_id" in indexes


def test_inquiry_extract_accepts_dispatch_target(test_db_engine_at_head):
    """An extract can be scoped to a manufacturer without adding dispatch workflow."""
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO cases (id, case_number, user_id, tenant_id)
                VALUES (
                    'case-dispatch-scope', 'CASE-DISPATCH-SCOPE',
                    'user-dispatch', 'tenant-dispatch'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO inquiry_extracts (
                    extract_id, case_id, tenant_id, dispatched_to_manufacturer_id,
                    case_revision, artifact_type
                ) VALUES (
                    'extract-dispatch-scope', 'case-dispatch-scope',
                    'tenant-dispatch', 'mfr-dispatch-target', 0,
                    'manufacturer_inquiry'
                )
                """
            )
        )

        extract = conn.execute(
            text(
                """
                SELECT dispatched_to_manufacturer_id
                FROM inquiry_extracts
                WHERE extract_id = 'extract-dispatch-scope'
                """
            )
        ).mappings().one()

    assert extract["dispatched_to_manufacturer_id"] == "mfr-dispatch-target"


def test_inquiry_extract_dispatch_target_can_remain_null(test_db_engine_at_head):
    """Nullable scope preserves draft/manual extract creation before dispatch."""
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO cases (id, case_number, user_id, tenant_id)
                VALUES (
                    'case-dispatch-null', 'CASE-DISPATCH-NULL',
                    'user-dispatch-null', 'tenant-dispatch-null'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO inquiry_extracts (
                    extract_id, case_id, tenant_id, case_revision
                ) VALUES (
                    'extract-dispatch-null', 'case-dispatch-null',
                    'tenant-dispatch-null', 0
                )
                """
            )
        )

        extract = conn.execute(
            text(
                """
                SELECT dispatched_to_manufacturer_id
                FROM inquiry_extracts
                WHERE extract_id = 'extract-dispatch-null'
                """
            )
        ).mappings().one()

    assert extract["dispatched_to_manufacturer_id"] is None
