from __future__ import annotations

import os

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

from app.mcp.calculations.compliance import (
    ComplianceFlag,
    ComplianceResult,
    FlagResult,
    check_compliance,
)


# ──────────────────────────────────────────────────────────────────────────────
# Tests aus der Aufgabenstellung
# ──────────────────────────────────────────────────────────────────────────────

def test_nbr_fda_blocked():
    r = check_compliance("NBR", flags=[ComplianceFlag.FDA])
    fda = next(f for f in r.flag_results if f.flag == ComplianceFlag.FDA)
    assert not fda.passed
    assert fda.severity == "blocker"


def test_ptfe_fda_ok():
    r = check_compliance("PTFE", flags=[ComplianceFlag.FDA])
    fda = next(f for f in r.flag_results if f.flag == ComplianceFlag.FDA)
    assert fda.passed


def test_vmq_norsok_blocked():
    r = check_compliance("VMQ", medium="H2", flags=[ComplianceFlag.NORSOK])
    norsok = next(f for f in r.flag_results if f.flag == ComplianceFlag.NORSOK)
    assert not norsok.passed


def test_norsok_no_sour_medium_passes():
    r = check_compliance("NBR", medium="Wasser", flags=[ComplianceFlag.NORSOK])
    norsok = next(f for f in r.flag_results if f.flag == ComplianceFlag.NORSOK)
    assert norsok.passed  # kein Sour-Medium


def test_is_critical_high_pressure():
    r = check_compliance("FKM", pressure_bar=150.0)
    assert r.is_critical_application is True


def test_aed_epdm_blocked():
    r = check_compliance("EPDM", flags=[ComplianceFlag.AED])
    aed = next(f for f in r.flag_results if f.flag == ComplianceFlag.AED)
    assert not aed.passed


# ──────────────────────────────────────────────────────────────────────────────
# Erweiterte Tests
# ──────────────────────────────────────────────────────────────────────────────

def test_ffkm_fda_ok():
    r = check_compliance("FFKM", flags=[ComplianceFlag.FDA])
    fda = next(f for f in r.flag_results if f.flag == ComplianceFlag.FDA)
    assert fda.passed
    assert fda.severity == "ok"


def test_fkm_fda_warning():
    r = check_compliance("FKM", flags=[ComplianceFlag.FDA])
    fda = next(f for f in r.flag_results if f.flag == ComplianceFlag.FDA)
    assert fda.passed
    assert fda.severity == "warning"


def test_cr_fda_blocked():
    r = check_compliance("CR", flags=[ComplianceFlag.FDA])
    fda = next(f for f in r.flag_results if f.flag == ComplianceFlag.FDA)
    assert not fda.passed
    assert fda.severity == "blocker"


def test_nbr_ehedg_blocked():
    r = check_compliance("NBR", flags=[ComplianceFlag.EHEDG])
    ehedg = next(f for f in r.flag_results if f.flag == ComplianceFlag.EHEDG)
    assert not ehedg.passed
    assert ehedg.severity == "blocker"


def test_vmq_ehedg_ok():
    r = check_compliance("VMQ", flags=[ComplianceFlag.EHEDG])
    ehedg = next(f for f in r.flag_results if f.flag == ComplianceFlag.EHEDG)
    assert ehedg.passed
    assert ehedg.severity == "ok"


def test_fkm_ta_luft_ok():
    r = check_compliance("FKM", flags=[ComplianceFlag.TA_LUFT])
    ta = next(f for f in r.flag_results if f.flag == ComplianceFlag.TA_LUFT)
    assert ta.passed


def test_epdm_ta_luft_blocked():
    r = check_compliance("EPDM", flags=[ComplianceFlag.TA_LUFT])
    ta = next(f for f in r.flag_results if f.flag == ComplianceFlag.TA_LUFT)
    assert not ta.passed
    assert ta.severity == "blocker"


def test_vmq_aed_blocked():
    r = check_compliance("VMQ", flags=[ComplianceFlag.AED])
    aed = next(f for f in r.flag_results if f.flag == ComplianceFlag.AED)
    assert not aed.passed


def test_hnbr_aed_ok():
    r = check_compliance("HNBR", flags=[ComplianceFlag.AED])
    aed = next(f for f in r.flag_results if f.flag == ComplianceFlag.AED)
    assert aed.passed


def test_atex_nonflammable_medium_ok():
    r = check_compliance("NBR", medium="Wasser", flags=[ComplianceFlag.ATEX])
    atex = next(f for f in r.flag_results if f.flag == ComplianceFlag.ATEX)
    assert atex.passed
    assert atex.severity == "ok"


def test_atex_flammable_medium_warning():
    r = check_compliance("NBR", medium="H2", flags=[ComplianceFlag.ATEX])
    atex = next(f for f in r.flag_results if f.flag == ComplianceFlag.ATEX)
    assert atex.passed
    assert atex.severity == "warning"


def test_atex_ptfe_flammable_warning():
    r = check_compliance("PTFE", medium="ethanol", flags=[ComplianceFlag.ATEX])
    atex = next(f for f in r.flag_results if f.flag == ComplianceFlag.ATEX)
    assert atex.passed
    assert atex.severity == "warning"
    assert "antistatisch" in atex.reasons[0]


def test_ped_below_threshold_ok():
    r = check_compliance("FKM", pressure_bar=0.3, flags=[ComplianceFlag.PED])
    ped = next(f for f in r.flag_results if f.flag == ComplianceFlag.PED)
    assert ped.passed
    assert ped.severity == "ok"


def test_ped_group1_warning():
    r = check_compliance("FKM", medium="H2", pressure_bar=50.0, flags=[ComplianceFlag.PED])
    ped = next(f for f in r.flag_results if f.flag == ComplianceFlag.PED)
    assert ped.passed
    assert ped.severity == "warning"


def test_ped_group2_ok():
    r = check_compliance("NBR", medium="Wasser", pressure_bar=50.0, flags=[ComplianceFlag.PED])
    ped = next(f for f in r.flag_results if f.flag == ComplianceFlag.PED)
    assert ped.passed
    assert ped.severity == "ok"


def test_norsok_hnbr_h2_ok():
    r = check_compliance("HNBR", medium="H2", flags=[ComplianceFlag.NORSOK])
    norsok = next(f for f in r.flag_results if f.flag == ComplianceFlag.NORSOK)
    assert norsok.passed
    assert norsok.severity == "ok"


def test_norsok_nbr_sour_warning():
    r = check_compliance("NBR", medium="H2", flags=[ComplianceFlag.NORSOK])
    norsok = next(f for f in r.flag_results if f.flag == ComplianceFlag.NORSOK)
    assert norsok.passed
    assert norsok.severity == "warning"


def test_is_critical_h2_medium():
    r = check_compliance("FKM", medium="H2")
    assert r.is_critical_application is True


def test_is_critical_high_temp():
    r = check_compliance("FFKM", temp_c=450.0)
    assert r.is_critical_application is True


def test_is_critical_low_temp():
    r = check_compliance("VMQ", temp_c=-60.0)
    assert r.is_critical_application is True


def test_is_not_critical_normal_conditions():
    r = check_compliance("NBR", medium="Wasser", temp_c=80.0, pressure_bar=10.0)
    assert r.is_critical_application is False


def test_no_flags_returns_empty_results():
    r = check_compliance("FKM")
    assert r.flag_results == []
    assert r.overall_passed is True


def test_multiple_flags_aggregated():
    r = check_compliance(
        "NBR",
        flags=[ComplianceFlag.FDA, ComplianceFlag.AED, ComplianceFlag.TA_LUFT],
    )
    assert len(r.flag_results) == 3
    # FDA blocked, AED ok, TA_LUFT ok
    assert not r.overall_passed
    assert len(r.blockers) >= 1


def test_alias_viton_fkm():
    r = check_compliance("Viton", flags=[ComplianceFlag.FDA])
    fda = next(f for f in r.flag_results if f.flag == ComplianceFlag.FDA)
    assert fda.passed  # Viton → FKM → warning → passed=True


def test_unknown_material_raises():
    import pytest
    with pytest.raises(KeyError):
        check_compliance("Unobtainium")


def test_result_material_normalized():
    r = check_compliance("viton")
    assert r.material == "FKM"


def test_norm_ref_populated():
    r = check_compliance("NBR", flags=[ComplianceFlag.FDA])
    fda = next(f for f in r.flag_results if f.flag == ComplianceFlag.FDA)
    assert "21 CFR" in fda.norm_ref
