"""Tests for Sprint 3 Patch 3.1 migration: terminology registry tables."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


REVISION = "e3a9c7d1f0b2"
DOWN_REVISION = "b8c4d6e2f901"
MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / f"{REVISION}_create_terminology_registry_tables.py"
)


def test_revision_exists_with_correct_down_revision():
    """Migration 05 exists at the expected point in the Alembic chain."""
    spec = importlib.util.spec_from_file_location(
        "terminology_registry_migration",
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
    """Migration reverses; terminology registry tables are removed."""
    from alembic import command

    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, DOWN_REVISION)

    inspector = inspect(test_db_engine)
    tables = set(inspector.get_table_names())
    assert "generic_concepts" not in tables
    assert "product_terms" not in tables
    assert "term_mappings" not in tables
    assert "term_audit_log" not in tables


def test_terminology_registry_tables_and_columns_exist(test_db_engine_at_head):
    """All terminology registry tables expose the planned columns."""
    inspector = inspect(test_db_engine_at_head)
    tables = set(inspector.get_table_names())
    assert {
        "generic_concepts",
        "product_terms",
        "term_mappings",
        "term_audit_log",
    }.issubset(tables)

    expected_columns = {
        "generic_concepts": {
            "concept_id",
            "canonical_name",
            "display_name",
            "standards_refs",
            "engineering_path",
            "sealing_material_family",
            "description",
            "structural_parameters",
            "created_at",
            "updated_at",
        },
        "product_terms": {
            "term_id",
            "term_text",
            "normalized_term",
            "term_language",
            "term_type",
            "originating_manufacturer_id",
            "is_trademark",
            "created_at",
        },
        "term_mappings": {
            "mapping_id",
            "term_id",
            "concept_id",
            "source_type",
            "source_reference",
            "confidence",
            "validity_from",
            "validity_to",
            "reviewer_status",
            "reviewer_id",
            "review_notes",
            "is_active",
            "created_at",
        },
        "term_audit_log": {
            "audit_id",
            "mapping_id",
            "concept_id",
            "term_id",
            "action",
            "actor_id",
            "actor_type",
            "payload",
            "created_at",
        },
    }
    for table_name, columns in expected_columns.items():
        actual = {column["name"] for column in inspector.get_columns(table_name)}
        assert columns == actual


def test_terminology_registry_constraints_and_indexes_exist(test_db_engine_at_head):
    """Core unique constraints, FKs, and lookup indexes are present."""
    inspector = inspect(test_db_engine_at_head)

    concept_uniques = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("generic_concepts")
    }
    assert "uq_generic_concepts_canonical_name" in concept_uniques

    mapping_fks = {
        fk["name"]: (
            fk["constrained_columns"],
            fk["referred_table"],
            fk["referred_columns"],
        )
        for fk in inspector.get_foreign_keys("term_mappings")
    }
    assert mapping_fks["fk_term_mappings_term_id"] == (
        ["term_id"],
        "product_terms",
        ["term_id"],
    )
    assert mapping_fks["fk_term_mappings_concept_id"] == (
        ["concept_id"],
        "generic_concepts",
        ["concept_id"],
    )

    audit_fks = {
        fk["name"]: fk.get("options", {}).get("ondelete")
        for fk in inspector.get_foreign_keys("term_audit_log")
    }
    assert audit_fks["fk_term_audit_log_mapping_id"] == "SET NULL"
    assert audit_fks["fk_term_audit_log_concept_id"] == "SET NULL"
    assert audit_fks["fk_term_audit_log_term_id"] == "SET NULL"

    indexes_by_table = {
        table_name: {index["name"] for index in inspector.get_indexes(table_name)}
        for table_name in (
            "generic_concepts",
            "product_terms",
            "term_mappings",
            "term_audit_log",
        )
    }
    assert "ix_generic_concepts_engineering_path" in indexes_by_table["generic_concepts"]
    assert "ix_generic_concepts_sealing_material_family" in indexes_by_table["generic_concepts"]
    assert "uq_product_terms_normalized_scope" in indexes_by_table["product_terms"]
    assert "ix_product_terms_normalized_term" in indexes_by_table["product_terms"]
    assert "uq_term_mappings_source_window" in indexes_by_table["term_mappings"]
    assert "ix_term_mappings_term_id" in indexes_by_table["term_mappings"]
    assert "ix_term_mappings_concept_id" in indexes_by_table["term_mappings"]
    assert "ix_term_audit_log_created_at" in indexes_by_table["term_audit_log"]


def test_minimal_valid_terminology_registry_insert_succeeds(test_db_engine_at_head):
    """A concept, product term, mapping, and audit event can be inserted."""
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO generic_concepts (
                    concept_id, canonical_name, display_name, engineering_path,
                    sealing_material_family
                ) VALUES (
                    'concept-rwdr-ptfe-1',
                    'rwdr_ptfe_lip_spring_loaded',
                    'Spring-energized PTFE lip seal',
                    'rwdr',
                    'ptfe_mixed_filled'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO product_terms (
                    term_id, term_text, normalized_term, term_language, term_type,
                    is_trademark
                ) VALUES (
                    'term-variseal-1', 'Turcon Variseal', 'turcon variseal',
                    'de', 'brand_name', true
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO term_mappings (
                    mapping_id, term_id, concept_id, source_type,
                    source_reference, confidence, reviewer_status
                ) VALUES (
                    'mapping-variseal-1', 'term-variseal-1',
                    'concept-rwdr-ptfe-1', 'manufacturer_datasheet',
                    'datasheet:example', 5, 'published'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO term_audit_log (
                    audit_id, mapping_id, action, actor_type, payload
                ) VALUES (
                    'audit-variseal-1', 'mapping-variseal-1',
                    'mapping_published', 'system', '{"source":"test"}'::jsonb
                )
                """
            )
        )

        mapping = conn.execute(
            text(
                """
                SELECT source_type, confidence, reviewer_status
                FROM term_mappings
                WHERE mapping_id = 'mapping-variseal-1'
                """
            )
        ).mappings().one()
        assert mapping["source_type"] == "manufacturer_datasheet"
        assert mapping["confidence"] == 5
        assert mapping["reviewer_status"] == "published"


def test_duplicate_generic_concept_canonical_name_is_rejected(test_db_engine_at_head):
    """Concept canonical names are stable identifiers and must be unique."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO generic_concepts (
                        concept_id, canonical_name, display_name, engineering_path
                    ) VALUES
                        ('concept-dup-1', 'rwdr_ptfe_duplicate', 'First', 'rwdr'),
                        ('concept-dup-2', 'rwdr_ptfe_duplicate', 'Second', 'rwdr')
                    """
                )
            )


def test_invalid_term_type_is_rejected(test_db_engine_at_head):
    """Product terms are limited to the authority-defined term types."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO product_terms (
                        term_id, term_text, normalized_term, term_language, term_type
                    ) VALUES (
                        'term-bad-type', 'Bad', 'bad', 'de', 'marketing_label'
                    )
                    """
                )
            )


def test_mapping_requires_existing_term_and_concept(test_db_engine_at_head):
    """Mapping FKs reject orphaned registry links."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO term_mappings (
                        mapping_id, term_id, concept_id, source_type,
                        source_reference, confidence
                    ) VALUES (
                        'mapping-orphan', 'missing-term', 'missing-concept',
                        'public_reference', 'source:example', 3
                    )
                    """
                )
            )


def test_mapping_confidence_range_is_rejected(test_db_engine_at_head):
    """Mapping confidence stays within the Supplement v2 1-5 range."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO generic_concepts (
                        concept_id, canonical_name, display_name, engineering_path
                    ) VALUES (
                        'concept-confidence', 'confidence_concept', 'Confidence', 'rwdr'
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO product_terms (
                        term_id, term_text, normalized_term, term_language, term_type
                    ) VALUES (
                        'term-confidence', 'Confidence', 'confidence', 'de',
                        'generic_term'
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO term_mappings (
                        mapping_id, term_id, concept_id, source_type,
                        source_reference, confidence
                    ) VALUES (
                        'mapping-bad-confidence', 'term-confidence',
                        'concept-confidence', 'expert_judgment',
                        'source:example', 6
                    )
                    """
                )
            )
