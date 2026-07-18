"""Evidence-reviewed, disqualify-only material rule-pack capability.

MAT-RULES-01 does not change the immutable MAT-GOV-03A, MAT-EVID-01A/B/C,
or MED-NORM-01 contracts.  It joins their exact snapshots at one repository
boundary and grants no activation or public-response authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Callable

from sealai_v2.core.contracts import MaterialConstraintVerdict
from sealai_v2.core.material_evidence import EvidenceManifestSnapshotV1
from sealai_v2.core.material_evidence_binding import (
    EvidenceRuntimeBindingState,
    EvidenceRuntimeBindingV1,
    validate_runtime_binding,
)
from sealai_v2.core.material_evidence_review import (
    EvidenceClaimType,
    EvidenceReviewProjection,
    EvidenceReviewSnapshotV1,
    FactualApprovalState,
    FactualReviewState,
)
from sealai_v2.core.material_rulesets import MaterialRulesetSnapshotV1
from sealai_v2.core.medium_catalog import (
    EvidenceVerifiedMediumCatalogSnapshotV1,
)


MAT_RULES_CONTRACT_VERSION = "MAT-RULES-01.v1"
MAT_RULES_CAPABILITY_SCHEMA_VERSION = 1
REVIEWED_DISQUALIFY_ONLY_AUTHORITY = "FACTUAL_REVIEWED_DISQUALIFY_ONLY"

_RULE_REF_RE = re.compile(r"^MR-[A-Z0-9][A-Z0-9_-]{0,124}$", re.ASCII)
_CLAIM_REF_RE = re.compile(r"^mec_[0-9a-f]{64}$", re.ASCII)
_SOURCE_REF_RE = re.compile(r"^msr_[0-9a-f]{64}$", re.ASCII)
_MEDIA_ID_RE = re.compile(r"^med_[0-9a-f]{64}$", re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


class ReviewedMaterialRulesErrorCode(str, Enum):
    INVALID_TYPE = "MAT_RULES_INVALID_TYPE"
    IDENTITY_DRIFT = "MAT_RULES_IDENTITY_DRIFT"
    DOMAIN_PACK_MISMATCH = "MAT_RULES_DOMAIN_PACK_MISMATCH"
    EVIDENCE_UNREVIEWED = "MAT_RULES_EVIDENCE_UNREVIEWED"
    REVIEW_DRIFT = "MAT_RULES_REVIEW_DRIFT"
    CATALOG_DRIFT = "MAT_RULES_CATALOG_DRIFT"
    INCOMPLETE = "MAT_RULES_INCOMPLETE"
    NON_ATOMIC_SCOPE = "MAT_RULES_NON_ATOMIC_SCOPE"
    STATEMENT_UNBOUND = "MAT_RULES_STATEMENT_UNBOUND"
    CLAIM_TYPE_MISMATCH = "MAT_RULES_CLAIM_TYPE_MISMATCH"
    POSITIVE_RULE_FORBIDDEN = "MAT_RULES_POSITIVE_RULE_FORBIDDEN"
    DB_INTEGRITY = "MAT_RULES_DB_INTEGRITY"


class ReviewedMaterialRulesValidationError(ValueError):
    def __init__(
        self,
        code: ReviewedMaterialRulesErrorCode,
        message: str,
        *,
        path: str = "$",
    ) -> None:
        self.code = code
        self.path = path
        super().__init__(f"{code.value} at {path}: {message}")


class ReviewedMaterialRulesIntegrityError(RuntimeError):
    quarantine_candidate = True

    def __init__(self, code: ReviewedMaterialRulesErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _validation(
    code: ReviewedMaterialRulesErrorCode,
    message: str,
    *,
    path: str = "$",
) -> None:
    raise ReviewedMaterialRulesValidationError(code, message, path=path)


@dataclass(frozen=True, slots=True, order=True)
class ReviewedMaterialRuleReferenceV1:
    """Exact reviewed references for one atomic, non-positive rule."""

    rule_ref: str
    media_id: str
    verdict: MaterialConstraintVerdict
    statement_claim_ref: str
    claim_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    media_catalog_entry_sha256: str

    def __post_init__(self) -> None:
        if type(self.rule_ref) is not str or not _RULE_REF_RE.fullmatch(self.rule_ref):
            raise ValueError("invalid rule_ref")
        if type(self.media_id) is not str or not _MEDIA_ID_RE.fullmatch(self.media_id):
            raise ValueError("invalid media_id")
        if type(self.verdict) is not MaterialConstraintVerdict or self.verdict not in {
            MaterialConstraintVerdict.UNVERTRAEGLICH,
            MaterialConstraintVerdict.BEDINGT,
        }:
            raise ValueError("reviewed rule references are disqualify-only")
        if type(self.statement_claim_ref) is not str or not _CLAIM_REF_RE.fullmatch(
            self.statement_claim_ref
        ):
            raise ValueError("invalid statement_claim_ref")
        for name, values, pattern in (
            ("claim_refs", self.claim_refs, _CLAIM_REF_RE),
            ("source_refs", self.source_refs, _SOURCE_REF_RE),
        ):
            if (
                type(values) is not tuple
                or not values
                or any(
                    type(item) is not str or not pattern.fullmatch(item)
                    for item in values
                )
                or values != tuple(sorted(set(values)))
            ):
                raise ValueError(f"{name} must be a non-empty canonical tuple")
        if self.statement_claim_ref not in self.claim_refs:
            raise ValueError("statement claim must be part of the rule evidence")
        if type(self.media_catalog_entry_sha256) is not str or not _SHA256_RE.fullmatch(
            self.media_catalog_entry_sha256
        ):
            raise ValueError("invalid catalog entry SHA-256")


def _required_primary_claim_type(
    verdict: MaterialConstraintVerdict,
) -> EvidenceClaimType:
    if verdict is MaterialConstraintVerdict.UNVERTRAEGLICH:
        return EvidenceClaimType.INCOMPATIBILITY
    if verdict is MaterialConstraintVerdict.BEDINGT:
        return EvidenceClaimType.CONDITIONAL_COMPATIBILITY
    _validation(
        ReviewedMaterialRulesErrorCode.POSITIVE_RULE_FORBIDDEN,
        "reviewed v1 rule packs cannot contain positive compatibility rules",
    )


_SUPPORTING_CLAIM_TYPES = frozenset(
    {
        EvidenceClaimType.TEMPERATURE_LIMIT,
        EvidenceClaimType.APPLICATION_LIMIT,
        EvidenceClaimType.REGULATORY_CONSTRAINT,
    }
)


def _validate_reviewed_material_rules(
    *,
    binding: EvidenceRuntimeBindingV1,
    ruleset: MaterialRulesetSnapshotV1,
    evidence: EvidenceManifestSnapshotV1,
    review: EvidenceReviewSnapshotV1,
    projection: EvidenceReviewProjection,
    catalog: EvidenceVerifiedMediumCatalogSnapshotV1,
) -> tuple[ReviewedMaterialRuleReferenceV1, ...]:
    """Validate exact reviewed authority without interpreting technical prose."""

    for value, expected, name in (
        (binding, EvidenceRuntimeBindingV1, "binding"),
        (ruleset, MaterialRulesetSnapshotV1, "ruleset"),
        (evidence, EvidenceManifestSnapshotV1, "evidence"),
        (review, EvidenceReviewSnapshotV1, "review"),
        (projection, EvidenceReviewProjection, "projection"),
        (catalog, EvidenceVerifiedMediumCatalogSnapshotV1, "catalog"),
    ):
        if type(value) is not expected:
            _validation(
                ReviewedMaterialRulesErrorCode.INVALID_TYPE,
                f"{name} must be exact {expected.__name__}",
            )
    if binding.state is not EvidenceRuntimeBindingState.BOUND_UNREVIEWED:
        _validation(
            ReviewedMaterialRulesErrorCode.EVIDENCE_UNREVIEWED,
            "reviewed rule packs require an exact technical evidence binding",
        )
    resolved = validate_runtime_binding(binding, ruleset=ruleset, evidence=evidence)
    if (
        review.payload.evidence_snapshot_id != evidence.snapshot_id
        or review.payload.evidence_content_sha256 != evidence.content_sha256
    ):
        _validation(
            ReviewedMaterialRulesErrorCode.REVIEW_DRIFT,
            "review is not pinned to the exact evidence snapshot",
        )
    review.payload.validate_for_approval(evidence)
    if (
        projection.review_state is not FactualReviewState.REVIEWED
        or projection.approval_state is not FactualApprovalState.APPROVED
    ):
        _validation(
            ReviewedMaterialRulesErrorCode.EVIDENCE_UNREVIEWED,
            "factual evidence is not currently reviewed and approved",
        )
    if not (
        ruleset.payload.domain_pack_id
        == evidence.payload.domain_pack_id
        == catalog.payload.domain_pack_id
        == binding.domain_pack_id
    ):
        _validation(
            ReviewedMaterialRulesErrorCode.DOMAIN_PACK_MISMATCH,
            "ruleset, evidence, binding, and catalog domain packs differ",
        )
    catalog.assert_current()

    evidence_claims = {claim.claim_ref: claim for claim in evidence.payload.claims}
    reviewed_claims = {claim.claim_ref: claim for claim in review.payload.claims}
    references_by_rule: dict[str, list] = {}
    for reference in resolved.references:
        references_by_rule.setdefault(reference.rule_ref, []).append(reference)

    reviewed: list[ReviewedMaterialRuleReferenceV1] = []
    for index, rule in enumerate(ruleset.payload.rules):
        path = f"$.rules[{index}]"
        required_primary_type = _required_primary_claim_type(rule.verdict)
        if (
            rule.scope.materials != (rule.material,)
            or rule.scope.media != (rule.medium,)
            or rule.scope.conditions != (rule.condition,)
        ):
            _validation(
                ReviewedMaterialRulesErrorCode.NON_ATOMIC_SCOPE,
                "reviewed v1 rules require exact single material, medium, and condition scope",
                path=f"{path}.scope",
            )
        catalog_entry = catalog.payload.entry(rule.medium)
        if catalog_entry is None:
            _validation(
                ReviewedMaterialRulesErrorCode.CATALOG_DRIFT,
                "rule medium is absent from the exact reviewed catalog",
                path=f"{path}.medium",
            )
        bound = references_by_rule.get(rule.rule_ref, [])
        if not bound:
            _validation(
                ReviewedMaterialRulesErrorCode.INCOMPLETE,
                "reviewed rule lacks evidence references",
                path=path,
            )
        claim_refs = tuple(sorted(reference.claim_ref for reference in bound))
        claims = [evidence_claims[claim_ref] for claim_ref in claim_refs]
        metadata = [reviewed_claims[claim_ref] for claim_ref in claim_refs]
        statement_claims = [
            claim.claim_ref for claim in claims if claim.claim_text == rule.statement
        ]
        if len(statement_claims) != 1:
            _validation(
                ReviewedMaterialRulesErrorCode.STATEMENT_UNBOUND,
                "exactly one approved claim must equal the complete rule statement",
                path=f"{path}.statement",
            )
        metadata_by_ref = {item.claim_ref: item for item in metadata}
        statement_metadata = metadata_by_ref[statement_claims[0]]
        if statement_metadata.claim_type is not required_primary_type:
            _validation(
                ReviewedMaterialRulesErrorCode.CLAIM_TYPE_MISMATCH,
                "primary claim type does not authorize the rule verdict",
                path=f"{path}.verdict",
            )
        allowed_types = _SUPPORTING_CLAIM_TYPES | {required_primary_type}
        if any(item.claim_type not in allowed_types for item in metadata):
            _validation(
                ReviewedMaterialRulesErrorCode.CLAIM_TYPE_MISMATCH,
                "rule contains a claim type outside the closed verdict allowlist",
                path=path,
            )
        source_refs = tuple(
            sorted({source for reference in bound for source in reference.source_refs})
        )
        reviewed.append(
            ReviewedMaterialRuleReferenceV1(
                rule_ref=rule.rule_ref,
                media_id=rule.medium,
                verdict=rule.verdict,
                statement_claim_ref=statement_claims[0],
                claim_refs=claim_refs,
                source_refs=source_refs,
                media_catalog_entry_sha256=catalog_entry.entry_sha256,
            )
        )
    ordered = tuple(sorted(reviewed))
    if len(ordered) != len(ruleset.payload.rules):
        _validation(
            ReviewedMaterialRulesErrorCode.INCOMPLETE,
            "reviewed references do not cover every rule",
        )
    return ordered


_REVIEWED_RULES_TOKEN = object()


class EvidenceReviewedMaterialRulesV1:
    """Repository-issued live capability; intentionally non-serializable."""

    __slots__ = (
        "__binding",
        "__catalog",
        "__evidence",
        "__references",
        "__revalidate",
        "__review",
        "__ruleset",
        "__tenant_id",
    )

    def __init__(
        self,
        *,
        binding: EvidenceRuntimeBindingV1,
        ruleset: MaterialRulesetSnapshotV1,
        evidence: EvidenceManifestSnapshotV1,
        review: EvidenceReviewSnapshotV1,
        catalog: EvidenceVerifiedMediumCatalogSnapshotV1,
        references: tuple[ReviewedMaterialRuleReferenceV1, ...],
        tenant_id: str,
        revalidate: Callable[[], None],
        _token: object | None = None,
    ) -> None:
        if _token is not _REVIEWED_RULES_TOKEN:
            _validation(
                ReviewedMaterialRulesErrorCode.INVALID_TYPE,
                "reviewed rule capabilities are repository-issued only",
            )
        if (
            type(tenant_id) is not str
            or not tenant_id
            or tenant_id != catalog.tenant_id
        ):
            _validation(
                ReviewedMaterialRulesErrorCode.IDENTITY_DRIFT,
                "capability tenant differs from the verified catalog tenant",
            )
        if type(references) is not tuple or not references:
            raise TypeError("reviewed rule capability requires references")
        if not callable(revalidate):
            raise TypeError("reviewed rule capability requires live revalidation")
        self.__binding = binding
        self.__ruleset = ruleset
        self.__evidence = evidence
        self.__review = review
        self.__catalog = catalog
        self.__references = references
        self.__tenant_id = tenant_id
        self.__revalidate = revalidate

    @property
    def binding(self) -> EvidenceRuntimeBindingV1:
        self.assert_current()
        return self.__binding

    @property
    def ruleset(self) -> MaterialRulesetSnapshotV1:
        self.assert_current()
        return self.__ruleset

    @property
    def evidence(self) -> EvidenceManifestSnapshotV1:
        self.assert_current()
        return self.__evidence

    @property
    def review(self) -> EvidenceReviewSnapshotV1:
        self.assert_current()
        return self.__review

    @property
    def catalog(self) -> EvidenceVerifiedMediumCatalogSnapshotV1:
        self.assert_current()
        return self.__catalog

    @property
    def references(self) -> tuple[ReviewedMaterialRuleReferenceV1, ...]:
        self.assert_current()
        return self.__references

    @property
    def tenant_id(self) -> str:
        return self.__tenant_id

    @property
    def authority(self) -> str:
        self.assert_current()
        return REVIEWED_DISQUALIFY_ONLY_AUTHORITY

    @property
    def positive_statement_allowed(self) -> bool:
        return False

    def assert_current(self) -> None:
        self.__revalidate()

    def __reduce__(self):
        raise TypeError("reviewed material rule capabilities are not serializable")


def _bind_evidence_reviewed_material_rules(
    *,
    binding: EvidenceRuntimeBindingV1,
    ruleset: MaterialRulesetSnapshotV1,
    evidence: EvidenceManifestSnapshotV1,
    review: EvidenceReviewSnapshotV1,
    catalog: EvidenceVerifiedMediumCatalogSnapshotV1,
    projection: EvidenceReviewProjection,
    tenant_id: str,
    revalidate: Callable[[], None],
) -> EvidenceReviewedMaterialRulesV1:
    references = _validate_reviewed_material_rules(
        binding=binding,
        ruleset=ruleset,
        evidence=evidence,
        review=review,
        projection=projection,
        catalog=catalog,
    )
    return EvidenceReviewedMaterialRulesV1(
        binding=binding,
        ruleset=ruleset,
        evidence=evidence,
        review=review,
        catalog=catalog,
        references=references,
        tenant_id=tenant_id,
        revalidate=revalidate,
        _token=_REVIEWED_RULES_TOKEN,
    )


__all__ = [
    "MAT_RULES_CAPABILITY_SCHEMA_VERSION",
    "MAT_RULES_CONTRACT_VERSION",
    "REVIEWED_DISQUALIFY_ONLY_AUTHORITY",
    "EvidenceReviewedMaterialRulesV1",
    "ReviewedMaterialRuleReferenceV1",
    "ReviewedMaterialRulesErrorCode",
    "ReviewedMaterialRulesIntegrityError",
    "ReviewedMaterialRulesValidationError",
]
