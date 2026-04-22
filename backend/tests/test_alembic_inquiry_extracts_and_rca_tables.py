"""Tests for Sprint 3 Patch 3.3 migration: inquiry/RCA support tables."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


REVISION = "b2e4f6a8c0d1"
DOWN_REVISION = "91f0c2d4a6b8"
MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / f"{REVISION}_create_inquiry_extracts_golden_cases_rca_early_access.py"
)


def test_revision_exists_with_correct_down_revision():
    """Migration 07 exists at the expected point in the Alembic chain."""
    spec = importlib.util.spec_from_file_location(
        "inquiry_extracts_and_rca_migration",
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
    """Migration reverses; Patch 3.3 tables are removed."""
    from alembic import command

    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, DOWN_REVISION)

    inspector = inspect(test_db_engine)
    tables = set(inspector.get_table_names())
    assert "inquiry_extracts" not in tables
    assert "golden_cases" not in tables
    assert "rca_early_access" not in tables


def test_tables_and_columns_exist(test_db_engine_at_head):
    """Patch 3.3 tables expose only the planned minimal columns."""
    inspector = inspect(test_db_engine_at_head)
    tables = set(inspector.get_table_names())
    assert {"inquiry_extracts", "golden_cases", "rca_early_access"}.issubset(tables)

    expected_columns = {
        "inquiry_extracts": {
            "extract_id",
            "case_id",
            "tenant_id",
            "dispatched_to_manufacturer_id",
            "case_revision",
            "artifact_type",
            "payload",
            "source_kind",
            "created_by",
            "created_at",
        },
        "golden_cases": {
            "golden_case_id",
            "stable_key",
            "name",
            "request_type",
            "engineering_path",
            "sealing_material_family",
            "payload",
            "expected_output_class",
            "version",
            "active",
            "notes",
            "created_at",
            "updated_at",
        },
        "rca_early_access": {
            "entry_id",
            "tenant_id",
            "contact_identifier",
            "contact_consent",
            "submission_text",
            "structured_snapshot",
            "status",
            "created_at",
        },
    }
    for table_name, columns in expected_columns.items():
        actual = {column["name"] for column in inspector.get_columns(table_name)}
        assert columns == actual


def test_fks_constraints_and_indexes_exist(test_db_engine_at_head):
    """Core FKs, uniques, checks, and lookup indexes are present."""
    inspector = inspect(test_db_engine_at_head)

    inquiry_fks = {
        fk["name"]: (
            fk["constrained_columns"],
            fk["referred_table"],
            fk["referred_columns"],
            fk.get("options", {}).get("ondelete"),
        )
        for fk in inspector.get_foreign_keys("inquiry_extracts")
    }
    assert inquiry_fks["fk_inquiry_extracts_case_id"] == (
        ["case_id"],
        "cases",
        ["id"],
        "CASCADE",
    )

    uniques_by_table = {
        table_name: {
            constraint["name"] for constraint in inspector.get_unique_constraints(table_name)
        }
        for table_name in ("inquiry_extracts", "golden_cases")
    }
    assert (
        "uq_inquiry_extracts_case_revision_type"
        in uniques_by_table["inquiry_extracts"]
    )
    assert "uq_golden_cases_stable_key_version" in uniques_by_table["golden_cases"]

    checks_by_table = {
        table_name: {
            constraint["name"] for constraint in inspector.get_check_constraints(table_name)
        }
        for table_name in ("inquiry_extracts", "golden_cases", "rca_early_access")
    }
    assert "ck_inquiry_extracts_artifact_type" in checks_by_table["inquiry_extracts"]
    assert "ck_inquiry_extracts_source_kind" in checks_by_table["inquiry_extracts"]
    assert "ck_golden_cases_request_type" in checks_by_table["golden_cases"]
    assert "ck_golden_cases_engineering_path" in checks_by_table["golden_cases"]
    assert "ck_golden_cases_expected_output_class" in checks_by_table["golden_cases"]
    assert "ck_rca_early_access_status" in checks_by_table["rca_early_access"]
    assert (
        "ck_rca_early_access_contact_requires_consent"
        in checks_by_table["rca_early_access"]
    )
    assert (
        "ck_rca_early_access_submission_text_not_blank"
        in checks_by_table["rca_early_access"]
    )

    indexes_by_table = {
        table_name: {index["name"] for index in inspector.get_indexes(table_name)}
        for table_name in ("inquiry_extracts", "golden_cases", "rca_early_access")
    }
    assert "ix_inquiry_extracts_case_id" in indexes_by_table["inquiry_extracts"]
    assert "ix_inquiry_extracts_tenant_id" in indexes_by_table["inquiry_extracts"]
    assert (
        "ix_inquiry_extracts_dispatched_to_manufacturer_id"
        in indexes_by_table["inquiry_extracts"]
    )
    assert "ix_inquiry_extracts_artifact_type" in indexes_by_table["inquiry_extracts"]
    assert "ix_golden_cases_stable_key" in indexes_by_table["golden_cases"]
    assert (
        "ix_golden_cases_request_path_material" in indexes_by_table["golden_cases"]
    )
    assert "ix_golden_cases_active" in indexes_by_table["golden_cases"]
    assert "ix_rca_early_access_tenant_id" in indexes_by_table["rca_early_access"]
    assert "ix_rca_early_access_status" in indexes_by_table["rca_early_access"]


def test_minimal_valid_rows_insert_for_each_table(test_db_engine_at_head):
    """Minimal valid records can be inserted for all Patch 3.3 tables."""
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO cases (id, case_number, user_id, tenant_id)
                VALUES (
                    'case-p3-3-valid', 'CASE-P3-3-VALID',
                    'user-p3-3', 'tenant-p3-3'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO inquiry_extracts (
                    extract_id, case_id, tenant_id, case_revision,
                    artifact_type, payload, source_kind, created_by
                ) VALUES (
                    'extract-p3-3-valid', 'case-p3-3-valid', 'tenant-p3-3', 0,
                    'manufacturer_inquiry', '{"technical":"summary"}'::jsonb,
                    'case_revision', 'user-p3-3'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO golden_cases (
                    golden_case_id, stable_key, name, request_type,
                    engineering_path, sealing_material_family, payload,
                    expected_output_class
                ) VALUES (
                    'golden-p3-3-valid', 'ptfe-rwdr-basic-valid-v1',
                    'PTFE RWDR basic valid case', 'new_design', 'rwdr',
                    'ptfe_glass_filled', '{"fixture":"minimal"}'::jsonb,
                    'technical_preselection'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO rca_early_access (
                    entry_id, tenant_id, contact_identifier, contact_consent,
                    submission_text, structured_snapshot, status
                ) VALUES (
                    'rca-p3-3-valid', 'tenant-p3-3', 'user@example.test', true,
                    'Leckage nach kurzer Laufzeit.',
                    '{"medium":"unknown"}'::jsonb, 'new'
                )
                """
            )
        )

        extract = conn.execute(
            text(
                """
                SELECT artifact_type, source_kind
                FROM inquiry_extracts
                WHERE extract_id = 'extract-p3-3-valid'
                """
            )
        ).mappings().one()
        assert extract["artifact_type"] == "manufacturer_inquiry"
        assert extract["source_kind"] == "case_revision"


def test_inquiry_extract_rejects_orphan_case(test_db_engine_at_head):
    """Inquiry extracts must reference an existing case."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO inquiry_extracts (
                        extract_id, case_id, tenant_id, case_revision
                    ) VALUES (
                        'extract-orphan', 'missing-case', 'tenant-p3-3', 0
                    )
                    """
                )
            )


def test_inquiry_extract_rejects_duplicate_case_revision_type(test_db_engine_at_head):
    """A case revision may have only one extract per artifact type."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO cases (id, case_number, user_id, tenant_id)
                    VALUES (
                        'case-dup-extract', 'CASE-P3-3-DUP',
                        'user-p3-3', 'tenant-p3-3'
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO inquiry_extracts (
                        extract_id, case_id, tenant_id, case_revision, artifact_type
                    ) VALUES
                        (
                            'extract-dup-1', 'case-dup-extract', 'tenant-p3-3',
                            0, 'manufacturer_inquiry'
                        ),
                        (
                            'extract-dup-2', 'case-dup-extract', 'tenant-p3-3',
                            0, 'manufacturer_inquiry'
                        )
                    """
                )
            )


def test_golden_case_rejects_invalid_expected_output_class(test_db_engine_at_head):
    """Golden cases cannot reintroduce uncontrolled output classes."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO golden_cases (
                        golden_case_id, stable_key, name, request_type,
                        engineering_path, sealing_material_family,
                        expected_output_class
                    ) VALUES (
                        'golden-bad-output', 'bad-output-v1',
                        'Bad output class case', 'new_design', 'rwdr',
                        'ptfe_virgin', 'result_form'
                    )
                    """
                )
            )


def test_rca_early_access_requires_consent_for_contact(test_db_engine_at_head):
    """Contact identifiers require explicit consent."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO rca_early_access (
                        entry_id, contact_identifier, contact_consent,
                        submission_text
                    ) VALUES (
                        'rca-no-consent', 'user@example.test', false,
                        'Warum ist die Dichtung ausgefallen?'
                    )
                    """
                )
            )


def test_rca_early_access_rejects_blank_submission(test_db_engine_at_head):
    """RCA early-access entries need user-provided case text."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO rca_early_access (
                        entry_id, submission_text
                    ) VALUES (
                        'rca-blank', '   '
                    )
                    """
                )
            )
