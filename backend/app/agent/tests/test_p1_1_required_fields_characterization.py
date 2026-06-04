"""P1-1 characterization: freeze `required_fields_for` behaviour before the
core/pack relocation. Behaviour-neutral refactor — these snapshots must stay
GREEN before AND after the move (no red-before-green; this is a freeze).

Snapshot taken 2026-06-04 against the pre-refactor core hardcode in
`app/agent/v92/orchestrator.py`.
"""
from __future__ import annotations

import pytest

from app.domain.seal_type import SealFamily, SealType
from app.agent.v92.orchestrator import _required_fields_for

# Frozen expected outputs (byte-for-byte).
_RWDR = (
    "sealing_type",
    "medium",
    "temperature_c",
    "pressure_at_seal_bar",
    "shaft_diameter_mm",
    "speed_rpm",
)
_ORING = (
    "sealing_type",
    "medium",
    "temperature_c",
    "pressure_at_seal_bar",
    "oring_cross_section_mm",
    "groove_depth_mm",
    "groove_width_mm",
)
_HYDRAULIC = (
    "sealing_type",
    "medium",
    "temperature_c",
    "pressure_at_seal_bar",
    "rod_diameter_mm",
    "stroke_speed_mm_s",
)
_DEFAULT = ("sealing_type", "medium", "temperature_c", "pressure_at_seal_bar")


@pytest.mark.parametrize(
    "seal_type,seal_family,expected",
    [
        (SealType.radial_shaft_seal.value, "", _RWDR),
        (SealType.rotary_lip_seal.value, "", _RWDR),
        (SealType.cassette_seal.value, "", _RWDR),
        (SealType.v_ring.value, "", _RWDR),
        ("anything", SealFamily.rotary_shaft.value, _RWDR),
        (SealType.o_ring.value, "", _ORING),
        (SealType.x_ring.value, "", _ORING),
        (SealType.backup_ring.value, "", _ORING),
        ("x", SealFamily.hydraulic.value, _HYDRAULIC),
        ("x", SealFamily.pneumatic.value, _HYDRAULIC),
        ("unknown_type", "unknown_family", _DEFAULT),
        ("", "", _DEFAULT),
    ],
)
def test_required_fields_for_is_frozen(seal_type, seal_family, expected):
    assert _required_fields_for(seal_type, seal_family) == expected


def test_rwdr_takes_precedence_over_oring_family_default():
    # RWDR seal_type wins regardless of an unrelated family value.
    assert _required_fields_for(SealType.radial_shaft_seal.value, "irrelevant") == _RWDR
