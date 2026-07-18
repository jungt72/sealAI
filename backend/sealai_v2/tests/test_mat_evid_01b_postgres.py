from __future__ import annotations

from dataclasses import replace
import os

from alembic import command
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_evidence import MaterialEvidenceRepository
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.material_shadow import MaterialShadowRepository
from sealai_v2.db.migrate import _config, _upgrade_engine, migration_status
from sealai_v2.tests.test_mat_evid_01b_domain import _binding as _evidence_binding
from sealai_v2.tests.test_mat_evid_01b_domain import _evidence, _ruleset
from sealai_v2.tests.test_mat_evid_01b_persistence import TABLES
from sealai_v2.tests.test_mat_gov_03b_persistence import (
    IDENTITY,
    NOW,
    RULESET_ID,
    _binding,
    _input,
    _keyring,
)


POSTGRES_URL = os.environ.get("SEALAI_V2_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="dedicated local SEALAI_V2_TEST_POSTGRES_URL is required",
)


def test_real_postgres_01b_fingerprint_atomicity_immutability_and_downgrade() -> None:
    parsed = make_url(POSTGRES_URL)
    assert parsed.host in {"127.0.0.1", "localhost", "host.docker.internal"}
    assert (parsed.database or "").startswith("sealai_mat_evid_01b_test")
    engine = make_engine(POSTGRES_URL)
    assert inspect(engine).get_table_names() == []
    _upgrade_engine(engine)
    assert migration_status(engine) == ("20260718_0015", "20260718_0015")
    assert TABLES <= set(inspect(engine).get_table_names())

    factory = make_sessionmaker(engine)
    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=RULESET_ID,
        domain_pack_id="material.test.v1",
        created_by_subject=IDENTITY.subject,
        created_at=NOW,
    )
    ruleset = rulesets.store_snapshot(
        ruleset_id=RULESET_ID,
        raw_payload=_ruleset().canonical_bytes,
        created_by_subject=IDENTITY.subject,
        created_at=NOW,
    )
    evidence_repository = MaterialEvidenceRepository(factory)
    evidence_repository.create_manifest(
        manifest_id="mef_" + "2" * 32,
        ruleset_snapshot_id=ruleset.snapshot_id,
        domain_pack_id="material.test.v1",
        created_by_subject=IDENTITY.subject,
        created_at=NOW,
    )
    evidence = evidence_repository.store_snapshot(
        manifest_id="mef_" + "2" * 32,
        raw_payload=_evidence(ruleset).canonical_bytes,
        created_by_subject=IDENTITY.subject,
        created_at=NOW,
    )
    shadow = _binding(ruleset)
    companion = replace(
        _evidence_binding(ruleset, evidence), binding_id=shadow.binding_id
    )
    repository = MaterialShadowRepository(factory)
    repository.create_binding(
        shadow,
        identity=IDENTITY,
        created_at=NOW,
        evidence_binding=companion,
    )
    repository.persist_pin_and_job(
        binding=shadow,
        identity=IDENTITY,
        session_id="postgres-session",
        correlation_id="postgres-request",
        material_input=_input(),
        hmac_keyring=_keyring(),
        acquired_at="2026-07-17T12:05:00.000000Z",
        evidence_binding_required=True,
    )
    with pytest.raises(DBAPIError, match="MAT-EVID-01B immutable table"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE v2_material_evidence_runtime_bindings "
                    "SET binding_state=binding_state"
                )
            )
    with pytest.raises(RuntimeError, match="contain data"):
        with engine.begin() as connection:
            command.downgrade(_config(connection=connection), "20260718_0014")
    assert migration_status(engine)[0] == "20260718_0015"
