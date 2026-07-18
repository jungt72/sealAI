from __future__ import annotations

from alembic import command
import json
import os

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.medium_catalog import MediumCatalogRepository
from sealai_v2.db.migrate import _config, _upgrade_engine, migration_status
from sealai_v2.db.models import V2MediumCatalogValidationEvent


POSTGRES_URL = os.environ.get("SEALAI_V2_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="dedicated local SEALAI_V2_TEST_POSTGRES_URL is required",
)


class _NoEvidenceEntries:
    def load_snapshot(self, *_args, **_kwargs):
        raise AssertionError("empty catalog cannot request evidence")

    def load_projection(self, *_args, **_kwargs):
        raise AssertionError("empty catalog cannot request evidence")


def test_real_postgres_catalog_fingerprint_fk_and_immutability() -> None:
    parsed = make_url(POSTGRES_URL)
    assert parsed.host in {"127.0.0.1", "localhost", "host.docker.internal"}
    assert (parsed.database or "").startswith("sealai_med_norm_01_test")
    engine = make_engine(POSTGRES_URL)
    assert inspect(engine).get_table_names() == []
    _upgrade_engine(engine)
    assert migration_status(engine) == ("20260718_0017", "20260718_0017")
    factory = make_sessionmaker(engine)
    repository = MediumCatalogRepository(factory, _NoEvidenceEntries())
    identity = VerifiedIdentity("tenant-a", "session-a", "subject-a")
    family = repository.create_catalog(
        catalog_id="mcf_" + "1" * 32,
        identity=identity,
        domain_pack_id="material.test.v1",
        created_at="2026-07-18T16:00:00Z",
    )
    snapshot = repository.store_snapshot(
        catalog_id=family.catalog_id,
        raw_payload=json.dumps(
            {
                "media_catalog_schema_version": 1,
                "canonicalization_version": 1,
                "med_norm_contract_version": "MED-NORM-01.v1",
                "domain_pack_id": "material.test.v1",
                "entries": [],
            }
        ),
        identity=identity,
        created_at="2026-07-18T16:00:00Z",
    )
    assert repository.load_snapshot(snapshot.snapshot_id, identity=identity) == snapshot

    with pytest.raises(IntegrityError):
        with factory() as session, session.begin():
            session.add(
                V2MediumCatalogValidationEvent(
                    event_id="mcv_" + "2" * 32,
                    snapshot_id="mcs_" + "3" * 64,
                    validator_contract_version="MED-NORM-01.v1",
                    validation_state="valid",
                    error_code="none",
                    validation_sha256="4" * 64,
                    created_at="2026-07-18T16:00:00Z",
                )
            )

    for statement in (
        "UPDATE v2_medium_catalog_snapshots SET created_at=created_at "
        "WHERE snapshot_id=:snapshot_id",
        "DELETE FROM v2_medium_catalog_audit_events WHERE snapshot_id=:snapshot_id",
    ):
        with pytest.raises(DBAPIError, match="MED-NORM-01 immutable table"):
            with engine.begin() as connection:
                connection.execute(
                    text(statement), {"snapshot_id": snapshot.snapshot_id}
                )

    with pytest.raises(RuntimeError, match="contain data"):
        with engine.begin() as connection:
            command.downgrade(_config(connection=connection), "20260718_0016")
    assert migration_status(engine)[0] == "20260718_0017"
