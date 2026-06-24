"""Unit tests for extract_seal_spec (INC-4a acceptance criteria).

All tests are deterministic, offline, no LLM.
"""

from __future__ import annotations


from sealai_v2.core.seal_spec_extract import extract_seal_spec


# ---------------------------------------------------------------------------
# Acceptance tests (verbatim from INC-4a spec)
# ---------------------------------------------------------------------------


def test_nbr_rwdr():
    result = extract_seal_spec("Ich habe aktuell einen NBR-RWDR verbaut.")
    assert result == {"material": "NBR", "type": "RWDR"}


def test_fkm_oring():
    result = extract_seal_spec("FKM O-Ring")
    assert result == {"material": "FKM", "type": "O-Ring"}


def test_synonym_fpm_to_fkm():
    result = extract_seal_spec("FPM-Dichtung")
    assert result is not None
    assert result["material"] == "FKM"


def test_material_only_epdm():
    result = extract_seal_spec("EPDM")
    assert result == {"material": "EPDM"}


def test_no_material():
    result = extract_seal_spec("irgendeine Dichtung aus dem Regal")
    assert result is None


def test_ambiguous_two_materials():
    result = extract_seal_spec("NBR oder FKM")
    assert result is None


# ---------------------------------------------------------------------------
# Additional coverage
# ---------------------------------------------------------------------------


def test_synonym_vmq_to_silikon():
    result = extract_seal_spec("VMQ")
    assert result is not None
    assert result["material"] == "Silikon"


def test_silikon_no_type():
    result = extract_seal_spec("Silikon")
    assert result == {"material": "Silikon"}


def test_all_canonical_materials_recognised():
    # The 8 distinct canonical OUTPUT tags. AFLAS is an input synonym of FEPM
    # (Axis 1), not a canonical output — covered by test_aflas_canonicalises_to_fepm.
    for tag in (
        "EPDM",
        "FEPM",
        "FFKM",
        "FKM",
        "HNBR",
        "NBR",
        "PTFE",
        "Silikon",
    ):
        result = extract_seal_spec(tag)
        assert result is not None, f"Expected recognition of {tag}"
        assert result["material"] == tag


def test_case_insensitive_material():
    assert extract_seal_spec("nbr") == {"material": "NBR"}
    assert extract_seal_spec("epdm") == {"material": "EPDM"}


def test_type_x_ring():
    result = extract_seal_spec("FKM X-Ring")
    assert result == {"material": "FKM", "type": "X-Ring"}


def test_type_v_ring():
    result = extract_seal_spec("NBR V-Ring")
    assert result == {"material": "NBR", "type": "V-Ring"}


def test_type_nutring():
    result = extract_seal_spec("PTFE Nutring")
    assert result == {"material": "PTFE", "type": "Nutring"}


def test_type_wellendichtring():
    result = extract_seal_spec("HNBR Wellendichtring")
    assert result == {"material": "HNBR", "type": "Wellendichtring"}


def test_type_not_guessed_when_absent():
    result = extract_seal_spec("FKM Dichtung")
    assert result == {"material": "FKM"}
    assert "type" not in result


def test_empty_string():
    assert extract_seal_spec("") is None


def test_three_materials_ambiguous():
    result = extract_seal_spec("NBR, FKM und EPDM")
    assert result is None


def test_fpm_and_fkm_same_canonical_not_ambiguous():
    # FPM and FKM are synonyms -> same canonical "FKM" -> not ambiguous
    result = extract_seal_spec("FPM bzw. FKM Dichtung")
    assert result is not None
    assert result["material"] == "FKM"


def test_rwdr_case_insensitive():
    result = extract_seal_spec("NBR-rwdr")
    assert result == {"material": "NBR", "type": "RWDR"}


# ---------------------------------------------------------------------------
# Axis 1 — AFLAS canonicalised to FEPM (trade name -> ASTM-D1418 class)
# ---------------------------------------------------------------------------


def test_aflas_canonicalises_to_fepm():
    # AFLAS is the trade name; FEPM is the ASTM-D1418 class — one material.
    assert extract_seal_spec("AFLAS") == {"material": "FEPM"}


def test_aflas_fepm_single_material():
    # REGRESSION (was None pre-Axis-1): trade name + class name name ONE material.
    assert extract_seal_spec("AFLAS FEPM") == {"material": "FEPM"}


def test_fepm_self_map_preserved():
    assert extract_seal_spec("FEPM") == {"material": "FEPM"}


# ---------------------------------------------------------------------------
# Axis 2 — Type ambiguity is fail-closed (omit the optional field, don't guess)
# ---------------------------------------------------------------------------


def test_type_ambiguous_omits_field_keeps_material():
    # Two distinct types named -> don't guess; keep the material, drop the type.
    result = extract_seal_spec("NBR O-Ring oder X-Ring")
    assert result == {"material": "NBR"}
    assert "type" not in result
