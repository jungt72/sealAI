from __future__ import annotations

import os

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

import pytest
from app.mcp.calculations.chemical_resistance import (
    lookup,
    get_compatible_materials,
)


# ──────────────────────────────────────────────────────────────────────────────
# Kernbewertungen: A/B/C korrekt
# ──────────────────────────────────────────────────────────────────────────────

def test_nbr_hydraulic_oil_a():
    """NBR in Hydrauliköl HLP → A (Standardanwendung)"""
    r = lookup("HLP", "NBR")
    assert r.rating == "A"
    assert r.material == "NBR"


def test_epdm_mineral_oil_blocked():
    """EPDM in Hydrauliköl → C (quillt stark in Mineralöl)"""
    r = lookup("hydrauliköl", "EPDM")
    assert r.rating == "C"


def test_fkm_steam_blocked():
    """FKM in Dampf → C (Hydrolyse)"""
    r = lookup("Dampf", "FKM")
    assert r.rating == "C"


def test_epdm_steam_ok():
    """EPDM in Dampf → A (beste Dampfbeständigkeit)"""
    r = lookup("steam", "EPDM")
    assert r.rating == "A"
    assert r.temp_limit_c == 150


def test_ffkm_acetone_a():
    """FFKM in Aceton → A (universell beständig)"""
    r = lookup("Aceton", "FFKM")
    assert r.rating == "A"


def test_nbr_o2_blocked():
    """NBR in O₂ → C (Brandgefahr)"""
    r = lookup("O2", "NBR")
    assert r.rating == "C"
    assert "BAM" in r.source or "ASTM" in r.source


def test_hnbr_h2_ok():
    """HNBR in H₂ → A (ISO 23936-2, RGD-beständig)"""
    r = lookup("H2", "HNBR")
    assert r.rating == "A"
    assert "ISO 23936-2" in r.source


# ──────────────────────────────────────────────────────────────────────────────
# Alias-Auflösung (DE/EN, Trivialname)
# ──────────────────────────────────────────────────────────────────────────────

def test_alias_de_natronlauge_viton():
    """Alias 'natronlauge' + 'viton' → FKM × NaOH = C"""
    r = lookup("natronlauge", "viton")
    assert r.rating == "C"
    assert r.material == "FKM"


def test_alias_en_hydrogen_kalrez():
    """Alias 'hydrogen' + 'kalrez' → FFKM × H₂ = A"""
    r = lookup("hydrogen", "kalrez")
    assert r.rating == "A"
    assert r.material == "FFKM"


# ──────────────────────────────────────────────────────────────────────────────
# get_compatible_materials
# ──────────────────────────────────────────────────────────────────────────────

def test_compatible_materials_steam():
    """
    Dampf: A-Werkstoffe = EPDM, PTFE, FFKM; B = HNBR
    C-Werkstoffe dürfen NICHT enthalten sein.
    """
    results = get_compatible_materials("Dampf")
    ratings = {r.material: r.rating for r in results}

    assert ratings.get("EPDM") == "A"
    assert ratings.get("PTFE") == "A"
    assert ratings.get("FFKM") == "A"
    assert ratings.get("HNBR") == "B"

    # C-Werkstoffe ausgeschlossen
    assert "NBR" not in ratings
    assert "FKM" not in ratings
    assert "CR" not in ratings
    assert "VMQ" not in ratings

    # Reihenfolge: alle A vor allen B
    rating_list = [r.rating for r in results]
    last_a = max((i for i, v in enumerate(rating_list) if v == "A"), default=-1)
    first_b = min((i for i, v in enumerate(rating_list) if v == "B"), default=len(rating_list))
    assert last_a < first_b, "A-Einträge müssen vor B-Einträgen kommen"


# ──────────────────────────────────────────────────────────────────────────────
# Fehlerbehandlung
# ──────────────────────────────────────────────────────────────────────────────

def test_unknown_medium_raises():
    """Unbekanntes Medium → KeyError"""
    with pytest.raises(KeyError, match="Meerwasser"):
        lookup("Meerwasser", "NBR")


def test_unknown_material_raises():
    """Unbekannter Werkstoff → KeyError"""
    with pytest.raises(KeyError, match="PVC"):
        lookup("Wasser", "PVC")
