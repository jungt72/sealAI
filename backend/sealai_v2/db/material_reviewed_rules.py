"""Repository coordinator for the inert MAT-RULES-01 capability."""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.core.material_evidence_binding import (
    EvidenceRuntimeBindingState,
    MaterialEvidenceRuntimeErrorCode,
    MaterialEvidenceRuntimeIntegrityError,
)
from sealai_v2.core.material_reviewed_rules import (
    EvidenceReviewedMaterialRulesV1,
    ReviewedMaterialRulesErrorCode,
    ReviewedMaterialRulesIntegrityError,
    _bind_evidence_reviewed_material_rules,
    _validate_reviewed_material_rules,
)
from sealai_v2.db.material_evidence import MaterialEvidenceRepository
from sealai_v2.db.material_evidence_binding import MaterialEvidenceRuntimeRepository
from sealai_v2.db.material_evidence_review import MaterialEvidenceReviewRepository
from sealai_v2.db.material_rulesets import MaterialRulesetRepository
from sealai_v2.db.medium_catalog import MediumCatalogRepository


class ReviewedMaterialRulesRepository:
    """Load exact dependencies and revalidate current factual authority."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._rulesets = MaterialRulesetRepository(session_factory)
        self._evidence = MaterialEvidenceRepository(session_factory)
        self._bindings = MaterialEvidenceRuntimeRepository(session_factory)
        self._reviews = MaterialEvidenceReviewRepository(session_factory)
        self._catalogs = MediumCatalogRepository(session_factory, self._reviews)

    def load_capability(
        self,
        *,
        binding_id: str,
        review_snapshot_id: str,
        catalog_snapshot_id: str,
        identity: VerifiedIdentity,
    ) -> EvidenceReviewedMaterialRulesV1:
        self._require_identity(identity)
        dependencies = self._load_and_validate(
            binding_id=binding_id,
            review_snapshot_id=review_snapshot_id,
            catalog_snapshot_id=catalog_snapshot_id,
            identity=identity,
        )
        binding, ruleset, evidence, review, projection, catalog = dependencies
        expected = (binding, ruleset, evidence, review, catalog)
        return _bind_evidence_reviewed_material_rules(
            binding=binding,
            ruleset=ruleset,
            evidence=evidence,
            review=review,
            projection=projection,
            catalog=catalog,
            tenant_id=identity.tenant_id,
            revalidate=lambda: self._assert_current(
                binding_id=binding_id,
                review_snapshot_id=review_snapshot_id,
                catalog_snapshot_id=catalog_snapshot_id,
                identity=identity,
                expected=expected,
            ),
        )

    def _assert_current(
        self,
        *,
        binding_id: str,
        review_snapshot_id: str,
        catalog_snapshot_id: str,
        identity: VerifiedIdentity,
        expected: tuple,
    ) -> None:
        current = self._load_and_validate(
            binding_id=binding_id,
            review_snapshot_id=review_snapshot_id,
            catalog_snapshot_id=catalog_snapshot_id,
            identity=identity,
        )
        (
            current_binding,
            current_ruleset,
            current_evidence,
            current_review,
            _,
            current_catalog,
        ) = current
        (
            expected_binding,
            expected_ruleset,
            expected_evidence,
            expected_review,
            expected_catalog,
        ) = expected
        if (
            current_binding != expected_binding
            or current_ruleset != expected_ruleset
            or current_evidence != expected_evidence
            or current_review != expected_review
            or current_catalog.snapshot_id != expected_catalog.snapshot_id
            or current_catalog.content_sha256 != expected_catalog.content_sha256
            or current_catalog.tenant_id != expected_catalog.tenant_id
        ):
            raise ReviewedMaterialRulesIntegrityError(
                ReviewedMaterialRulesErrorCode.IDENTITY_DRIFT,
                "held capability dependencies changed identity",
            )

    def _load_and_validate(
        self,
        *,
        binding_id: str,
        review_snapshot_id: str,
        catalog_snapshot_id: str,
        identity: VerifiedIdentity,
    ):
        try:
            binding = self._bindings.load_binding(binding_id)
            if (
                binding.state is not EvidenceRuntimeBindingState.BOUND_UNREVIEWED
                or binding.evidence_snapshot_id is None
            ):
                raise MaterialEvidenceRuntimeIntegrityError(
                    MaterialEvidenceRuntimeErrorCode.UNBOUND,
                    "reviewed rules require bound_unreviewed 01B identity",
                )
            ruleset = self._rulesets.load_snapshot(binding.ruleset_snapshot_id)
            evidence = self._evidence.load_snapshot(binding.evidence_snapshot_id)
            review = self._reviews.load_snapshot(review_snapshot_id, identity=identity)
            projection = self._reviews.load_projection(
                review_snapshot_id, identity=identity
            )
            catalog = self._catalogs.load_snapshot(
                catalog_snapshot_id, identity=identity
            )
            _validate_reviewed_material_rules(
                binding=binding,
                ruleset=ruleset,
                evidence=evidence,
                review=review,
                projection=projection,
                catalog=catalog,
            )
            return binding, ruleset, evidence, review, projection, catalog
        except ReviewedMaterialRulesIntegrityError:
            raise
        except Exception as exc:
            raise ReviewedMaterialRulesIntegrityError(
                ReviewedMaterialRulesErrorCode.DB_INTEGRITY,
                "reviewed material rules failed strict repository revalidation",
            ) from exc

    @staticmethod
    def _require_identity(identity: VerifiedIdentity) -> None:
        if type(identity) is not VerifiedIdentity:
            raise TypeError("identity must be exact VerifiedIdentity")


__all__ = ["ReviewedMaterialRulesRepository"]
