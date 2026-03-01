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
from app.mcp.calculations.material_limits import get_limits, check


# ──────────────────────────────────────────────────────────────────────────────
# get_limits — Grunddaten
# ──────────────────────────────────────────────────────────────────────────────

def test_fkm_limits():
    limits = get_limits("FKM")
    assert limits.temp_max_c == 200
    assert limits.aed_certifiable is True


def test_epdm_not_aed():
    limits = get_limits("EPDM")
    assert limits.aed_certifiable is False


def test_alias_viton():
    limits = get_limits("viton")
    assert limits.name == "FKM"


def test_alias_silikon():
    limits = get_limits("silikon")
    assert limits.name == "VMQ"


def test_alias_kalrez():
    limits = get_limits("kalrez")
    assert limits.name == "FFKM"


def test_unknown_material_raises():
    with pytest.raises(KeyError, match="unbekannt"):
        get_limits("XUNOKNOWN")


def test_all_eight_materials():
    for mat in ["NBR", "FKM", "EPDM", "PTFE", "HNBR", "FFKM", "CR", "VMQ"]:
        lim = get_limits(mat)
        assert lim.temp_min_c < lim.temp_max_c < lim.temp_peak_c
        assert lim.pressure_static_max_bar >= lim.pressure_dynamic_max_bar


# ──────────────────────────────────────────────────────────────────────────────
# check — Temperaturprüfung
# ──────────────────────────────────────────────────────────────────────────────

def test_check_temp_ok():
    r = check("FKM", temp_c=180.0)
    assert r.temp_ok is True


def test_check_temp_warning():
    # FKM: max_c=200, peak_c=230 → 215 °C liegt im Kurzzeitbereich
    r = check("FKM", temp_c=215.0)
    assert r.temp_ok == "warning"
    assert any("Kurzzeitbereich" in w for w in r.warnings)


def test_check_temp_nok():
    # NBR: peak_c=140 → 160 °C = NOK
    r = check("NBR", temp_c=160.0)
    assert r.temp_ok is False


def test_check_temp_cold_nok():
    # FKM: min_c=-20 → -30 °C = NOK
    r = check("FKM", temp_c=-30.0)
    assert r.temp_ok is False
    assert any("Kältegrenze" in w for w in r.warnings)


def test_check_temp_none_when_not_given():
    r = check("NBR")
    assert r.temp_ok is None


# ──────────────────────────────────────────────────────────────────────────────
# check — Druckprüfung
# ──────────────────────────────────────────────────────────────────────────────

def test_check_pressure_dynamic_nok():
    # VMQ dynamisch max = 50 bar → 80 bar = False
    r = check("VMQ", pressure_bar=80.0, is_dynamic=True)
    assert r.pressure_ok is False


def test_check_pressure_dynamic_ok():
    # VMQ dynamisch max = 50 bar → 30 bar = True
    r = check("VMQ", pressure_bar=30.0, is_dynamic=True)
    assert r.pressure_ok is True


def test_check_pressure_static_ok():
    # HNBR statisch max = 700 bar → 400 bar = True
    r = check("HNBR", pressure_bar=400.0, is_dynamic=False)
    assert r.pressure_ok is True


def test_check_pressure_static_nok():
    # CR statisch max = 200 bar → 250 bar = False
    r = check("CR", pressure_bar=250.0, is_dynamic=False)
    assert r.pressure_ok is False
    assert any("statisches" in w for w in r.warnings)


def test_check_pressure_none_when_not_given():
    r = check("FKM")
    assert r.pressure_ok is None


# ──────────────────────────────────────────────────────────────────────────────
# check — AED-Prüfung
# ──────────────────────────────────────────────────────────────────────────────

def test_check_aed_fail():
    r = check("EPDM", aed_required=True)
    assert r.aed_ok is False
    assert any("AED" in w for w in r.warnings)


def test_check_aed_pass():
    r = check("FKM", aed_required=True)
    assert r.aed_ok is True


def test_check_aed_none_when_not_required():
    r = check("EPDM", aed_required=False)
    assert r.aed_ok is None


def test_check_aed_vmq_fail():
    r = check("VMQ", aed_required=True)
    assert r.aed_ok is False


def test_check_aed_hnbr_pass():
    r = check("HNBR", aed_required=True)
    assert r.aed_ok is True


# ──────────────────────────────────────────────────────────────────────────────
# check — Kombination + Recommendation
# ──────────────────────────────────────────────────────────────────────────────

def test_check_combined_blocker():
    # NBR bei 160 °C + 300 bar dynamisch + AED → alle drei NOK
    r = check("NBR", temp_c=160.0, pressure_bar=300.0, is_dynamic=True, aed_required=False)
    assert r.temp_ok is False
    assert r.pressure_ok is False
    assert "BLOCKER" in r.recommendation


def test_check_all_ok_recommendation():
    r = check("HNBR", temp_c=100.0, pressure_bar=200.0, is_dynamic=False, aed_required=True)
    assert r.temp_ok is True
    assert r.pressure_ok is True
    assert r.aed_ok is True
    assert "erfüllt" in r.recommendation


def test_check_no_params_recommendation():
    r = check("FKM")
    assert "verfügbar" in r.recommendation
