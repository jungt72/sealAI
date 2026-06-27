"""PostgresPartnerRegistry CRUD + queries — sqlite-backed (offline, hermetic). The row<->domain map +
the dashboard CRUD; selection-layer neutrality is locked in test_hersteller_partner (rank_partners)."""

from __future__ import annotations

from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.hersteller_partner import PostgresPartnerRegistry
from sealai_v2.knowledge.hersteller_partner import HerstellerPartner


def _reg() -> PostgresPartnerRegistry:
    eng = make_engine("sqlite://")
    Base.metadata.create_all(eng)
    return PostgresPartnerRegistry(make_sessionmaker(eng))


def _p(name, *, aktiv=True, plan="", werkstoffe=()):
    return HerstellerPartner(
        hersteller=name,
        firmenname=f"{name} GmbH",
        aktiv=aktiv,
        lead_email=f"leads@{name}",
        plan=plan,
        werkstoffe=werkstoffe,
    )


def test_upsert_get_roundtrip():
    r = _reg()
    r.upsert(_p("acme", werkstoffe=("FKM", "EPDM"), plan="basic"))
    got = r.get("acme")
    assert got is not None
    assert got.firmenname == "acme GmbH" and got.werkstoffe == ("FKM", "EPDM")
    assert got.aktiv is True and got.lead_email == "leads@acme"


def test_upsert_updates_in_place():
    r = _reg()
    r.upsert(_p("acme", aktiv=False))
    r.upsert(_p("acme", aktiv=True, plan="premium"))
    assert len(r.list_all()) == 1
    assert r.get("acme").aktiv is True and r.get("acme").plan == "premium"


def test_list_active_filters_inactive():
    r = _reg()
    r.upsert(_p("a", aktiv=True))
    r.upsert(_p("b", aktiv=False))
    assert {p.hersteller for p in r.list_active()} == {"a"}
    assert len(r.list_all()) == 2  # list_all includes inactive (the dashboard view)


def test_delete():
    r = _reg()
    r.upsert(_p("a"))
    assert r.delete("a") is True
    assert r.get("a") is None
    assert r.delete("a") is False
