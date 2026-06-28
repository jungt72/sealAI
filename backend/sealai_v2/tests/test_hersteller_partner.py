"""Hersteller-PARTNER layer + the neutrality-preserving selection: payment gates pool membership but
NEVER reorders (no pay-to-rank at the pool layer). The capability keystone (hersteller.py) is untouched."""

from __future__ import annotations

from sealai_v2.knowledge.hersteller_partner import (
    HerstellerPartner,
    InProcessPartnerRegistry,
    rank_partners,
)


def _pp(name, werkstoffe=(), bauformen=(), *, aktiv=True, plan=""):
    return HerstellerPartner(
        hersteller=name,
        firmenname=name,
        aktiv=aktiv,
        lead_email="",
        plan=plan,
        werkstoffe=werkstoffe,
        bauformen=bauformen,
    )


def test_list_active_excludes_inactive():
    reg = InProcessPartnerRegistry((_pp("A", aktiv=True), _pp("B", aktiv=False)))
    assert {p.hersteller for p in reg.list_active()} == {"A"}


def test_rank_partners_orders_by_capability_fit():
    partners = (
        _pp(
            "Nur-Material", werkstoffe=("FKM",), bauformen=("Flachdichtung",)
        ),  # 2 (material)
        _pp(
            "Voll-Fit", werkstoffe=("FKM", "EPDM"), bauformen=("O-Ring",)
        ),  # 4 (material+bauform)
        _pp("Kein-Fit", werkstoffe=("PTFE",), bauformen=("Stange",)),  # 0 → dropped
    )
    out = rank_partners(partners, material="FKM", bauform="O-Ring")
    assert [p.firmenname for p in out] == [
        "Voll-Fit",
        "Nur-Material",
    ]  # best fit first, 0-fit dropped


def test_rank_partners_payment_never_reorders():
    partners = (
        _pp(
            "Premium-schlechter-Fit",
            werkstoffe=("FKM",),
            bauformen=(),
            plan="enterprise",
        ),  # 2
        _pp(
            "Basic-besser-Fit", werkstoffe=("FKM",), bauformen=("O-Ring",), plan="basic"
        ),  # 4
    )
    out = rank_partners(partners, material="FKM", bauform="O-Ring")
    assert out[0].firmenname == "Basic-besser-Fit"  # fit wins; plan ignored


def test_rank_partners_drops_inactive():
    partners = (
        _pp("Aktiv", werkstoffe=("FKM",), aktiv=True),
        _pp("Inaktiv", werkstoffe=("FKM",), aktiv=False),
    )
    assert [p.firmenname for p in rank_partners(partners, material="FKM")] == ["Aktiv"]
