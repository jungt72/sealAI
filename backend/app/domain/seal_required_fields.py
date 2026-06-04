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

# The selector that maps seal type/family → required fields lives in the pack seam
# (`app/domain/seal_packs.py::required_fields_for`); this module holds only the
# data tuples so the pack can own the RWDR set without a circular import.
