from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import make_url
import pytest

from sealai_v2.core.material_evidence_ai_review import AIReviewEnvironment
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_evidence_ai_review import (
    MaterialEvidenceAIReviewRepositoryV1,
    NonProductionAIReviewContextV1,
)
from sealai_v2.db.material_evidence_v2 import MaterialEvidenceRepositoryV2
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.migrate import _upgrade_engine, migration_status
from sealai_v2.material_evidence_ai_review.rp001_pack import build_rp001_pack
from sealai_v2.tests.test_rp001_ai_pack import _raw_inputs


POSTGRES_URL = os.environ.get("SEALAI_V2_TEST_POSTGRES_URL", "")
CREATED_BY = "ai-agent:codex-rp001-creator-20260718-01"


def _persist(database_url: str):
    creator_input, creator_prompt, candidate_register = _raw_inputs()
    artifacts = build_rp001_pack(
        creator_input_raw=creator_input,
        creator_prompt_raw=creator_prompt,
        candidate_register_raw=candidate_register,
    )
    engine = make_engine(database_url)
    _upgrade_engine(engine, "20260718_0019")
    factory = make_sessionmaker(engine)
    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=artifacts.ruleset.ruleset_id,
        domain_pack_id=artifacts.ruleset.payload.domain_pack_id,
        created_by_subject=CREATED_BY,
        created_at=artifacts.package_input["created_at"],
    )
    assert (
        rulesets.store_snapshot(
            ruleset_id=artifacts.ruleset.ruleset_id,
            raw_payload=artifacts.ruleset.canonical_bytes,
            created_by_subject=CREATED_BY,
            created_at=artifacts.package_input["created_at"],
        )
        == artifacts.ruleset
    )
    evidence = MaterialEvidenceRepositoryV2(factory)
    for snapshot in (artifacts.evidence, *artifacts.media_identity_evidence):
        evidence.create_manifest(
            manifest_id=snapshot.manifest_id,
            target=snapshot.payload.target,
            domain_pack_id=snapshot.payload.domain_pack_id,
            created_by_subject=CREATED_BY,
            created_at=artifacts.package_input["created_at"],
        )
        assert (
            evidence.store_snapshot(
                manifest_id=snapshot.manifest_id,
                raw_payload=snapshot.canonical_bytes,
                created_by_subject=CREATED_BY,
                created_at=artifacts.package_input["created_at"],
            )
            == snapshot
        )
    context = NonProductionAIReviewContextV1(
        tenant_id=artifacts.package_input["tenant_id"],
        environment=AIReviewEnvironment.TEST,
        authorization_ref=artifacts.package_input["authorization_ref"],
    )
    reviews = MaterialEvidenceAIReviewRepositoryV1(factory)
    reviews.create_batch(
        payload=artifacts.review.payload,
        context=context,
        created_at=artifacts.package_input["created_at"],
        batch_id=artifacts.review.batch_id,
    )
    assert (
        reviews.store_snapshot(
            batch_id=artifacts.review.batch_id,
            raw_payload=artifacts.review.canonical_bytes,
            context=context,
            created_at=artifacts.package_input["created_at"],
        )
        == artifacts.review
    )
    assert (
        reviews.load_snapshot(artifacts.review.review_snapshot_id, context=context)
        == artifacts.review
    )
    return engine, artifacts


def test_rp001_draft_roundtrips_through_isolated_sqlite(tmp_path: Path) -> None:
    engine, _ = _persist(f"sqlite:///{tmp_path / 'rp001.db'}")
    assert migration_status(engine) == ("20260718_0019", "20260718_0019")


@pytest.mark.skipif(
    not POSTGRES_URL, reason="dedicated local SEALAI_V2_TEST_POSTGRES_URL is required"
)
def test_rp001_draft_roundtrips_through_real_postgres() -> None:
    parsed = make_url(POSTGRES_URL)
    assert parsed.host in {"127.0.0.1", "localhost", "host.docker.internal"}
    assert (parsed.database or "").startswith("sealai_rp001_ai_pack_test")
    clean = make_engine(POSTGRES_URL)
    assert inspect(clean).get_table_names() == []
    clean.dispose()
    engine, _ = _persist(POSTGRES_URL)
    assert migration_status(engine) == ("20260718_0019", "20260718_0019")
