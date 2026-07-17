"""MAT-GOV-03B pointerless, non-authoritative shadow contracts.

The contracts in this module are pure and deliberately incapable of producing
an authoritative material pin or a positive material statement.  They carry
only server-verified structured identifiers; MED-NORM-01 remains outside this
package.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import re
from typing import NoReturn

from sealai_v2.core.contracts import (
    InputResolutionState,
    MaterialConstraintQuery,
    MediumCardinality,
    RelationState,
)
from sealai_v2.core.material_rulesets import validate_domain_pack_id


SHADOW_BINDING_SCHEMA_VERSION = 1
SHADOW_PIN_SCHEMA_VERSION = 1
SHADOW_POLICY_VERSION = "MAT-GOV-03B.shadow.v1"

_HEX40 = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
_HEX64 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_BINDING_ID = re.compile(r"^mshb_[0-9a-f]{32}$", re.ASCII)
_PIN_ID = re.compile(r"^mshp_[0-9a-f]{32}$", re.ASCII)
_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", re.ASCII)
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}$", re.ASCII)


class ShadowEnvironment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class ShadowPurpose(str, Enum):
    MATERIAL_RULESET_SHADOW = "MATERIAL_RULESET_SHADOW"


class ShadowScopeKind(str, Enum):
    GLOBAL = "GLOBAL"
    TENANT_CANARY = "TENANT_CANARY"


class ShadowAuthority(str, Enum):
    NON_AUTHORITATIVE = "SHADOW_NON_AUTHORITATIVE"


class ShadowBindingEventType(str, Enum):
    CREATED = "CREATED"
    REVOKED = "REVOKED"
    TERMINATED = "TERMINATED"


class ShadowReadinessState(str, Enum):
    DISABLED = "disabled"
    UNSAMPLED = "unsampled"
    NO_BINDING = "no_binding"
    INELIGIBLE_UNRESOLVED_INPUT = "ineligible_unresolved_input"
    DB_UNAVAILABLE = "db_unavailable"
    CACHE_UNAVAILABLE = "cache_unavailable"
    AMBIGUOUS_BINDING = "ambiguous_binding"
    EXPIRED_LEASE = "expired_lease"
    SNAPSHOT_DRIFT = "snapshot_drift"
    EVALUATOR_INCOMPATIBLE = "evaluator_incompatible"
    READY = "ready"


class ShadowEvaluationState(str, Enum):
    EVALUATED = "evaluated"
    BLOCKED = "blocked"
    NO_RULE_DATA = "no_rule_data"
    INELIGIBLE_UNRESOLVED_INPUT = "ineligible_unresolved_input"
    REVOKED = "revoked"
    INTEGRITY_BLOCKED = "integrity_blocked"
    CACHE_UNAVAILABLE = "cache_unavailable"
    RETRY_EXHAUSTED = "retry_exhausted"


class ShadowJobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ShadowErrorCode(str, Enum):
    NONE = "none"
    DB_UNAVAILABLE = "SHADOW_DB_UNAVAILABLE"
    CACHE_UNAVAILABLE = "SHADOW_CACHE_UNAVAILABLE"
    BINDING_AMBIGUOUS = "SHADOW_BINDING_AMBIGUOUS"
    BINDING_INACTIVE = "SHADOW_BINDING_INACTIVE"
    SNAPSHOT_DRIFT = "SHADOW_SNAPSHOT_DRIFT"
    EVALUATOR_INCOMPATIBLE = "SHADOW_EVALUATOR_INCOMPATIBLE"
    INPUT_INELIGIBLE = "SHADOW_INPUT_INELIGIBLE"
    HMAC_KEY_UNAVAILABLE = "SHADOW_HMAC_KEY_UNAVAILABLE"
    LEASE_ATTEMPTS_EXHAUSTED = "SHADOW_LEASE_ATTEMPTS_EXHAUSTED"
    RETRY_EXHAUSTED = "SHADOW_RETRY_EXHAUSTED"
    INTERNAL = "SHADOW_INTERNAL_ERROR"


class ShadowContractError(ValueError):
    def __init__(self, code: ShadowErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: ShadowErrorCode, message: str) -> NoReturn:
    raise ShadowContractError(code, message)


def _require_stable(value: str, *, field: str) -> str:
    if type(value) is not str or not _STABLE_ID.fullmatch(value):
        raise ValueError(f"{field} must be a canonical structured identifier")
    return value


def _require_version(value: str, *, field: str) -> str:
    if type(value) is not str or not _VERSION.fullmatch(value):
        raise ValueError(f"{field} must be a stable version identifier")
    return value


def validate_shadow_reason(value: str) -> str:
    """Accept only a stable technical reason code, never operator free text."""

    return _require_stable(value, field="reason")


def parse_utc(value: str, *, field: str) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError(f"{field} must be canonical UTC ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{field} must be canonical UTC") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError(f"{field} must be UTC")
    canonical = (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
    if value != canonical:
        raise ValueError(f"{field} must use canonical microsecond UTC form")
    return parsed


@dataclass(frozen=True, slots=True)
class ServerVerifiedCanonicalId:
    """A structured ID produced by a trusted server-side registry seam.

    This value validates identity syntax only; the trusted adapter is
    responsible for constructing it after registry verification.  Request and
    LLM data never cross that adapter directly.
    """

    canonical_id: str
    registry_ref: str

    def __post_init__(self) -> None:
        _require_stable(self.canonical_id, field="canonical_id")
        _require_stable(self.registry_ref, field="registry_ref")


@dataclass(frozen=True, slots=True)
class ShadowMaterialInput:
    material_id: ServerVerifiedCanonicalId
    medium_id: ServerVerifiedCanonicalId
    material_state: InputResolutionState
    medium_state: InputResolutionState
    medium_cardinality: MediumCardinality
    relation_state: RelationState
    domain_pack_id: str
    domain_pack_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.material_id, ServerVerifiedCanonicalId):
            raise TypeError("material_id must be server verified")
        if not isinstance(self.medium_id, ServerVerifiedCanonicalId):
            raise TypeError("medium_id must be server verified")
        validate_domain_pack_id(self.domain_pack_id)
        _require_version(self.domain_pack_version, field="domain_pack_version")
        query = MaterialConstraintQuery(
            material=self.material_id.canonical_id,
            medium=self.medium_id.canonical_id,
            material_state=self.material_state,
            medium_state=self.medium_state,
            medium_cardinality=self.medium_cardinality,
            relation_state=self.relation_state,
        )
        if (
            not query.evaluable
            or self.material_state is not InputResolutionState.KNOWN
            or self.medium_state is not InputResolutionState.KNOWN
            or self.medium_cardinality is not MediumCardinality.SINGLE
            or self.relation_state is not RelationState.NOT_APPLICABLE
        ):
            _fail(
                ShadowErrorCode.INPUT_INELIGIBLE,
                "shadow input requires known single-medium evaluable states",
            )


@dataclass(frozen=True, slots=True)
class ShadowInputEligibility:
    state: ShadowReadinessState
    eligible_input: ShadowMaterialInput | None = None

    def __post_init__(self) -> None:
        if self.state is ShadowReadinessState.READY:
            if self.eligible_input is None:
                raise ValueError("ready eligibility requires a structured input")
        elif self.eligible_input is not None:
            raise ValueError("ineligible state cannot carry a structured input")


def assess_shadow_input_eligibility(
    query: MaterialConstraintQuery,
    *,
    material_id: ServerVerifiedCanonicalId | None,
    medium_id: ServerVerifiedCanonicalId | None,
    domain_pack_id: str | None,
    domain_pack_version: str | None,
) -> ShadowInputEligibility:
    """Return eligibility without guessing, splitting, or normalizing text."""

    if not isinstance(query, MaterialConstraintQuery):
        raise TypeError("query must be MaterialConstraintQuery")
    if not query.evaluable or material_id is None or medium_id is None:
        return ShadowInputEligibility(ShadowReadinessState.INELIGIBLE_UNRESOLVED_INPUT)
    if not domain_pack_id or not domain_pack_version:
        return ShadowInputEligibility(ShadowReadinessState.INELIGIBLE_UNRESOLVED_INPUT)
    try:
        candidate = ShadowMaterialInput(
            material_id=material_id,
            medium_id=medium_id,
            material_state=query.material_state,
            medium_state=query.medium_state,
            medium_cardinality=query.medium_cardinality,
            relation_state=query.relation_state,
            domain_pack_id=domain_pack_id,
            domain_pack_version=domain_pack_version,
        )
    except (TypeError, ValueError):
        return ShadowInputEligibility(ShadowReadinessState.INELIGIBLE_UNRESOLVED_INPUT)
    return ShadowInputEligibility(ShadowReadinessState.READY, candidate)


@dataclass(frozen=True, slots=True)
class ShadowBinding:
    binding_id: str
    snapshot_id: str
    content_sha256: str
    environment: ShadowEnvironment
    purpose: ShadowPurpose
    scope_kind: ShadowScopeKind
    tenant_ref_hmac: str | None
    hmac_key_id: str | None
    domain_pack_id: str
    domain_pack_version: str
    evaluator_version: str
    kernel_version: str
    runtime_profile_sha256: str
    build_git_sha: str
    build_tree_hash: str
    valid_from: str
    valid_until: str
    creator_subject: str
    reason: str
    sampling_policy_version: str
    sampling_basis_points: int = 0
    binding_schema_version: int = SHADOW_BINDING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not _BINDING_ID.fullmatch(self.binding_id):
            raise ValueError("invalid shadow binding_id")
        if not self.snapshot_id.startswith("mss_") or len(self.snapshot_id) != 68:
            raise ValueError("invalid snapshot_id")
        for value, field in (
            (self.content_sha256, "content_sha256"),
            (self.runtime_profile_sha256, "runtime_profile_sha256"),
        ):
            if not _HEX64.fullmatch(value):
                raise ValueError(f"{field} must be lowercase SHA-256")
        for value, field in (
            (self.build_git_sha, "build_git_sha"),
            (self.build_tree_hash, "build_tree_hash"),
        ):
            if not _HEX40.fullmatch(value):
                raise ValueError(f"{field} must be a full lowercase Git hash")
        if not isinstance(self.environment, ShadowEnvironment):
            raise TypeError("environment must be ShadowEnvironment")
        if self.purpose is not ShadowPurpose.MATERIAL_RULESET_SHADOW:
            raise ValueError("shadow purpose is fixed")
        if not isinstance(self.scope_kind, ShadowScopeKind):
            raise TypeError("scope_kind must be ShadowScopeKind")
        if self.scope_kind is ShadowScopeKind.GLOBAL and (
            self.tenant_ref_hmac is not None or self.hmac_key_id is not None
        ):
            raise ValueError("GLOBAL binding cannot carry a tenant reference")
        if self.scope_kind is ShadowScopeKind.TENANT_CANARY:
            if not _HEX64.fullmatch(self.tenant_ref_hmac or ""):
                raise ValueError("tenant canary requires a lowercase tenant HMAC")
            _require_stable(self.hmac_key_id or "", field="hmac_key_id")
        validate_domain_pack_id(self.domain_pack_id)
        for value, field in (
            (self.domain_pack_version, "domain_pack_version"),
            (self.evaluator_version, "evaluator_version"),
            (self.kernel_version, "kernel_version"),
            (self.sampling_policy_version, "sampling_policy_version"),
        ):
            _require_version(value, field=field)
        _require_stable(self.creator_subject, field="creator_subject")
        validate_shadow_reason(self.reason)
        start = parse_utc(self.valid_from, field="valid_from")
        end = parse_utc(self.valid_until, field="valid_until")
        if end <= start:
            raise ValueError("valid_until must be after valid_from")
        max_seconds = (
            4 * 3600 if self.environment is ShadowEnvironment.PRODUCTION else 24 * 3600
        )
        if (end - start).total_seconds() > max_seconds:
            raise ValueError("binding exceeds the environment lifetime limit")
        if type(self.sampling_basis_points) is not int or not (
            0 <= self.sampling_basis_points <= 10_000
        ):
            raise ValueError("sampling_basis_points must be an integer 0..10000")
        if self.sampling_basis_points != 0:
            raise ValueError("MAT-GOV-03B sampling is owner-frozen at zero percent")
        if self.binding_schema_version != SHADOW_BINDING_SCHEMA_VERSION:
            raise ValueError("unsupported shadow binding schema")


@dataclass(frozen=True, slots=True)
class ShadowMaterialRulesetPin:
    pin_id: str
    binding_id: str
    snapshot_id: str
    content_sha256: str
    environment: ShadowEnvironment
    purpose: ShadowPurpose
    scope_kind: ShadowScopeKind
    tenant_ref_hmac: str
    hmac_key_id: str
    domain_pack_id: str
    domain_pack_version: str
    evaluator_version: str
    kernel_version: str
    runtime_profile_sha256: str
    build_git_sha: str
    build_tree_hash: str
    sampling_policy_version: str
    sampled: bool
    acquired_at: str
    binding_valid_until: str
    pin_schema_version: int = SHADOW_PIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not _PIN_ID.fullmatch(self.pin_id):
            raise ValueError("invalid shadow pin_id")
        if not _BINDING_ID.fullmatch(self.binding_id):
            raise ValueError("invalid binding_id")
        if not self.snapshot_id.startswith("mss_") or len(self.snapshot_id) != 68:
            raise ValueError("invalid snapshot_id")
        for value, field in (
            (self.content_sha256, "content_sha256"),
            (self.runtime_profile_sha256, "runtime_profile_sha256"),
        ):
            if not _HEX64.fullmatch(value):
                raise ValueError(f"{field} must be lowercase SHA-256")
        if not _HEX64.fullmatch(self.tenant_ref_hmac):
            raise ValueError("tenant_ref_hmac must be a lowercase HMAC-SHA-256")
        _require_stable(self.hmac_key_id, field="hmac_key_id")
        validate_domain_pack_id(self.domain_pack_id)
        for value, field in (
            (self.domain_pack_version, "domain_pack_version"),
            (self.evaluator_version, "evaluator_version"),
            (self.kernel_version, "kernel_version"),
            (self.sampling_policy_version, "sampling_policy_version"),
        ):
            _require_version(value, field=field)
        parse_utc(self.acquired_at, field="acquired_at")
        parse_utc(self.binding_valid_until, field="binding_valid_until")
        if self.pin_schema_version != SHADOW_PIN_SCHEMA_VERSION:
            raise ValueError("unsupported shadow pin schema")
        if self.sampled is not False:
            raise ValueError("MAT-GOV-03B sampling is owner-frozen at zero percent")

    @property
    def authority(self) -> ShadowAuthority:
        return ShadowAuthority.NON_AUTHORITATIVE

    @property
    def positive_statement_allowed(self) -> bool:
        return False


__all__ = [
    "SHADOW_BINDING_SCHEMA_VERSION",
    "SHADOW_PIN_SCHEMA_VERSION",
    "SHADOW_POLICY_VERSION",
    "ServerVerifiedCanonicalId",
    "ShadowAuthority",
    "ShadowBinding",
    "ShadowBindingEventType",
    "ShadowContractError",
    "ShadowEnvironment",
    "ShadowErrorCode",
    "ShadowEvaluationState",
    "ShadowInputEligibility",
    "ShadowJobStatus",
    "ShadowMaterialInput",
    "ShadowMaterialRulesetPin",
    "ShadowPurpose",
    "ShadowReadinessState",
    "ShadowScopeKind",
    "assess_shadow_input_eligibility",
    "parse_utc",
    "validate_shadow_reason",
]
