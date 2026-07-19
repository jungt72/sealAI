from __future__ import annotations

import json
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
from sealai_v2.core.material_evidence_v2 import MediaIdentityTargetV2
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_evidence_review_v2 import (
    MaterialEvidenceReviewRepositoryV2,
)
from sealai_v2.db.material_evidence_v2 import MaterialEvidenceRepositoryV2
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.migrate import _upgrade_engine, migration_status
from sealai_v2.tests.test_mat_evid_02_persistence import (
    CREATED_AT,
    DOMAIN_PACK,
    MEDIA_MANIFEST_ID,
    MEDIA_REF,
    REVIEW_ID,
    RULESET_ID,
    V2_TABLES,
    _actor,
    _payload,
    _review_raw,
    _ruleset_payload,
)


POSTGRES_URL = os.environ.get("SEALAI_V2_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="dedicated local SEALAI_V2_TEST_POSTGRES_URL is required",
)


def test_real_postgres_v2_fingerprint_roundtrip_lifecycle_and_immutability() -> None:
    parsed = make_url(POSTGRES_URL)
    assert parsed.host in {"127.0.0.1", "localhost", "host.docker.internal"}
    assert (parsed.database or "").startswith("sealai_mat_evid_02_test")
    engine = make_engine(POSTGRES_URL)
    assert inspect(engine).get_table_names() == []
    _upgrade_engine(engine)
    assert migration_status(engine) == ("20260718_0019", "20260718_0019")
    assert V2_TABLES <= set(inspect(engine).get_table_names())
    factory = make_sessionmaker(engine)
    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=RULESET_ID,
        domain_pack_id=DOMAIN_PACK,
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    ruleset = rulesets.store_snapshot(
        ruleset_id=RULESET_ID,
        raw_payload=_ruleset_payload(),
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    evidence = MaterialEvidenceRepositoryV2(factory)
    evidence.create_manifest(
        manifest_id=MEDIA_MANIFEST_ID,
        target=MediaIdentityTargetV2(MEDIA_REF),
        domain_pack_id=DOMAIN_PACK,
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    manifest = evidence.store_snapshot(
        manifest_id=MEDIA_MANIFEST_ID,
        raw_payload=json.dumps(
            _payload(ruleset.snapshot_id, media_identity=True).to_dict()
        ),
        created_by_subject="subject:creator",
        created_at=CREATED_AT,
    )
    creator = _actor("creator", CREATE_ROLE)
    reviews = MaterialEvidenceReviewRepositoryV2(factory)
    reviews.create_review(
        review_id=REVIEW_ID,
        evidence_snapshot_id=manifest.snapshot_id,
        identity=creator,
        created_at=CREATED_AT,
    )
    review = reviews.store_snapshot(
        review_id=REVIEW_ID,
        raw_payload=_review_raw(manifest),
        identity=creator,
        created_at=CREATED_AT,
    )
    reviews.record_review(
        review.review_snapshot_id,
        identity=_actor("reviewer", REVIEW_ROLE),
        created_at="2026-07-18T18:01:00Z",
    )
    reviews.record_approval(
        review.review_snapshot_id,
        identity=_actor("approver", APPROVE_ROLE),
        created_at="2026-07-18T18:02:00Z",
    )
    assert evidence.load_snapshot(manifest.snapshot_id) == manifest
    assert reviews.load_snapshot(review.review_snapshot_id, identity=creator) == review
    with pytest.raises(DBAPIError, match="MAT-EVID-02 immutable table"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE v2_material_evidence_review_snapshots_v2 "
                    "SET created_at=created_at WHERE review_snapshot_id=:snapshot_id"
                ),
                {"snapshot_id": review.review_snapshot_id},
            )
