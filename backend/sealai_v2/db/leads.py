"""Lead store (owner business model: manufacturers RECEIVE the leads). A captured Anfrage = the
structured RFQ briefing (the worked-out sealing situation + the AI's recommendations) routed to a
partner. Durable so the partner/owner can retrieve it; email delivery is an optional config-gated
add-on (not a hard dependency). In-process impl for CI; Postgres for prod (build-spec §3)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.db.models import V2Lead


@dataclass(frozen=True)
class Lead:
    partner_id: str
    firmenname: str
    lead_email: str
    tenant_id: str
    session_id: str
    briefing_title: str
    briefing_body: str
    created_at: str
    status: str = "neu"
    id: int = 0


def _to_domain(row: V2Lead) -> Lead:
    return Lead(
        id=row.id,
        partner_id=row.partner_id,
        firmenname=row.firmenname,
        lead_email=row.lead_email,
        tenant_id=row.tenant_id,
        session_id=row.session_id,
        briefing_title=row.briefing_title,
        briefing_body=row.briefing_body,
        created_at=row.created_at,
        status=row.status,
    )


class LeadStore(Protocol):
    def store(self, lead: Lead) -> int: ...
    def list_for_partner(self, partner_id: str) -> tuple[Lead, ...]: ...
    def list_all(self) -> tuple[Lead, ...]: ...


class InProcessLeadStore:
    """CI/eval fallback (no DB). Captures leads in memory; ids are 1-based + monotonic."""

    def __init__(self) -> None:
        self._leads: list[Lead] = []

    def store(self, lead: Lead) -> int:
        new_id = len(self._leads) + 1
        self._leads.append(replace(lead, id=new_id))
        return new_id

    def list_for_partner(self, partner_id: str) -> tuple[Lead, ...]:
        return tuple(line for line in self._leads if line.partner_id == partner_id)

    def list_all(self) -> tuple[Lead, ...]:
        return tuple(self._leads)


class PostgresLeadStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def store(self, lead: Lead) -> int:
        with self._sf() as s:
            row = V2Lead(
                partner_id=lead.partner_id,
                firmenname=lead.firmenname,
                lead_email=lead.lead_email,
                tenant_id=lead.tenant_id,
                session_id=lead.session_id,
                briefing_title=lead.briefing_title,
                briefing_body=lead.briefing_body,
                created_at=lead.created_at,
                status=lead.status,
            )
            s.add(row)
            s.commit()
            return row.id

    def list_for_partner(self, partner_id: str) -> tuple[Lead, ...]:
        with self._sf() as s:
            rows = s.scalars(
                select(V2Lead)
                .where(V2Lead.partner_id == partner_id)
                .order_by(V2Lead.id.desc())
            ).all()
            return tuple(_to_domain(r) for r in rows)

    def list_all(self) -> tuple[Lead, ...]:
        with self._sf() as s:
            rows = s.scalars(select(V2Lead).order_by(V2Lead.id.desc())).all()
            return tuple(_to_domain(r) for r in rows)


def build_lead_store(settings) -> LeadStore:
    """The Postgres lead store (durable, dashboard/partner-retrievable) when ``database_url`` is set,
    else the in-process store (eval/CI hermetic). Fail-safe: a missing dep / unreachable DB falls
    back to in-process rather than crashing the API."""
    if getattr(settings, "database_url", None):
        try:
            from sealai_v2.db.engine import make_engine, make_sessionmaker

            return PostgresLeadStore(
                make_sessionmaker(make_engine(settings.database_url))
            )
        except Exception:  # noqa: BLE001 — fail safe to in-process; never crash on startup
            pass
    return InProcessLeadStore()
