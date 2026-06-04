"""Authority-conformant sealing material family derivation.

This module is intentionally conservative. Generic material hints such as
``PTFE`` or ``FKM`` are not enough to populate the authority-level
``sealing_material_family`` value.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

AUTHORITY_SEALING_MATERIAL_FAMILIES: frozenset[str] = frozenset(
    {
        "ptfe_virgin",
        "ptfe_glass_filled",
        "ptfe_carbon_filled",
        "ptfe_bronze_filled",
        "ptfe_mos2_filled",
        "ptfe_graphite_filled",
        "ptfe_peek_filled",
        "ptfe_mixed_filled",
        "elastomer_nbr",
        "elastomer_hnbr",
        "elastomer_fkm",
        "elastomer_ffkm",
        "elastomer_epdm",
        "elastomer_silicone",
        "elastomer_acm",
        "elastomer_other",
        "unknown",
    }
)

_GENERIC_FAMILY_MARKERS: dict[str, str] = {
    "PTFE": "ptfe",
    "NBR": "elastomer_nbr",
    "HNBR": "elastomer_hnbr",
    "FKM": "elastomer_fkm",
    "FFKM": "elastomer_ffkm",
    "EPDM": "elastomer_epdm",
    "SILIKON": "elastomer_silicone",
    "SILICONE": "elastomer_silicone",
    "ACM": "elastomer_acm",
}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _authority_value(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    candidate = text.lower()
    return candidate if candidate in AUTHORITY_SEALING_MATERIAL_FAMILIES else None


def _family_marker(value: Any) -> str | None:
    text = _text(value)
    if text is None:
        return None
    authority = _authority_value(text)
    if authority is not None:
        if authority.startswith("ptfe_"):
            return "ptfe"
        return authority
    return _GENERIC_FAMILY_MARKERS.get(text.upper())


def _iter_qualified_material_family_values(
    qualified_materials: Iterable[Mapping[str, Any]] | None,
) -> Iterable[Any]:
    for material in qualified_materials or ():
        if not isinstance(material, Mapping):
            continue
        if material.get("sealing_material_family") is not None:
            yield material.get("sealing_material_family")
        if material.get("material_family") is not None:
            yield material.get("material_family")


def derive_sealing_material_family(
    *,
    asserted_material: Any = None,
    sealai_norm_material_family: Any = None,
    qualified_materials: Iterable[Mapping[str, Any]] | None = None,
) -> str | None:
    """Return an authority ``sealing_material_family`` value, or ``None``.

    Accepted outputs are exclusively from
    ``AUTHORITY_SEALING_MATERIAL_FAMILIES``. Generic material hints are used
    only as conflict guards; they are never mapped into an authority value by
    themselves.
    """

    raw_values: list[Any] = [
        asserted_material,
        sealai_norm_material_family,
        *_iter_qualified_material_family_values(qualified_materials),
    ]
    authority_values = {
        authority
        for authority in (_authority_value(value) for value in raw_values)
        if authority is not None
    }
    if len(authority_values) != 1:
        return None

    selected = next(iter(authority_values))
    selected_marker = _family_marker(selected)
    for value in raw_values:
        marker = _family_marker(value)
        if marker is not None and marker != selected_marker:
            return None
    return selected
