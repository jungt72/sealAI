from __future__ import annotations

from dataclasses import replace
import hashlib
import json

from alembic import command
import pytest
from sqlalchemy import inspect, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from sealai_v2.core.material_evidence_ai_review import (
    AIReviewEnvironment,
    AIReviewErrorCode,
    AIReviewSnapshotV1,
    AIReviewState,
    AIReviewValidationError,
    AgentExecutionIsolationV1,
    ChallengerAgentRunV1,
)
from sealai_v2.core.material_evidence_review import (
    EvidenceRightsState,
    OmittedExcerptV1,
)
from sealai_v2.db.engine import make_engine, make_sessionmaker
from sealai_v2.db.material_evidence_ai_review import (
    MaterialEvidenceAIReviewRepositoryV1,
    NonProductionAIReviewContextV1,
)
from sealai_v2.db.material_evidence_v2 import MaterialEvidenceRepositoryV2
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.migrate import _config, _upgrade_engine, migration_status
from sealai_v2.db.models import (
    V2MaterialEvidenceAIAdjudication,
    V2MaterialEvidenceAIAuditEvent,
    V2MaterialEvidenceAIChallenge,
    V2MaterialEvidenceAILifecycleEvent,
    V2MaterialEvidenceAIReviewBatch,
    V2MaterialEvidenceAIReviewSnapshot,
    V2MaterialEvidenceAIValidationEvent,
)
from sealai_v2.material_evidence_ai_review.audit import (
    AIFindingCategory,
    AIFindingSeverity,
    AUDIT_OUTPUT_DOMAIN,
    ClaudeChallengeV1,
    FindingAdjudicationV1,
    FindingDisposition,
    build_claude_audit_input,
    create_adjudication,
    create_corrected_media_identity_snapshot,
    parse_claude_audit_report,
)
from sealai_v2.tests.test_mat_evid_ai_review_domain import (
    BATCH_ID,
    MANIFEST_ID,
    RULESET_ID,
    _adjudicator,
    _identity_evidence,
    _pass_report,
    _payload,
    _source_identity,
    SHA,
)


CREATED_AT = "2026-07-18T20:00:00Z"
AI_TABLES = {
    "v2_material_evidence_ai_review_batches",
    "v2_material_evidence_ai_review_snapshots",
    "v2_material_evidence_ai_challenges",
    "v2_material_evidence_ai_adjudications",
    "v2_material_evidence_ai_validation_events",
    "v2_material_evidence_ai_lifecycle_events",
    "v2_material_evidence_ai_audit_events",
}


def _setup(tmp_path, *, payload_override=None, database_url: str | None = None):
    engine = make_engine(database_url or f"sqlite:///{tmp_path / 'ai-review.db'}")
    _upgrade_engine(engine, "20260718_0019")
    factory = make_sessionmaker(engine)
    payload, ruleset, evidence = _payload()
    payload = payload_override or payload
    rulesets = MaterialRulesetRepository(factory)
    rulesets.create_ruleset(
        ruleset_id=RULESET_ID,
        domain_pack_id=ruleset.payload.domain_pack_id,
        created_by_subject="ai-agent:creator",
        created_at=CREATED_AT,
    )
    persisted_ruleset = rulesets.store_snapshot(
        ruleset_id=RULESET_ID,
        raw_payload=ruleset.canonical_bytes,
        created_by_subject="ai-agent:creator",
        created_at=CREATED_AT,
    )
    evidence_repo = MaterialEvidenceRepositoryV2(factory)
    evidence_repo.create_manifest(
        manifest_id=MANIFEST_ID,
        target=evidence.payload.target,
        domain_pack_id=evidence.payload.domain_pack_id,
        created_by_subject="ai-agent:creator",
        created_at=CREATED_AT,
    )
    persisted_evidence = evidence_repo.store_snapshot(
        manifest_id=MANIFEST_ID,
        raw_payload=evidence.canonical_bytes,
        created_by_subject="ai-agent:creator",
        created_at=CREATED_AT,
    )
    identity_evidence = _identity_evidence()
    evidence_repo.create_manifest(
        manifest_id=identity_evidence.manifest_id,
        target=identity_evidence.payload.target,
        domain_pack_id=identity_evidence.payload.domain_pack_id,
        created_by_subject="ai-agent:creator",
        created_at=CREATED_AT,
    )
    persisted_identity_evidence = evidence_repo.store_snapshot(
        manifest_id=identity_evidence.manifest_id,
        raw_payload=identity_evidence.canonical_bytes,
        created_by_subject="ai-agent:creator",
        created_at=CREATED_AT,
    )
    assert persisted_ruleset == ruleset
    assert persisted_evidence == evidence
    assert persisted_identity_evidence == identity_evidence
    context = NonProductionAIReviewContextV1(
        tenant_id=payload.tenant_id,
        environment=payload.environment,
        authorization_ref="owner-change:mat-evid-ai-review-v1",
    )
    repo = MaterialEvidenceAIReviewRepositoryV1(factory)
    family = repo.create_batch(
        payload=payload,
        context=context,
        created_at=CREATED_AT,
        batch_id=BATCH_ID,
    )
    snapshot = repo.store_snapshot(
        batch_id=family.batch_id,
        raw_payload=json.dumps(payload.to_dict(), ensure_ascii=False),
        context=context,
        created_at=CREATED_AT,
    )
    return engine, factory, repo, context, snapshot


def _challenge(snapshot: AIReviewSnapshotV1) -> ClaudeChallengeV1:
    report = parse_claude_audit_report(_pass_report(snapshot), snapshot)
    report_hash = hashlib.sha256(
        AUDIT_OUTPUT_DOMAIN
        + json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    challenger = ChallengerAgentRunV1(
        agent_version="claude-cli-test-version",
        prompt_version="challenge.v1",
        prompt_sha256="e" * 64,
        run_id="claude-persistence-run",
        audit_input_sha256=build_claude_audit_input(snapshot).audit_input_sha256,
        audit_output_sha256=report_hash,
        isolation=AgentExecutionIsolationV1(False, False, False, 0, 0, False),
    )
    return ClaudeChallengeV1.create(snapshot, challenger, report)


def test_repository_round_trip_challenge_and_cross_review(tmp_path) -> None:
    engine, factory, repo, context, snapshot = _setup(tmp_path)
    assert AI_TABLES <= set(inspect(engine).get_table_names())
    assert repo.load_snapshot(snapshot.review_snapshot_id, context=context) == snapshot
    assert (
        repo.load_projection(snapshot.review_snapshot_id, context=context).state
        is AIReviewState.AI_DRAFT
    )

    challenge = _challenge(snapshot)
    projection = repo.record_challenge(
        challenge=challenge,
        context=context,
        created_at=CREATED_AT,
    )
    assert projection.state is AIReviewState.AI_CHALLENGED
    adjudication = create_adjudication(
        snapshot=snapshot,
        challenge=challenge,
        adjudicator=_adjudicator("codex-persistence-adjudicator"),
        finding_adjudications=(),
    )
    projection = repo.record_adjudication(
        adjudication=adjudication,
        context=context,
        created_at=CREATED_AT,
    )
    assert projection.state is AIReviewState.AI_CROSS_REVIEWED_NON_AUTHORITATIVE
    assert (
        repo.load_projection(snapshot.review_snapshot_id, context=context) == projection
    )

    with factory() as session:
        assert len(session.scalars(select(V2MaterialEvidenceAIReviewBatch)).all()) == 1
        assert (
            len(session.scalars(select(V2MaterialEvidenceAIReviewSnapshot)).all()) == 1
        )
        challenges = session.scalars(select(V2MaterialEvidenceAIChallenge)).all()
        assert len(challenges) == 1
        assert challenges[0].challenger_version == "claude-cli-test-version"
        assert challenges[0].challenger_prompt_version == "challenge.v1"
        assert challenges[0].challenger_prompt_sha256 == "e" * 64
        assert len(session.scalars(select(V2MaterialEvidenceAIAdjudication)).all()) == 1
        assert (
            len(session.scalars(select(V2MaterialEvidenceAIValidationEvent)).all()) == 1
        )
        assert (
            len(session.scalars(select(V2MaterialEvidenceAILifecycleEvent)).all()) == 2
        )
        assert len(session.scalars(select(V2MaterialEvidenceAIAuditEvent)).all()) == 3


def test_repository_persists_identity_only_correction_without_material_laundering(
    tmp_path,
) -> None:
    _, factory, repo, context, snapshot = _setup(tmp_path)
    raw = json.loads(_pass_report(snapshot))
    raw["overall_verdict"] = "CHANGES_REQUIRED"
    identity_claim_ref = snapshot.payload.media_identities[0].claims[0].claim_ref
    result = next(
        item for item in raw["claim_results"] if item["claim_ref"] == identity_claim_ref
    )
    result.update(
        {
            "findings": [
                {
                    "category": AIFindingCategory.SOURCE_COVERAGE.value,
                    "detail": "Identity source correction required.",
                    "finding_ref": "AIF-DB-MEDIA-001",
                    "recommended_correction": "Create exact new identity Evidence.",
                    "severity": AIFindingSeverity.MEDIUM.value,
                }
            ],
            "severity": "MEDIUM",
            "verdict": "CHANGES_REQUIRED",
        }
    )
    report = parse_claude_audit_report(json.dumps(raw), snapshot)
    report_hash = hashlib.sha256(
        AUDIT_OUTPUT_DOMAIN
        + json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    challenge = ClaudeChallengeV1.create(
        snapshot,
        ChallengerAgentRunV1(
            agent_version="claude-cli-test-version",
            prompt_version="challenge.v1",
            prompt_sha256="e" * 64,
            run_id="claude-identity-correction-run",
            audit_input_sha256=build_claude_audit_input(snapshot).audit_input_sha256,
            audit_output_sha256=report_hash,
            isolation=AgentExecutionIsolationV1(False, False, False, 0, 0, False),
        ),
        report,
    )
    repo.record_challenge(challenge=challenge, context=context, created_at=CREATED_AT)

    previous = _identity_evidence()
    revised_source = _source_identity(SHA("7"))
    revised_claim = replace(
        previous.payload.claims[0], source_refs=(revised_source.source_ref,)
    )
    corrected = create_corrected_media_identity_snapshot(
        previous_evidence=previous,
        manifest_id=previous.manifest_id,
        evidence_payload=replace(
            previous.payload,
            sources=(revised_source,),
            claims=(revised_claim,),
        ),
    )
    persisted = MaterialEvidenceRepositoryV2(factory).store_snapshot(
        manifest_id=corrected.manifest_id,
        raw_payload=corrected.canonical_bytes,
        created_by_subject="ai-agent:adjudicator",
        created_at=CREATED_AT,
    )
    assert persisted == corrected
    adjudication = create_adjudication(
        snapshot=snapshot,
        challenge=challenge,
        adjudicator=_adjudicator("codex-db-identity-adjudicator"),
        finding_adjudications=(
            FindingAdjudicationV1(
                "AIF-DB-MEDIA-001",
                FindingDisposition.CORRECTED_IN_NEW_SNAPSHOT,
                "Replacement identity Evidence was persisted immutably.",
            ),
        ),
        replacement_media_identity_evidence=(corrected,),
    )
    assert (
        repo.record_adjudication(
            adjudication=adjudication,
            context=context,
            created_at=CREATED_AT,
        ).state
        is AIReviewState.CHANGES_REQUIRED
    )
    with factory() as session:
        row = session.get(
            V2MaterialEvidenceAIAdjudication, adjudication.adjudication_id
        )
        assert row.replacement_ruleset_snapshot_id is None
        assert row.replacement_evidence_snapshot_id is None
        assert (
            row.canonical_adjudication_json["replacement_media_identity_evidence"][0][
                "replacement_evidence_snapshot_id"
            ]
            == corrected.snapshot_id
        )
        assert (
            len(session.scalars(select(V2MaterialEvidenceAIReviewSnapshot)).all()) == 1
        )
        challenges = session.scalars(select(V2MaterialEvidenceAIChallenge)).all()
        assert len(challenges) == 1
        assert challenges[0].challenger_version == "claude-cli-test-version"
        assert challenges[0].challenger_prompt_version == "challenge.v1"
        assert challenges[0].challenger_prompt_sha256 == "e" * 64
        assert len(session.scalars(select(V2MaterialEvidenceAIAdjudication)).all()) == 1
        assert (
            len(session.scalars(select(V2MaterialEvidenceAIValidationEvent)).all()) == 1
        )
        assert (
            len(session.scalars(select(V2MaterialEvidenceAILifecycleEvent)).all()) == 2
        )
        assert len(session.scalars(select(V2MaterialEvidenceAIAuditEvent)).all()) == 3


def test_cross_tenant_or_environment_access_fails_closed(tmp_path) -> None:
    _, _, repo, context, snapshot = _setup(tmp_path)
    for foreign in (
        NonProductionAIReviewContextV1(
            "other-tenant", context.environment, context.authorization_ref
        ),
        NonProductionAIReviewContextV1(
            context.tenant_id,
            AIReviewEnvironment.DARK_STAGING,
            context.authorization_ref,
        ),
    ):
        with pytest.raises(AIReviewValidationError) as exc:
            repo.load_snapshot(snapshot.review_snapshot_id, context=foreign)
        assert exc.value.code is AIReviewErrorCode.TENANT_MISMATCH


def test_source_preflight_blocks_challenge_before_any_challenge_row(tmp_path) -> None:
    payload, _, _ = _payload()
    blocked_source = replace(
        payload.sources[0],
        metadata=replace(
            payload.sources[0].metadata,
            rights_state=EvidenceRightsState.UNKNOWN,
            excerpt=OmittedExcerptV1(),
        ),
    )
    blocked_payload = replace(payload, sources=(blocked_source,))
    _, factory, repo, context, snapshot = _setup(
        tmp_path, payload_override=blocked_payload
    )
    with pytest.raises(AIReviewValidationError) as exc:
        repo.record_challenge(
            challenge=_challenge(snapshot),
            context=context,
            created_at=CREATED_AT,
        )
    assert exc.value.code is AIReviewErrorCode.SOURCE_BLOCKED
    with factory() as session:
        assert session.scalar(select(V2MaterialEvidenceAIChallenge)) is None


def test_quarantine_and_revocation_are_append_only_terminal_events(tmp_path) -> None:
    _, _, repo, context, snapshot = _setup(tmp_path)
    quarantine = repo.record_quarantine(
        review_snapshot_id=snapshot.review_snapshot_id,
        context=context,
        actor_provider=snapshot.payload.creator.agent_provider,
        actor_run_id=snapshot.payload.creator.run_id,
        artifact_ref=snapshot.review_snapshot_id,
        reason_sha256="9" * 64,
        created_at=CREATED_AT,
    )
    assert quarantine.state is AIReviewState.QUARANTINED
    revoked = repo.record_revocation(
        review_snapshot_id=snapshot.review_snapshot_id,
        context=context,
        actor_provider=snapshot.payload.creator.agent_provider,
        actor_run_id="codex-revocation-run",
        artifact_ref=snapshot.review_snapshot_id,
        reason_sha256="8" * 64,
        created_at=CREATED_AT,
    )
    assert revoked.state is AIReviewState.REVOKED
    with pytest.raises(AIReviewValidationError):
        repo.record_quarantine(
            review_snapshot_id=snapshot.review_snapshot_id,
            context=context,
            actor_provider=snapshot.payload.creator.agent_provider,
            actor_run_id="codex-invalid-reentry",
            artifact_ref=snapshot.review_snapshot_id,
            reason_sha256="7" * 64,
            created_at=CREATED_AT,
        )


def test_database_constraints_reject_human_identity_production_and_positive_authority(
    tmp_path,
) -> None:
    _, factory, _, _, snapshot = _setup(tmp_path)
    with pytest.raises(IntegrityError):
        with factory() as session, session.begin():
            family = session.get(V2MaterialEvidenceAIReviewBatch, BATCH_ID)
            session.add(
                V2MaterialEvidenceAIReviewBatch(
                    batch_id="mai_" + "9" * 32,
                    tenant_id="tenant-test",
                    environment="production",
                    domain_pack_id=family.domain_pack_id,
                    ruleset_snapshot_id=family.ruleset_snapshot_id,
                    evidence_snapshot_id=family.evidence_snapshot_id,
                    creator_identity_kind="verified_human",
                    creator_provider="openai",
                    creator_model="test",
                    creator_version="test",
                    creator_run_id="forbidden-run",
                    created_at=CREATED_AT,
                )
            )
    with pytest.raises(DBAPIError, match="MAT-EVID AI immutable table"):
        with factory() as session, session.begin():
            session.execute(
                update(V2MaterialEvidenceAIReviewSnapshot)
                .where(
                    V2MaterialEvidenceAIReviewSnapshot.review_snapshot_id
                    == snapshot.review_snapshot_id
                )
                .values(positive_statement_allowed=True)
            )


def test_every_ai_table_rejects_update_and_delete(tmp_path) -> None:
    engine, _, repo, context, snapshot = _setup(tmp_path)
    challenge = _challenge(snapshot)
    repo.record_challenge(challenge=challenge, context=context, created_at=CREATED_AT)
    adjudication = create_adjudication(
        snapshot=snapshot,
        challenge=challenge,
        adjudicator=_adjudicator("codex-immutability-adjudicator"),
        finding_adjudications=(),
    )
    repo.record_adjudication(
        adjudication=adjudication, context=context, created_at=CREATED_AT
    )
    for table in sorted(AI_TABLES):
        for statement in (
            f'UPDATE "{table}" SET created_at = created_at',
            f'DELETE FROM "{table}"',
        ):
            with pytest.raises(DBAPIError, match="MAT-EVID AI immutable table"):
                with engine.begin() as connection:
                    connection.execute(text(statement))


def test_populated_tables_block_downgrade(tmp_path) -> None:
    engine, _, _, _, _ = _setup(tmp_path)
    assert migration_status(engine)[0] == "20260718_0019"
    with pytest.raises(RuntimeError, match="contain data"):
        with engine.begin() as connection:
            command.downgrade(_config(connection=connection), "20260718_0018")


def test_repository_exposes_no_update_delete_approval_or_activation_methods() -> None:
    forbidden = {
        "update",
        "delete",
        "approve",
        "record_approval",
        "activate",
        "set_active_pointer",
        "set_sampling",
    }
    assert not forbidden & set(dir(MaterialEvidenceAIReviewRepositoryV1))
