"""Tests for Sprint 1 Patch 1.1 migration: extend_cases_table_phase1a."""

from sqlalchemy import inspect


def test_migration_has_correct_revision_id(alembic_config):
    """Patch 1.1 migration exists in the Alembic chain."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_config)
    migration = script.get_revision("6d8f1b3a9c20")

    assert migration is not None
    assert migration.revision == "6d8f1b3a9c20"
    assert migration.down_revision == "a1b2c3d4e5f6"


def test_migration_upgrades_cleanly(alembic_config, test_db_engine):
    """Migration applies without error."""
    from alembic import command

    command.upgrade(alembic_config, "head")


def test_migration_downgrades_cleanly(alembic_config, test_db_engine):
    """Migration reverses without error."""
    from alembic import command

    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "-1")


def test_new_columns_present_after_upgrade(test_db_engine_at_head):
    """All 16 Phase 1a columns exist on cases table after migration."""
    inspector = inspect(test_db_engine_at_head)
    columns = {column["name"] for column in inspector.get_columns("cases")}
    expected_new = {
        "tenant_id",
        "case_revision",
        "schema_version",
        "ruleset_version",
        "calc_library_version",
        "risk_engine_version",
        "phase",
        "routing_path",
        "pre_gate_classification",
        "request_type",
        "engineering_path",
        "sealing_material_family",
        "application_pattern_id",
        "rfq_ready",
        "inquiry_admissible",
        "payload",
    }

    missing = expected_new - columns
    assert not missing, f"Missing Phase 1a columns: {missing}"


def test_existing_columns_preserved(test_db_engine_at_head):
    """Pre-existing cases columns are untouched."""
    inspector = inspect(test_db_engine_at_head)
    columns = {column["name"] for column in inspector.get_columns("cases")}
    preserved = {
        "id",
        "case_number",
        "user_id",
        "subsegment",
        "status",
        "created_at",
        "updated_at",
        "session_id",
    }

    missing = preserved - columns
    assert not missing, f"Pre-existing columns lost: {missing}"


def test_preexisting_indexes_preserved(test_db_engine_at_head):
    """Pre-existing indexes are never dropped."""
    inspector = inspect(test_db_engine_at_head)
    primary_key = inspector.get_pk_constraint("cases")
    indexes = {index["name"] for index in inspector.get_indexes("cases")}
    preserved = {
        "ix_cases_case_number",
        "ix_cases_session_id",
        "ix_cases_user_id",
    }

    missing = preserved - indexes
    assert primary_key["name"] == "cases_pkey"
    assert primary_key["constrained_columns"] == ["id"]
    assert not missing, f"Pre-existing indexes dropped: {missing}"


def test_new_indexes_created(test_db_engine_at_head):
    """All 5 Phase 1a indexes exist."""
    inspector = inspect(test_db_engine_at_head)
    indexes = {index["name"] for index in inspector.get_indexes("cases")}
    expected = {
        "idx_cases_tenant_id",
        "idx_cases_engineering_path",
        "idx_cases_request_type",
        "idx_cases_updated_at",
        "idx_cases_payload_sealing_family",
    }

    missing = expected - indexes
    assert not missing, f"Missing Phase 1a indexes: {missing}"


def test_payload_defaults_to_empty_jsonb(test_db_engine_at_head):
    """Payload column accepts empty jsonb as default."""
    from sqlalchemy import text

    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cases (id, case_number, user_id) "
                "VALUES ('test-001', 'CASE-TEST-001', 'user-test')"
            )
        )
        result = conn.execute(
            text("SELECT payload FROM cases WHERE id = 'test-001'")
        ).scalar()
        assert result == {} or result == "{}", (
            f"Expected empty JSONB default, got: {result!r}"
        )
        conn.execute(text("DELETE FROM cases WHERE id = 'test-001'"))


def test_case_revision_defaults_to_zero(test_db_engine_at_head):
    """case_revision column defaults to 0 for new inserts."""
    from sqlalchemy import text

    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO cases (id, case_number, user_id) "
                "VALUES ('test-002', 'CASE-TEST-002', 'user-test')"
            )
        )
        result = conn.execute(
            text("SELECT case_revision FROM cases WHERE id = 'test-002'")
        ).scalar()
        assert result == 0, f"Expected case_revision=0, got: {result}"
        conn.execute(text("DELETE FROM cases WHERE id = 'test-002'"))
