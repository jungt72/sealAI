"""Seal DomainPack registry + thin selector seam (Blueprint §3.3, §10.1).

RWDR is the ONLY pack. The "registry" is a one-entry tuple — no machinery, no
multi-pack speculation (Rule of Three §3.5). The selector maps a normalized seal
type / family to a pack; non-pack seal types (O-Ring / Hydraulic) fall through to
explicitly-marked SHALLOW STUBS.

⛔ STOP SIGN: a new seal type is added as a `DomainPack` (one entry in `_PACKS`),
never as another `if seal_type == …` branch in the core or another shallow stub.
"""
from __future__ import annotations

from app.domain.domain_pack import DomainPack
from app.domain.seal_required_fields import (
    DEFAULT_REQUIRED_FIELDS,
    HYDRAULIC_REQUIRED_FIELDS,
    ORING_REQUIRED_FIELDS,
    RWDR_REQUIRED_FIELDS,
    RWDR_STATE_GATE_REQUIRED_FIELDS,
    STATE_GATE_SHALLOW_STUBS,
)
from app.domain.seal_type import SealFamily, SealType

# RWDR calc ids (owned by the RWDR pack). SoT for the id strings stays the
# derived-dependency contract / calculation engine; the pack only declares
# ownership so consumers ask the pack instead of string-matching.
_RWDR_CALC_IDS: tuple[str, ...] = (
    "rwdr_pv_precheck",
    "rwdr_dn_value",
    "rwdr_circumferential_speed",
)


class RwdrPack:
    """The RWDR seal domain — the only DomainPack implementation today."""

    pack_id: str = "rwdr"
    # SoT: app/agent/communication/rfq_one_pager.py::RFQ_ONE_PAGER_TEMPLATE_ID
    rfq_template_id: str = "rfq.rfq_one_pager.v1"

    def classification_signals(self) -> tuple[frozenset[str], frozenset[str]]:
        return (
            frozenset(
                {
                    SealType.radial_shaft_seal.value,
                    SealType.rotary_lip_seal.value,
                    SealType.cassette_seal.value,
                    SealType.v_ring.value,
                }
            ),
            frozenset({SealFamily.rotary_shaft.value}),
        )

    def required_fields(self) -> tuple[str, ...]:
        return RWDR_REQUIRED_FIELDS

    def state_gate_required_fields(self) -> tuple[str, ...]:
        return RWDR_STATE_GATE_REQUIRED_FIELDS

    def calculations(self) -> tuple[str, ...]:
        return _RWDR_CALC_IDS

    def owns_calc_id(self, calc_id: str) -> bool:
        # Matches the legacy core string check (`== "rwdr"` / `startswith("rwdr.")`).
        cid = str(calc_id or "")
        return cid == self.pack_id or cid.startswith(self.pack_id + ".")


# One entry — Rule of Three (§3.5): no registry class until pack #2 exists.
_PACKS: tuple[DomainPack, ...] = (RwdrPack(),)


def pack_for(seal_type: str, seal_family: str) -> DomainPack | None:
    """Select the DomainPack for a normalized seal type / family, or ``None``."""
    for pack in _PACKS:
        seal_types, families = pack.classification_signals()
        if seal_type in seal_types or seal_family in families:
            return pack
    return None


def required_fields_for(seal_type: str, seal_family: str) -> tuple[str, ...]:
    """Seal-system required fields: pack first, else SHALLOW STUB, else default.

    Behaviour-identical to the former core `_required_fields_for`.
    """
    pack = pack_for(seal_type, seal_family)
    if pack is not None:
        return pack.required_fields()
    # SHALLOW STUBS (no DomainPack) — behaviour preserved, not real packs.
    if seal_type in {SealType.o_ring.value, SealType.x_ring.value, SealType.backup_ring.value}:
        return ORING_REQUIRED_FIELDS
    if seal_family in {SealFamily.hydraulic.value, SealFamily.pneumatic.value}:
        return HYDRAULIC_REQUIRED_FIELDS
    return DEFAULT_REQUIRED_FIELDS


# --- calc/risk routing seam (P1-1 PR3) -------------------------------------- #
# Consumers ask the pack about a calc id / engineering path instead of matching
# rwdr strings in the core. Each helper mirrors exactly one legacy check.

def pack_for_calc_id(calc_id: str) -> DomainPack | None:
    """Pack that owns ``calc_id`` by id pattern (legacy: `== "rwdr"` /
    `startswith("rwdr.")`), or ``None``."""
    for pack in _PACKS:
        if pack.owns_calc_id(calc_id):
            return pack
    return None


def is_pack_calculation(calc_id: str) -> bool:
    """True when ``calc_id`` is one of a pack's declared calculations (legacy:
    membership of the explicit ``{rwdr_pv_precheck, rwdr_dn_value,
    rwdr_circumferential_speed}`` set)."""
    cid = str(calc_id or "")
    return any(cid in pack.calculations() for pack in _PACKS)


def pack_for_calc_type(calc_type: str | None) -> DomainPack | None:
    """Pack whose ``pack_id`` EXACTLY equals a coarse calc_type label (legacy
    exact ``calc_type == "rwdr"``), or ``None``.

    Distinct from ``pack_for_calc_id``: this mirrors equality on the coarse
    ``calc_type`` field and deliberately does NOT match the ``rwdr.<id>`` calc-id
    namespace (a ``calc_type`` of ``"rwdr.surface_speed"`` is NOT the rwdr type
    label), so it stays byte-for-byte equivalent to the legacy ``== "rwdr"``.
    """
    value = str(calc_type or "")
    return next((pack for pack in _PACKS if pack.pack_id == value), None)


def pack_for_engineering_path(engineering_path: str | None) -> DomainPack | None:
    """Pack whose ``pack_id`` equals the engineering path (legacy:
    `engineering_path == "rwdr"`), or ``None``."""
    path = str(engineering_path or "")
    return next((pack for pack in _PACKS if pack.pack_id == path), None)


def state_gate_type_sensitive_fields_for(sealing_type: str) -> tuple[str, ...] | None:
    """State-gate type-sensitive required fields for a sealing_type token, or
    ``None`` when the type is unknown (P1-4 PR1).

    Behaviour-identical to the former core reducer dict
    (`reducers.py::_SEALING_TYPE_REQUIRED_FIELDS`): RWDR is owned by the pack
    (keyed by ``pack_id``, NOT by the SealType-enum classification signals — the
    reducer passes a raw ``"rwdr"`` token); the non-pack types are explicit
    SHALLOW STUBS. ``None`` (not ``()``) marks an unknown type so the reducer's
    rotary-context fallback path is preserved exactly.
    """
    for pack in _PACKS:
        if pack.pack_id == sealing_type:
            return pack.state_gate_required_fields()
    return STATE_GATE_SHALLOW_STUBS.get(sealing_type)
