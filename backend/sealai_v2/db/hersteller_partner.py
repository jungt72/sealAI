"""PostgresPartnerRegistry — the dashboard-editable, durable Hersteller-PARTNER store (build-spec §3).

Implements ``PartnerRegistry`` (get / list_active) + the dashboard CRUD (upsert / delete / list_all),
mapping the ``V2HerstellerPartner`` row <-> the ``HerstellerPartner`` domain object. ``plan`` is stored
but NEVER read by the selection (``rank_partners`` ranks by capability fit) — no pay-to-rank. GLOBAL:
manufacturer data is not tenant-scoped (manufacturers serve all tenants)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.db.models import V2HerstellerPartner
from sealai_v2.knowledge.hersteller_partner import HerstellerPartner


def _to_domain(row: V2HerstellerPartner) -> HerstellerPartner:
    return HerstellerPartner(
        hersteller=row.hersteller,
        firmenname=row.firmenname,
        aktiv=row.aktiv,
        lead_email=row.lead_email,
        website=row.website,
        beschreibung=row.beschreibung,
        standort=row.standort,
        kontakt_oeffentlich=row.kontakt_oeffentlich,
        partner_seit=row.partner_seit,
        plan=row.plan,
        werkstoffe=tuple(row.werkstoffe or ()),
        bauformen=tuple(row.bauformen or ()),
        groessen=row.groessen,
        zertifikate=tuple(row.zertifikate or ()),
    )


class PostgresPartnerRegistry:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def get(self, hersteller: str) -> HerstellerPartner | None:
        with self._sf() as s:
            row = s.get(V2HerstellerPartner, hersteller)
            return _to_domain(row) if row is not None else None

    def list_active(self) -> tuple[HerstellerPartner, ...]:
        with self._sf() as s:
            rows = s.scalars(
                select(V2HerstellerPartner).where(V2HerstellerPartner.aktiv.is_(True))
            ).all()
            return tuple(_to_domain(r) for r in rows)

    def list_all(self) -> tuple[HerstellerPartner, ...]:
        with self._sf() as s:
            rows = s.scalars(
                select(V2HerstellerPartner).order_by(V2HerstellerPartner.firmenname)
            ).all()
            return tuple(_to_domain(r) for r in rows)

    def upsert(self, p: HerstellerPartner) -> None:
        with self._sf() as s:
            row = s.get(V2HerstellerPartner, p.hersteller)
            if row is None:
                row = V2HerstellerPartner(hersteller=p.hersteller)
                s.add(row)
            row.firmenname = p.firmenname
            row.aktiv = p.aktiv
            row.lead_email = p.lead_email
            row.website = p.website
            row.beschreibung = p.beschreibung
            row.standort = p.standort
            row.kontakt_oeffentlich = p.kontakt_oeffentlich
            row.partner_seit = p.partner_seit
            row.plan = p.plan
            row.werkstoffe = list(p.werkstoffe)
            row.bauformen = list(p.bauformen)
            row.groessen = p.groessen
            row.zertifikate = list(p.zertifikate)
            s.commit()

    def delete(self, hersteller: str) -> bool:
        with self._sf() as s:
            row = s.get(V2HerstellerPartner, hersteller)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True
