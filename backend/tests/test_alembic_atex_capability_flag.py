"""Tests for Sprint 3 Patch 3.8 migration: ATEX capability flag."""

import importlib.util
from pathlib import Path

from sqlalchemy import inspect, text


REVISION = "c4d7e8f9a0b1"
DOWN_REVISION = "b2e4f6a8c0d1"
MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / f"{REVISION}_add_atex_capability_flag.py"
)


def test_revision_exists_with_correct_down_revision():
    """Migration 08 exists at the expected point in the Alembic chain."""
    spec = importlib.util.spec_from_file_location(
        "atex_capability_flag_migration",
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
    """Migration reverses; ATEX flag column and index are removed."""
    from alembic import command

    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, DOWN_REVISION)

    inspector = inspect(test_db_engine)
    columns = {
        column["name"]
        for column in inspector.get_columns("manufacturer_capability_claims")
    }
    indexes = {
        index["name"]
        for index in inspector.get_indexes("manufacturer_capability_claims")
    }
    assert "atex_capable" not in columns
    assert "ix_manufacturer_capability_claims_atex_capable" not in indexes


def test_atex_capability_column_and_index_exist(test_db_engine_at_head):
    """ATEX capability is a relational, indexed claim flag."""
    inspector = inspect(test_db_engine_at_head)
    columns = {
        column["name"]
        for column in inspector.get_columns("manufacturer_capability_claims")
    }
    indexes = {
        index["name"]
        for index in inspector.get_indexes("manufacturer_capability_claims")
    }

    assert "atex_capable" in columns
    assert "ix_manufacturer_capability_claims_atex_capable" in indexes


def test_valid_atex_capability_claim_insert_succeeds(test_db_engine_at_head):
    """ATEX capability can be stored as a certification capability claim."""
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO manufacturer_profiles (
                    manufacturer_id, legal_name, display_name, slug, country,
                    size_category
                ) VALUES (
                    'mfr-atex-1', 'ATEX Capable Seals GmbH',
                    'ATEX Capable Seals', 'atex-capable-seals', 'DE',
                    'medium'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO manufacturer_capability_claims (
                    claim_id, manufacturer_id, capability_type,
                    engineering_path, sealing_material_family,
                    capability_payload, source_type, source_reference,
                    confidence, validity_from, status, atex_capable
                ) VALUES (
                    'claim-atex-1', 'mfr-atex-1', 'certification',
                    'rwdr', 'ptfe_glass_filled',
                    '{"scope":"atex_capability_flag"}'::jsonb,
                    'third_party_verified', 'certificate:atex-test',
                    4, DATE '2026-04-20', 'active', true
                )
                """
            )
        )

        claim = conn.execute(
            text(
                """
                SELECT capability_type, atex_capable
                FROM manufacturer_capability_claims
                WHERE claim_id = 'claim-atex-1'
                """
            )
        ).mappings().one()

    assert claim["capability_type"] == "certification"
    assert claim["atex_capable"] is True


def test_atex_capability_unknown_can_remain_null(test_db_engine_at_head):
    """Existing or unrelated claims need not invent an ATEX capability value."""
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO manufacturer_profiles (
                    manufacturer_id, legal_name, display_name, slug, country,
                    size_category
                ) VALUES (
                    'mfr-atex-null', 'Unknown ATEX Seals GmbH',
                    'Unknown ATEX Seals', 'unknown-atex-seals', 'DE',
                    'small'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO manufacturer_capability_claims (
                    claim_id, manufacturer_id, capability_type,
                    capability_payload, source_type, source_reference,
                    confidence, validity_from
                ) VALUES (
                    'claim-atex-null', 'mfr-atex-null', 'material_expertise',
                    '{"scope":"ptfe"}'::jsonb, 'self_declared',
                    'onboarding:atex-null', 3, DATE '2026-04-20'
                )
                """
            )
        )

        claim = conn.execute(
            text(
                """
                SELECT atex_capable
                FROM manufacturer_capability_claims
                WHERE claim_id = 'claim-atex-null'
                """
            )
        ).mappings().one()

    assert claim["atex_capable"] is None
