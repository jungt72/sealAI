"""Hersteller-PARTNER layer + the neutrality-preserving selection: payment gates pool membership but
NEVER reorders (no pay-to-rank at the pool layer). The capability keystone (hersteller.py) is untouched."""

from __future__ import annotations

from sealai_v2.knowledge.hersteller import HerstellerFaehigkeit
from sealai_v2.knowledge.hersteller_partner import (
    HerstellerPartner,
    InProcessPartnerRegistry,
    rank_partners,
    select_partners,
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


def _f(name: str) -> HerstellerFaehigkeit:
    return HerstellerFaehigkeit(
        id=f"HF-{name}",
        hersteller=name,
        werkstoffe=("FKM",),
        bauformen=("O-Ring",),
        groessen="",
        zertifikate=(),
        review_state="reviewed",
        provenance=("owner:test",),
    )


def _p(name: str, *, aktiv: bool = True, plan: str = "") -> HerstellerPartner:
    return HerstellerPartner(
        hersteller=name,
        firmenname=name,
        aktiv=aktiv,
        lead_email=f"leads@{name}",
        plan=plan,
    )


def test_selection_preserves_capability_fit_order():
    matches = (_f("A"), _f("B"), _f("C"))  # fit-ordered by the neutral capability store
    reg = InProcessPartnerRegistry(
        (_p("C", plan="premium"), _p("B", plan="basic"), _p("A", plan="basic"))
    )
    out = select_partners(matches, reg)
    assert [m.partner.hersteller for m in out] == ["A", "B", "C"]  # fit order, NOT plan


def test_only_active_partners_in_pool():
    matches = (_f("A"), _f("B"), _f("C"))
    reg = InProcessPartnerRegistry(
        (_p("A", aktiv=True), _p("B", aktiv=False))
    )  # C absent
    out = select_partners(matches, reg)
    assert [m.partner.hersteller for m in out] == ["A"]  # B inactive, C not a partner


def test_premium_plan_never_outranks_better_fit():
    matches = (_f("B"), _f("A"))  # B is the better capability fit (earlier)
    reg = InProcessPartnerRegistry((_p("A", plan="premium-xxl"), _p("B", plan="basic")))
    out = select_partners(matches, reg)
    assert out[0].partner.hersteller == "B"  # fit wins; payment never reorders


def test_empty_registry_yields_no_partners():
    assert select_partners((_f("A"),), InProcessPartnerRegistry()) == ()


def test_list_active_excludes_inactive():
    reg = InProcessPartnerRegistry((_p("A", aktiv=True), _p("B", aktiv=False)))
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
