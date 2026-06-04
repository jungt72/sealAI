"""Seal-type required-field sets — the domain-owned source for which inputs a
seal system needs, by seal type / family.

P1-1: relocated verbatim out of the v92 core orchestrator (`_required_fields_for`)
so the core no longer hardcodes per-type field lists. Behaviour-neutral move —
the tuples and the selector logic are byte-for-byte identical to the previous
`app/agent/v92/orchestrator.py` definitions.

NOTE — owner boundaries:
* This is the **v92 SealSystemState** required-field seam (6/7-field tuples). It is
  a *different* concern from the Technical RWDR RFQ Brief's 31-field minimal core
  (`app/services/rwdr_mvp_brief.py::_MINIMAL_RWDR_FIELDS`), which stays the owner of
  the brief's fields. The two are not duplicates and must not be merged.
* O-Ring / Hydraulic are SHALLOW STUBS (no DomainPack). New seal-type branches must
  land as a DomainPack, never as another hardcoded tuple here (see P1-1 PR2 seam).
"""

from __future__ import annotations

RWDR_REQUIRED_FIELDS: tuple[str, ...] = (
    "sealing_type",
    "medium",
    "temperature_c",
    "pressure_at_seal_bar",
    "shaft_diameter_mm",
    "speed_rpm",
)
# SHALLOW STUB (no DomainPack) — behaviour preserved, not a real pack.
ORING_REQUIRED_FIELDS: tuple[str, ...] = (
    "sealing_type",
    "medium",
    "temperature_c",
    "pressure_at_seal_bar",
    "oring_cross_section_mm",
    "groove_depth_mm",
    "groove_width_mm",
)
# SHALLOW STUB (no DomainPack) — behaviour preserved, not a real pack.
HYDRAULIC_REQUIRED_FIELDS: tuple[str, ...] = (
    "sealing_type",
    "medium",
    "temperature_c",
    "pressure_at_seal_bar",
    "rod_diameter_mm",
    "stroke_speed_mm_s",
)
DEFAULT_REQUIRED_FIELDS: tuple[str, ...] = (
    "sealing_type",
    "medium",
    "temperature_c",
    "pressure_at_seal_bar",
)

# --- State-gate type-sensitive required fields (P1-4 PR1) -------------------- #
# The per-seal-type EXTRA inputs the governed STATE GATE demands beyond the base
# preselection set (medium / pressure / temperature / sealing_type). This is a
# THIRD, distinct concern from RWDR_REQUIRED_FIELDS above (the SealSystemState
# 6-tuple) and from the brief's `_MINIMAL_RWDR_FIELDS` (31). Relocated verbatim
# out of the v92 core reducer (`reducers.py::_SEALING_TYPE_REQUIRED_FIELDS`) so
# the core no longer hardcodes a per-type field dict (CORE_PACK_BOUNDARY.md:13).
# RWDR's set is owned by the pack (`RwdrPack.state_gate_required_fields`); the
# others are SHALLOW STUBS — behaviour preserved, not real packs.
RWDR_STATE_GATE_REQUIRED_FIELDS: tuple[str, ...] = ("shaft_diameter_mm", "speed_rpm")
STATE_GATE_SHALLOW_STUBS: dict[str, tuple[str, ...]] = {
    "mechanical_seal": ("duty_profile", "installation"),
    "o_ring": ("geometry_context",),
    "gasket": ("geometry_context",),
    "packing": ("installation",),
}

# The selector that maps seal type/family → required fields lives in the pack seam
# (`app/domain/seal_packs.py::required_fields_for`); this module holds only the
# data tuples so the pack can own the RWDR set without a circular import.
