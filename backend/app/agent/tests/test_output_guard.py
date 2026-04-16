"""
Tests for Fast-Path Output Guard — Phase 0C.1

Covers all three violation categories (manufacturer, recommendation, suitability)
and verifies clean output passes through unchanged.
"""
import pytest

from app.agent.agent.output_guard import (
    FAST_PATH_GUARD_FALLBACK,
    check_fast_path_output,
)


# ---------------------------------------------------------------------------
# Violation: manufacturer name
# ---------------------------------------------------------------------------

class TestManufacturerViolations:
    def test_freudenberg_blocked(self):
        safe, cat = check_fast_path_output("Freudenberg bietet dafür passende Produkte an.")
        assert safe is False
        assert cat == "manufacturer"

    def test_skf_blocked(self):
        safe, cat = check_fast_path_output("Das könnte SKF lösen.")
        assert safe is False
        assert cat == "manufacturer"

    def test_parker_hannifin_blocked(self):
        safe, cat = check_fast_path_output("Parker Hannifin ist hier gut aufgestellt.")
        assert safe is False
        assert cat == "manufacturer"

    def test_trelleborg_blocked(self):
        safe, cat = check_fast_path_output("Trelleborg hat solche Dichtringe im Programm.")
        assert safe is False
        assert cat == "manufacturer"

    def test_manufacturer_case_insensitive(self):
        safe, cat = check_fast_path_output("freudenberg stellt das her.")
        assert safe is False
        assert cat == "manufacturer"


# ---------------------------------------------------------------------------
# Violation: recommendation language
# ---------------------------------------------------------------------------

class TestRecommendationViolations:
    def test_empfehlen_blocked(self):
        safe, cat = check_fast_path_output("Ich empfehle FKM für diesen Fall.")
        assert safe is False
        assert cat == "recommendation"

    def test_empfohlen_blocked(self):
        safe, cat = check_fast_path_output("NBR wird hier empfohlen.")
        assert safe is False
        assert cat == "recommendation"

    def test_schlage_vor_blocked(self):
        safe, cat = check_fast_path_output("Ich schlage vor, EPDM zu verwenden.")
        assert safe is False
        assert cat == "recommendation"

    def test_sollte_verwenden_blocked(self):
        safe, cat = check_fast_path_output("Sie sollten HNBR einsetzen.")
        assert safe is False
        assert cat == "recommendation"

    def test_am_besten_waehlen_blocked(self):
        safe, cat = check_fast_path_output("Am besten wählen Sie FKM.")
        assert safe is False
        assert cat == "recommendation"


# ---------------------------------------------------------------------------
# Violation: suitability assertion
# ---------------------------------------------------------------------------

class TestSuitabilityViolations:
    def test_geeignet_blocked(self):
        safe, cat = check_fast_path_output("FKM ist gut geeignet für dieses Medium.")
        assert safe is False
        assert cat == "suitability"

    def test_ideal_fuer_blocked(self):
        safe, cat = check_fast_path_output("PTFE ist ideal für aggressive Medien.")
        assert safe is False
        assert cat == "suitability"

    def test_kein_problem_blocked(self):
        safe, cat = check_fast_path_output("Das ist kein Problem bei 80°C.")
        assert safe is False
        assert cat == "suitability"

    def test_das_geht_problemlos_blocked(self):
        # "problemlos" is the trigger here, not "das geht" (too broad on its own)
        safe, cat = check_fast_path_output("Das geht problemlos bei diesem Druck.")
        assert safe is False
        assert cat == "suitability"

    def test_das_funktioniert_erklaerung_passiert(self):
        # Mechanism explanation — must NOT be blocked
        safe, cat = check_fast_path_output("Das funktioniert durch radialen Anpressdruck der Dichtlippe.")
        assert safe is True
        assert cat is None

    def test_unkritisch_blocked(self):
        safe, cat = check_fast_path_output("Die Temperatur ist unkritisch.")
        assert safe is False
        assert cat == "suitability"

    def test_freigegeben_fuer_blocked(self):
        safe, cat = check_fast_path_output("Das Material ist freigegeben für Lebensmittelkontakt.")
        assert safe is False
        assert cat == "suitability"

    def test_bestens_geeignet_blocked(self):
        safe, cat = check_fast_path_output("NBR ist bestens geeignet für Mineralöl.")
        assert safe is False
        assert cat == "suitability"


# ---------------------------------------------------------------------------
# Clean output: passes through unchanged
# ---------------------------------------------------------------------------

class TestCleanOutput:
    def test_factual_knowledge_passes(self):
        text = "FKM ist ein Fluorelastomer mit hoher Temperaturbeständigkeit bis ca. 200°C."
        safe, cat = check_fast_path_output(text)
        assert safe is True
        assert cat is None

    def test_material_name_alone_passes(self):
        # Material names are NOT blocked; only recommendation/suitability intent is
        text = "EPDM, NBR und FKM sind gängige Elastomere in der Dichttechnik."
        safe, cat = check_fast_path_output(text)
        assert safe is True
        assert cat is None

    def test_greeting_passes(self):
        safe, cat = check_fast_path_output("Hallo! Ich helfe Ihnen gerne bei Ihrer technischen Frage.")
        assert safe is True
        assert cat is None

    def test_parameter_request_passes(self):
        text = "Bitte nennen Sie Wellendurchmesser, Druck und Betriebstemperatur."
        safe, cat = check_fast_path_output(text)
        assert safe is True
        assert cat is None

    def test_empty_string_passes(self):
        safe, cat = check_fast_path_output("")
        assert safe is True
        assert cat is None


# ---------------------------------------------------------------------------
# Fallback constant is deterministic (not empty, not LLM-generated)
# ---------------------------------------------------------------------------

class TestFallbackConstant:
    def test_fallback_is_non_empty(self):
        assert len(FAST_PATH_GUARD_FALLBACK) > 0

    def test_fallback_itself_is_clean(self):
        """The fallback text must not trigger its own guard."""
        safe, cat = check_fast_path_output(FAST_PATH_GUARD_FALLBACK)
        assert safe is True, f"Fallback text triggered its own guard: category={cat}"
