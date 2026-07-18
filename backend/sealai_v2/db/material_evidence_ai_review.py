"""Tenant-isolated, append-only persistence for MAT-EVID-AI-REVIEW.v1."""

from __future__ import annotations

from dataclasses import dataclass
import json
import secrets

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.core.material_evidence_ai_review import (
    AI_REVIEW_AUTHORITY,
    MAT_EVID_AI_REVIEW_CONTRACT_VERSION,
    AIReviewEnvironment,
    AIReviewErrorCode,
    AIReviewEventType,
    AIReviewIntegrityError,
    AIReviewPayloadV1,
    AIReviewProjectionV1,
    AIReviewSnapshotV1,
    AIReviewState,
    AIReviewValidationError,
    AgentExecutionIsolationV1,
    AgentProvider,
    ChallengerAgentRunV1,
    compute_ai_review_audit_sha256,
    compute_ai_review_lifecycle_sha256,
    compute_ai_review_validation_sha256,
    transition_ai_review,
    validate_ai_review_batch_id,
    validate_ai_review_snapshot_id,
)
from sealai_v2.db.material_evidence_v2 import MaterialEvidenceRepositoryV2
from sealai_v2.core.material_evidence_v2 import (
    EvidenceManifestSnapshotV2,
    MediaIdentityTargetV2,
)
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
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
    AIAdjudicationOutcome,
    AIAdjudicationV1,
    ClaudeChallengeV1,
    create_adjudication,
    parse_claude_audit_report,
)


@dataclass(frozen=True, slots=True)
class NonProductionAIReviewContextV1:
    tenant_id: str
    environment: AIReviewEnvironment
    authorization_ref: str

    def __post_init__(self) -> None:
        for name, value in (
            ("tenant_id", self.tenant_id),
            ("authorization_ref", self.authorization_ref),
        ):
            if type(value) is not str or not any(not char.isspace() for char in value):
                raise ValueError(f"{name} must be a non-whitespace string")
        if type(self.environment) is not AIReviewEnvironment:
            raise AIReviewValidationError(
                AIReviewErrorCode.PRODUCTION_FORBIDDEN,
                "only a closed non-production environment is accepted",
            )


@dataclass(frozen=True, slots=True)
class AIReviewBatchFamilyV1:
    batch_id: str
    tenant_id: str
    environment: AIReviewEnvironment
    domain_pack_id: str
    ruleset_snapshot_id: str
    evidence_snapshot_id: str
    creator_run_id: str
    created_at: str


def _identity(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


def _metadata(value: str, *, field: str) -> str:
    if type(value) is not str or not any(not char.isspace() for char in value):
        raise ValueError(f"{field} must be a non-whitespace string")
    return value


class MaterialEvidenceAIReviewRepositoryV1:
    """Offline/non-production repository with no runtime or public API seam."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._rulesets = MaterialRulesetRepository(session_factory)
        self._evidence = MaterialEvidenceRepositoryV2(session_factory)

    def create_batch(
        self,
        *,
        payload: AIReviewPayloadV1,
        context: NonProductionAIReviewContextV1,
        created_at: str,
        batch_id: str | None = None,
    ) -> AIReviewBatchFamilyV1:
        if type(payload) is not AIReviewPayloadV1:
            raise TypeError("payload must be AIReviewPayloadV1")
        self._require_context(payload, context)
        timestamp = _metadata(created_at, field="created_at")
        identifier = batch_id or _identity("mai")
        validate_ai_review_batch_id(identifier)
        ruleset = self._rulesets.load_snapshot(payload.ruleset_snapshot_id)
        evidence = self._evidence.load_snapshot(payload.evidence_snapshot_id)
        payload.validate_against(
            ruleset, evidence, self._load_media_identity_evidence(payload)
        )
        with self._session_factory() as session, session.begin():
            if session.get(V2MaterialEvidenceAIReviewBatch, identifier) is not None:
                raise ValueError("batch_id already exists")
            session.add(
                V2MaterialEvidenceAIReviewBatch(
                    batch_id=identifier,
                    tenant_id=context.tenant_id,
                    environment=context.environment.value,
                    domain_pack_id=payload.domain_pack_id,
                    ruleset_snapshot_id=payload.ruleset_snapshot_id,
                    evidence_snapshot_id=payload.evidence_snapshot_id,
                    creator_identity_kind="ai_agent",
                    creator_provider=payload.creator.agent_provider.value,
                    creator_model=payload.creator.agent_model,
                    creator_version=payload.creator.agent_version,
                    creator_run_id=payload.creator.run_id,
                    created_at=timestamp,
                )
            )
        return AIReviewBatchFamilyV1(
            batch_id=identifier,
            tenant_id=context.tenant_id,
            environment=context.environment,
            domain_pack_id=payload.domain_pack_id,
            ruleset_snapshot_id=payload.ruleset_snapshot_id,
            evidence_snapshot_id=payload.evidence_snapshot_id,
            creator_run_id=payload.creator.run_id,
            created_at=timestamp,
        )

    def store_snapshot(
        self,
        *,
        batch_id: str,
        raw_payload: str | bytes,
        context: NonProductionAIReviewContextV1,
        created_at: str,
    ) -> AIReviewSnapshotV1:
        validate_ai_review_batch_id(batch_id)
        timestamp = _metadata(created_at, field="created_at")
        snapshot = AIReviewSnapshotV1.from_json(batch_id, raw_payload)
        self._require_context(snapshot.payload, context)
        ruleset = self._rulesets.load_snapshot(snapshot.payload.ruleset_snapshot_id)
        evidence = self._evidence.load_snapshot(snapshot.payload.evidence_snapshot_id)
        snapshot.payload.validate_against(
            ruleset,
            evidence,
            self._load_media_identity_evidence(snapshot.payload),
        )
        with self._session_factory() as session, session.begin():
            family = self._family_for_context(session, batch_id, context)
            self._validate_family_payload(family, snapshot.payload)
            existing = session.get(
                V2MaterialEvidenceAIReviewSnapshot, snapshot.review_snapshot_id
            )
            if existing is not None:
                return self._validated_snapshot(existing, family, session)
            session.add(
                V2MaterialEvidenceAIReviewSnapshot(
                    review_snapshot_id=snapshot.review_snapshot_id,
                    batch_id=batch_id,
                    ruleset_snapshot_id=snapshot.payload.ruleset_snapshot_id,
                    ruleset_content_sha256=snapshot.payload.ruleset_content_sha256,
                    evidence_snapshot_id=snapshot.payload.evidence_snapshot_id,
                    evidence_content_sha256=snapshot.payload.evidence_content_sha256,
                    ai_review_schema_version=(
                        snapshot.payload.ai_review_schema_version
                    ),
                    canonicalization_version=(
                        snapshot.payload.canonicalization_version
                    ),
                    ai_review_contract_version=(
                        snapshot.payload.mat_evid_ai_review_contract_version
                    ),
                    content_sha256=snapshot.content_sha256,
                    canonical_payload_json=snapshot.payload.to_dict(),
                    canonical_bytes=snapshot.canonical_bytes,
                    authority=AI_REVIEW_AUTHORITY,
                    positive_statement_allowed=False,
                    creator_input_sha256=snapshot.payload.creator.input_sha256,
                    creator_output_sha256=snapshot.payload.creator.output_sha256,
                    created_at=timestamp,
                )
            )
            session.flush()
            validation_event_id = _identity("mav")
            session.add(
                V2MaterialEvidenceAIValidationEvent(
                    event_id=validation_event_id,
                    review_snapshot_id=snapshot.review_snapshot_id,
                    validator_contract_version=MAT_EVID_AI_REVIEW_CONTRACT_VERSION,
                    validation_state="valid",
                    error_code="none",
                    validation_sha256=compute_ai_review_validation_sha256(snapshot),
                    created_at=timestamp,
                )
            )
            audit_payload = {
                "authorization_ref": context.authorization_ref,
                "content_sha256": snapshot.content_sha256,
                "review_snapshot_id": snapshot.review_snapshot_id,
                "validation_event_id": validation_event_id,
            }
            self._add_audit(
                session,
                snapshot.review_snapshot_id,
                event_type="review_snapshot_created",
                actor_provider=AgentProvider.OPENAI,
                actor_run_id=snapshot.payload.creator.run_id,
                payload=audit_payload,
                created_at=timestamp,
            )
        return snapshot

    def load_snapshot(
        self,
        review_snapshot_id: str,
        *,
        context: NonProductionAIReviewContextV1,
    ) -> AIReviewSnapshotV1:
        validate_ai_review_snapshot_id(review_snapshot_id)
        with self._session_factory() as session:
            row = session.get(V2MaterialEvidenceAIReviewSnapshot, review_snapshot_id)
            if row is None:
                raise KeyError(review_snapshot_id)
            family = self._family_for_context(session, row.batch_id, context)
            return self._validated_snapshot(row, family, session)

    def record_challenge(
        self,
        *,
        challenge: ClaudeChallengeV1,
        context: NonProductionAIReviewContextV1,
        created_at: str,
    ) -> AIReviewProjectionV1:
        if type(challenge) is not ClaudeChallengeV1:
            raise TypeError("challenge must be ClaudeChallengeV1")
        timestamp = _metadata(created_at, field="created_at")
        snapshot = self.load_snapshot(challenge.review_snapshot_id, context=context)
        challenge.validate_against(snapshot)
        failures = snapshot.payload.eligibility_failures()
        if failures:
            raise AIReviewValidationError(
                AIReviewErrorCode.SOURCE_BLOCKED,
                f"challenge preflight blocked: {failures}",
            )
        if challenge.review_content_sha256 != snapshot.content_sha256:
            raise AIReviewValidationError(
                AIReviewErrorCode.HASH_MISMATCH, "challenge content drift"
            )
        with self._session_factory() as session, session.begin():
            row = session.get(
                V2MaterialEvidenceAIReviewSnapshot, snapshot.review_snapshot_id
            )
            family = self._family_for_context(session, row.batch_id, context)
            projection = self._replay(session, row, family)
            if projection.state is not AIReviewState.AI_DRAFT:
                raise AIReviewValidationError(
                    AIReviewErrorCode.INVALID_TRANSITION,
                    "a snapshot may be challenged exactly once",
                )
            if session.get(V2MaterialEvidenceAIChallenge, challenge.challenge_id):
                raise ValueError("challenge already exists")
            isolation = challenge.challenger.isolation
            session.add(
                V2MaterialEvidenceAIChallenge(
                    challenge_id=challenge.challenge_id,
                    review_snapshot_id=challenge.review_snapshot_id,
                    challenger_identity_kind="ai_agent",
                    challenger_provider=challenge.challenger.agent_provider.value,
                    challenger_model=challenge.challenger.agent_model,
                    challenger_version=challenge.challenger.agent_version,
                    challenger_run_id=challenge.challenger.run_id,
                    challenger_prompt_version=challenge.challenger.prompt_version,
                    challenger_prompt_sha256=challenge.challenger.prompt_sha256,
                    audit_input_sha256=challenge.challenger.audit_input_sha256,
                    audit_output_sha256=challenge.challenger.audit_output_sha256,
                    report_sha256=challenge.report_sha256,
                    tools_enabled=isolation.tools_enabled,
                    mcp_enabled=isolation.mcp_enabled,
                    hooks_enabled=isolation.hooks_enabled,
                    session_persistence_enabled=(isolation.session_persistence_enabled),
                    web_search_requests=isolation.web_search_requests,
                    web_fetch_requests=isolation.web_fetch_requests,
                    canonical_report_json=challenge.report.to_dict(),
                    created_at=timestamp,
                )
            )
            projection = self._append_lifecycle(
                session,
                row,
                family,
                event_type=AIReviewEventType.CHALLENGED,
                actor_provider=AgentProvider.ANTHROPIC,
                actor_run_id=challenge.challenger.run_id,
                artifact_ref=challenge.challenge_id,
                created_at=timestamp,
            )
            self._add_audit(
                session,
                snapshot.review_snapshot_id,
                event_type="challenge_recorded",
                actor_provider=AgentProvider.ANTHROPIC,
                actor_run_id=challenge.challenger.run_id,
                payload={
                    "challenge_id": challenge.challenge_id,
                    "report_sha256": challenge.report_sha256,
                    "review_snapshot_id": snapshot.review_snapshot_id,
                },
                created_at=timestamp,
            )
            return projection

    def record_adjudication(
        self,
        *,
        adjudication: AIAdjudicationV1,
        context: NonProductionAIReviewContextV1,
        created_at: str,
    ) -> AIReviewProjectionV1:
        if type(adjudication) is not AIAdjudicationV1:
            raise TypeError("adjudication must be AIAdjudicationV1")
        timestamp = _metadata(created_at, field="created_at")
        snapshot = self.load_snapshot(adjudication.review_snapshot_id, context=context)
        if adjudication.review_content_sha256 != snapshot.content_sha256:
            raise AIReviewValidationError(
                AIReviewErrorCode.HASH_MISMATCH, "adjudication content drift"
            )
        with self._session_factory() as session, session.begin():
            row = session.get(
                V2MaterialEvidenceAIReviewSnapshot, snapshot.review_snapshot_id
            )
            family = self._family_for_context(session, row.batch_id, context)
            projection = self._replay(session, row, family)
            if projection.state is not AIReviewState.AI_CHALLENGED:
                raise AIReviewValidationError(
                    AIReviewErrorCode.INVALID_TRANSITION,
                    "adjudication requires ai_challenged state",
                )
            challenge = session.get(
                V2MaterialEvidenceAIChallenge, adjudication.challenge_id
            )
            if challenge is None:
                raise AIReviewValidationError(
                    AIReviewErrorCode.HASH_MISMATCH,
                    "adjudication references a foreign challenge",
                )
            try:
                stored_report = parse_claude_audit_report(
                    json.dumps(
                        challenge.canonical_report_json,
                        ensure_ascii=False,
                        allow_nan=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    snapshot,
                )
                stored_challenge = ClaudeChallengeV1(
                    challenge_id=challenge.challenge_id,
                    review_snapshot_id=snapshot.review_snapshot_id,
                    review_content_sha256=snapshot.content_sha256,
                    challenger=ChallengerAgentRunV1(
                        agent_version=challenge.challenger_version,
                        prompt_version=challenge.challenger_prompt_version,
                        prompt_sha256=challenge.challenger_prompt_sha256,
                        run_id=challenge.challenger_run_id,
                        audit_input_sha256=challenge.audit_input_sha256,
                        audit_output_sha256=challenge.audit_output_sha256,
                        isolation=AgentExecutionIsolationV1(
                            tools_enabled=challenge.tools_enabled,
                            mcp_enabled=challenge.mcp_enabled,
                            hooks_enabled=challenge.hooks_enabled,
                            web_search_requests=challenge.web_search_requests,
                            web_fetch_requests=challenge.web_fetch_requests,
                            session_persistence_enabled=(
                                challenge.session_persistence_enabled
                            ),
                        ),
                    ),
                    report=stored_report,
                    report_sha256=challenge.report_sha256,
                )
                stored_challenge.validate_against(snapshot)
            except (AIReviewValidationError, TypeError, ValueError) as exc:
                raise AIReviewIntegrityError(
                    AIReviewErrorCode.DB_INTEGRITY,
                    "stored challenge provenance or report drift",
                ) from exc
            if (
                stored_challenge.challenge_id != adjudication.challenge_id
                or stored_challenge.report_sha256
                != adjudication.challenger_report_sha256
            ):
                raise AIReviewValidationError(
                    AIReviewErrorCode.HASH_MISMATCH,
                    "adjudication challenge binding drift",
                )
            if session.get(
                V2MaterialEvidenceAIAdjudication, adjudication.adjudication_id
            ):
                raise ValueError("adjudication already exists")
            replacement_ruleset_id = (
                adjudication.replacement_ruleset_snapshot_id
                if adjudication.replacement_ruleset_snapshot_id != "not_applicable"
                else None
            )
            replacement_evidence_id = (
                adjudication.replacement_evidence_snapshot_id
                if adjudication.replacement_evidence_snapshot_id != "not_applicable"
                else None
            )
            replacement_ruleset = None
            replacement_evidence = None
            if replacement_ruleset_id is not None:
                replacement_ruleset = self._rulesets.load_snapshot(
                    replacement_ruleset_id
                )
                replacement_evidence = self._evidence.load_snapshot(
                    replacement_evidence_id
                )
                if (
                    replacement_evidence.payload.target.ruleset_snapshot_id
                    != replacement_ruleset.snapshot_id
                ):
                    raise AIReviewValidationError(
                        AIReviewErrorCode.HASH_MISMATCH,
                        "replacement snapshot pair is not bound",
                    )
            replacement_identity_evidence = []
            for correction in adjudication.replacement_media_identity_evidence:
                replacement = self._evidence.load_snapshot(
                    correction.replacement_evidence_snapshot_id
                )
                if (
                    replacement.content_sha256
                    != correction.replacement_evidence_content_sha256
                    or type(replacement.payload.target) is not MediaIdentityTargetV2
                    or replacement.payload.target.media_ref != correction.media_ref
                ):
                    raise AIReviewValidationError(
                        AIReviewErrorCode.HASH_MISMATCH,
                        "media identity replacement binding drift",
                    )
                replacement_identity_evidence.append(replacement)
            expected_adjudication = create_adjudication(
                snapshot=snapshot,
                challenge=stored_challenge,
                adjudicator=adjudication.adjudicator,
                finding_adjudications=adjudication.finding_adjudications,
                replacement_ruleset=replacement_ruleset,
                replacement_evidence=replacement_evidence,
                replacement_media_identity_evidence=tuple(
                    replacement_identity_evidence
                ),
            )
            if (
                adjudication != expected_adjudication
                or adjudication.to_dict() != expected_adjudication.to_dict()
            ):
                raise AIReviewValidationError(
                    AIReviewErrorCode.INVALID_TRANSITION,
                    "adjudication differs from the canonical stored-report derivation",
                )
            run = adjudication.adjudicator
            session.add(
                V2MaterialEvidenceAIAdjudication(
                    adjudication_id=adjudication.adjudication_id,
                    review_snapshot_id=adjudication.review_snapshot_id,
                    challenge_id=adjudication.challenge_id,
                    adjudicator_identity_kind="ai_agent",
                    adjudicator_provider=run.agent_provider.value,
                    adjudicator_model=run.agent_model,
                    adjudicator_version=run.agent_version,
                    adjudicator_run_id=run.run_id,
                    input_sha256=run.input_sha256,
                    output_sha256=run.output_sha256,
                    outcome=adjudication.outcome.value,
                    replacement_ruleset_snapshot_id=replacement_ruleset_id,
                    replacement_evidence_snapshot_id=replacement_evidence_id,
                    canonical_adjudication_json=adjudication.to_dict(),
                    created_at=timestamp,
                )
            )
            projection = self._append_lifecycle(
                session,
                row,
                family,
                event_type=adjudication.event_type,
                actor_provider=AgentProvider.OPENAI,
                actor_run_id=run.run_id,
                artifact_ref=adjudication.adjudication_id,
                created_at=timestamp,
            )
            self._add_audit(
                session,
                snapshot.review_snapshot_id,
                event_type=(
                    "quarantine_recorded"
                    if adjudication.outcome is AIAdjudicationOutcome.QUARANTINED
                    else "adjudication_recorded"
                ),
                actor_provider=AgentProvider.OPENAI,
                actor_run_id=run.run_id,
                payload={
                    "adjudication_id": adjudication.adjudication_id,
                    "challenge_id": adjudication.challenge_id,
                    "outcome": adjudication.outcome.value,
                },
                created_at=timestamp,
            )
            return projection

    def record_quarantine(
        self,
        *,
        review_snapshot_id: str,
        context: NonProductionAIReviewContextV1,
        actor_provider: AgentProvider,
        actor_run_id: str,
        artifact_ref: str,
        reason_sha256: str,
        created_at: str,
    ) -> AIReviewProjectionV1:
        return self._record_terminal_event(
            review_snapshot_id=review_snapshot_id,
            context=context,
            event_type=AIReviewEventType.QUARANTINED,
            audit_type="quarantine_recorded",
            actor_provider=actor_provider,
            actor_run_id=actor_run_id,
            artifact_ref=artifact_ref,
            reason_sha256=reason_sha256,
            created_at=created_at,
        )

    def record_revocation(
        self,
        *,
        review_snapshot_id: str,
        context: NonProductionAIReviewContextV1,
        actor_provider: AgentProvider,
        actor_run_id: str,
        artifact_ref: str,
        reason_sha256: str,
        created_at: str,
    ) -> AIReviewProjectionV1:
        return self._record_terminal_event(
            review_snapshot_id=review_snapshot_id,
            context=context,
            event_type=AIReviewEventType.REVOKED,
            audit_type="revocation_recorded",
            actor_provider=actor_provider,
            actor_run_id=actor_run_id,
            artifact_ref=artifact_ref,
            reason_sha256=reason_sha256,
            created_at=created_at,
        )

    def load_projection(
        self,
        review_snapshot_id: str,
        *,
        context: NonProductionAIReviewContextV1,
    ) -> AIReviewProjectionV1:
        validate_ai_review_snapshot_id(review_snapshot_id)
        with self._session_factory() as session:
            row = session.get(V2MaterialEvidenceAIReviewSnapshot, review_snapshot_id)
            if row is None:
                raise KeyError(review_snapshot_id)
            family = self._family_for_context(session, row.batch_id, context)
            return self._replay(session, row, family)

    def _record_terminal_event(
        self,
        *,
        review_snapshot_id: str,
        context: NonProductionAIReviewContextV1,
        event_type: AIReviewEventType,
        audit_type: str,
        actor_provider: AgentProvider,
        actor_run_id: str,
        artifact_ref: str,
        reason_sha256: str,
        created_at: str,
    ) -> AIReviewProjectionV1:
        validate_ai_review_snapshot_id(review_snapshot_id)
        if type(actor_provider) is not AgentProvider:
            raise TypeError("actor_provider must be AgentProvider")
        _metadata(actor_run_id, field="actor_run_id")
        _metadata(artifact_ref, field="artifact_ref")
        if len(artifact_ref) != 68:
            raise ValueError("artifact_ref must be a content-addressed 68-character ID")
        if (
            type(reason_sha256) is not str
            or len(reason_sha256) != 64
            or any(char not in "0123456789abcdef" for char in reason_sha256)
        ):
            raise ValueError("reason_sha256 must be lowercase SHA-256")
        timestamp = _metadata(created_at, field="created_at")
        with self._session_factory() as session, session.begin():
            row = session.get(V2MaterialEvidenceAIReviewSnapshot, review_snapshot_id)
            if row is None:
                raise KeyError(review_snapshot_id)
            family = self._family_for_context(session, row.batch_id, context)
            projection = self._append_lifecycle(
                session,
                row,
                family,
                event_type=event_type,
                actor_provider=actor_provider,
                actor_run_id=actor_run_id,
                artifact_ref=artifact_ref,
                created_at=timestamp,
            )
            self._add_audit(
                session,
                review_snapshot_id,
                event_type=audit_type,
                actor_provider=actor_provider,
                actor_run_id=actor_run_id,
                payload={
                    "artifact_ref": artifact_ref,
                    "reason_sha256": reason_sha256,
                    "review_snapshot_id": review_snapshot_id,
                },
                created_at=timestamp,
            )
            return projection

    @staticmethod
    def _require_context(
        payload: AIReviewPayloadV1, context: NonProductionAIReviewContextV1
    ) -> None:
        if type(context) is not NonProductionAIReviewContextV1:
            raise TypeError("context must be NonProductionAIReviewContextV1")
        if (
            payload.tenant_id != context.tenant_id
            or payload.environment is not context.environment
        ):
            raise AIReviewValidationError(
                AIReviewErrorCode.TENANT_MISMATCH,
                "payload differs from the authorized non-production context",
            )

    @staticmethod
    def _family_for_context(session, batch_id: str, context):
        family = session.get(V2MaterialEvidenceAIReviewBatch, batch_id)
        if family is None:
            raise KeyError(batch_id)
        if (
            family.tenant_id != context.tenant_id
            or family.environment != context.environment.value
        ):
            raise AIReviewValidationError(
                AIReviewErrorCode.TENANT_MISMATCH,
                "AI review family belongs to another context",
            )
        if (
            family.creator_identity_kind != "ai_agent"
            or family.creator_provider != "openai"
        ):
            raise AIReviewIntegrityError(
                AIReviewErrorCode.DB_INTEGRITY, "creator identity columns drifted"
            )
        return family

    @staticmethod
    def _validate_family_payload(family, payload: AIReviewPayloadV1) -> None:
        if (
            family.domain_pack_id != payload.domain_pack_id
            or family.ruleset_snapshot_id != payload.ruleset_snapshot_id
            or family.evidence_snapshot_id != payload.evidence_snapshot_id
            or family.creator_run_id != payload.creator.run_id
            or family.creator_model != payload.creator.agent_model
            or family.creator_version != payload.creator.agent_version
        ):
            raise AIReviewValidationError(
                AIReviewErrorCode.HASH_MISMATCH, "batch family binding drift"
            )

    def _load_media_identity_evidence(
        self, payload: AIReviewPayloadV1
    ) -> tuple[EvidenceManifestSnapshotV2, ...]:
        return tuple(
            self._evidence.load_snapshot(item.evidence_snapshot_id)
            for item in payload.media_identities
        )

    def _validated_snapshot(self, row, family, session) -> AIReviewSnapshotV1:
        try:
            canonical = bytes(row.canonical_bytes)
            snapshot = AIReviewSnapshotV1.from_json(row.batch_id, canonical)
            self._validate_family_payload(family, snapshot.payload)
            if (
                row.review_snapshot_id != snapshot.review_snapshot_id
                or row.content_sha256 != snapshot.content_sha256
                or row.canonical_payload_json != snapshot.payload.to_dict()
                or row.ruleset_snapshot_id != snapshot.payload.ruleset_snapshot_id
                or row.ruleset_content_sha256 != snapshot.payload.ruleset_content_sha256
                or row.evidence_snapshot_id != snapshot.payload.evidence_snapshot_id
                or row.evidence_content_sha256
                != snapshot.payload.evidence_content_sha256
                or row.ai_review_schema_version
                != snapshot.payload.ai_review_schema_version
                or row.canonicalization_version
                != snapshot.payload.canonicalization_version
                or row.ai_review_contract_version
                != snapshot.payload.mat_evid_ai_review_contract_version
                or row.authority != AI_REVIEW_AUTHORITY
                or row.positive_statement_allowed is not False
                or row.creator_input_sha256 != snapshot.payload.creator.input_sha256
                or row.creator_output_sha256 != snapshot.payload.creator.output_sha256
            ):
                raise AIReviewIntegrityError(
                    AIReviewErrorCode.DB_INTEGRITY, "snapshot columns drifted"
                )
            ruleset = self._rulesets.load_snapshot(snapshot.payload.ruleset_snapshot_id)
            evidence = self._evidence.load_snapshot(
                snapshot.payload.evidence_snapshot_id
            )
            snapshot.payload.validate_against(
                ruleset,
                evidence,
                self._load_media_identity_evidence(snapshot.payload),
            )
            validations = session.scalars(
                select(V2MaterialEvidenceAIValidationEvent).where(
                    V2MaterialEvidenceAIValidationEvent.review_snapshot_id
                    == snapshot.review_snapshot_id
                )
            ).all()
            creation_audits = session.scalars(
                select(V2MaterialEvidenceAIAuditEvent).where(
                    V2MaterialEvidenceAIAuditEvent.review_snapshot_id
                    == snapshot.review_snapshot_id,
                    V2MaterialEvidenceAIAuditEvent.event_type
                    == "review_snapshot_created",
                )
            ).all()
            if len(validations) != 1 or len(creation_audits) != 1:
                raise AIReviewIntegrityError(
                    AIReviewErrorCode.DB_INTEGRITY,
                    "snapshot requires one validation and one creation audit",
                )
            validation = validations[0]
            if (
                validation.validator_contract_version
                != MAT_EVID_AI_REVIEW_CONTRACT_VERSION
                or validation.validation_state != "valid"
                or validation.error_code != "none"
                or validation.validation_sha256
                != compute_ai_review_validation_sha256(snapshot)
            ):
                raise AIReviewIntegrityError(
                    AIReviewErrorCode.DB_INTEGRITY, "validation event drifted"
                )
            audit = creation_audits[0]
            if (
                audit.actor_identity_kind != "ai_agent"
                or audit.actor_provider != "openai"
                or audit.actor_run_id != snapshot.payload.creator.run_id
                or audit.event_sha256
                != compute_ai_review_audit_sha256(audit.event_payload_json)
            ):
                raise AIReviewIntegrityError(
                    AIReviewErrorCode.DB_INTEGRITY, "creation audit drifted"
                )
            return snapshot
        except AIReviewIntegrityError:
            raise
        except Exception as exc:
            raise AIReviewIntegrityError(
                AIReviewErrorCode.DB_INTEGRITY,
                "persisted AI review failed strict revalidation",
            ) from exc

    def _append_lifecycle(
        self,
        session,
        row,
        family,
        *,
        event_type: AIReviewEventType,
        actor_provider: AgentProvider,
        actor_run_id: str,
        artifact_ref: str,
        created_at: str,
    ) -> AIReviewProjectionV1:
        current = self._replay(session, row, family)
        transitioned = transition_ai_review(current, event_type)
        sequence = current.last_sequence + 1
        payload = {
            "actor_identity_kind": "ai_agent",
            "actor_provider": actor_provider.value,
            "actor_run_id": actor_run_id,
            "artifact_ref": artifact_ref,
            "created_at": created_at,
            "event_type": event_type.value,
            "previous_event_sha256": current.last_event_sha256,
            "review_snapshot_id": row.review_snapshot_id,
            "sequence_no": sequence,
            "state": transitioned.state.value,
        }
        event_hash = compute_ai_review_lifecycle_sha256(payload)
        session.add(
            V2MaterialEvidenceAILifecycleEvent(
                event_id=_identity("mal"),
                review_snapshot_id=row.review_snapshot_id,
                sequence_no=sequence,
                event_type=event_type.value,
                state=transitioned.state.value,
                actor_identity_kind="ai_agent",
                actor_provider=actor_provider.value,
                actor_run_id=actor_run_id,
                artifact_ref=artifact_ref,
                previous_event_sha256=current.last_event_sha256,
                event_sha256=event_hash,
                created_at=created_at,
            )
        )
        return AIReviewProjectionV1(
            state=transitioned.state,
            last_sequence=sequence,
            last_event_sha256=event_hash,
        )

    @staticmethod
    def _replay(session, row, family) -> AIReviewProjectionV1:
        events = session.scalars(
            select(V2MaterialEvidenceAILifecycleEvent)
            .where(
                V2MaterialEvidenceAILifecycleEvent.review_snapshot_id
                == row.review_snapshot_id
            )
            .order_by(V2MaterialEvidenceAILifecycleEvent.sequence_no)
        ).all()
        projection = AIReviewProjectionV1()
        for expected_sequence, event in enumerate(events, start=1):
            if (
                event.sequence_no != expected_sequence
                or event.previous_event_sha256 != projection.last_event_sha256
                or event.actor_identity_kind != "ai_agent"
                or event.actor_provider not in {"openai", "anthropic"}
            ):
                raise AIReviewIntegrityError(
                    AIReviewErrorCode.DB_INTEGRITY, "lifecycle sequence drifted"
                )
            try:
                event_type = AIReviewEventType(event.event_type)
                next_projection = transition_ai_review(projection, event_type)
                payload = {
                    "actor_identity_kind": event.actor_identity_kind,
                    "actor_provider": event.actor_provider,
                    "actor_run_id": event.actor_run_id,
                    "artifact_ref": event.artifact_ref,
                    "created_at": event.created_at,
                    "event_type": event.event_type,
                    "previous_event_sha256": event.previous_event_sha256,
                    "review_snapshot_id": event.review_snapshot_id,
                    "sequence_no": event.sequence_no,
                    "state": next_projection.state.value,
                }
                if (
                    event.state != next_projection.state.value
                    or event.event_sha256 != compute_ai_review_lifecycle_sha256(payload)
                ):
                    raise AIReviewIntegrityError(
                        AIReviewErrorCode.DB_INTEGRITY,
                        "lifecycle state or hash drifted",
                    )
            except AIReviewIntegrityError:
                raise
            except Exception as exc:
                raise AIReviewIntegrityError(
                    AIReviewErrorCode.DB_INTEGRITY, "invalid lifecycle event"
                ) from exc
            projection = AIReviewProjectionV1(
                state=next_projection.state,
                last_sequence=event.sequence_no,
                last_event_sha256=event.event_sha256,
            )
        return projection

    @staticmethod
    def _add_audit(
        session,
        review_snapshot_id: str,
        *,
        event_type: str,
        actor_provider: AgentProvider,
        actor_run_id: str,
        payload: dict,
        created_at: str,
    ) -> None:
        session.add(
            V2MaterialEvidenceAIAuditEvent(
                event_id=f"maaev_{secrets.token_hex(16)}",
                review_snapshot_id=review_snapshot_id,
                event_type=event_type,
                actor_identity_kind="ai_agent",
                actor_provider=actor_provider.value,
                actor_run_id=actor_run_id,
                event_payload_json=payload,
                event_sha256=compute_ai_review_audit_sha256(payload),
                created_at=created_at,
            )
        )


__all__ = [
    "AIReviewBatchFamilyV1",
    "MaterialEvidenceAIReviewRepositoryV1",
    "NonProductionAIReviewContextV1",
]
