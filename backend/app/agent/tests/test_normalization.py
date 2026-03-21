"""
Unit tests for Phase 0B.3 — Normalization Layer V1.

Tests cover:
1. MappingConfidence enum values
2. NormalizedEntity dataclass
3. Temperature normalization: °F→°C conversion, native °C pass-through, unrecognised input
4. Pressure normalization: bar, psi, MPa, kPa conversions; unrecognised input
5. Material normalization: confirmed canonical names, estimated synonyms, trade name confirmation
6. Medium normalization: confirmed, estimated, and REQUIRES_CONFIRMATION (Heißdampf, Dampf)
7. normalize_parameter() dispatch and unknown domain_type fallback
8. Confidence bridge helpers (confidence_to_identity_class, confidence_to_normalization_certainty)
9. Backward-compat layer (NormalizationDecision, extract_parameters) still works
10. Integration: normalize_parameter drives identity_class in logic.py style
"""
from __future__ import annotations

import math
import pytest

from app.agent.domain.normalization import (
    MappingConfidence,
    NormalizedEntity,
    normalize_parameter,
    confidence_to_identity_class,
    confidence_to_normalization_certainty,
    # backward-compat
    NormalizationDecision,
    normalize_material_decision,
    normalize_medium_decision,
    normalize_unit_value,
    extract_parameters,
)


# ---------------------------------------------------------------------------
# 1. MappingConfidence
# ---------------------------------------------------------------------------

class TestMappingConfidence:
    def test_all_four_values_exist(self):
        assert MappingConfidence.CONFIRMED
        assert MappingConfidence.ESTIMATED
        assert MappingConfidence.INFERRED
        assert MappingConfidence.REQUIRES_CONFIRMATION

    def test_is_str_enum(self):
        assert isinstance(MappingConfidence.CONFIRMED, str)
        assert MappingConfidence.CONFIRMED == "confirmed"
        assert MappingConfidence.REQUIRES_CONFIRMATION == "requires_confirmation"

    def test_ordering_by_value_string(self):
        """Just ensure they are distinct and not equal to each other."""
        values = {c.value for c in MappingConfidence}
        assert len(values) == 4


# ---------------------------------------------------------------------------
# 2. NormalizedEntity
# ---------------------------------------------------------------------------

class TestNormalizedEntity:
    def test_required_fields(self):
        e = NormalizedEntity(
            raw_value="Viton",
            normalized_value="FKM",
            domain_type="material",
            confidence=MappingConfidence.REQUIRES_CONFIRMATION,
            warning_message="trade_name:viton",
        )
        assert e.raw_value == "Viton"
        assert e.normalized_value == "FKM"
        assert e.domain_type == "material"
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION
        assert "viton" in e.warning_message

    def test_warning_message_optional(self):
        e = NormalizedEntity("NBR", "NBR", "material", MappingConfidence.CONFIRMED)
        assert e.warning_message is None

    def test_frozen(self):
        e = NormalizedEntity("x", "y", "material", MappingConfidence.CONFIRMED)
        with pytest.raises((AttributeError, TypeError)):
            e.raw_value = "z"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. Temperature normalization
# ---------------------------------------------------------------------------

class TestTemperatureNormalization:
    def test_celsius_string_passed_through(self):
        e = normalize_parameter("temperature", "200°C")
        assert e.confidence == MappingConfidence.CONFIRMED
        assert e.normalized_value == 200.0
        assert e.domain_type == "temperature"

    def test_celsius_without_degree_symbol(self):
        e = normalize_parameter("temperature", "200C")
        assert e.normalized_value == 200.0
        assert e.confidence == MappingConfidence.CONFIRMED

    def test_fahrenheit_to_celsius_conversion(self):
        """400°F → 204.44°C (±0.1°C tolerance)."""
        e = normalize_parameter("temperature", "400°F")
        assert e.confidence == MappingConfidence.CONFIRMED
        assert e.normalized_value is not None
        assert abs(e.normalized_value - 204.44) < 0.1

    def test_fahrenheit_32_to_0_celsius(self):
        e = normalize_parameter("temperature", "32°F")
        assert e.normalized_value is not None
        assert abs(e.normalized_value - 0.0) < 0.01

    def test_fahrenheit_212_to_100_celsius(self):
        e = normalize_parameter("temperature", "212F")
        assert e.normalized_value is not None
        assert abs(e.normalized_value - 100.0) < 0.01

    def test_negative_fahrenheit(self):
        e = normalize_parameter("temperature", "-40°F")
        assert e.normalized_value is not None
        # -40°F == -40°C
        assert abs(e.normalized_value - (-40.0)) < 0.01

    def test_bare_number_assumed_celsius(self):
        e = normalize_parameter("temperature", 150.0)
        assert e.normalized_value == 150.0
        assert e.confidence == MappingConfidence.CONFIRMED

    def test_unrecognised_format_requires_confirmation(self):
        e = normalize_parameter("temperature", "hot")
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION
        assert e.normalized_value is None

    def test_warning_message_on_fahrenheit_conversion(self):
        e = normalize_parameter("temperature", "400°F")
        assert e.warning_message is not None
        assert "204" in e.warning_message  # shows the Celsius value


# ---------------------------------------------------------------------------
# 4. Pressure normalization
# ---------------------------------------------------------------------------

class TestPressureNormalization:
    def test_bar_passthrough(self):
        e = normalize_parameter("pressure", "100 bar")
        assert e.confidence == MappingConfidence.CONFIRMED
        assert e.normalized_value == 100.0

    def test_psi_to_bar(self):
        """100 psi ≈ 6.89 bar (±0.01)."""
        e = normalize_parameter("pressure", "100 psi")
        assert e.confidence == MappingConfidence.CONFIRMED
        assert e.normalized_value is not None
        assert abs(e.normalized_value - 6.89476) < 0.01

    def test_mpa_to_bar(self):
        """1.5 MPa = 15 bar."""
        e = normalize_parameter("pressure", "1.5 MPa")
        assert e.confidence == MappingConfidence.CONFIRMED
        assert e.normalized_value is not None
        assert abs(e.normalized_value - 15.0) < 0.01

    def test_kpa_to_bar(self):
        """500 kPa = 5 bar."""
        e = normalize_parameter("pressure", "500 kPa")
        assert e.confidence == MappingConfidence.CONFIRMED
        assert e.normalized_value is not None
        assert abs(e.normalized_value - 5.0) < 0.01

    def test_bare_number_assumed_bar(self):
        e = normalize_parameter("pressure", 25.0)
        assert e.normalized_value == 25.0

    def test_unrecognised_format_requires_confirmation(self):
        e = normalize_parameter("pressure", "sehr hoch")
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION
        assert e.normalized_value is None

    def test_no_warning_for_bar(self):
        e = normalize_parameter("pressure", "10 bar")
        assert e.warning_message is None

    def test_warning_present_for_unit_conversion(self):
        e = normalize_parameter("pressure", "100 psi")
        assert e.warning_message is not None


# ---------------------------------------------------------------------------
# 5. Material normalization
# ---------------------------------------------------------------------------

class TestMaterialNormalization:
    @pytest.mark.parametrize("raw, expected_canonical", [
        ("NBR",    "NBR"),
        ("nbr",    "NBR"),
        ("PTFE",   "PTFE"),
        ("FKM",    "FKM"),
        ("FFKM",   "FFKM"),
        ("EPDM",   "EPDM"),
        ("SILIKON", "SILIKON"),
        ("HNBR",   "HNBR"),
    ])
    def test_confirmed_canonical_materials(self, raw, expected_canonical):
        e = normalize_parameter("material", raw)
        assert e.normalized_value == expected_canonical
        assert e.confidence == MappingConfidence.CONFIRMED

    def test_nitril_is_estimated_synonym_for_nbr(self):
        e = normalize_parameter("material", "Nitril")
        assert e.normalized_value == "NBR"
        assert e.confidence == MappingConfidence.ESTIMATED
        assert e.warning_message is not None

    def test_nitrilkautschuk_is_estimated_synonym_for_nbr(self):
        e = normalize_parameter("material", "Nitrilkautschuk")
        assert e.normalized_value == "NBR"
        assert e.confidence == MappingConfidence.ESTIMATED

    def test_viton_requires_confirmation_maps_to_fkm(self):
        """Viton → FKM but requires confirmation (compound-specific trade name)."""
        e = normalize_parameter("material", "Viton")
        assert e.normalized_value == "FKM"
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION
        assert e.warning_message is not None
        assert "viton" in e.warning_message.lower()

    def test_viton_lowercase_works(self):
        e = normalize_parameter("material", "viton")
        assert e.normalized_value == "FKM"
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION

    def test_kalrez_requires_confirmation_maps_to_ffkm(self):
        e = normalize_parameter("material", "Kalrez")
        assert e.normalized_value == "FFKM"
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION

    def test_teflon_requires_confirmation_maps_to_ptfe(self):
        e = normalize_parameter("material", "Teflon")
        assert e.normalized_value == "PTFE"
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION

    def test_unknown_material_returns_inferred(self):
        e = normalize_parameter("material", "Unobtainium")
        assert e.confidence == MappingConfidence.INFERRED
        assert e.normalized_value is None


# ---------------------------------------------------------------------------
# 6. Medium normalization
# ---------------------------------------------------------------------------

class TestMediumNormalization:
    @pytest.mark.parametrize("raw, expected_canonical", [
        ("Wasser",    "Wasser"),
        ("water",     "Wasser"),
        ("Druckluft", "Druckluft"),
        ("Stickstoff","Stickstoff"),
        ("nitrogen",  "Stickstoff"),
    ])
    def test_confirmed_media(self, raw, expected_canonical):
        e = normalize_parameter("medium", raw)
        assert e.normalized_value == expected_canonical
        assert e.confidence == MappingConfidence.CONFIRMED

    def test_oil_is_estimated(self):
        e = normalize_parameter("medium", "Öl")
        assert e.normalized_value == "Öl"
        assert e.confidence == MappingConfidence.ESTIMATED

    def test_hydraulikoel_is_estimated(self):
        e = normalize_parameter("medium", "Hydrauliköl")
        assert e.confidence == MappingConfidence.ESTIMATED

    def test_heissdampf_requires_confirmation(self):
        """Heißdampf is phase-aware and MUST trigger a confirmation gate."""
        e = normalize_parameter("medium", "Heißdampf")
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION
        assert e.normalized_value == "Dampf"
        assert e.warning_message is not None
        assert "Dampf" in e.warning_message or "dampf" in e.warning_message.lower()

    def test_dampf_requires_confirmation(self):
        e = normalize_parameter("medium", "Dampf")
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION

    def test_steam_requires_confirmation(self):
        e = normalize_parameter("medium", "steam")
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION

    def test_saeure_requires_confirmation(self):
        e = normalize_parameter("medium", "Säure")
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION

    def test_panolin_requires_confirmation(self):
        e = normalize_parameter("medium", "panolin")
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION

    def test_unknown_medium_returns_inferred(self):
        e = normalize_parameter("medium", "Flüssigkristall")
        assert e.confidence == MappingConfidence.INFERRED
        assert e.normalized_value is None


# ---------------------------------------------------------------------------
# 7. normalize_parameter() dispatch
# ---------------------------------------------------------------------------

class TestNormalizeParameterDispatch:
    def test_dispatches_to_material(self):
        e = normalize_parameter("material", "NBR")
        assert e.domain_type == "material"

    def test_dispatches_to_temperature(self):
        e = normalize_parameter("temperature", "200°C")
        assert e.domain_type == "temperature"

    def test_dispatches_to_pressure(self):
        e = normalize_parameter("pressure", "10 bar")
        assert e.domain_type == "pressure"

    def test_dispatches_to_medium(self):
        e = normalize_parameter("medium", "Wasser")
        assert e.domain_type == "medium"

    def test_unknown_domain_type_returns_inferred(self):
        e = normalize_parameter("speed", "1500 rpm")
        assert e.confidence == MappingConfidence.INFERRED
        assert e.domain_type == "speed"
        # passes value through
        assert e.normalized_value == "1500 rpm"

    def test_never_raises_for_none_value(self):
        for dt in ("material", "temperature", "pressure", "medium"):
            e = normalize_parameter(dt, None)
            assert e.confidence in (MappingConfidence.REQUIRES_CONFIRMATION, MappingConfidence.INFERRED)


# ---------------------------------------------------------------------------
# 8. Confidence bridge helpers
# ---------------------------------------------------------------------------

class TestConfidenceBridgeHelpers:
    @pytest.mark.parametrize("confidence, expected_class", [
        (MappingConfidence.CONFIRMED,             "identity_confirmed"),
        (MappingConfidence.ESTIMATED,             "identity_probable"),
        (MappingConfidence.INFERRED,              "identity_probable"),
        (MappingConfidence.REQUIRES_CONFIRMATION, "identity_unresolved"),
    ])
    def test_confidence_to_identity_class(self, confidence, expected_class):
        assert confidence_to_identity_class(confidence) == expected_class

    @pytest.mark.parametrize("confidence, expected_certainty", [
        (MappingConfidence.CONFIRMED,             "explicit_value"),
        (MappingConfidence.ESTIMATED,             "inferred"),
        (MappingConfidence.INFERRED,              "ambiguous"),
        (MappingConfidence.REQUIRES_CONFIRMATION, "ambiguous"),
    ])
    def test_confidence_to_normalization_certainty(self, confidence, expected_certainty):
        assert confidence_to_normalization_certainty(confidence) == expected_certainty


# ---------------------------------------------------------------------------
# 9. Backward-compat layer
# ---------------------------------------------------------------------------

class TestBackwardCompatLayer:
    def test_normalize_material_decision_confirmed(self):
        d = normalize_material_decision("FKM")
        assert isinstance(d, NormalizationDecision)
        assert d.canonical_value == "FKM"
        assert d.status == "confirmed"

    def test_normalize_material_decision_viton_confirmation_required(self):
        d = normalize_material_decision("viton")
        assert d.status == "confirmation_required"
        assert d.canonical_value == "FKM"

    def test_normalize_medium_decision_wasser_confirmed(self):
        d = normalize_medium_decision("Wasser")
        assert d.canonical_value == "Wasser"
        assert d.status == "confirmed"

    def test_normalize_unit_value_psi_to_bar(self):
        bar, unit = normalize_unit_value(14.5038, "psi")
        assert unit == "bar"
        assert abs(bar - 1.0) < 0.01

    def test_normalize_unit_value_f_to_c(self):
        c, unit = normalize_unit_value(212, "F")
        assert unit == "C"
        assert abs(c - 100.0) < 0.01

    def test_extract_parameters_temperature(self):
        result = extract_parameters("Temperatur 150°C bei 20 bar Druck")
        assert "temperature_c" in result
        assert abs(result["temperature_c"] - 150.0) < 0.1

    def test_extract_parameters_pressure(self):
        result = extract_parameters("Betriebsdruck 200 bar")
        assert "pressure_bar" in result
        assert abs(result["pressure_bar"] - 200.0) < 0.1

    def test_extract_parameters_viton_confirmation(self):
        result = extract_parameters("Wir verwenden Viton als Dichtungswerkstoff")
        assert "material_confirmation_required" in result
        assert result["material_confirmation_required"] == "FKM"


# ---------------------------------------------------------------------------
# 10. Key domain scenarios (regression guard)
# ---------------------------------------------------------------------------

class TestDomainScenarios:
    def test_400f_to_celsius(self):
        """Canonical test case from the Umbauplan: 400°F → 204.4°C."""
        e = normalize_parameter("temperature", "400°F")
        assert e.normalized_value is not None
        assert abs(e.normalized_value - 204.44) < 0.1

    def test_viton_to_fkm_with_confirmation_required(self):
        """Canonical test case: Viton → FKM, REQUIRES_CONFIRMATION."""
        e = normalize_parameter("material", "Viton")
        assert e.normalized_value == "FKM"
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION

    def test_heissdampf_triggers_requires_confirmation(self):
        """Canonical test case: Heißdampf → REQUIRES_CONFIRMATION (phase-aware)."""
        e = normalize_parameter("medium", "Heißdampf")
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION

    def test_50_psi_to_bar(self):
        """50 psi ≈ 3.447 bar."""
        e = normalize_parameter("pressure", "50 psi")
        assert e.normalized_value is not None
        assert abs(e.normalized_value - 3.447) < 0.01

    def test_kalrez_to_ffkm_with_confirmation_required(self):
        e = normalize_parameter("material", "Kalrez")
        assert e.normalized_value == "FFKM"
        assert e.confidence == MappingConfidence.REQUIRES_CONFIRMATION

    def test_nitril_estimated_synonym_for_nbr(self):
        e = normalize_parameter("material", "Nitril")
        assert e.normalized_value == "NBR"
        assert e.confidence == MappingConfidence.ESTIMATED
