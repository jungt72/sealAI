"""Sprint 2 — Jinja2 template golden-file & StrictUndefined tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from jinja2 import UndefinedError

from app.services.rag.render import render_and_hash_rag, render_rag_template

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

PROFILE = {
    "medium": "Heißdampf",
    "pressure_max_bar": 40.0,
    "temperature_max_c": 400.0,
    "flange_standard": "EN 1092-1",
    "flange_dn": 150,
    "flange_pn": 40,
    "bolt_count": 12,
    "bolt_size": "M20",
}

MATERIAL = {
    "name": "Spiraldichtung 316L/Graphit",
    "family": "Spiralwound",
    "t_max_c": 550,
    "p_max_bar": 100,
    "compatible_media": ["Dampf", "Wasser", "Stickstoff"],
}

CALCULATION = {
    "safety_factor": 1.8,
    "required_bolt_load_kn": 245.0,
    "gasket_stress_mpa": 50.0,
    "notes": ["EN 13555 Anhang A angewendet", "Kriechrelaxation berücksichtigt"],
}

CRITIQUE_LOG = [
    "Temperatur nahe Materialgrenze — Sicherheitsfaktor erhöht",
    "Zyklische Belastung nicht spezifiziert",
]

SESSION_ID = "sess-abc-123"
TENANT_ID = "tenant-xyz-789"

PARTNER = {
    "name": "Freudenberg Sealing Technologies",
    "contact_email": "anfrage@fst.com",
}


def _full_engineering_context(*, is_critical: bool = False) -> dict:
    return {
        "profile": PROFILE,
        "material": MATERIAL,
        "calculation": CALCULATION,
        "critique_log": CRITIQUE_LOG,
        "is_critical_application": is_critical,
        "session_id": SESSION_ID,
    }


def _full_rfq_context(*, partner: dict | None = PARTNER, is_critical: bool = False) -> dict:
    return {
        "profile": PROFILE,
        "material": MATERIAL,
        "calculation": CALCULATION,
        "critique_log": CRITIQUE_LOG,
        "is_critical_application": is_critical,
        "partner": partner,
        "session_id": SESSION_ID,
        "tenant_id": TENANT_ID,
    }


# ===================================================================
# StrictUndefined enforcement
# ===================================================================


class TestStrictUndefined:
    """StrictUndefined must raise on every required top-level variable."""

    @pytest.mark.parametrize("missing_key", ["profile", "material", "calculation", "critique_log"])
    def test_engineering_report_missing_key(self, missing_key: str):
        ctx = _full_engineering_context()
        del ctx[missing_key]
        with pytest.raises(UndefinedError):
            render_rag_template("engineering_report.j2", ctx)

    @pytest.mark.parametrize("missing_key", ["profile", "material", "calculation", "critique_log"])
    def test_rfq_template_missing_key(self, missing_key: str):
        ctx = _full_rfq_context()
        del ctx[missing_key]
        with pytest.raises(UndefinedError):
            render_rag_template("rfq_template.j2", ctx)

    def test_watermark_missing_session_id(self):
        with pytest.raises(UndefinedError):
            render_rag_template("watermark_critical.j2", {})


# ===================================================================
# Golden-file tests
# ===================================================================


def _read_golden(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class TestGoldenFiles:
    """Rendered output must match golden files exactly."""

    def test_engineering_report(self):
        rendered = render_rag_template("engineering_report.j2", _full_engineering_context())
        assert rendered == _read_golden("golden_engineering_report.txt")

    def test_rfq_with_partner(self):
        rendered = render_rag_template("rfq_template.j2", _full_rfq_context(partner=PARTNER))
        assert rendered == _read_golden("golden_rfq_partner.txt")

    def test_rfq_neutral(self):
        rendered = render_rag_template("rfq_template.j2", _full_rfq_context(partner=None))
        assert rendered == _read_golden("golden_rfq_neutral.txt")

    def test_watermark(self):
        rendered = render_rag_template("watermark_critical.j2", {"session_id": SESSION_ID})
        assert rendered == _read_golden("golden_watermark.txt")


# ===================================================================
# Content assertions
# ===================================================================


class TestContentAssertions:
    """Verify key content appears or is absent based on flags."""

    def test_critical_application_includes_watermark(self):
        rendered = render_rag_template("engineering_report.j2", _full_engineering_context(is_critical=True))
        assert "KRITISCHER ANWENDUNGSHINWEIS" in rendered
        assert SESSION_ID in rendered

    def test_non_critical_application_excludes_watermark(self):
        rendered = render_rag_template("engineering_report.j2", _full_engineering_context(is_critical=False))
        assert "KRITISCHER ANWENDUNGSHINWEIS" not in rendered

    def test_critique_log_entries_appear(self):
        rendered = render_rag_template("engineering_report.j2", _full_engineering_context())
        for entry in CRITIQUE_LOG:
            assert entry in rendered

    def test_profile_fields_appear(self):
        rendered = render_rag_template("engineering_report.j2", _full_engineering_context())
        assert "Heißdampf" in rendered
        assert "40.0" in rendered or "40" in rendered
        assert "400.0" in rendered or "400" in rendered
        assert "EN 1092-1" in rendered
        assert "150" in rendered
        assert "M20" in rendered

    def test_rfq_partner_info_present(self):
        rendered = render_rag_template("rfq_template.j2", _full_rfq_context(partner=PARTNER))
        assert "Freudenberg Sealing Technologies" in rendered
        assert "anfrage@fst.com" in rendered

    def test_rfq_no_partner_section_when_none(self):
        rendered = render_rag_template("rfq_template.j2", _full_rfq_context(partner=None))
        assert "Freudenberg" not in rendered
        assert "anfrage@fst.com" not in rendered


# ===================================================================
# Renderer / hash tests
# ===================================================================


class TestRenderer:
    """render_rag_template and render_and_hash_rag basic contracts."""

    def test_returns_string(self):
        result = render_rag_template("watermark_critical.j2", {"session_id": SESSION_ID})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_deterministic(self):
        ctx = {"session_id": SESSION_ID}
        r1 = render_and_hash_rag("watermark_critical.j2", ctx)
        r2 = render_and_hash_rag("watermark_critical.j2", ctx)
        assert r1.hash_sha256 == r2.hash_sha256

    def test_hash_matches_manual_sha256(self):
        ctx = {"session_id": SESSION_ID}
        result = render_and_hash_rag("watermark_critical.j2", ctx)
        expected_hash = hashlib.sha256(result.rendered_text.encode("utf-8")).hexdigest()
        assert result.hash_sha256 == expected_hash

    def test_rendered_prompt_fields(self):
        ctx = _full_engineering_context()
        result = render_and_hash_rag("engineering_report.j2", ctx)
        assert result.template_name == "engineering_report.j2"
        assert result.version == "1.0.0"
        assert len(result.rendered_text) > 0
        assert len(result.hash_sha256) == 64
