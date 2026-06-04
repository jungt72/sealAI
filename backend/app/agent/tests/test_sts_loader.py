"""Tests fuer STS-Seed-Daten, Loader und Code-Lookup."""

from __future__ import annotations

import pytest

from app.agent.sts.loader import (
    clear_cache,
    load_all,
    load_catalog,
    validate_all,
    validate_catalog,
)
from app.agent.sts.codes import (
    get_material,
    get_medium,
    get_open_point,
    get_requirement_class,
    get_sealing_type,
    is_valid_code,
    list_codes,
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    """Jeder Test startet mit leerem Cache."""
    clear_cache()
    yield
    clear_cache()


# ── Loader ──────────────────────────────────────────────────────────


class TestLoadAll:
    def test_load_all_returns_five_catalogs(self):
        catalogs = load_all()
        assert set(catalogs.keys()) == {
            "STS-MAT",
            "STS-TYPE",
            "STS-RS",
            "STS-MED",
            "STS-OPEN",
        }

    def test_load_all_non_empty(self):
        catalogs = load_all()
        for prefix, data in catalogs.items():
            assert len(data) > 0, f"{prefix} ist leer"


class TestLoadCatalog:
    def test_load_materials(self):
        mat = load_catalog("STS-MAT")
        assert len(mat) >= 15

    def test_load_sealing_types(self):
        types = load_catalog("STS-TYPE")
        assert len(types) >= 10

    def test_load_requirement_classes(self):
        rc = load_catalog("STS-RS")
        assert len(rc) >= 6

    def test_load_media(self):
        med = load_catalog("STS-MED")
        assert len(med) >= 15

    def test_load_open_points(self):
        op = load_catalog("STS-OPEN")
        assert len(op) >= 10

    def test_unknown_prefix_raises(self):
        with pytest.raises(ValueError, match="Unbekannter STS-Prefix"):
            load_catalog("STS-NOPE")

    def test_cache_returns_same_object(self):
        a = load_catalog("STS-MAT")
        b = load_catalog("STS-MAT")
        assert a is b


# ── Validierung ─────────────────────────────────────────────────────


class TestValidation:
    def test_validate_all_no_errors(self):
        errors = validate_all()
        assert errors == [], f"Validierungsfehler: {errors}"

    def test_all_codes_have_correct_prefix(self):
        catalogs = load_all()
        for prefix, data in catalogs.items():
            for code in data:
                assert code.startswith(prefix), (
                    f"{code} beginnt nicht mit {prefix}"
                )

    def test_no_duplicate_canonical_names_per_catalog(self):
        catalogs = load_all()
        for prefix, data in catalogs.items():
            names = [e["canonical_name"] for e in data.values()]
            assert len(names) == len(set(names)), (
                f"Doppelte canonical_names in {prefix}"
            )

    def test_validate_catalog_detects_missing_field(self):
        bad_data = {"STS-MAT-BAD": {"canonical_name": "Test"}}
        errors = validate_catalog("STS-MAT", bad_data)
        assert any("material_family" in e for e in errors)
        assert any("temperature_max_c" in e for e in errors)

    def test_validate_catalog_detects_wrong_prefix(self):
        bad_data = {"WRONG-001": {"canonical_name": "X", "category": "y"}}
        errors = validate_catalog("STS-MED", bad_data)
        assert any("beginnt nicht mit STS-MED" in e for e in errors)

    def test_validate_catalog_detects_empty(self):
        errors = validate_catalog("STS-MAT", {})
        assert any("leer" in e for e in errors)


# ── Pflicht-Materialien ────────────────────────────────────────────


class TestRequiredMaterials:
    @pytest.mark.parametrize(
        "code,name_part",
        [
            ("STS-MAT-SIC-A1", "gesintert"),
            ("STS-MAT-SIC-B1", "reaktionsgebunden"),
            ("STS-MAT-WC-A1", "Wolframkarbid"),
            ("STS-MAT-FKM-A1", "FKM Standard"),
            ("STS-MAT-FKM-HT", "Hochtemperatur"),
            ("STS-MAT-EPDM-A1", "EPDM"),
            ("STS-MAT-NBR-A1", "NBR"),
            ("STS-MAT-PTFE-A1", "ungefuellt"),
            ("STS-MAT-PTFE-B1", "gefuellt"),
            ("STS-MAT-GRAPH-A1", "Grafit"),
            ("STS-MAT-VMQ-A1", "Silikon"),
        ],
    )
    def test_required_material_present(self, code: str, name_part: str):
        mat = get_material(code)
        assert mat is not None, f"{code} fehlt"
        assert name_part.lower() in mat["canonical_name"].lower(), (
            f"{code}: '{name_part}' nicht in canonical_name"
        )


# ── Pflicht-Dichtungstypen ─────────────────────────────────────────


class TestRequiredSealingTypes:
    @pytest.mark.parametrize(
        "code,name_part",
        [
            ("STS-TYPE-GS-S", "einfachwirkend"),
            ("STS-TYPE-GS-CART", "Cartridge"),
            ("STS-TYPE-GS-D", "doppeltwirkend"),
            ("STS-TYPE-GS-GAS", "gasgeschmiert"),
            ("STS-TYPE-RWDR-A", "Radialwellendichtring"),
            ("STS-TYPE-RWDR-B", "Radialwellendichtring"),
            ("STS-TYPE-OR-A", "O-Ring"),
            ("STS-TYPE-FLAT-A", "Flachdichtung"),
            ("STS-TYPE-SPIRAL-A", "Spiraldichtung"),
        ],
    )
    def test_required_sealing_type_present(self, code: str, name_part: str):
        st = get_sealing_type(code)
        assert st is not None, f"{code} fehlt"
        assert name_part.lower() in st["canonical_name"].lower(), (
            f"{code}: '{name_part}' nicht in canonical_name"
        )


# ── Code-Lookup (codes.py) ─────────────────────────────────────────


class TestCodeLookup:
    def test_get_material_found(self):
        mat = get_material("STS-MAT-SIC-A1")
        assert mat is not None
        assert mat["material_family"] == "ceramic"

    def test_get_material_not_found(self):
        assert get_material("STS-MAT-NONEXISTENT") is None

    def test_get_sealing_type_found(self):
        st = get_sealing_type("STS-TYPE-GS-S")
        assert st is not None
        assert st["category"] == "mechanical_seal"

    def test_get_requirement_class_found(self):
        rc = get_requirement_class("STS-RS-A")
        assert rc is not None
        assert rc["severity"] == "low"

    def test_get_medium_found(self):
        med = get_medium("STS-MED-SALTWATER-A1")
        assert med is not None
        assert med["corrosivity"] == "high"

    def test_get_open_point_found(self):
        op = get_open_point("STS-OPEN-001")
        assert op is not None
        assert op["severity"] == "blocking"

    def test_is_valid_code_true(self):
        assert is_valid_code("STS-MAT-SIC-A1") is True
        assert is_valid_code("STS-TYPE-GS-S") is True
        assert is_valid_code("STS-RS-A") is True
        assert is_valid_code("STS-MED-WATER-A1") is True
        assert is_valid_code("STS-OPEN-001") is True

    def test_is_valid_code_false(self):
        assert is_valid_code("STS-MAT-NOPE") is False
        assert is_valid_code("INVALID") is False
        assert is_valid_code("") is False

    def test_list_codes_sorted(self):
        codes = list_codes("STS-MAT")
        assert codes == sorted(codes)
        assert len(codes) >= 15

    def test_list_codes_all_prefixes(self):
        for prefix in ["STS-MAT", "STS-TYPE", "STS-RS", "STS-MED", "STS-OPEN"]:
            codes = list_codes(prefix)
            assert len(codes) > 0
            assert all(c.startswith(prefix) for c in codes)


# ── Datenqualitaet ──────────────────────────────────────────────────


class TestDataQuality:
    def test_materials_have_temperature(self):
        catalog = load_catalog("STS-MAT")
        for code, entry in catalog.items():
            assert isinstance(entry["temperature_max_c"], (int, float)), (
                f"{code}: temperature_max_c ist kein Zahlwert"
            )

    def test_sealing_types_have_category(self):
        catalog = load_catalog("STS-TYPE")
        valid_categories = {
            "mechanical_seal",
            "lip_seal",
            "static_seal",
            "compression_packing",
        }
        for code, entry in catalog.items():
            assert entry["category"] in valid_categories, (
                f"{code}: unbekannte Kategorie '{entry['category']}'"
            )

    def test_requirement_classes_severity_order(self):
        catalog = load_catalog("STS-RS")
        valid_severities = {"low", "medium", "high", "critical"}
        for code, entry in catalog.items():
            assert entry["severity"] in valid_severities, (
                f"{code}: unbekannte severity '{entry['severity']}'"
            )

    def test_media_have_category(self):
        catalog = load_catalog("STS-MED")
        valid_categories = {
            "aqueous",
            "hydrocarbon",
            "chemical",
            "food_pharma",
            "gas",
        }
        for code, entry in catalog.items():
            assert entry["category"] in valid_categories, (
                f"{code}: unbekannte Kategorie '{entry['category']}'"
            )

    def test_open_points_have_typical_question(self):
        catalog = load_catalog("STS-OPEN")
        for code, entry in catalog.items():
            assert "typical_question" in entry, (
                f"{code}: typical_question fehlt"
            )
            assert entry["typical_question"].endswith("?"), (
                f"{code}: typical_question endet nicht mit '?'"
            )

    def test_material_sealing_type_cross_references(self):
        """Alle sealing_types in Materialien muessen existieren."""
        materials = load_catalog("STS-MAT")
        types = load_catalog("STS-TYPE")
        for code, entry in materials.items():
            for st_code in entry.get("sealing_types", []):
                assert st_code in types, (
                    f"{code}: referenziert unbekannten Typ {st_code}"
                )
