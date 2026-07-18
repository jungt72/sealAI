"""MAT-EVID-01B immutable runtime evidence-binding companion.

The canonical material result and MAT-GOV-03A payload remain unbound.  This
separate contract can only prove structural binding to one exact immutable
ruleset and evidence-manifest snapshot.  It never grants factual authority or
permission for a positive material statement.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from sealai_v2.core.material_evidence import (
    CANONICALIZATION_VERSION as EVIDENCE_CANONICALIZATION_VERSION,
    EVIDENCE_MANIFEST_SCHEMA_VERSION,
    MAT_EVID_CONTRACT_VERSION,
    EvidenceManifestSnapshotV1,
)
from sealai_v2.core.material_rulesets import MaterialRulesetSnapshotV1


MAT_EVID_RUNTIME_CONTRACT_VERSION = "MAT-EVID-01B.v1"
MAT_EVID_RUNTIME_BINDING_SCHEMA_VERSION = 1
MAT_EVID_RUNTIME_PIN_SCHEMA_VERSION = 1

_BINDING_ID = re.compile(r"^mshb_[0-9a-f]{32}$", re.ASCII)
_PIN_ID = re.compile(r"^mshp_[0-9a-f]{32}$", re.ASCII)
_RULESET_SNAPSHOT_ID = re.compile(r"^mss_[0-9a-f]{64}$", re.ASCII)
_EVIDENCE_SNAPSHOT_ID = re.compile(r"^mes_[0-9a-f]{64}$", re.ASCII)
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}$", re.ASCII)


class EvidenceRuntimeBindingState(str, Enum):
    UNBOUND = "unbound"
    BOUND_UNREVIEWED = "bound_unreviewed"


class EvidenceRuntimeAuthority(str, Enum):
    NONE = "NONE"
    TECHNICAL_UNREVIEWED = "TECHNICAL_UNREVIEWED"


class MaterialEvidenceRuntimeErrorCode(str, Enum):
    UNBOUND = "MAT_EVID_RUNTIME_UNBOUND"
    BINDING_DRIFT = "MAT_EVID_RUNTIME_BINDING_DRIFT"
    RULESET_DRIFT = "MAT_EVID_RUNTIME_RULESET_DRIFT"
    EVIDENCE_DRIFT = "MAT_EVID_RUNTIME_EVIDENCE_DRIFT"
    VERSION_MISMATCH = "MAT_EVID_RUNTIME_VERSION_MISMATCH"
    DOMAIN_PACK_MISMATCH = "MAT_EVID_RUNTIME_DOMAIN_PACK_MISMATCH"
    INCOMPLETE = "MAT_EVID_RUNTIME_INCOMPLETE"
    FOREIGN_RULE = "MAT_EVID_RUNTIME_FOREIGN_RULE"
    CLAIM_REUSED = "MAT_EVID_RUNTIME_CLAIM_REUSED"
    SCOPE_MISMATCH = "MAT_EVID_RUNTIME_SCOPE_MISMATCH"
    RULE_SCOPE_INCONSISTENT = "MAT_EVID_RUNTIME_RULE_SCOPE_INCONSISTENT"
    INTERNAL = "MAT_EVID_RUNTIME_INTERNAL"


class MaterialEvidenceRuntimeIntegrityError(RuntimeError):
    """Stable fail-closed error; callers must not derive a verdict from it."""

    def __init__(self, code: MaterialEvidenceRuntimeErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _require_version(value: str, *, field: str) -> None:
    if type(value) is not str or not _VERSION.fullmatch(value):
        raise ValueError(f"{field} must be a stable version identifier")


def _require_hash(value: str, *, field: str) -> None:
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class EvidenceRuntimeBindingV1:
    """One immutable companion for one exact 03B shadow binding."""

    binding_id: str
    state: EvidenceRuntimeBindingState
    ruleset_snapshot_id: str
    ruleset_content_sha256: str
    evidence_snapshot_id: str | None
    evidence_content_sha256: str | None
    evidence_manifest_schema_version: int | None
    evidence_canonicalization_version: int | None
    evidence_contract_version: str | None
    domain_pack_id: str
    domain_pack_version: str
    evaluator_version: str
    kernel_version: str
    binding_schema_version: int = MAT_EVID_RUNTIME_BINDING_SCHEMA_VERSION
    binding_contract_version: str = MAT_EVID_RUNTIME_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if type(self.binding_id) is not str or not _BINDING_ID.fullmatch(
            self.binding_id
        ):
            raise ValueError("invalid shadow binding_id")
        if type(self.state) is not EvidenceRuntimeBindingState:
            raise TypeError("state must be EvidenceRuntimeBindingState")
        if type(
            self.ruleset_snapshot_id
        ) is not str or not _RULESET_SNAPSHOT_ID.fullmatch(self.ruleset_snapshot_id):
            raise ValueError("invalid ruleset_snapshot_id")
        _require_hash(self.ruleset_content_sha256, field="ruleset_content_sha256")
        for value, field in (
            (self.domain_pack_id, "domain_pack_id"),
            (self.domain_pack_version, "domain_pack_version"),
            (self.evaluator_version, "evaluator_version"),
            (self.kernel_version, "kernel_version"),
        ):
            _require_version(value, field=field)
        if self.binding_schema_version != MAT_EVID_RUNTIME_BINDING_SCHEMA_VERSION:
            raise ValueError("unsupported runtime binding schema")
        if self.binding_contract_version != MAT_EVID_RUNTIME_CONTRACT_VERSION:
            raise ValueError("unsupported runtime binding contract")
        evidence_fields = (
            self.evidence_snapshot_id,
            self.evidence_content_sha256,
            self.evidence_manifest_schema_version,
            self.evidence_canonicalization_version,
            self.evidence_contract_version,
        )
        if self.state is EvidenceRuntimeBindingState.UNBOUND:
            if any(value is not None for value in evidence_fields):
                raise ValueError("unbound companion cannot carry evidence identity")
            return
        if any(value is None for value in evidence_fields):
            raise ValueError("bound_unreviewed requires complete evidence identity")
        if type(
            self.evidence_snapshot_id
        ) is not str or not _EVIDENCE_SNAPSHOT_ID.fullmatch(self.evidence_snapshot_id):
            raise ValueError("invalid evidence_snapshot_id")
        _require_hash(
            self.evidence_content_sha256 or "", field="evidence_content_sha256"
        )
        if self.evidence_manifest_schema_version != EVIDENCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported evidence manifest schema")
        if self.evidence_canonicalization_version != EVIDENCE_CANONICALIZATION_VERSION:
            raise ValueError("unsupported evidence canonicalization version")
        if self.evidence_contract_version != MAT_EVID_CONTRACT_VERSION:
            raise ValueError("unsupported evidence contract version")

    @property
    def authority(self) -> EvidenceRuntimeAuthority:
        if self.state is EvidenceRuntimeBindingState.UNBOUND:
            return EvidenceRuntimeAuthority.NONE
        return EvidenceRuntimeAuthority.TECHNICAL_UNREVIEWED

    @property
    def positive_statement_allowed(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class EvidenceRuntimePinV1:
    """Request/session pin to the exact ruleset and evidence identities."""

    pin_id: str
    binding: EvidenceRuntimeBindingV1
    pin_schema_version: int = MAT_EVID_RUNTIME_PIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if type(self.pin_id) is not str or not _PIN_ID.fullmatch(self.pin_id):
            raise ValueError("invalid shadow pin_id")
        if type(self.binding) is not EvidenceRuntimeBindingV1:
            raise TypeError("binding must be EvidenceRuntimeBindingV1")
        if self.pin_schema_version != MAT_EVID_RUNTIME_PIN_SCHEMA_VERSION:
            raise ValueError("unsupported runtime pin schema")

    @property
    def state(self) -> EvidenceRuntimeBindingState:
        return self.binding.state

    @property
    def authority(self) -> EvidenceRuntimeAuthority:
        return self.binding.authority

    @property
    def positive_statement_allowed(self) -> bool:
        return False


@dataclass(frozen=True, slots=True, order=True)
class BoundEvidenceReferenceV1:
    rule_ref: str
    claim_ref: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.rule_ref) is not str or not self.rule_ref:
            raise ValueError("rule_ref must be non-empty")
        if type(self.claim_ref) is not str or not self.claim_ref:
            raise ValueError("claim_ref must be non-empty")
        if (
            type(self.source_refs) is not tuple
            or not self.source_refs
            or any(type(value) is not str or not value for value in self.source_refs)
        ):
            raise ValueError("source_refs must be a non-empty tuple")
        if self.source_refs != tuple(sorted(set(self.source_refs))):
            raise ValueError("source_refs must be unique and ordered")


@dataclass(frozen=True, slots=True)
class ResolvedEvidenceBindingV1:
    state: EvidenceRuntimeBindingState
    references: tuple[BoundEvidenceReferenceV1, ...]

    def __post_init__(self) -> None:
        if self.state is not EvidenceRuntimeBindingState.BOUND_UNREVIEWED:
            raise ValueError("only bound_unreviewed can be resolved")
        if type(self.references) is not tuple or not self.references:
            raise ValueError("resolved evidence requires references")
        if self.references != tuple(sorted(set(self.references))):
            raise ValueError("evidence references must be unique and ordered")

    def for_rules(
        self, rule_refs: tuple[str, ...]
    ) -> tuple[BoundEvidenceReferenceV1, ...]:
        wanted = set(rule_refs)
        return tuple(ref for ref in self.references if ref.rule_ref in wanted)


def validate_runtime_binding(
    binding: EvidenceRuntimeBindingV1,
    *,
    ruleset: MaterialRulesetSnapshotV1,
    evidence: EvidenceManifestSnapshotV1 | None,
) -> ResolvedEvidenceBindingV1:
    """Resolve an exact technical binding without interpreting claim prose."""

    if type(binding) is not EvidenceRuntimeBindingV1:
        raise TypeError("binding must be EvidenceRuntimeBindingV1")
    if type(ruleset) is not MaterialRulesetSnapshotV1:
        raise TypeError("ruleset must be MaterialRulesetSnapshotV1")
    if (
        binding.ruleset_snapshot_id != ruleset.snapshot_id
        or binding.ruleset_content_sha256 != ruleset.content_sha256
    ):
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.RULESET_DRIFT,
            "ruleset identity differs from the runtime companion",
        )
    if binding.domain_pack_id != ruleset.payload.domain_pack_id:
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.DOMAIN_PACK_MISMATCH,
            "ruleset and runtime companion domain packs differ",
        )
    if binding.state is EvidenceRuntimeBindingState.UNBOUND:
        if evidence is not None:
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.BINDING_DRIFT,
                "unbound companion received an evidence snapshot",
            )
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.UNBOUND,
            "runtime evidence binding is explicitly unbound",
        )
    if type(evidence) is not EvidenceManifestSnapshotV1:
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.EVIDENCE_DRIFT,
            "bound_unreviewed companion requires an evidence snapshot",
        )
    if (
        binding.evidence_snapshot_id != evidence.snapshot_id
        or binding.evidence_content_sha256 != evidence.content_sha256
    ):
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.EVIDENCE_DRIFT,
            "evidence identity differs from the runtime companion",
        )
    payload = evidence.payload
    if (
        binding.evidence_manifest_schema_version
        != payload.evidence_manifest_schema_version
        or binding.evidence_canonicalization_version != payload.canonicalization_version
        or binding.evidence_contract_version != payload.mat_evid_contract_version
    ):
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.VERSION_MISMATCH,
            "evidence versions differ from the runtime companion",
        )
    if payload.ruleset_snapshot_id != ruleset.snapshot_id:
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.RULESET_DRIFT,
            "evidence manifest names another ruleset snapshot",
        )
    if payload.domain_pack_id != binding.domain_pack_id:
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.DOMAIN_PACK_MISMATCH,
            "evidence and runtime companion domain packs differ",
        )

    rules = {rule.rule_ref: rule for rule in ruleset.payload.rules}
    claims = {claim.claim_ref: claim for claim in payload.claims}
    binding_rules = {item.rule_ref for item in payload.rule_claim_bindings}
    foreign = binding_rules - set(rules)
    if foreign:
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.FOREIGN_RULE,
            "evidence references a rule outside the exact ruleset snapshot",
        )
    if binding_rules != set(rules):
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.INCOMPLETE,
            "every rule in the exact snapshot requires evidence",
        )

    claim_owners: dict[str, str] = {}
    references: list[BoundEvidenceReferenceV1] = []
    for item in payload.rule_claim_bindings:
        previous = claim_owners.setdefault(item.claim_ref, item.rule_ref)
        if previous != item.rule_ref:
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.CLAIM_REUSED,
                "one claim cannot support multiple rules in v1",
            )
        rule = rules[item.rule_ref]
        claim = claims[item.claim_ref]
        if (
            rule.material not in rule.scope.materials
            or rule.medium not in rule.scope.media
            or (rule.condition and rule.condition not in rule.scope.conditions)
        ):
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.RULE_SCOPE_INCONSISTENT,
                "rule primary selectors are outside its declared scope",
            )
        if claim.scope.to_dict() != rule.scope.to_dict():
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.SCOPE_MISMATCH,
                "rule and claim scopes must be exactly equal in v1",
            )
        references.append(
            BoundEvidenceReferenceV1(
                rule_ref=item.rule_ref,
                claim_ref=item.claim_ref,
                source_refs=claim.source_refs,
            )
        )
    ordered = tuple(sorted(references))
    return ResolvedEvidenceBindingV1(
        state=EvidenceRuntimeBindingState.BOUND_UNREVIEWED,
        references=ordered,
    )


__all__ = [
    "MAT_EVID_RUNTIME_BINDING_SCHEMA_VERSION",
    "MAT_EVID_RUNTIME_CONTRACT_VERSION",
    "MAT_EVID_RUNTIME_PIN_SCHEMA_VERSION",
    "BoundEvidenceReferenceV1",
    "EvidenceRuntimeAuthority",
    "EvidenceRuntimeBindingState",
    "EvidenceRuntimeBindingV1",
    "EvidenceRuntimePinV1",
    "MaterialEvidenceRuntimeErrorCode",
    "MaterialEvidenceRuntimeIntegrityError",
    "ResolvedEvidenceBindingV1",
    "validate_runtime_binding",
]
