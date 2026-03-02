from __future__ import annotations

import os

import pytest

# Keep this test isolated from global env/config requirements.
os.environ.setdefault("postgres_user", "test")
os.environ.setdefault("postgres_password", "test")
os.environ.setdefault("postgres_host", "localhost")
os.environ.setdefault("postgres_port", "5432")
os.environ.setdefault("postgres_db", "testdb")
os.environ.setdefault("database_url", "postgresql+asyncpg://test:test@localhost:5432/testdb")
os.environ.setdefault("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/testdb")
os.environ.setdefault("openai_api_key", "sk-test")
os.environ.setdefault("qdrant_url", "http://localhost:6333")
os.environ.setdefault("qdrant_collection", "test")
os.environ.setdefault("redis_url", "redis://localhost:6379/0")
os.environ.setdefault("nextauth_url", "http://localhost")
os.environ.setdefault("nextauth_secret", "test")
os.environ.setdefault("keycloak_issuer", "http://localhost")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_client_id", "test")
os.environ.setdefault("keycloak_client_secret", "test")
os.environ.setdefault("keycloak_expected_azp", "test")

from app.langgraph_v2.state.sealai_state import SealAIState, LiveCalcTile
from app.services.rag.state import WorkingProfile
from app.services.rag.nodes.p4_live_calc import node_p4_live_calc


def _tile_from_patch(patch: dict) -> LiveCalcTile:
    tile = patch.get("live_calc_tile")
    assert isinstance(tile, LiveCalcTile)
    return tile


def test_happy_path_kinematics() -> None:
    state = SealAIState(
        working_profile=WorkingProfile(
            d1=50,
            rpm=1500,
            pressure_max_bar=5,
            surface_hardness_hrc=60,
        )
    )

    patch = node_p4_live_calc(state)
    tile = _tile_from_patch(patch)

    assert tile.v_surface_m_s == pytest.approx(3.92699, rel=1e-4)
    assert tile.pv_value_mpa_m_s == pytest.approx(1.96349, rel=1e-4)
    assert tile.status == "ok"
    assert tile.hrc_warning is False


def test_tribology_warnings() -> None:
    state = SealAIState(
        working_profile=WorkingProfile(
            d1=50,
            rpm=1500,
            pressure_max_bar=5,
            surface_hardness_hrc=40,
        )
    )

    patch = node_p4_live_calc(state)
    tile = _tile_from_patch(patch)

    assert tile.hrc_warning is True
    assert tile.status in {"warning", "critical"}


def test_insufficient_data_handling() -> None:
    state = SealAIState(working_profile=WorkingProfile(pressure_max_bar=5))

    patch = node_p4_live_calc(state)
    tile = _tile_from_patch(patch)

    assert tile.v_surface_m_s is None
    assert tile.status == "insufficient_data"


def test_full_physics_engine() -> None:
    state = SealAIState(
        working_profile=WorkingProfile(
            d1=50.0,
            rpm=1200.0,
            pressure_max_bar=300.0,
            surface_hardness_hrc=60.0,
            shaft_d1=50.0,
            temperature_min_c=-60.0,
            temperature_max_c=80.0,
        )
    )
    # Adding fields not in WorkingProfile but used by calc (simulating extraction)
    state.extracted_params = {
        "cross_section_d2": 5.33,
        "groove_depth": 4.5,
        "groove_width": 6.0,
        "seal_inner_d": 48.5,
    }

    patch = node_p4_live_calc(state)
    tile = _tile_from_patch(patch)

    assert tile.compression_ratio_pct == pytest.approx(((5.33 - 4.5) / 5.33) * 100.0, rel=1e-4)
    assert tile.requires_backup_ring is True
    assert tile.extrusion_risk is True
    assert tile.status == "critical"


def test_chemical_resistance_integration() -> None:
    # Test NBR vs HLP (A - Recommended)
    state = SealAIState(
        working_profile=WorkingProfile(
            elastomer_material="NBR",
            medium="HLP"
        )
    )
    patch = node_p4_live_calc(state)
    tile = _tile_from_patch(patch)
    assert tile.chem_warning is False
    assert "Chemisch beständig" in tile.chem_message

    # Test NBR vs HEES (C - Exclusion with Failure Modes)
    state = SealAIState(
        working_profile=WorkingProfile(
            elastomer_material="nitril",  # Synonym
            medium="bio-öl"              # Synonym
        )
    )
    patch = node_p4_live_calc(state)
    tile = _tile_from_patch(patch)
    assert tile.chem_warning is True
    assert "Strikt ausgeschlossen" in tile.chem_message
    assert "Schrumpfung" in tile.chem_message

    # Test PTFE vs HEES (A - Recommended)
    state = SealAIState(
        working_profile=WorkingProfile(
            elastomer_material="PTFE",
            medium="HEES"
        )
    )
    patch = node_p4_live_calc(state)
    tile = _tile_from_patch(patch)
    assert tile.chem_warning is False
    assert "Chemisch beständig" in tile.chem_message

    # Test FKM vs Wasser (B - Conditional with Constraints)
    state = SealAIState(
        working_profile=WorkingProfile(
            elastomer_material="viton", # Synonym
            medium="wasser"
        )
    )
    patch = node_p4_live_calc(state)
    tile = _tile_from_patch(patch)
    assert tile.chem_warning is True
    assert "Bedingt geeignet" in tile.chem_message
    # No Hydrolyse in message because constraints are joined separately, 
    # and "Wasser" entry has failure_modes: ["Hydrolyse > 80°C"] which is B.
    # Wait, the YAML has failure_modes: ["Hydrolyse > 80°C"] for FKM vs Wasser.
    # In calc_chemical_resistance, failure_modes are only shown for Rating C.
    # For Rating B, conditions are shown. FKM vs Wasser in YAML has conditions: [].
    assert tile.chem_message == "Bedingt geeignet."

    # Test Unknown
    state = SealAIState(
        working_profile=WorkingProfile(
            elastomer_material="unobtainium",
            medium="kryptonit"
        )
    )
    patch = node_p4_live_calc(state)
    tile = _tile_from_patch(patch)
    assert tile.chem_warning is True
    assert "Unzureichende Daten" in tile.chem_message
