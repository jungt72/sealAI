"""P1-1 PR2: DomainPack protocol + RWDR pack + thin selector seam.

Behaviour-neutral: the seam reproduces the former core `_required_fields_for`
exactly (the existing characterization test
`test_p1_1_required_fields_characterization.py` is the behaviour freeze through
the orchestrator). These tests pin the new pack contract itself.
"""
from __future__ import annotations

import pytest

from app.domain.domain_pack import DomainPack
from app.domain.seal_type import SealFamily, SealType
from app.domain.seal_required_fields import RWDR_REQUIRED_FIELDS
from app.domain.seal_packs import RwdrPack, pack_for, required_fields_for


def test_rwdr_pack_satisfies_protocol():
    assert isinstance(RwdrPack(), DomainPack)


def test_pack_for_selects_rwdr_for_rwdr_signals_only():
    for st in (
        SealType.radial_shaft_seal.value,
        SealType.rotary_lip_seal.value,
        SealType.cassette_seal.value,
        SealType.v_ring.value,
    ):
        assert isinstance(pack_for(st, ""), RwdrPack)
    assert isinstance(pack_for("x", SealFamily.rotary_shaft.value), RwdrPack)
    # Non-RWDR seal types resolve to no pack (shallow-stub territory).
    assert pack_for(SealType.o_ring.value, "") is None
    assert pack_for("x", SealFamily.hydraulic.value) is None
    assert pack_for("unknown", "unknown") is None


def test_rwdr_pack_metadata():
    pack = RwdrPack()
    assert pack.pack_id == "rwdr"
    assert pack.rfq_template_id == "rfq.rfq_one_pager.v1"
    assert pack.required_fields() == RWDR_REQUIRED_FIELDS
    assert pack.calculations() == (
        "rwdr_pv_precheck",
        "rwdr_dn_value",
        "rwdr_circumferential_speed",
    )


@pytest.mark.parametrize(
    "calc_id,owned",
    [
        ("rwdr", True),
        ("rwdr.circumferential_speed", True),
        ("rwdr_pv_precheck", False),  # explicit ids go through calculations(), not the string check
        ("oring.groove", False),
        ("", False),
    ],
)
def test_owns_calc_id_matches_legacy_string_check(calc_id, owned):
    assert RwdrPack().owns_calc_id(calc_id) is owned


def test_seam_routes_rwdr_through_the_pack():
    # required_fields_for for an RWDR signal returns exactly the pack's fields.
    assert required_fields_for(SealType.radial_shaft_seal.value, "") == RwdrPack().required_fields()
