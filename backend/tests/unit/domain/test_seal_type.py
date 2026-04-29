from __future__ import annotations

import pytest

from app.domain.seal_type import (
    SealFamily,
    SealType,
    normalize_seal_type,
    seal_family_for_type,
)


def test_seal_family_contains_stable_v083_values() -> None:
    assert {member.value for member in SealFamily} == {
        "static_elastomer",
        "flat_gasket",
        "rotary_shaft",
        "mechanical_face",
        "hydraulic",
        "pneumatic",
        "packing",
        "metal_seal",
        "custom_profile",
        "unknown",
    }


def test_seal_type_contains_stable_v083_values() -> None:
    assert {member.value for member in SealType} == {
        "o_ring",
        "x_ring",
        "backup_ring",
        "flat_gasket",
        "flange_gasket",
        "profile_gasket",
        "bonded_seal",
        "clamp_gasket",
        "radial_shaft_seal",
        "cassette_seal",
        "v_ring",
        "rotary_lip_seal",
        "rotary_swivel_seal",
        "mechanical_seal",
        "hydraulic_rod_seal",
        "hydraulic_piston_seal",
        "hydraulic_wiper",
        "hydraulic_guide_ring",
        "hydraulic_buffer_seal",
        "pneumatic_rod_seal",
        "pneumatic_piston_seal",
        "u_cup",
        "chevron_packing",
        "gland_packing",
        "valve_stem_seal",
        "expansion_joint_seal",
        "spring_energized_seal",
        "metal_seal",
        "custom_profile",
        "molded_seal",
        "fabric_reinforced_seal",
        "unknown_seal",
    }


def test_every_seal_type_maps_to_a_family() -> None:
    for seal_type in SealType:
        assert seal_family_for_type(seal_type) in set(SealFamily)


@pytest.mark.parametrize(
    "alias",
    [
        "Wellendichtring",
        "Radialwellendichtring",
        "RWDR",
        "WDR",
        "Simmerring",
        "Simmerring®",
        "oil seal",
        "rotary lip seal",
        "shaft seal",
    ],
)
def test_rwdr_aliases_normalize_to_radial_shaft_seal(alias: str) -> None:
    result = normalize_seal_type(alias)

    assert result.seal_type is SealType.radial_shaft_seal
    assert result.seal_family is SealFamily.rotary_shaft
    assert result.ambiguous is False
    assert "SealTypeNormalized" in result.event_names


@pytest.mark.parametrize("alias", ["Flachdichtung", "flat gasket", "cut gasket"])
def test_flat_gasket_aliases_normalize_to_flat_gasket(alias: str) -> None:
    result = normalize_seal_type(alias)

    assert result.seal_type is SealType.flat_gasket
    assert result.seal_family is SealFamily.flat_gasket


@pytest.mark.parametrize("alias", ["Flanschdichtung", "flange gasket"])
def test_flange_gasket_aliases_normalize_to_flange_gasket(alias: str) -> None:
    result = normalize_seal_type(alias)

    assert result.seal_type is SealType.flange_gasket
    assert result.seal_family is SealFamily.flat_gasket


@pytest.mark.parametrize("alias", ["Stangendichtung", "rod seal"])
def test_rod_seal_normalizes_to_hydraulic_with_hydraulic_context(alias: str) -> None:
    result = normalize_seal_type(alias, context={"application": "Hydraulikzylinder"})

    assert result.seal_type is SealType.hydraulic_rod_seal
    assert result.seal_family is SealFamily.hydraulic
    assert result.ambiguous is False


def test_stangendichtung_without_context_is_ambiguous_not_final() -> None:
    result = normalize_seal_type("Stangendichtung")

    assert result.seal_type is SealType.unknown_seal
    assert result.ambiguous is True
    assert result.candidate_types == (
        SealType.hydraulic_rod_seal,
        SealType.pneumatic_rod_seal,
    )


@pytest.mark.parametrize("alias", ["Kolbendichtung", "piston seal"])
def test_piston_seal_normalizes_to_hydraulic_with_hydraulic_context(alias: str) -> None:
    result = normalize_seal_type(alias, context={"application": "hydraulic cylinder"})

    assert result.seal_type is SealType.hydraulic_piston_seal
    assert result.seal_family is SealFamily.hydraulic


@pytest.mark.parametrize(
    "alias, expected",
    [
        ("Pneumatikdichtung", SealType.unknown_seal),
        ("pneumatic rod seal", SealType.pneumatic_rod_seal),
        ("pneumatic piston seal", SealType.pneumatic_piston_seal),
    ],
)
def test_pneumatic_aliases_normalize_to_pneumatic_family(
    alias: str, expected: SealType
) -> None:
    result = normalize_seal_type(alias)

    assert result.seal_type is expected
    assert result.seal_family is SealFamily.pneumatic


@pytest.mark.parametrize("alias", ["O-Ring", "Oring", "O ring"])
def test_o_ring_aliases_normalize_to_o_ring(alias: str) -> None:
    result = normalize_seal_type(alias)

    assert result.seal_type is SealType.o_ring
    assert result.seal_family is SealFamily.static_elastomer


@pytest.mark.parametrize("alias", ["X-Ring", "Quad Ring"])
def test_x_ring_aliases_normalize_to_x_ring(alias: str) -> None:
    result = normalize_seal_type(alias)

    assert result.seal_type is SealType.x_ring
    assert result.seal_family is SealFamily.static_elastomer


@pytest.mark.parametrize("alias", ["Gleitringdichtung", "mechanical seal", "face seal"])
def test_mechanical_seal_aliases_normalize_to_mechanical_seal(alias: str) -> None:
    result = normalize_seal_type(alias)

    assert result.seal_type is SealType.mechanical_seal
    assert result.seal_family is SealFamily.mechanical_face


@pytest.mark.parametrize("alias", ["Stopfbuchspackung", "gland packing"])
def test_gland_packing_aliases_normalize_to_gland_packing(alias: str) -> None:
    result = normalize_seal_type(alias)

    assert result.seal_type is SealType.gland_packing
    assert result.seal_family is SealFamily.packing


@pytest.mark.parametrize(
    "alias, expected",
    [
        ("Sonderprofil", SealType.custom_profile),
        ("custom profile", SealType.custom_profile),
        ("Formteildichtung", SealType.molded_seal),
    ],
)
def test_custom_aliases_normalize_to_custom_types(
    alias: str, expected: SealType
) -> None:
    result = normalize_seal_type(alias)

    assert result.seal_type is expected
    assert result.seal_family is SealFamily.custom_profile


def test_unknown_text_returns_unknown_seal() -> None:
    result = normalize_seal_type("Bitte pruefen Sie die Anlage.")

    assert result.seal_type is SealType.unknown_seal
    assert result.seal_family is SealFamily.unknown
    assert result.ambiguous is False
    assert result.event_names == ("SealTypeRemainsUnknown",)


def test_engineering_path_only_is_weak_ambiguous_hint() -> None:
    result = normalize_seal_type(None, context={"engineering_path": "rwdr"})

    assert result.seal_type is SealType.radial_shaft_seal
    assert result.seal_family is SealFamily.rotary_shaft
    assert result.confidence < 0.55
    assert result.ambiguous is True
    assert result.source == "weak_engineering_path_hint"


def test_explicit_text_beats_weak_engineering_path_hint_with_ambiguity_note() -> None:
    result = normalize_seal_type(
        "Gleitringdichtung fuer Pumpe",
        context={"engineering_path": "rwdr"},
    )

    assert result.seal_type is SealType.mechanical_seal
    assert result.seal_family is SealFamily.mechanical_face
    assert result.ambiguous is True
    assert SealType.radial_shaft_seal in result.candidate_types
    assert any("explicit alias preferred" in note for note in result.notes)
