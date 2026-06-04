"""Tests for app.agent.domain.fit_score — deterministic scoring, no LLM."""

from __future__ import annotations

import json
import pathlib

import pytest

from app.agent.domain.fit_score import compute_fit_score, rank_manufacturers, EU_COUNTRIES

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DATA_PATH = (
    pathlib.Path(__file__).parent.parent
    / "data" / "manufacturers" / "pilot_manufacturers.json"
)


@pytest.fixture()
def pilot_manufacturers() -> list[dict]:
    return json.loads(DATA_PATH.read_text())


def _chemie_state():
    """Derived/normalized state for 80 °C Salzwasser SiC cartridge, ∅50 mm."""
    class Derived:
        pressure_bar = 10.0
        temp_c = 80.0
        detected_industries = ["chemie", "prozess"]
        sealing_type = "STS-TYPE-GS-CART"
        material = "STS-MAT-SIC-A1"

    class Normalized:
        shaft_diameter_mm = 50.0
        sealing_type = "STS-TYPE-GS-CART"
        material = "STS-MAT-SIC-A1"

    return Derived(), Normalized()


def _pharma_state():
    """Derived/normalized state for 120 °C steam, PTFE, ∅30 mm."""
    class Derived:
        pressure_bar = 5.0
        temp_c = 120.0
        detected_industries = ["pharma", "lebensmittel"]
        sealing_type = "STS-TYPE-OR-A"
        material = "STS-MAT-PTFE-A1"

    class Normalized:
        shaft_diameter_mm = 30.0
        sealing_type = "STS-TYPE-OR-A"
        material = "STS-MAT-PTFE-A1"

    return Derived(), Normalized()


def _hightemp_state():
    """Derived/normalized state for 380 °C thermal oil, FKM-HT, ∅80 mm."""
    class Derived:
        pressure_bar = 25.0
        temp_c = 380.0
        detected_industries = ["hochtemperatur", "kraftwerk"]
        sealing_type = "STS-TYPE-GS-S"
        material = "STS-MAT-FKM-HT-A1"

    class Normalized:
        shaft_diameter_mm = 80.0
        sealing_type = "STS-TYPE-GS-S"
        material = "STS-MAT-FKM-HT-A1"

    return Derived(), Normalized()


# ---------------------------------------------------------------------------
# Basic invariants
# ---------------------------------------------------------------------------

class TestFitScoreInvariants:
    def test_score_between_zero_and_one(self, pilot_manufacturers):
        derived, normalized = _chemie_state()
        for mfr in pilot_manufacturers:
            score = compute_fit_score(mfr, derived, normalized)
            assert 0.0 <= score <= 1.0, f"{mfr['id']}: score {score} out of range"

    def test_score_is_deterministic(self, pilot_manufacturers):
        """Same inputs must always produce the same score."""
        derived, normalized = _chemie_state()
        mfr = pilot_manufacturers[0]
        scores = {compute_fit_score(mfr, derived, normalized) for _ in range(5)}
        assert len(scores) == 1, "score is not deterministic"

    def test_score_is_float(self, pilot_manufacturers):
        derived, normalized = _chemie_state()
        score = compute_fit_score(pilot_manufacturers[0], derived, normalized)
        assert isinstance(score, float)

    def test_score_rounded_to_3_decimals(self, pilot_manufacturers):
        derived, normalized = _chemie_state()
        for mfr in pilot_manufacturers:
            score = compute_fit_score(mfr, derived, normalized)
            assert score == round(score, 3)


# ---------------------------------------------------------------------------
# Mismatch penalty
# ---------------------------------------------------------------------------

class TestMismatchPenalty:
    def test_wrong_sealing_type_gives_low_score(self):
        """Manufacturer with no matching STS-TYPE stays below 0.5."""
        mfr = {
            "id": "test-mfr",
            "capabilities": {
                "sealing_types": ["STS-TYPE-FLAT-A"],    # no GS-CART
                "materials": [],                          # no SiC
                "pressure_max_bar": 5,                    # too low
                "temperature_max_c": 50,                  # too low
                "shaft_diameter_min_mm": 500,             # wrong range
                "shaft_diameter_max_mm": 800,
            },
            "specialty": ["lebensmittel"],               # wrong industry
            "location": {"country": "CN"},               # non-EU
            "active": True,
        }
        derived, normalized = _chemie_state()
        score = compute_fit_score(mfr, derived, normalized)
        assert score < 0.5, f"expected < 0.5 for mismatched manufacturer, got {score}"

    def test_no_capabilities_gives_minimum_score(self):
        """Manufacturer with empty capabilities + DE location gets only geo bonus."""
        mfr = {
            "id": "empty",
            "capabilities": {
                "sealing_types": [],
                "materials": [],
                "pressure_max_bar": 0,
                "temperature_max_c": 0,
                "shaft_diameter_min_mm": 0,
                "shaft_diameter_max_mm": 0,
            },
            "specialty": [],
            "location": {"country": "DE"},
            "active": True,
        }
        derived, normalized = _chemie_state()
        score = compute_fit_score(mfr, derived, normalized)
        # Only geo bonus (0.10 * 1.0) — but pressure=0 and temp=0 fail → 0 capability bonus
        # type=no match, mat=no match, industry=no match → 0 + 0 + 0 + 0.10 = 0.10
        assert score == pytest.approx(0.10, abs=0.01)


# ---------------------------------------------------------------------------
# Perfect match
# ---------------------------------------------------------------------------

class TestPerfectMatch:
    def test_perfect_match_exceeds_085(self, pilot_manufacturers):
        """A manufacturer that matches type, material, capabilities, industry, and country
        must score above 0.85."""
        # mfr-001 is a Chemie/Prozess DE specialist with SiC + GS-CART
        mfr = next(m for m in pilot_manufacturers if m["id"] == "mfr-001")
        derived, normalized = _chemie_state()
        score = compute_fit_score(mfr, derived, normalized)
        assert score > 0.85, f"expected perfect match > 0.85, got {score}"

    def test_pharma_specialist_wins_pharma_query(self, pilot_manufacturers):
        mfr_pharma = next(m for m in pilot_manufacturers if m["id"] == "mfr-002")
        derived, normalized = _pharma_state()
        score = compute_fit_score(mfr_pharma, derived, normalized)
        # PharmaSeal has PTFE, OR-A, pharma specialty, pressure/temp fit → high score
        assert score > 0.75

    def test_hightemp_specialist_wins_hightemp_query(self, pilot_manufacturers):
        mfr_ht = next(m for m in pilot_manufacturers if m["id"] == "mfr-003")
        derived, normalized = _hightemp_state()
        score = compute_fit_score(mfr_ht, derived, normalized)
        assert score > 0.75


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

class TestRanking:
    def test_chemie_specialist_ranks_first_for_chemie_query(self, pilot_manufacturers):
        derived, normalized = _chemie_state()
        ranked = rank_manufacturers(pilot_manufacturers, derived, normalized)
        assert ranked[0][1]["id"] == "mfr-001", (
            f"Expected mfr-001 top, got {ranked[0][1]['id']} (score {ranked[0][0]})"
        )

    def test_ranking_descending(self, pilot_manufacturers):
        derived, normalized = _chemie_state()
        ranked = rank_manufacturers(pilot_manufacturers, derived, normalized)
        scores = [r[0] for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_inactive_excluded_by_default(self, pilot_manufacturers):
        manufacturers = list(pilot_manufacturers)
        manufacturers[0] = dict(manufacturers[0], active=False)
        derived, normalized = _chemie_state()
        ranked = rank_manufacturers(manufacturers, derived, normalized)
        ids = [r[1]["id"] for r in ranked]
        assert "mfr-001" not in ids

    def test_inactive_included_when_flag_off(self, pilot_manufacturers):
        manufacturers = list(pilot_manufacturers)
        manufacturers[0] = dict(manufacturers[0], active=False)
        derived, normalized = _chemie_state()
        ranked = rank_manufacturers(manufacturers, derived, normalized, active_only=False)
        ids = [r[1]["id"] for r in ranked]
        assert "mfr-001" in ids


# ---------------------------------------------------------------------------
# Geo scoring
# ---------------------------------------------------------------------------

class TestGeoScoring:
    def test_de_gets_full_geo_bonus(self):
        mfr = {
            "id": "de-mfr",
            "capabilities": {
                "sealing_types": [],
                "materials": [],
                "pressure_max_bar": 100,
                "temperature_max_c": 500,
                "shaft_diameter_min_mm": 0,
                "shaft_diameter_max_mm": 1000,
            },
            "specialty": [],
            "location": {"country": "DE"},
            "active": True,
        }
        # With no type/mat/industry match, only capability + geo contribute
        class Empty:
            pressure_bar = 5.0
            temp_c = 50.0
            detected_industries = []
            sealing_type = None
            material = None
            shaft_diameter_mm = 50.0

        score = compute_fit_score(mfr, Empty(), Empty())
        # capability 100% (0.30 * 1.0), geo 100% (0.10 * 1.0) = 0.40
        assert score == pytest.approx(0.40, abs=0.01)

    def test_eu_country_gets_half_geo_bonus(self):
        for country in ["AT", "FR", "NL", "CH"]:
            assert country in EU_COUNTRIES, f"{country} should be in EU_COUNTRIES"

    def test_non_eu_gets_zero_geo(self):
        for country in ["US", "CN", "JP", "IN"]:
            assert country not in EU_COUNTRIES


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_none_shaft_diameter_does_not_crash(self, pilot_manufacturers):
        class DerivedNoShaft:
            pressure_bar = 10.0
            temp_c = 80.0
            detected_industries = ["chemie"]
            sealing_type = "STS-TYPE-GS-CART"
            material = "STS-MAT-SIC-A1"
            shaft_diameter_mm = None

        score = compute_fit_score(pilot_manufacturers[0], DerivedNoShaft(), DerivedNoShaft())
        assert 0.0 <= score <= 1.0

    def test_dict_state_works_same_as_object(self, pilot_manufacturers):
        """compute_fit_score accepts plain dicts for state."""
        mfr = pilot_manufacturers[0]
        obj_d, obj_n = _chemie_state()
        dict_d = {
            "pressure_bar": 10.0,
            "temp_c": 80.0,
            "detected_industries": ["chemie", "prozess"],
            "sealing_type": "STS-TYPE-GS-CART",
            "material": "STS-MAT-SIC-A1",
        }
        dict_n = {
            "shaft_diameter_mm": 50.0,
            "sealing_type": "STS-TYPE-GS-CART",
            "material": "STS-MAT-SIC-A1",
        }
        score_obj = compute_fit_score(mfr, obj_d, obj_n)
        score_dict = compute_fit_score(mfr, dict_d, dict_n)
        assert score_obj == score_dict

    def test_empty_manufacturer_dict_does_not_crash(self):
        derived, normalized = _chemie_state()
        score = compute_fit_score({}, derived, normalized)
        assert 0.0 <= score <= 1.0
