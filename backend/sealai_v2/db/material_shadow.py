"""Postgres/SQLite adapter for the isolated MAT-GOV-03B shadow aggregate."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import secrets

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import sessionmaker

from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.core.material_shadow import (
    SHADOW_PIN_SCHEMA_VERSION,
    ShadowBinding,
    ShadowBindingEventType,
    ShadowErrorCode,
    ShadowJobStatus,
    ShadowMaterialInput,
    ShadowMaterialRulesetPin,
    ShadowScopeKind,
    parse_utc,
    validate_shadow_reason,
)
from sealai_v2.db.models import (
    V2MaterialShadowBinding,
    V2MaterialShadowBindingEvent,
    V2MaterialShadowOutbox,
    V2MaterialShadowPin,
    V2MaterialShadowSessionUpgradeEvent,
    V2MaterialShadowSessionVersion,
)
from sealai_v2.material_shadow.hmac_refs import (
    BINDING_LOCK_DOMAIN,
    CASE_REF_DOMAIN,
    DECISION_REF_DOMAIN,
    REQUEST_REF_DOMAIN,
    SESSION_REF_DOMAIN,
    TENANT_REF_DOMAIN,
    ShadowHmacKeyring,
    encode_hmac_fields,
)


_EVENT_DOMAIN = b"sealai.material-shadow.binding-event.v1\x00"
_INPUT_DOMAIN = b"sealai.material-shadow.input.v1\x00"
_IDEMPOTENCY_DOMAIN = b"sealai.material-shadow.idempotency.v1\x00"


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


def _event_hash(payload: dict[str, str | int]) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(_EVENT_DOMAIN + encoded).hexdigest()


def _input_fingerprint(value: ShadowMaterialInput) -> str:
    payload = {
        "domain_pack_id": value.domain_pack_id,
        "domain_pack_version": value.domain_pack_version,
        "material_id": value.material_id.canonical_id,
        "material_state": value.material_state.value,
        "medium_cardinality": value.medium_cardinality.value,
        "medium_id": value.medium_id.canonical_id,
        "medium_state": value.medium_state.value,
        "relation_state": value.relation_state.value,
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("ascii")
    return hashlib.sha256(_INPUT_DOMAIN + encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class AtomicCaptureResult:
    pin: ShadowMaterialRulesetPin
    job_id: str
    session_version_id: str
    sequence_no: int
    created: bool


class MaterialShadowRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def create_binding(
        self,
        binding: ShadowBinding,
        *,
        identity: VerifiedIdentity,
        created_at: str,
        hmac_keyring: ShadowHmacKeyring | None = None,
    ) -> None:
        if not isinstance(binding, ShadowBinding):
            raise TypeError("binding must be ShadowBinding")
        if not isinstance(identity, VerifiedIdentity):
            raise TypeError("identity must be VerifiedIdentity")
        if binding.creator_subject != identity.subject:
            raise ValueError("binding creator must equal the verified subject")
        if binding.scope_kind is ShadowScopeKind.TENANT_CANARY:
            if hmac_keyring is None or binding.hmac_key_id is None:
                raise ValueError("tenant canary requires the server HMAC keyring")
            expected_tenant_ref = hmac_keyring.digest_fields(
                TENANT_REF_DOMAIN,
                (identity.tenant_id,),
                key_id=binding.hmac_key_id,
            )
            if binding.tenant_ref_hmac != expected_tenant_ref:
                raise ValueError("tenant canary must equal the verified tenant")
        event_id = _id("mshe")
        event_payload = {
            "actor_subject": identity.subject,
            "binding_id": binding.binding_id,
            "created_at": created_at,
            "effective_at": binding.valid_from,
            "event_id": event_id,
            "event_schema_version": 1,
            "event_type": ShadowBindingEventType.CREATED.value,
            "reason": binding.reason,
        }
        with self._session_factory() as session, session.begin():
            if binding.scope_kind is ShadowScopeKind.TENANT_CANARY:
                assert hmac_keyring is not None
                if (
                    session.bind is not None
                    and session.bind.dialect.name == "postgresql"
                ):
                    # Serialize the verified tenant partition independently of
                    # the active HMAC key.  The raw value is used only as
                    # transaction-local lock material and is never persisted.
                    lock_material = encode_hmac_fields(
                        BINDING_LOCK_DOMAIN,
                        (
                            binding.environment.value,
                            binding.purpose.value,
                            identity.tenant_id,
                            binding.domain_pack_id,
                        ),
                    ).hex()
                    session.execute(
                        text(
                            "SELECT pg_advisory_xact_lock("
                            "hashtextextended(:value,73005))"
                        ),
                        {"value": lock_material},
                    )
                tenant_predicates = tuple(
                    (V2MaterialShadowBinding.hmac_key_id == key_id)
                    & (V2MaterialShadowBinding.tenant_ref_hmac == tenant_ref)
                    for key_id, tenant_ref in hmac_keyring.references_fields(
                        TENANT_REF_DOMAIN,
                        (identity.tenant_id,),
                    )
                )
                overlap = session.scalar(
                    select(V2MaterialShadowBinding.binding_id).where(
                        V2MaterialShadowBinding.environment
                        == binding.environment.value,
                        V2MaterialShadowBinding.purpose == binding.purpose.value,
                        V2MaterialShadowBinding.scope_kind
                        == ShadowScopeKind.TENANT_CANARY.value,
                        V2MaterialShadowBinding.domain_pack_id
                        == binding.domain_pack_id,
                        V2MaterialShadowBinding.valid_from < binding.valid_until,
                        V2MaterialShadowBinding.valid_until > binding.valid_from,
                        or_(*tenant_predicates),
                    )
                )
                if overlap is not None:
                    raise ValueError("overlapping binding")
            session.add(
                V2MaterialShadowBinding(
                    binding_id=binding.binding_id,
                    binding_schema_version=binding.binding_schema_version,
                    snapshot_id=binding.snapshot_id,
                    content_sha256=binding.content_sha256,
                    environment=binding.environment.value,
                    purpose=binding.purpose.value,
                    scope_kind=binding.scope_kind.value,
                    tenant_ref_hmac=binding.tenant_ref_hmac,
                    hmac_key_id=binding.hmac_key_id,
                    domain_pack_id=binding.domain_pack_id,
                    domain_pack_version=binding.domain_pack_version,
                    evaluator_version=binding.evaluator_version,
                    kernel_version=binding.kernel_version,
                    runtime_profile_sha256=binding.runtime_profile_sha256,
                    build_git_sha=binding.build_git_sha,
                    build_tree_hash=binding.build_tree_hash,
                    valid_from=binding.valid_from,
                    valid_until=binding.valid_until,
                    creator_subject=binding.creator_subject,
                    reason=binding.reason,
                    sampling_policy_version=binding.sampling_policy_version,
                    sampling_basis_points=binding.sampling_basis_points,
                    created_at=created_at,
                )
            )
            session.flush()
            session.add(
                V2MaterialShadowBindingEvent(
                    event_id=event_id,
                    event_schema_version=1,
                    binding_id=binding.binding_id,
                    event_type=ShadowBindingEventType.CREATED.value,
                    actor_subject=identity.subject,
                    reason=binding.reason,
                    effective_at=binding.valid_from,
                    created_at=created_at,
                    event_sha256=_event_hash(event_payload),
                )
            )

    def terminate_binding(
        self,
        binding_id: str,
        *,
        event_type: ShadowBindingEventType,
        identity: VerifiedIdentity,
        reason: str,
        effective_at: str,
        created_at: str,
        hmac_keyring: ShadowHmacKeyring | None = None,
    ) -> None:
        if event_type not in {
            ShadowBindingEventType.REVOKED,
            ShadowBindingEventType.TERMINATED,
        }:
            raise ValueError("only terminal binding events may be appended")
        validate_shadow_reason(reason)
        event_id = _id("mshe")
        payload = {
            "actor_subject": identity.subject,
            "binding_id": binding_id,
            "created_at": created_at,
            "effective_at": effective_at,
            "event_id": event_id,
            "event_schema_version": 1,
            "event_type": event_type.value,
            "reason": reason,
        }
        with self._session_factory() as session, session.begin():
            row = session.get(V2MaterialShadowBinding, binding_id)
            if row is None:
                raise KeyError(binding_id)
            if row.scope_kind == ShadowScopeKind.TENANT_CANARY.value:
                if hmac_keyring is None or row.hmac_key_id is None:
                    raise ValueError("tenant canary requires the server HMAC keyring")
                expected_tenant_ref = hmac_keyring.digest_fields(
                    TENANT_REF_DOMAIN,
                    (identity.tenant_id,),
                    key_id=row.hmac_key_id,
                )
                if row.tenant_ref_hmac != expected_tenant_ref:
                    raise ValueError("terminal actor tenant does not match the binding")
            session.add(
                V2MaterialShadowBindingEvent(
                    event_id=event_id,
                    event_schema_version=1,
                    binding_id=binding_id,
                    event_type=event_type.value,
                    actor_subject=identity.subject,
                    reason=reason,
                    effective_at=effective_at,
                    created_at=created_at,
                    event_sha256=_event_hash(payload),
                )
            )

    def current_candidates(
        self,
        *,
        environment: str,
        tenant_references: tuple[tuple[str, str], ...],
        domain_pack_id: str,
        now: str,
        tenant_tier: bool,
    ) -> tuple[V2MaterialShadowBinding, ...]:
        scope = (
            ShadowScopeKind.TENANT_CANARY.value
            if tenant_tier
            else ShadowScopeKind.GLOBAL.value
        )
        with self._session_factory() as session:
            statement = select(V2MaterialShadowBinding).where(
                V2MaterialShadowBinding.environment == environment,
                V2MaterialShadowBinding.purpose == "MATERIAL_RULESET_SHADOW",
                V2MaterialShadowBinding.scope_kind == scope,
                V2MaterialShadowBinding.domain_pack_id == domain_pack_id,
                V2MaterialShadowBinding.valid_from <= now,
                V2MaterialShadowBinding.valid_until > now,
            )
            if tenant_tier:
                if not tenant_references:
                    return ()
                statement = statement.where(
                    or_(
                        *(
                            (V2MaterialShadowBinding.hmac_key_id == key_id)
                            & (
                                V2MaterialShadowBinding.tenant_ref_hmac
                                == tenant_ref_hmac
                            )
                            for key_id, tenant_ref_hmac in tenant_references
                        )
                    )
                )
            else:
                statement = statement.where(
                    V2MaterialShadowBinding.tenant_ref_hmac.is_(None),
                    V2MaterialShadowBinding.hmac_key_id.is_(None),
                )
            return tuple(session.scalars(statement).all())

    def binding_is_terminal(self, binding_id: str, *, now: str) -> bool:
        with self._session_factory() as session:
            terminal = session.scalar(
                select(func.count())
                .select_from(V2MaterialShadowBindingEvent)
                .where(
                    V2MaterialShadowBindingEvent.binding_id == binding_id,
                    V2MaterialShadowBindingEvent.event_type.in_(
                        (
                            ShadowBindingEventType.REVOKED.value,
                            ShadowBindingEventType.TERMINATED.value,
                        )
                    ),
                    V2MaterialShadowBindingEvent.effective_at <= now,
                )
            )
            return bool(terminal)

    @staticmethod
    def binding_from_row(row: V2MaterialShadowBinding) -> ShadowBinding:
        from sealai_v2.core.material_shadow import (
            ShadowEnvironment,
            ShadowPurpose,
        )

        return ShadowBinding(
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
            valid_from=row.valid_from,
            valid_until=row.valid_until,
            creator_subject=row.creator_subject,
            reason=row.reason,
            sampling_policy_version=row.sampling_policy_version,
            sampling_basis_points=row.sampling_basis_points,
            binding_schema_version=row.binding_schema_version,
        )

    def persist_pin_and_job(
        self,
        *,
        binding: ShadowBinding,
        identity: VerifiedIdentity,
        session_id: str,
        correlation_id: str,
        case_id: str | None = None,
        decision_id: str | None = None,
        material_input: ShadowMaterialInput,
        hmac_keyring: ShadowHmacKeyring,
        acquired_at: str,
        upgrade_reason: str | None = None,
    ) -> AtomicCaptureResult:
        """Atomically create a pin and outbox job under session ordering.

        This low-level transaction is independently testable while production
        sampling remains frozen at zero and therefore never calls it.
        """

        if not isinstance(binding, ShadowBinding):
            raise TypeError("binding must be ShadowBinding")
        if not isinstance(identity, VerifiedIdentity):
            raise TypeError("identity must be VerifiedIdentity")
        if not isinstance(material_input, ShadowMaterialInput):
            raise TypeError("material_input must be ShadowMaterialInput")
        if not isinstance(hmac_keyring, ShadowHmacKeyring):
            raise TypeError("hmac_keyring must be ShadowHmacKeyring")
        if case_id is not None and (type(case_id) is not str or not case_id):
            raise ValueError("case_id must be absent or non-empty")
        if decision_id is not None and (
            type(decision_id) is not str or not decision_id
        ):
            raise ValueError("decision_id must be absent or non-empty")
        if upgrade_reason is not None:
            validate_shadow_reason(upgrade_reason)
        if binding.scope_kind is ShadowScopeKind.TENANT_CANARY:
            if binding.hmac_key_id is None:
                raise ValueError("tenant canary lacks hmac_key_id")
            expected_tenant_ref = hmac_keyring.digest_fields(
                TENANT_REF_DOMAIN,
                (identity.tenant_id,),
                key_id=binding.hmac_key_id,
            )
            if binding.tenant_ref_hmac != expected_tenant_ref:
                raise ValueError("tenant canary must equal the verified tenant")
        if (
            material_input.domain_pack_id != binding.domain_pack_id
            or material_input.domain_pack_version != binding.domain_pack_version
        ):
            raise ValueError("shadow input and binding domain pack differ")
        acquired = parse_utc(acquired_at, field="acquired_at")
        if not (
            parse_utc(binding.valid_from, field="binding.valid_from")
            <= acquired
            < parse_utc(binding.valid_until, field="binding.valid_until")
        ):
            raise ValueError("shadow pin must be acquired inside the binding interval")
        tenant_references = dict(
            hmac_keyring.references_fields(TENANT_REF_DOMAIN, (identity.tenant_id,))
        )
        session_references = dict(
            hmac_keyring.references_fields(
                SESSION_REF_DOMAIN,
                (identity.tenant_id, session_id),
            )
        )
        identity_references = tuple(
            (key_id, tenant_references[key_id], session_references[key_id])
            for key_id in sorted(tenant_references)
        )
        tenant_ref = tenant_references[hmac_keyring.active_key_id]
        session_ref = session_references[hmac_keyring.active_key_id]
        correlation_ref = hmac_keyring.digest_fields(
            REQUEST_REF_DOMAIN,
            (identity.tenant_id, session_id, correlation_id),
        )
        case_ref = (
            hmac_keyring.digest_fields(
                CASE_REF_DOMAIN,
                (identity.tenant_id, case_id),
            )
            if case_id is not None
            else None
        )
        decision_ref = (
            hmac_keyring.digest_fields(
                DECISION_REF_DOMAIN,
                (identity.tenant_id, decision_id),
            )
            if decision_id is not None
            else None
        )
        input_fingerprint = _input_fingerprint(material_input)
        idempotency = hashlib.sha256(
            _IDEMPOTENCY_DOMAIN
            + tenant_ref.encode("ascii")
            + b"\x00"
            + correlation_ref.encode("ascii")
            + b"\x00"
            + (case_ref or "<NO_CASE>").encode("ascii")
            + b"\x00"
            + (decision_ref or "<NO_DECISION>").encode("ascii")
            + b"\x00"
            + binding.binding_id.encode("ascii")
            + b"\x00"
            + input_fingerprint.encode("ascii")
            + b"\x00"
            + binding.sampling_policy_version.encode("ascii")
        ).hexdigest()
        with self._session_factory() as session, session.begin():
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                # The raw verified values are transaction-local lock material,
                # never persisted.  This keeps rotation between active HMAC
                # keys from creating a second silent session lineage.
                lock_material = hashlib.sha256(
                    encode_hmac_fields(
                        SESSION_REF_DOMAIN,
                        (identity.tenant_id, session_id),
                    )
                ).hexdigest()
                session.execute(
                    text(
                        "SELECT pg_advisory_xact_lock(hashtextextended(:value,73004))"
                    ),
                    {"value": lock_material},
                )
            stored_binding = session.get(
                V2MaterialShadowBinding, binding.binding_id, with_for_update=True
            )
            if (
                stored_binding is None
                or self.binding_from_row(stored_binding) != binding
            ):
                raise ValueError("shadow binding is absent or drifted")
            terminal = session.scalar(
                select(V2MaterialShadowBindingEvent.event_id).where(
                    V2MaterialShadowBindingEvent.binding_id == binding.binding_id,
                    V2MaterialShadowBindingEvent.event_type.in_(
                        (
                            ShadowBindingEventType.REVOKED.value,
                            ShadowBindingEventType.TERMINATED.value,
                        )
                    ),
                    V2MaterialShadowBindingEvent.effective_at <= acquired_at,
                )
            )
            if terminal is not None:
                raise ValueError("shadow binding is terminal")
            existing_job = session.scalar(
                select(V2MaterialShadowOutbox).where(
                    V2MaterialShadowOutbox.idempotency_key == idempotency
                )
            )
            if existing_job is not None:
                pin_row = session.get(V2MaterialShadowPin, existing_job.pin_id)
                if pin_row is None:
                    raise RuntimeError(
                        "shadow idempotency row references a missing pin"
                    )
                return AtomicCaptureResult(
                    pin=self._pin_from_row(pin_row),
                    job_id=existing_job.job_id,
                    session_version_id=existing_job.session_version_id,
                    sequence_no=existing_job.sequence_no,
                    created=False,
                )
            versions = list(
                session.scalars(
                    select(V2MaterialShadowSessionVersion)
                    .where(
                        or_(
                            *(
                                (V2MaterialShadowSessionVersion.hmac_key_id == key_id)
                                & (
                                    V2MaterialShadowSessionVersion.tenant_ref_hmac
                                    == tenant_reference
                                )
                                & (
                                    V2MaterialShadowSessionVersion.session_ref_hmac
                                    == session_reference
                                )
                                for (
                                    key_id,
                                    tenant_reference,
                                    session_reference,
                                ) in identity_references
                            )
                        )
                    )
                    .order_by(V2MaterialShadowSessionVersion.version_no)
                    .with_for_update()
                ).all()
            )
            pin_id = _id("mshp")
            pin = ShadowMaterialRulesetPin(
                pin_id=pin_id,
                binding_id=binding.binding_id,
                snapshot_id=binding.snapshot_id,
                content_sha256=binding.content_sha256,
                environment=binding.environment,
                purpose=binding.purpose,
                scope_kind=binding.scope_kind,
                tenant_ref_hmac=tenant_ref,
                hmac_key_id=hmac_keyring.active_key_id,
                domain_pack_id=binding.domain_pack_id,
                domain_pack_version=binding.domain_pack_version,
                evaluator_version=binding.evaluator_version,
                kernel_version=binding.kernel_version,
                runtime_profile_sha256=binding.runtime_profile_sha256,
                build_git_sha=binding.build_git_sha,
                build_tree_hash=binding.build_tree_hash,
                sampling_policy_version=binding.sampling_policy_version,
                sampled=False,
                acquired_at=acquired_at,
                binding_valid_until=binding.valid_until,
            )
            session.add(
                V2MaterialShadowPin(
                    pin_id=pin.pin_id,
                    pin_schema_version=SHADOW_PIN_SCHEMA_VERSION,
                    binding_id=pin.binding_id,
                    snapshot_id=pin.snapshot_id,
                    content_sha256=pin.content_sha256,
                    environment=pin.environment.value,
                    purpose=pin.purpose.value,
                    scope_kind=pin.scope_kind.value,
                    tenant_ref_hmac=pin.tenant_ref_hmac,
                    hmac_key_id=pin.hmac_key_id,
                    domain_pack_id=pin.domain_pack_id,
                    domain_pack_version=pin.domain_pack_version,
                    evaluator_version=pin.evaluator_version,
                    kernel_version=pin.kernel_version,
                    runtime_profile_sha256=pin.runtime_profile_sha256,
                    build_git_sha=pin.build_git_sha,
                    build_tree_hash=pin.build_tree_hash,
                    sampling_policy_version=pin.sampling_policy_version,
                    sampled=pin.sampled,
                    authority=pin.authority.value,
                    positive_statement_allowed=pin.positive_statement_allowed,
                    acquired_at=pin.acquired_at,
                    binding_valid_until=pin.binding_valid_until,
                )
            )
            if not versions:
                session_version_id = _id("mshs")
                session.add(
                    V2MaterialShadowSessionVersion(
                        session_version_id=session_version_id,
                        tenant_ref_hmac=tenant_ref,
                        session_ref_hmac=session_ref,
                        hmac_key_id=hmac_keyring.active_key_id,
                        version_no=1,
                        pin_id=pin_id,
                        created_at=acquired_at,
                    )
                )
            else:
                session_version_id = self._unique_session_head(session, versions)
                head = session.get(V2MaterialShadowSessionVersion, session_version_id)
                if head is None:
                    raise RuntimeError("shadow session head disappeared")
                frozen_pin = session.get(V2MaterialShadowPin, head.pin_id)
                if frozen_pin is None:
                    raise RuntimeError("shadow session head references a missing pin")
                binding_changed = (
                    frozen_pin.binding_id != binding.binding_id
                    or frozen_pin.snapshot_id != binding.snapshot_id
                    or frozen_pin.content_sha256 != binding.content_sha256
                )
                if binding_changed:
                    if upgrade_reason is None:
                        raise ValueError(
                            "shadow session is frozen to a different binding"
                        )
                    old_session_version_id = session_version_id
                    session_version_id = _id("mshs")
                    new_version_no = max(row.version_no for row in versions) + 1
                    session.add(
                        V2MaterialShadowSessionVersion(
                            session_version_id=session_version_id,
                            tenant_ref_hmac=tenant_ref,
                            session_ref_hmac=session_ref,
                            hmac_key_id=hmac_keyring.active_key_id,
                            version_no=new_version_no,
                            pin_id=pin_id,
                            created_at=acquired_at,
                        )
                    )
                    session.add(
                        V2MaterialShadowSessionUpgradeEvent(
                            event_id=_id("mshu"),
                            from_session_version_id=old_session_version_id,
                            to_session_version_id=session_version_id,
                            actor_subject=identity.subject,
                            reason=upgrade_reason,
                            created_at=acquired_at,
                        )
                    )
                elif upgrade_reason is not None:
                    raise ValueError("session upgrade requires a different binding")
            prior = session.scalar(
                select(func.max(V2MaterialShadowOutbox.sequence_no)).where(
                    V2MaterialShadowOutbox.session_version_id == session_version_id
                )
            )
            sequence_no = int(prior or 0) + 1
            job_id = _id("mshj")
            session.add(
                V2MaterialShadowOutbox(
                    job_id=job_id,
                    pin_id=pin_id,
                    session_version_id=session_version_id,
                    sequence_no=sequence_no,
                    hmac_key_id=hmac_keyring.active_key_id,
                    correlation_hmac=correlation_ref,
                    case_ref_hmac=case_ref,
                    decision_ref_hmac=decision_ref,
                    material_id=material_input.material_id.canonical_id,
                    medium_id=material_input.medium_id.canonical_id,
                    material_state=material_input.material_state.value,
                    medium_state=material_input.medium_state.value,
                    medium_cardinality=material_input.medium_cardinality.value,
                    relation_state=material_input.relation_state.value,
                    domain_pack_id=material_input.domain_pack_id,
                    domain_pack_version=material_input.domain_pack_version,
                    input_fingerprint=input_fingerprint,
                    idempotency_key=idempotency,
                    status=ShadowJobStatus.PENDING.value,
                    attempts=0,
                    stable_error_code=ShadowErrorCode.NONE.value,
                    created_at=acquired_at,
                    claimed_at=None,
                    next_attempt_at=None,
                    completed_at=None,
                )
            )
            session.flush()
            return AtomicCaptureResult(
                pin, job_id, session_version_id, sequence_no, True
            )

    @staticmethod
    def _unique_session_head(
        session, versions: list[V2MaterialShadowSessionVersion]
    ) -> str:
        ids = {row.session_version_id for row in versions}
        outgoing = set(
            session.scalars(
                select(
                    V2MaterialShadowSessionUpgradeEvent.from_session_version_id
                ).where(
                    V2MaterialShadowSessionUpgradeEvent.from_session_version_id.in_(ids)
                )
            ).all()
        )
        heads = ids - outgoing
        if len(heads) != 1:
            raise ValueError("shadow session version graph has no unique head")
        return next(iter(heads))

    @staticmethod
    def _pin_from_row(row: V2MaterialShadowPin) -> ShadowMaterialRulesetPin:
        return ShadowMaterialRulesetPin.from_storage(
            {
                "pin_id": row.pin_id,
                "binding_id": row.binding_id,
                "snapshot_id": row.snapshot_id,
                "content_sha256": row.content_sha256,
                "environment": row.environment,
                "purpose": row.purpose,
                "scope_kind": row.scope_kind,
                "tenant_ref_hmac": row.tenant_ref_hmac,
                "hmac_key_id": row.hmac_key_id,
                "domain_pack_id": row.domain_pack_id,
                "domain_pack_version": row.domain_pack_version,
                "evaluator_version": row.evaluator_version,
                "kernel_version": row.kernel_version,
                "runtime_profile_sha256": row.runtime_profile_sha256,
                "build_git_sha": row.build_git_sha,
                "build_tree_hash": row.build_tree_hash,
                "sampling_policy_version": row.sampling_policy_version,
                "sampled": row.sampled,
                "acquired_at": row.acquired_at,
                "binding_valid_until": row.binding_valid_until,
                "pin_schema_version": row.pin_schema_version,
            }
        )
