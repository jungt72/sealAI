from __future__ import annotations

from alembic import command
import os

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_evidence import MaterialEvidenceRepository
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.migrate import _config, _upgrade_engine, migration_status
from sealai_v2.db.models import V2MaterialEvidenceValidationEvent
from sealai_v2.tests.test_mat_evid_01a_persistence import (
    CREATED_AT,
    MANIFEST_ID,
    RULESET_ID,
    _manifest_payload,
    _ruleset_payload,
)


POSTGRES_URL = os.environ.get("SEALAI_V2_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="dedicated local SEALAI_V2_TEST_POSTGRES_URL is required",
)


def _assert_dedicated_local_database(url: str) -> None:
    parsed = make_url(url)
    assert parsed.host in {"127.0.0.1", "localhost", "host.docker.internal"}
    assert (parsed.database or "").startswith("sealai_mat_evid_01a_test")


def test_real_postgres_hash_fk_immutability_and_downgrade_contract() -> None:
    _assert_dedicated_local_database(POSTGRES_URL)
    engine = make_engine(POSTGRES_URL)
    assert inspect(engine).get_table_names() == []
    _upgrade_engine(engine)
    assert migration_status(engine) == ("20260718_0019", "20260718_0019")

    factory = make_sessionmaker(engine)
    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=RULESET_ID,
        domain_pack_id="material.test.v1",
        created_by_subject="subject:postgres-test",
        created_at=CREATED_AT,
    )
    ruleset_snapshot = rulesets.store_snapshot(
        ruleset_id=RULESET_ID,
        raw_payload=_ruleset_payload(),
        created_by_subject="subject:postgres-test",
        created_at=CREATED_AT,
    )
    evidence = MaterialEvidenceRepository(factory)
    evidence.create_manifest(
        manifest_id=MANIFEST_ID,
        ruleset_snapshot_id=ruleset_snapshot.snapshot_id,
        domain_pack_id="material.test.v1",
        created_by_subject="subject:postgres-test",
        created_at=CREATED_AT,
    )
    snapshot = evidence.store_snapshot(
        manifest_id=MANIFEST_ID,
        raw_payload=_manifest_payload(ruleset_snapshot.snapshot_id),
        created_by_subject="subject:postgres-test",
        created_at=CREATED_AT,
    )
    assert evidence.load_snapshot(snapshot.snapshot_id) == snapshot

    with pytest.raises(IntegrityError):
        with factory() as session, session.begin():
            session.add(
                V2MaterialEvidenceValidationEvent(
                    event_id="mev_" + "3" * 32,
                    snapshot_id="mes_" + "4" * 64,
                    validator_contract_version="MAT-EVID-01A.v1",
                    validation_state="valid",
                    error_code="none",
                    validation_sha256="5" * 64,
                    created_at=CREATED_AT,
                )
            )

    for statement in (
        "UPDATE v2_material_evidence_snapshots SET created_at = created_at "
        "WHERE snapshot_id = :snapshot_id",
        "DELETE FROM v2_material_evidence_audit_events "
        "WHERE snapshot_id = :snapshot_id",
    ):
        with pytest.raises(DBAPIError, match="MAT-EVID-01A immutable table"):
            with engine.begin() as connection:
                connection.execute(
                    text(statement), {"snapshot_id": snapshot.snapshot_id}
                )

    with pytest.raises(RuntimeError, match="contain data"):
        with engine.begin() as connection:
            command.downgrade(_config(connection=connection), "20260717_0013")
    assert migration_status(engine)[0] == "20260718_0019"
