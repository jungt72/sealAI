"""Isolated durable worker for MAT-GOV-03B shadow jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import aliased, sessionmaker

from sealai_v2.core.contracts import (
    InputResolutionState,
    MediumCardinality,
    RelationState,
)
from sealai_v2.core.material_evidence_binding import (
    EvidenceRuntimeBindingState,
    MaterialEvidenceRuntimeErrorCode,
)
from sealai_v2.core.material_shadow import (
    ServerVerifiedCanonicalId,
    ShadowAuthority,
    ShadowErrorCode,
    ShadowJobStatus,
    ShadowMaterialInput,
)
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.material_evidence import MaterialEvidenceRepository
from sealai_v2.db.material_evidence_binding import (
    MaterialEvidenceRuntimeRepository,
)
from sealai_v2.db.models import (
    V2MaterialShadowBinding,
    V2MaterialShadowBindingEvent,
    V2MaterialShadowEvaluation,
    V2MaterialShadowEvaluationMatch,
    V2MaterialShadowEvaluationRef,
    V2MaterialShadowOutbox,
    V2MaterialShadowPin,
    V2MaterialShadowSessionVersion,
)
from sealai_v2.material_shadow.cache import (
    ShadowCache,
    ShadowCacheUnavailable,
    cache_key,
)
from sealai_v2.material_shadow.evaluator import evaluate_snapshot
from sealai_v2.material_shadow.hmac_refs import ShadowHmacKeyring
from sealai_v2.material_evidence_binding.cache import (
    EvidenceRuntimeCache,
    EvidenceRuntimeCacheUnavailable,
    evidence_cache_key,
)
from sealai_v2.material_evidence_binding.evaluator import (
    EvidenceRuntimeEvaluationV1,
    evaluate_with_evidence,
    integrity_blocked_evaluation,
)


_RETENTION_DAYS = 90


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _format(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True, slots=True)
class ShadowDrainResult:
    claimed: int
    evaluated: int
    retried: int
    failed: int


class ShadowLeaseLost(RuntimeError):
    pass


class MaterialShadowWorker:
    def __init__(
        self,
        *,
        session_factory: sessionmaker,
        cache: ShadowCache,
        keyring: ShadowHmacKeyring,
        max_attempts: int = 5,
        claim_timeout_s: int = 60,
        retry_base_s: int = 5,
        retry_max_s: int = 300,
        worker_id: str | None = None,
        evidence_binding_enabled: bool = False,
        evidence_cache: EvidenceRuntimeCache | None = None,
    ) -> None:
        if type(max_attempts) is not int or max_attempts <= 0:
            raise ValueError("shadow max_attempts must be positive")
        if type(claim_timeout_s) is not int or claim_timeout_s <= 0:
            raise ValueError("shadow claim timeout must be positive")
        self._sessions = session_factory
        self._rulesets = MaterialRulesetRepository(session_factory)
        self._evidence_manifests = MaterialEvidenceRepository(session_factory)
        self._evidence_runtime = MaterialEvidenceRuntimeRepository(session_factory)
        self._cache = cache
        self._evidence_binding_enabled = evidence_binding_enabled
        self._evidence_cache = evidence_cache
        if evidence_binding_enabled and evidence_cache is None:
            raise ValueError("enabled runtime evidence binding requires its cache")
        self._keyring = keyring
        self._max_attempts = max_attempts
        self._claim_timeout_s = claim_timeout_s
        self._retry_base_s = retry_base_s
        self._retry_max_s = retry_max_s
        self._worker_id = worker_id or _id("mshw")
        if (
            type(self._worker_id) is not str
            or not self._worker_id
            or len(self._worker_id) > 64
            or any(character.isspace() for character in self._worker_id)
        ):
            raise ValueError("shadow worker_id must be a stable non-whitespace ID")

    @staticmethod
    def _database_now(session) -> datetime:
        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
            value = session.scalar(select(func.clock_timestamp()))
        elif dialect == "sqlite":
            value = session.scalar(select(func.strftime("%Y-%m-%dT%H:%M:%fZ", "now")))
        else:
            raise RuntimeError(f"unsupported shadow worker database {dialect!r}")
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        if type(value) is str:
            return _parse(value)
        raise RuntimeError("database did not return a usable UTC timestamp")

    def _claim(self, *, batch_size: int) -> tuple[list[str], int]:
        earlier = aliased(V2MaterialShadowOutbox)
        with self._sessions() as session, session.begin():
            database_now = self._database_now(session)
            now = _format(database_now)
            exhausted_rows = list(
                session.scalars(
                    select(V2MaterialShadowOutbox)
                    .where(
                        V2MaterialShadowOutbox.status
                        == ShadowJobStatus.PROCESSING.value,
                        V2MaterialShadowOutbox.attempts >= self._max_attempts,
                        V2MaterialShadowOutbox.lease_expires_at <= now,
                    )
                    .with_for_update(skip_locked=True)
                ).all()
            )
            for row in exhausted_rows:
                row.status = ShadowJobStatus.FAILED.value
                row.stable_error_code = ShadowErrorCode.LEASE_ATTEMPTS_EXHAUSTED.value
                row.completed_at = now
                row.next_attempt_at = None
                row.lease_owner = None
                row.lease_expires_at = None
            session.flush()
            runnable = or_(
                (
                    (V2MaterialShadowOutbox.status == ShadowJobStatus.PENDING.value)
                    & (
                        V2MaterialShadowOutbox.next_attempt_at.is_(None)
                        | (V2MaterialShadowOutbox.next_attempt_at <= now)
                    )
                ),
                (
                    (V2MaterialShadowOutbox.status == ShadowJobStatus.PROCESSING.value)
                    & (V2MaterialShadowOutbox.lease_expires_at <= now)
                ),
            )
            prior_unfinished = exists(
                select(earlier.job_id).where(
                    earlier.session_version_id
                    == V2MaterialShadowOutbox.session_version_id,
                    earlier.sequence_no < V2MaterialShadowOutbox.sequence_no,
                    earlier.status.in_(
                        (
                            ShadowJobStatus.PENDING.value,
                            ShadowJobStatus.PROCESSING.value,
                        )
                    ),
                )
            )
            rows = list(
                session.scalars(
                    select(V2MaterialShadowOutbox)
                    .where(
                        runnable,
                        V2MaterialShadowOutbox.attempts < self._max_attempts,
                        ~prior_unfinished,
                    )
                    .order_by(
                        V2MaterialShadowOutbox.session_version_id,
                        V2MaterialShadowOutbox.sequence_no,
                    )
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                ).all()
            )
            for row in rows:
                row.status = ShadowJobStatus.PROCESSING.value
                row.attempts += 1
                row.claimed_at = now
                row.lease_owner = self._worker_id
                row.lease_expires_at = _format(
                    database_now + timedelta(seconds=self._claim_timeout_s)
                )
            return [row.job_id for row in rows], len(exhausted_rows)

    def _load_projection(self, job_id: str, *, now: str) -> tuple:
        with self._sessions() as session:
            job = session.get(V2MaterialShadowOutbox, job_id)
            if job is None:
                raise KeyError(job_id)
            pin = session.get(V2MaterialShadowPin, job.pin_id)
            if pin is None:
                raise RuntimeError("shadow job references a missing pin")
            binding = session.get(V2MaterialShadowBinding, pin.binding_id)
            if binding is None:
                raise RuntimeError("shadow pin references a missing binding")
            terminal = session.scalar(
                select(V2MaterialShadowBindingEvent.event_id).where(
                    V2MaterialShadowBindingEvent.binding_id == binding.binding_id,
                    V2MaterialShadowBindingEvent.event_type.in_(
                        ("REVOKED", "TERMINATED")
                    ),
                    V2MaterialShadowBindingEvent.effective_at <= now,
                )
            )
            if terminal is not None:
                raise PermissionError("SHADOW_BINDING_INACTIVE")
            if not self._keyring.contains(job.hmac_key_id):
                raise LookupError("SHADOW_HMAC_KEY_UNAVAILABLE")
            session_version = session.get(
                V2MaterialShadowSessionVersion, job.session_version_id
            )
            if session_version is None:
                raise RuntimeError("shadow job references a missing session version")
            if (
                pin.snapshot_id != binding.snapshot_id
                or pin.content_sha256 != binding.content_sha256
                or pin.domain_pack_id != job.domain_pack_id
                or pin.domain_pack_version != job.domain_pack_version
                or pin.hmac_key_id != job.hmac_key_id
                or not self._keyring.contains(session_version.hmac_key_id)
            ):
                raise RuntimeError("SHADOW_SNAPSHOT_DRIFT")
            return job, pin, binding, session_version

    @staticmethod
    def _material_input(job: V2MaterialShadowOutbox) -> ShadowMaterialInput:
        registry_ref = f"domain-pack:{job.domain_pack_id}"
        return ShadowMaterialInput(
            material_id=ServerVerifiedCanonicalId(job.material_id, registry_ref),
            medium_id=ServerVerifiedCanonicalId(job.medium_id, registry_ref),
            material_state=InputResolutionState(job.material_state),
            medium_state=InputResolutionState(job.medium_state),
            medium_cardinality=MediumCardinality(job.medium_cardinality),
            relation_state=RelationState(job.relation_state),
            domain_pack_id=job.domain_pack_id,
            domain_pack_version=job.domain_pack_version,
        )

    def _complete(
        self,
        job_id: str,
        projection: dict,
        *,
        now: str,
        cache_hit: bool,
        evidence_result: EvidenceRuntimeEvaluationV1 | None = None,
    ) -> None:
        with self._sessions() as session, session.begin():
            database_now = _format(self._database_now(session))
            job = session.get(V2MaterialShadowOutbox, job_id, with_for_update=True)
            if (
                job is None
                or job.status != ShadowJobStatus.PROCESSING.value
                or job.lease_owner != self._worker_id
                or job.lease_expires_at is None
                or job.lease_expires_at <= database_now
            ):
                raise ShadowLeaseLost("shadow job lost its processing lease")
            existing = session.scalar(
                select(V2MaterialShadowEvaluation).where(
                    V2MaterialShadowEvaluation.job_id == job_id
                )
            )
            if existing is None:
                session_version = session.get(
                    V2MaterialShadowSessionVersion, job.session_version_id
                )
                if session_version is None:
                    raise RuntimeError("shadow evaluation lost its session version")
                evaluation_id = _id("mshe")
                session.add(
                    V2MaterialShadowEvaluation(
                        evaluation_id=evaluation_id,
                        job_id=job_id,
                        pin_id=job.pin_id,
                        hmac_key_id=job.hmac_key_id,
                        evaluation_state=projection["evaluation_state"],
                        verdict=projection["verdict"],
                        decisive_ref=projection["decisive_ref"],
                        result_sha256=projection["result_sha256"],
                        stable_error_code=projection["stable_error_code"],
                        cache_hit=cache_hit,
                        authority=ShadowAuthority.NON_AUTHORITATIVE.value,
                        positive_statement_allowed=False,
                        created_at=now,
                        expires_at=_format(
                            _parse(now) + timedelta(days=_RETENTION_DAYS)
                        ),
                    )
                )
                for match in projection["matches"]:
                    session.add(
                        V2MaterialShadowEvaluationMatch(
                            match_id=_id("mshm"),
                            evaluation_id=evaluation_id,
                            rule_ref=match["rule_ref"],
                            verdict=match["verdict"],
                            source_ref=match["source_ref"],
                        )
                    )
                refs = {
                    "REQUEST": (job.correlation_hmac, job.hmac_key_id),
                    "SESSION": (
                        session_version.session_ref_hmac,
                        session_version.hmac_key_id,
                    ),
                    "CASE": (job.case_ref_hmac, job.hmac_key_id),
                    "DECISION": (job.decision_ref_hmac, job.hmac_key_id),
                }
                for ref_kind, (ref_hmac, ref_key_id) in refs.items():
                    if ref_hmac is None:
                        continue
                    session.add(
                        V2MaterialShadowEvaluationRef(
                            ref_id=_id("mshr"),
                            evaluation_id=evaluation_id,
                            ref_kind=ref_kind,
                            ref_hmac=ref_hmac,
                            hmac_key_id=ref_key_id,
                            authority=ShadowAuthority.NON_AUTHORITATIVE.value,
                        )
                    )
                if evidence_result is not None:
                    evidence_pin = self._evidence_runtime.load_pin(job.pin_id)
                    MaterialEvidenceRuntimeRepository.insert_evaluation_companion(
                        session,
                        evaluation_id=evaluation_id,
                        pin=evidence_pin,
                        result=evidence_result,
                        created_at=now,
                    )
            job.status = ShadowJobStatus.DONE.value
            job.stable_error_code = projection["stable_error_code"]
            job.completed_at = database_now
            job.next_attempt_at = None
            job.lease_owner = None
            job.lease_expires_at = None

    def _fail(self, job_id: str, *, code: ShadowErrorCode) -> bool | None:
        with self._sessions() as session, session.begin():
            database_now = self._database_now(session)
            now = _format(database_now)
            job = session.get(V2MaterialShadowOutbox, job_id, with_for_update=True)
            if job is None:
                return True
            if (
                job.status != ShadowJobStatus.PROCESSING.value
                or job.lease_owner != self._worker_id
                or job.lease_expires_at is None
                or job.lease_expires_at <= now
            ):
                return None
            job.stable_error_code = code.value
            terminal = job.attempts >= self._max_attempts or code in {
                ShadowErrorCode.SNAPSHOT_DRIFT,
                ShadowErrorCode.HMAC_KEY_UNAVAILABLE,
                ShadowErrorCode.BINDING_INACTIVE,
            }
            if terminal:
                job.status = ShadowJobStatus.FAILED.value
                job.completed_at = now
                job.next_attempt_at = None
            else:
                delay = min(
                    self._retry_base_s * (2 ** (job.attempts - 1)),
                    self._retry_max_s,
                )
                job.status = ShadowJobStatus.PENDING.value
                job.next_attempt_at = _format(database_now + timedelta(seconds=delay))
                job.claimed_at = None
            job.lease_owner = None
            job.lease_expires_at = None
            return terminal

    @staticmethod
    def _stable_code(exc: Exception) -> ShadowErrorCode:
        marker = str(exc)
        if marker == "SHADOW_BINDING_INACTIVE":
            return ShadowErrorCode.BINDING_INACTIVE
        if marker == "SHADOW_HMAC_KEY_UNAVAILABLE":
            return ShadowErrorCode.HMAC_KEY_UNAVAILABLE
        if marker == "SHADOW_SNAPSHOT_DRIFT":
            return ShadowErrorCode.SNAPSHOT_DRIFT
        if isinstance(exc, ShadowCacheUnavailable):
            return ShadowErrorCode.CACHE_UNAVAILABLE
        if isinstance(exc, EvidenceRuntimeCacheUnavailable):
            return ShadowErrorCode.CACHE_UNAVAILABLE
        return ShadowErrorCode.INTERNAL

    def drain_once(self, *, now: str, batch_size: int = 50) -> ShadowDrainResult:
        ids, exhausted = self._claim(batch_size=batch_size)
        evaluated = retried = 0
        failed = exhausted
        for job_id in ids:
            try:
                job, pin_row, _binding, _session_version = self._load_projection(
                    job_id, now=now
                )
                pin = MaterialShadowRepositoryPinAdapter.from_row(pin_row)
                evidence_result = None
                if self._evidence_binding_enabled:
                    evidence_pin = self._evidence_runtime.load_pin(pin.pin_id)
                    assert self._evidence_cache is not None
                    key = evidence_cache_key(
                        shadow_pin=pin,
                        evidence_pin=evidence_pin,
                        input_fingerprint=job.input_fingerprint,
                    )
                    evidence_result = self._evidence_cache.get(key)
                    cache_hit = evidence_result is not None
                    try:
                        snapshot = self._rulesets.load_snapshot(pin.snapshot_id)
                        evidence_snapshot = None
                        if (
                            evidence_pin.state
                            is EvidenceRuntimeBindingState.BOUND_UNREVIEWED
                        ):
                            assert evidence_pin.binding.evidence_snapshot_id is not None
                            evidence_snapshot = self._evidence_manifests.load_snapshot(
                                evidence_pin.binding.evidence_snapshot_id
                            )
                        verified_result = evaluate_with_evidence(
                            pin=evidence_pin,
                            ruleset=snapshot,
                            evidence=evidence_snapshot,
                            material_input=self._material_input(job),
                        )
                    except Exception:  # noqa: BLE001 - pinned integrity blocks
                        verified_result = integrity_blocked_evaluation(
                            evidence_pin,
                            MaterialEvidenceRuntimeErrorCode.INTERNAL,
                        )
                    if evidence_result is not None:
                        if evidence_result != verified_result:
                            raise EvidenceRuntimeCacheUnavailable(
                                "runtime evidence cache differs from Postgres state"
                            )
                    else:
                        evidence_result = verified_result
                        if evidence_result.evaluation_state != "integrity_blocked":
                            self._evidence_cache.put(
                                key,
                                evidence_result,
                                ttl_s=_RETENTION_DAYS * 86400,
                            )
                    projection = evidence_result.shadow_projection()
                else:
                    key = cache_key(pin=pin, input_fingerprint=job.input_fingerprint)
                    projection = self._cache.get(key)
                    cache_hit = projection is not None
                    if projection is None:
                        snapshot = self._rulesets.load_snapshot(pin.snapshot_id)
                        if snapshot.content_sha256 != pin.content_sha256:
                            raise RuntimeError("SHADOW_SNAPSHOT_DRIFT")
                        projection = evaluate_snapshot(
                            snapshot, self._material_input(job)
                        )
                        self._cache.put(key, projection, ttl_s=_RETENTION_DAYS * 86400)
                self._complete(
                    job_id,
                    projection,
                    now=now,
                    cache_hit=cache_hit,
                    evidence_result=evidence_result,
                )
                evaluated += 1
            except Exception as exc:  # noqa: BLE001 - stable shadow-only failure state
                terminal = self._fail(job_id, code=self._stable_code(exc))
                if terminal:
                    failed += 1
                else:
                    retried += 1
        return ShadowDrainResult(len(ids), evaluated, retried, failed)


class MaterialShadowRepositoryPinAdapter:
    """Strict row-to-domain adapter kept local to the worker read boundary."""

    @staticmethod
    def from_row(row: V2MaterialShadowPin):
        from sealai_v2.core.material_shadow import (
            ShadowEnvironment,
            ShadowMaterialRulesetPin,
            ShadowPurpose,
            ShadowScopeKind,
        )

        return ShadowMaterialRulesetPin(
            pin_id=row.pin_id,
            binding_id=row.binding_id,
            snapshot_id=row.snapshot_id,
            content_sha256=row.content_sha256,
            environment=ShadowEnvironment(row.environment),
            purpose=ShadowPurpose(row.purpose),
            scope_kind=ShadowScopeKind(row.scope_kind),
            tenant_ref_hmac=row.tenant_ref_hmac,
            hmac_key_id=row.hmac_key_id,
            domain_pack_id=row.domain_pack_id,
            domain_pack_version=row.domain_pack_version,
            evaluator_version=row.evaluator_version,
            kernel_version=row.kernel_version,
            runtime_profile_sha256=row.runtime_profile_sha256,
            build_git_sha=row.build_git_sha,
            build_tree_hash=row.build_tree_hash,
            sampling_policy_version=row.sampling_policy_version,
            sampled=row.sampled,
            acquired_at=row.acquired_at,
            binding_valid_until=row.binding_valid_until,
            pin_schema_version=row.pin_schema_version,
        )
