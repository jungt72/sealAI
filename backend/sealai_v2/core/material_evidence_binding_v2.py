"""MAT-EVID-01B.v2 exact binding for MAT-EVID-01A.v2 material manifests.

The v1 companion remains unchanged.  This additive contract accepts only the
v2 ``material_relation`` manifest target; a ``media_identity`` manifest is
factually reviewable but is never a material-rules runtime binding.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from sealai_v2.core.material_evidence_binding import (
    EvidenceRuntimeAuthority,
    EvidenceRuntimeBindingState,
    MaterialEvidenceRuntimeErrorCode,
    MaterialEvidenceRuntimeIntegrityError,
)
from sealai_v2.core.material_evidence_v2 import (
    CANONICALIZATION_VERSION_V2,
    EVIDENCE_MANIFEST_SCHEMA_VERSION_V2,
    MAT_EVID_CONTRACT_VERSION_V2,
    EvidenceManifestSnapshotV2,
    MaterialRelationClaimScopeV2,
    MaterialRelationTargetV2,
)
from sealai_v2.core.material_rulesets import MaterialRulesetSnapshotV1


MAT_EVID_RUNTIME_CONTRACT_VERSION_V2 = "MAT-EVID-01B.v2"
MAT_EVID_RUNTIME_BINDING_SCHEMA_VERSION_V2 = 2
MAT_EVID_RUNTIME_PIN_SCHEMA_VERSION_V2 = 2

_BINDING_ID = re.compile(r"^mshb_[0-9a-f]{32}$", re.ASCII)
_PIN_ID = re.compile(r"^mshp_[0-9a-f]{32}$", re.ASCII)
_RULESET_SNAPSHOT_ID = re.compile(r"^mss_[0-9a-f]{64}$", re.ASCII)
_EVIDENCE_SNAPSHOT_ID = re.compile(r"^mes_[0-9a-f]{64}$", re.ASCII)
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}$", re.ASCII)


def _require_version(value: str, *, field: str) -> None:
    if type(value) is not str or not _VERSION.fullmatch(value):
        raise ValueError(f"{field} must be a stable version identifier")


def _require_hash(value: str, *, field: str) -> None:
    if type(value) is not str or not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class EvidenceRuntimeBindingV2:
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
    binding_schema_version: int = MAT_EVID_RUNTIME_BINDING_SCHEMA_VERSION_V2
    binding_contract_version: str = MAT_EVID_RUNTIME_CONTRACT_VERSION_V2

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
        if self.binding_schema_version != MAT_EVID_RUNTIME_BINDING_SCHEMA_VERSION_V2:
            raise ValueError("unsupported v2 runtime binding schema")
        if self.binding_contract_version != MAT_EVID_RUNTIME_CONTRACT_VERSION_V2:
            raise ValueError("unsupported v2 runtime binding contract")
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
        if (
            self.evidence_manifest_schema_version != EVIDENCE_MANIFEST_SCHEMA_VERSION_V2
            or self.evidence_canonicalization_version != CANONICALIZATION_VERSION_V2
            or self.evidence_contract_version != MAT_EVID_CONTRACT_VERSION_V2
        ):
            raise ValueError("unsupported v2 evidence identity")

    @property
    def authority(self) -> EvidenceRuntimeAuthority:
        if self.state is EvidenceRuntimeBindingState.UNBOUND:
            return EvidenceRuntimeAuthority.NONE
        return EvidenceRuntimeAuthority.TECHNICAL_UNREVIEWED

    @property
    def positive_statement_allowed(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class EvidenceRuntimePinV2:
    pin_id: str
    binding: EvidenceRuntimeBindingV2
    pin_schema_version: int = MAT_EVID_RUNTIME_PIN_SCHEMA_VERSION_V2

    def __post_init__(self) -> None:
        if type(self.pin_id) is not str or not _PIN_ID.fullmatch(self.pin_id):
            raise ValueError("invalid shadow pin_id")
        if type(self.binding) is not EvidenceRuntimeBindingV2:
            raise TypeError("binding must be EvidenceRuntimeBindingV2")
        if self.pin_schema_version != MAT_EVID_RUNTIME_PIN_SCHEMA_VERSION_V2:
            raise ValueError("unsupported v2 runtime pin schema")

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
class BoundEvidenceReferenceV2:
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
class ResolvedEvidenceBindingV2:
    state: EvidenceRuntimeBindingState
    references: tuple[BoundEvidenceReferenceV2, ...]

    def __post_init__(self) -> None:
        if self.state is not EvidenceRuntimeBindingState.BOUND_UNREVIEWED:
            raise ValueError("only bound_unreviewed can be resolved")
        if type(self.references) is not tuple or not self.references:
            raise ValueError("resolved evidence requires references")
        if self.references != tuple(sorted(set(self.references))):
            raise ValueError("evidence references must be unique and ordered")

    def for_rules(
        self, rule_refs: tuple[str, ...]
    ) -> tuple[BoundEvidenceReferenceV2, ...]:
        wanted = set(rule_refs)
        return tuple(ref for ref in self.references if ref.rule_ref in wanted)


def validate_runtime_binding_v2(
    binding: EvidenceRuntimeBindingV2,
    *,
    ruleset: MaterialRulesetSnapshotV1,
    evidence: EvidenceManifestSnapshotV2 | None,
) -> ResolvedEvidenceBindingV2:
    if type(binding) is not EvidenceRuntimeBindingV2:
        raise TypeError("binding must be EvidenceRuntimeBindingV2")
    if type(ruleset) is not MaterialRulesetSnapshotV1:
        raise TypeError("ruleset must be MaterialRulesetSnapshotV1")
    if (
        binding.ruleset_snapshot_id != ruleset.snapshot_id
        or binding.ruleset_content_sha256 != ruleset.content_sha256
    ):
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.RULESET_DRIFT,
            "ruleset identity differs from the v2 runtime companion",
        )
    if binding.domain_pack_id != ruleset.payload.domain_pack_id:
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.DOMAIN_PACK_MISMATCH,
            "ruleset and v2 runtime companion domain packs differ",
        )
    if binding.state is EvidenceRuntimeBindingState.UNBOUND:
        if evidence is not None:
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.BINDING_DRIFT,
                "unbound v2 companion received evidence",
            )
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.UNBOUND,
            "runtime evidence binding is explicitly unbound",
        )
    if type(evidence) is not EvidenceManifestSnapshotV2:
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.EVIDENCE_DRIFT,
            "bound v2 companion requires an exact v2 evidence snapshot",
        )
    if (
        binding.evidence_snapshot_id != evidence.snapshot_id
        or binding.evidence_content_sha256 != evidence.content_sha256
    ):
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.EVIDENCE_DRIFT,
            "v2 evidence identity differs from the runtime companion",
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
            "v2 evidence versions differ from the runtime companion",
        )
    if type(payload.target) is not MaterialRelationTargetV2:
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.SCOPE_MISMATCH,
            "media_identity evidence is outside material-rules runtime binding",
        )
    if payload.target.ruleset_snapshot_id != ruleset.snapshot_id:
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.RULESET_DRIFT,
            "v2 evidence manifest names another ruleset snapshot",
        )
    if payload.domain_pack_id != binding.domain_pack_id:
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.DOMAIN_PACK_MISMATCH,
            "v2 evidence and runtime companion domain packs differ",
        )

    rules = {rule.rule_ref: rule for rule in ruleset.payload.rules}
    claims = {claim.claim_ref: claim for claim in payload.claims}
    binding_rules = {item.rule_ref for item in payload.rule_claim_bindings}
    if binding_rules - set(rules):
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.FOREIGN_RULE,
            "v2 evidence references a foreign rule",
        )
    if binding_rules != set(rules):
        raise MaterialEvidenceRuntimeIntegrityError(
            MaterialEvidenceRuntimeErrorCode.INCOMPLETE,
            "every rule requires v2 evidence",
        )

    claim_owners: dict[str, str] = {}
    references: list[BoundEvidenceReferenceV2] = []
    for item in payload.rule_claim_bindings:
        previous = claim_owners.setdefault(item.claim_ref, item.rule_ref)
        if previous != item.rule_ref:
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.CLAIM_REUSED,
                "one v2 claim cannot support multiple rules",
            )
        rule = rules[item.rule_ref]
        claim = claims[item.claim_ref]
        if type(claim.scope) is not MaterialRelationClaimScopeV2:
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.SCOPE_MISMATCH,
                "runtime claim must have material_relation scope",
            )
        if (
            rule.material not in rule.scope.materials
            or rule.medium not in rule.scope.media
            or (rule.condition and rule.condition not in rule.scope.conditions)
        ):
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.RULE_SCOPE_INCONSISTENT,
                "rule primary selectors are outside its declared scope",
            )
        if (
            claim.scope.materials != rule.scope.materials
            or claim.scope.media != rule.scope.media
            or claim.scope.conditions != rule.scope.conditions
        ):
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.SCOPE_MISMATCH,
                "v2 rule and material_relation claim scopes differ",
            )
        references.append(
            BoundEvidenceReferenceV2(
                rule_ref=item.rule_ref,
                claim_ref=item.claim_ref,
                source_refs=claim.source_refs,
            )
        )
    return ResolvedEvidenceBindingV2(
        state=EvidenceRuntimeBindingState.BOUND_UNREVIEWED,
        references=tuple(sorted(references)),
    )


__all__ = [
    "MAT_EVID_RUNTIME_BINDING_SCHEMA_VERSION_V2",
    "MAT_EVID_RUNTIME_CONTRACT_VERSION_V2",
    "MAT_EVID_RUNTIME_PIN_SCHEMA_VERSION_V2",
    "BoundEvidenceReferenceV2",
    "EvidenceRuntimeBindingV2",
    "EvidenceRuntimePinV2",
    "ResolvedEvidenceBindingV2",
    "validate_runtime_binding_v2",
]
