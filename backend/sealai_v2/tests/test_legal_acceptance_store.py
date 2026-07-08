"""db/legal_acceptance.py — in-process + Postgres(sqlite) store round-trip (mirrors
tests/test_partner_registry_db.py's sqlite-backed-offline shape)."""

from __future__ import annotations

from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.legal_acceptance import (
    InProcessLegalAcceptanceStore,
    LegalAcceptance,
    PostgresLegalAcceptanceStore,
)


def _acceptance(tenant_id: str = "tenant-A", **over) -> LegalAcceptance:
    base = dict(
        tenant_id=tenant_id,
        company_name="ACME Dichtungen GmbH",
        business_email="einkauf@acme-dichtungen.example",
        role="Einkauf",
        vat_id="DE123456789",
        legal_basis_accepted=True,
        dpa_accepted=True,
        business_user_confirmed=True,
        accepted_terms_version="2026-07-07-v1",
        accepted_privacy_version="2026-07-07-v1",
        accepted_dpa_version="2026-07-07-v1",
        accepted_at="2026-07-08T10:00:00+00:00",
        accepted_ip_hash="deadbeef",
        accepted_user_agent="pytest",
    )
    base.update(over)
    return LegalAcceptance(**base)


def test_in_process_store_get_before_upsert_is_none():
    store = InProcessLegalAcceptanceStore()
    assert store.get("tenant-A") is None


def test_in_process_store_upsert_then_get_round_trips():
    store = InProcessLegalAcceptanceStore()
    store.upsert(_acceptance())
    got = store.get("tenant-A")
    assert got is not None
    assert got.company_name == "ACME Dichtungen GmbH"
    assert got.legal_basis_accepted is True


def test_in_process_store_upsert_replaces_not_appends():
    store = InProcessLegalAcceptanceStore()
    store.upsert(_acceptance(company_name="Old GmbH"))
    store.upsert(_acceptance(company_name="New GmbH"))
    assert store.get("tenant-A").company_name == "New GmbH"


def test_in_process_store_is_tenant_scoped():
    store = InProcessLegalAcceptanceStore()
    store.upsert(_acceptance(tenant_id="tenant-A"))
    assert store.get("tenant-B") is None


def _sqlite_store() -> PostgresLegalAcceptanceStore:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return PostgresLegalAcceptanceStore(make_sessionmaker(engine))


def test_sqlite_backed_store_upsert_then_get_round_trips():
    store = _sqlite_store()
    store.upsert(_acceptance())
    got = store.get("tenant-A")
    assert got is not None
    assert got.accepted_terms_version == "2026-07-07-v1"
    assert got.accepted_ip_hash == "deadbeef"


def test_sqlite_backed_store_upsert_updates_the_same_row():
    store = _sqlite_store()
    store.upsert(_acceptance(accepted_terms_version="2026-07-07-v1"))
    store.upsert(_acceptance(accepted_terms_version="2026-08-01-v2"))
    got = store.get("tenant-A")
    assert got.accepted_terms_version == "2026-08-01-v2"
