"""Legal-Gate acceptance store (Legal-by-Design Phase B, Goal 3). One row per tenant — mirrors
``db/contributions.py``'s Postgres/in-process split (same ``build_*_store`` fail-safe pattern)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import sessionmaker

from sealai_v2.db.models import V2LegalAcceptance


@dataclass(frozen=True)
class LegalAcceptance:
    tenant_id: str
    company_name: str
    business_email: str
    role: str
    vat_id: str
    legal_basis_accepted: bool
    dpa_accepted: bool
    business_user_confirmed: bool
    accepted_terms_version: str
    accepted_privacy_version: str
    accepted_dpa_version: str
    accepted_at: str
    accepted_ip_hash: str = ""
    accepted_user_agent: str = ""


def _to_domain(r: V2LegalAcceptance) -> LegalAcceptance:
    return LegalAcceptance(
        tenant_id=r.tenant_id,
        company_name=r.company_name,
        business_email=r.business_email,
        role=r.role,
        vat_id=r.vat_id,
        legal_basis_accepted=r.legal_basis_accepted,
        dpa_accepted=r.dpa_accepted,
        business_user_confirmed=r.business_user_confirmed,
        accepted_terms_version=r.accepted_terms_version,
        accepted_privacy_version=r.accepted_privacy_version,
        accepted_dpa_version=r.accepted_dpa_version,
        accepted_at=r.accepted_at,
        accepted_ip_hash=r.accepted_ip_hash,
        accepted_user_agent=r.accepted_user_agent,
    )


class LegalAcceptanceStore(Protocol):
    def upsert(self, a: LegalAcceptance) -> None: ...
    def get(self, tenant_id: str) -> LegalAcceptance | None: ...


class InProcessLegalAcceptanceStore:
    def __init__(self) -> None:
        self._items: dict[str, LegalAcceptance] = {}

    def upsert(self, a: LegalAcceptance) -> None:
        self._items[a.tenant_id] = a

    def get(self, tenant_id: str) -> LegalAcceptance | None:
        return self._items.get(tenant_id)


class PostgresLegalAcceptanceStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def upsert(self, a: LegalAcceptance) -> None:
        with self._sf() as s:
            row = s.get(V2LegalAcceptance, a.tenant_id)
            if row is None:
                row = V2LegalAcceptance(tenant_id=a.tenant_id)
                s.add(row)
            row.company_name = a.company_name
            row.business_email = a.business_email
            row.role = a.role
            row.vat_id = a.vat_id
            row.legal_basis_accepted = a.legal_basis_accepted
            row.dpa_accepted = a.dpa_accepted
            row.business_user_confirmed = a.business_user_confirmed
            row.accepted_terms_version = a.accepted_terms_version
            row.accepted_privacy_version = a.accepted_privacy_version
            row.accepted_dpa_version = a.accepted_dpa_version
            row.accepted_at = a.accepted_at
            row.accepted_ip_hash = a.accepted_ip_hash
            row.accepted_user_agent = a.accepted_user_agent
            s.commit()

    def get(self, tenant_id: str) -> LegalAcceptance | None:
        with self._sf() as s:
            row = s.get(V2LegalAcceptance, tenant_id)
            return _to_domain(row) if row is not None else None


def build_legal_acceptance_store(settings) -> LegalAcceptanceStore:
    if getattr(settings, "database_url", None):
        try:
            from sealai_v2.db.engine import make_engine, make_sessionmaker

            return PostgresLegalAcceptanceStore(
                make_sessionmaker(make_engine(settings.database_url))
            )
        except Exception:  # noqa: BLE001 — fail safe to in-process; never crash on startup
            pass
    return InProcessLegalAcceptanceStore()
