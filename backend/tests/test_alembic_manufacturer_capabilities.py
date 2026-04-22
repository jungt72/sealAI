"""Tests for Sprint 3 Patch 3.2 migration: manufacturer capability tables."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


REVISION = "91f0c2d4a6b8"
DOWN_REVISION = "e3a9c7d1f0b2"
MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / f"{REVISION}_create_manufacturer_capability_tables.py"
)


def test_revision_exists_with_correct_down_revision():
    """Migration 06 exists at the expected point in the Alembic chain."""
    spec = importlib.util.spec_from_file_location(
        "manufacturer_capability_migration",
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
    """Migration reverses; manufacturer capability tables are removed."""
    from alembic import command

    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, DOWN_REVISION)

    inspector = inspect(test_db_engine)
    tables = set(inspector.get_table_names())
    assert "manufacturer_profiles" not in tables
    assert "manufacturer_capability_claims" not in tables


def test_manufacturer_capability_tables_and_columns_exist(test_db_engine_at_head):
    """Manufacturer profile and claim tables expose the planned columns."""
    inspector = inspect(test_db_engine_at_head)
    tables = set(inspector.get_table_names())
    assert {
        "manufacturer_profiles",
        "manufacturer_capability_claims",
    }.issubset(tables)

    expected_columns = {
        "manufacturer_profiles": {
            "manufacturer_id",
            "legal_name",
            "display_name",
            "slug",
            "country",
            "website_url",
            "size_category",
            "account_status",
            "onboarded_at",
            "created_at",
            "updated_at",
        },
        "manufacturer_capability_claims": {
            "claim_id",
            "manufacturer_id",
            "capability_type",
            "engineering_path",
            "sealing_material_family",
            "capability_payload",
            "source_type",
            "source_reference",
            "confidence",
            "validity_from",
            "validity_to",
            "verified_at",
            "verified_by",
            "status",
            "minimum_order_pieces",
            "typical_minimum_pieces",
            "maximum_order_pieces",
            "preferred_batch_min_pieces",
            "preferred_batch_max_pieces",
            "accepts_single_pieces",
            "atex_capable",
            "rapid_manufacturing_available",
            "rapid_manufacturing_surcharge_percent",
            "rapid_manufacturing_leadtime_hours",
            "standard_leadtime_weeks",
            "created_at",
            "updated_at",
        },
    }
    for table_name, columns in expected_columns.items():
        actual = {column["name"] for column in inspector.get_columns(table_name)}
        assert columns == actual


def test_manufacturer_capability_constraints_and_indexes_exist(test_db_engine_at_head):
    """Core unique constraints, FKs, checks, and lookup indexes are present."""
    inspector = inspect(test_db_engine_at_head)

    profile_uniques = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("manufacturer_profiles")
    }
    assert "uq_manufacturer_profiles_slug" in profile_uniques
    assert "uq_manufacturer_profiles_legal_name_country" in profile_uniques

    claim_fks = {
        fk["name"]: (
            fk["constrained_columns"],
            fk["referred_table"],
            fk["referred_columns"],
            fk.get("options", {}).get("ondelete"),
        )
        for fk in inspector.get_foreign_keys("manufacturer_capability_claims")
    }
    assert claim_fks["fk_manufacturer_capability_claims_manufacturer_id"] == (
        ["manufacturer_id"],
        "manufacturer_profiles",
        ["manufacturer_id"],
        "CASCADE",
    )

    checks_by_table = {
        table_name: {
            constraint["name"]
            for constraint in inspector.get_check_constraints(table_name)
        }
        for table_name in (
            "manufacturer_profiles",
            "manufacturer_capability_claims",
        )
    }
    assert "ck_manufacturer_profiles_country_iso2" in checks_by_table["manufacturer_profiles"]
    assert "ck_manufacturer_profiles_account_status" in checks_by_table["manufacturer_profiles"]
    assert (
        "ck_manufacturer_capability_claims_capability_type"
        in checks_by_table["manufacturer_capability_claims"]
    )
    assert (
        "ck_manufacturer_capability_claims_lot_size_required_fields"
        in checks_by_table["manufacturer_capability_claims"]
    )
    assert (
        "ck_manufacturer_capability_claims_single_piece_minimum"
        in checks_by_table["manufacturer_capability_claims"]
    )

    indexes_by_table = {
        table_name: {index["name"] for index in inspector.get_indexes(table_name)}
        for table_name in (
            "manufacturer_profiles",
            "manufacturer_capability_claims",
        )
    }
    assert "ix_manufacturer_profiles_country" in indexes_by_table["manufacturer_profiles"]
    assert (
        "ix_manufacturer_profiles_account_status"
        in indexes_by_table["manufacturer_profiles"]
    )
    assert (
        "uq_manufacturer_capability_claims_source_window"
        in indexes_by_table["manufacturer_capability_claims"]
    )
    assert (
        "ix_manufacturer_capability_claims_manufacturer_id"
        in indexes_by_table["manufacturer_capability_claims"]
    )
    assert (
        "ix_manufacturer_capability_claims_path_material"
        in indexes_by_table["manufacturer_capability_claims"]
    )
    assert (
        "ix_manufacturer_capability_claims_small_quantity"
        in indexes_by_table["manufacturer_capability_claims"]
    )
    assert (
        "ix_manufacturer_capability_claims_atex_capable"
        in indexes_by_table["manufacturer_capability_claims"]
    )


def test_minimal_valid_profile_and_lot_size_claim_insert_succeeds(test_db_engine_at_head):
    """A manufacturer profile and small-quantity lot-size claim can be inserted."""
    with test_db_engine_at_head.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO manufacturer_profiles (
                    manufacturer_id, legal_name, display_name, slug, country,
                    size_category
                ) VALUES (
                    'mfr-small-qty-1', 'Small Quantity Seals GmbH',
                    'Small Quantity Seals', 'small-quantity-seals', 'DE',
                    'small'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO manufacturer_capability_claims (
                    claim_id, manufacturer_id, capability_type, engineering_path,
                    sealing_material_family, capability_payload, source_type,
                    source_reference, confidence, validity_from, status,
                    minimum_order_pieces, typical_minimum_pieces,
                    maximum_order_pieces, preferred_batch_min_pieces,
                    preferred_batch_max_pieces, accepts_single_pieces,
                    rapid_manufacturing_available,
                    rapid_manufacturing_surcharge_percent,
                    rapid_manufacturing_leadtime_hours, standard_leadtime_weeks
                ) VALUES (
                    'claim-small-qty-1', 'mfr-small-qty-1',
                    'lot_size_capability', 'rwdr', 'ptfe_glass_filled',
                    '{"scope":"ptfe_rwdr"}'::jsonb, 'self_declared',
                    'onboarding:test', 4, DATE '2026-04-20', 'active',
                    1, 4, 100000, 100, 10000, true,
                    true, 50, 72, 4
                )
                """
            )
        )

        claim = conn.execute(
            text(
                """
                SELECT accepts_single_pieces, minimum_order_pieces,
                       rapid_manufacturing_available,
                       rapid_manufacturing_leadtime_hours
                FROM manufacturer_capability_claims
                WHERE claim_id = 'claim-small-qty-1'
                """
            )
        ).mappings().one()
        assert claim["accepts_single_pieces"] is True
        assert claim["minimum_order_pieces"] == 1
        assert claim["rapid_manufacturing_available"] is True
        assert claim["rapid_manufacturing_leadtime_hours"] == 72


def test_duplicate_profile_slug_is_rejected(test_db_engine_at_head):
    """Profile slugs are stable public identifiers and must be unique."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO manufacturer_profiles (
                        manufacturer_id, legal_name, display_name, slug, country,
                        size_category
                    ) VALUES
                        ('mfr-dup-slug-1', 'Dup One GmbH', 'Dup One',
                         'duplicate-maker', 'DE', 'small'),
                        ('mfr-dup-slug-2', 'Dup Two GmbH', 'Dup Two',
                         'duplicate-maker', 'DE', 'small')
                    """
                )
            )


def test_claim_requires_existing_profile(test_db_engine_at_head):
    """Capability claim FKs reject orphaned manufacturer references."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO manufacturer_capability_claims (
                        claim_id, manufacturer_id, capability_type, source_type,
                        source_reference, confidence, validity_from
                    ) VALUES (
                        'claim-orphan', 'missing-mfr', 'product_family',
                        'self_declared', 'onboarding:test', 3,
                        DATE '2026-04-20'
                    )
                    """
                )
            )


def test_invalid_capability_type_is_rejected(test_db_engine_at_head):
    """Claims are limited to the Supplement v2 capability types."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO manufacturer_profiles (
                        manufacturer_id, legal_name, display_name, slug, country,
                        size_category
                    ) VALUES (
                        'mfr-bad-cap-type', 'Bad Cap GmbH', 'Bad Cap',
                        'bad-cap', 'DE', 'small'
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO manufacturer_capability_claims (
                        claim_id, manufacturer_id, capability_type, source_type,
                        source_reference, confidence, validity_from
                    ) VALUES (
                        'claim-bad-cap-type', 'mfr-bad-cap-type',
                        'marketing_superiority', 'self_declared',
                        'onboarding:test', 3, DATE '2026-04-20'
                    )
                    """
                )
            )


def test_lot_size_claim_requires_small_quantity_core_fields(test_db_engine_at_head):
    """lot_size_capability claims must carry the core Supplement v3 §47 fields."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO manufacturer_profiles (
                        manufacturer_id, legal_name, display_name, slug, country,
                        size_category
                    ) VALUES (
                        'mfr-missing-lot-fields', 'Missing Lot Fields GmbH',
                        'Missing Lot Fields', 'missing-lot-fields', 'DE', 'small'
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO manufacturer_capability_claims (
                        claim_id, manufacturer_id, capability_type, source_type,
                        source_reference, confidence, validity_from
                    ) VALUES (
                        'claim-missing-lot-fields', 'mfr-missing-lot-fields',
                        'lot_size_capability', 'self_declared',
                        'onboarding:test', 3, DATE '2026-04-20'
                    )
                    """
                )
            )


def test_accepts_single_pieces_requires_minimum_order_one(test_db_engine_at_head):
    """A single-piece claim cannot advertise a minimum order above one."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO manufacturer_profiles (
                        manufacturer_id, legal_name, display_name, slug, country,
                        size_category
                    ) VALUES (
                        'mfr-bad-single-min', 'Bad Single Min GmbH',
                        'Bad Single Min', 'bad-single-min', 'DE', 'small'
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO manufacturer_capability_claims (
                        claim_id, manufacturer_id, capability_type, source_type,
                        source_reference, confidence, validity_from,
                        minimum_order_pieces, typical_minimum_pieces,
                        maximum_order_pieces, accepts_single_pieces
                    ) VALUES (
                        'claim-bad-single-min', 'mfr-bad-single-min',
                        'lot_size_capability', 'self_declared',
                        'onboarding:test', 3, DATE '2026-04-20',
                        4, 4, 100, true
                    )
                    """
                )
            )


def test_invalid_lot_size_ranges_are_rejected(test_db_engine_at_head):
    """Lot-size ranges must be internally ordered and positive."""
    with pytest.raises(IntegrityError):
        with test_db_engine_at_head.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO manufacturer_profiles (
                        manufacturer_id, legal_name, display_name, slug, country,
                        size_category
                    ) VALUES (
                        'mfr-bad-lot-range', 'Bad Lot Range GmbH',
                        'Bad Lot Range', 'bad-lot-range', 'DE', 'small'
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO manufacturer_capability_claims (
                        claim_id, manufacturer_id, capability_type, source_type,
                        source_reference, confidence, validity_from,
                        minimum_order_pieces, typical_minimum_pieces,
                        maximum_order_pieces, preferred_batch_min_pieces,
                        preferred_batch_max_pieces, accepts_single_pieces
                    ) VALUES (
                        'claim-bad-lot-range', 'mfr-bad-lot-range',
                        'lot_size_capability', 'self_declared',
                        'onboarding:test', 3, DATE '2026-04-20',
                        10, 4, 100, 1000, 100, false
                    )
                    """
                )
            )
