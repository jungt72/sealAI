from __future__ import annotations

from app.domain.sealing_material_family import derive_sealing_material_family


def test_explicit_authority_value_from_norm_slice_is_returned() -> None:
    assert (
        derive_sealing_material_family(
            sealai_norm_material_family="elastomer_fkm",
        )
        == "elastomer_fkm"
    )


def test_generic_ptfe_is_not_mapped_to_virgin() -> None:
    assert derive_sealing_material_family(asserted_material="PTFE") is None


def test_generic_fkm_hint_without_authority_context_is_not_mapped() -> None:
    assert derive_sealing_material_family(asserted_material="FKM") is None


def test_unknown_unmapped_value_returns_none() -> None:
    assert derive_sealing_material_family(asserted_material="Viton") is None


def test_conflicting_authority_and_generic_signals_return_none() -> None:
    assert (
        derive_sealing_material_family(
            asserted_material="PTFE",
            sealai_norm_material_family="elastomer_fkm",
        )
        is None
    )


def test_explicit_authority_input_is_preserved() -> None:
    assert (
        derive_sealing_material_family(asserted_material="ptfe_glass_filled")
        == "ptfe_glass_filled"
    )


def test_no_silent_defaulting_to_unknown() -> None:
    assert derive_sealing_material_family() is None
    assert derive_sealing_material_family(asserted_material="") is None


def test_explicit_unknown_authority_value_is_preserved() -> None:
    assert derive_sealing_material_family(sealai_norm_material_family="unknown") == "unknown"


def test_conflicting_authority_values_return_none() -> None:
    assert (
        derive_sealing_material_family(
            sealai_norm_material_family="ptfe_virgin",
            qualified_materials=[{"sealing_material_family": "ptfe_glass_filled"}],
        )
        is None
    )
