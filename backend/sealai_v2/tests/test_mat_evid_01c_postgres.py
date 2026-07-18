from __future__ import annotations

from alembic import command
import os

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from sealai_v2.core.material_evidence_review import (
    APPROVE_ROLE,
    CREATE_ROLE,
    REVIEW_ROLE,
)
from sealai_v2.db.engine import make_engine
from sealai_v2.db.migrate import _config, migration_status
from sealai_v2.tests.test_mat_evid_01c_review import (
    _actor,
    _store,
)


POSTGRES_URL = os.environ.get("SEALAI_V2_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="dedicated local SEALAI_V2_TEST_POSTGRES_URL is required",
)


def test_real_postgres_01c_fingerprint_fk_lifecycle_and_immutability(tmp_path) -> None:
    parsed = make_url(POSTGRES_URL)
    assert parsed.host in {"127.0.0.1", "localhost", "host.docker.internal"}
    assert (parsed.database or "").startswith("sealai_mat_evid_01c_test")
    clean = make_engine(POSTGRES_URL)
    assert inspect(clean).get_table_names() == []
    clean.dispose()

    # The shared helper accepts a path only for SQLite, so construct its complete
    # fixture against PostgreSQL by temporarily using the same repositories.
    from sealai_v2.db.migrate import _upgrade_engine
    from sealai_v2.db.engine import make_sessionmaker
    from sealai_v2.db.material_evidence import MaterialEvidenceRepository
    from sealai_v2.db.material_evidence_review import MaterialEvidenceReviewRepository
    from sealai_v2.db.material_rulesets import MaterialRulesetRepository
    from sealai_v2.tests.test_mat_evid_01c_review import (
        CREATED_AT,
        MANIFEST_ID,
        REVIEW_ID,
        RULESET_ID,
        _evidence_payload,
        _ruleset_payload,
    )

    engine = make_engine(POSTGRES_URL)
    _upgrade_engine(engine)
    assert migration_status(engine) == ("20260718_0017", "20260718_0017")
    factory = make_sessionmaker(engine)
    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=RULESET_ID,
        domain_pack_id="material.test.v1",
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    ruleset = rulesets.store_snapshot(
        ruleset_id=RULESET_ID,
        raw_payload=_ruleset_payload(),
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    evidence_repo = MaterialEvidenceRepository(factory)
    evidence_repo.create_manifest(
        manifest_id=MANIFEST_ID,
        ruleset_snapshot_id=ruleset.snapshot_id,
        domain_pack_id="material.test.v1",
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    raw_evidence, source_ref, claim_ref = _evidence_payload(ruleset.snapshot_id)
    evidence = evidence_repo.store_snapshot(
        manifest_id=MANIFEST_ID,
        raw_payload=raw_evidence,
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    reviews = MaterialEvidenceReviewRepository(factory)
    reviews.create_review(
        review_id=REVIEW_ID,
        evidence_snapshot_id=evidence.snapshot_id,
        identity=_actor("subject:creator", CREATE_ROLE),
        created_at=CREATED_AT,
    )
    stored = _store(reviews, evidence, source_ref, claim_ref)
    reviews.record_review(
        stored.review_snapshot_id,
        identity=_actor("subject:reviewer", REVIEW_ROLE),
        created_at="2026-07-18T14:01:00Z",
    )
    reviews.record_approval(
        stored.review_snapshot_id,
        identity=_actor("subject:approver", APPROVE_ROLE),
        created_at="2026-07-18T14:02:00Z",
    )
    with pytest.raises(DBAPIError, match="MAT-EVID-01C immutable table"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE v2_material_evidence_review_snapshots "
                    "SET created_at=created_at WHERE review_snapshot_id=:snapshot_id"
                ),
                {"snapshot_id": stored.review_snapshot_id},
            )
    with pytest.raises(RuntimeError, match="contain data"):
        with engine.begin() as connection:
            command.downgrade(_config(connection=connection), "20260718_0015")
    assert migration_status(engine)[0] == "20260718_0017"
