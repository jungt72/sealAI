from __future__ import annotations

from alembic import command
import json
import os

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError

from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.migrate import _config, _upgrade_engine, migration_status
from sealai_v2.db.models import V2MaterialSnapshotValidationEvent


POSTGRES_URL = os.environ.get("SEALAI_V2_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="dedicated local SEALAI_V2_TEST_POSTGRES_URL is required",
)


def _assert_dedicated_local_database(url: str) -> None:
    parsed = make_url(url)
    assert parsed.host in {"127.0.0.1", "localhost"}
    assert (parsed.database or "").startswith("sealai_mat_gov_03a_test")


def _payload() -> str:
    return json.dumps(
        {
            "snapshot_schema_version": 1,
            "canonicalization_version": 1,
            "mat_gov_contract_version": "MAT-GOV-03A.v1",
            "domain_pack_id": "material.test.v1",
            "positive_statement_allowed": False,
            "rules": [
                {
                    "rule_ref": "MR-POSTGRES-001",
                    "material": "TEST-MATERIAL",
                    "medium": "TEST-MEDIUM",
                    "condition": "TEST-CONDITION",
                    "verdict": "bedingt",
                    "statement": "Synthetischer Postgres-Vertragstest.",
                    "scope": {
                        "materials": ["TEST-MATERIAL"],
                        "media": ["TEST-MEDIUM"],
                        "conditions": ["TEST-CONDITION"],
                    },
                    "evidence_binding": {"state": "unbound"},
                }
            ],
        }
    )


def test_real_postgres_fk_triggers_and_downgrade_contract() -> None:
    _assert_dedicated_local_database(POSTGRES_URL)
    engine = make_engine(POSTGRES_URL)
    assert inspect(engine).get_table_names() == []

    _upgrade_engine(engine, "20260717_0011")
    assert migration_status(engine) == ("20260717_0011", "20260717_0013")
    with engine.begin() as connection:
        command.downgrade(_config(connection=connection), "20260714_0010")
    assert "v2_material_rulesets" not in inspect(engine).get_table_names()
    _upgrade_engine(engine, "20260717_0011")

    repository = MaterialRulesetRepository(make_sessionmaker(engine))
    family = repository.create_ruleset(
        domain_pack_id="material.test.v1",
        ruleset_id="mrs_22222222222222222222222222222222",
        created_by_subject="subject:postgres-test",
        created_at="2026-07-17T12:00:00Z",
    )
    snapshot = repository.store_snapshot(
        ruleset_id=family.ruleset_id,
        raw_payload=_payload(),
        created_by_subject="subject:postgres-test",
        created_at="2026-07-17T12:00:00Z",
    )
    assert repository.load_snapshot(snapshot.snapshot_id) == snapshot

    with pytest.raises(IntegrityError):
        with make_sessionmaker(engine)() as session, session.begin():
            session.add(
                V2MaterialSnapshotValidationEvent(
                    event_id="mtv_" + "3" * 32,
                    snapshot_id="mss_" + "4" * 64,
                    validator_contract_version="MAT-GOV-03A.v1",
                    validation_state="valid",
                    error_code="none",
                    validation_sha256="5" * 64,
                    created_at="2026-07-17T12:00:00Z",
                )
            )

    for statement in (
        "UPDATE v2_material_ruleset_snapshots SET created_at = created_at "
        "WHERE snapshot_id = :snapshot_id",
        "DELETE FROM v2_material_snapshot_audit_events "
        "WHERE snapshot_id = :snapshot_id",
    ):
        with pytest.raises(DBAPIError, match="MAT-GOV-03A immutable table"):
            with engine.begin() as connection:
                connection.execute(
                    text(statement), {"snapshot_id": snapshot.snapshot_id}
                )

    with pytest.raises(RuntimeError, match="contain data"):
        with engine.begin() as connection:
            command.downgrade(_config(connection=connection), "20260714_0010")
    assert migration_status(engine)[0] == "20260717_0011"
