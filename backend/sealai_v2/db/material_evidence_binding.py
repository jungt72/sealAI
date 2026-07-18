"""Persistence helpers for immutable MAT-EVID-01B runtime companions."""

from __future__ import annotations

import hashlib
import json
import secrets

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.core.material_evidence import EvidenceManifestSnapshotV1
from sealai_v2.core.material_evidence_binding import (
    EvidenceRuntimeBindingState,
    EvidenceRuntimeBindingV1,
    EvidenceRuntimePinV1,
    MaterialEvidenceRuntimeErrorCode,
    MaterialEvidenceRuntimeIntegrityError,
    validate_runtime_binding,
)
from sealai_v2.core.material_rulesets import MaterialRulesetSnapshotV1
from sealai_v2.core.material_shadow import ShadowBinding, ShadowMaterialRulesetPin
from sealai_v2.db.models import (
    V2MaterialEvidenceRuntimeAuditEvent,
    V2MaterialEvidenceRuntimeBinding,
    V2MaterialEvidenceRuntimeEvaluation,
    V2MaterialEvidenceRuntimeEvaluationRef,
    V2MaterialEvidenceRuntimePin,
    V2MaterialShadowEvaluation,
    V2MaterialShadowEvaluationMatch,
)
from sealai_v2.material_evidence_binding.evaluator import EvidenceRuntimeEvaluationV1


_AUDIT_DOMAIN = b"sealai.material-evidence.runtime-audit.v1\x00"


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


def _audit_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(_AUDIT_DOMAIN + encoded).hexdigest()


class MaterialEvidenceRuntimeRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    @staticmethod
    def assert_shadow_binding(
        companion: EvidenceRuntimeBindingV1, shadow: ShadowBinding
    ) -> None:
        if (
            companion.binding_id != shadow.binding_id
            or companion.ruleset_snapshot_id != shadow.snapshot_id
            or companion.ruleset_content_sha256 != shadow.content_sha256
            or companion.domain_pack_id != shadow.domain_pack_id
            or companion.domain_pack_version != shadow.domain_pack_version
            or companion.evaluator_version != shadow.evaluator_version
            or companion.kernel_version != shadow.kernel_version
        ):
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.BINDING_DRIFT,
                "runtime evidence companion differs from the shadow binding",
            )

    @classmethod
    def insert_binding_companion(
        cls,
        session,
        *,
        companion: EvidenceRuntimeBindingV1,
        shadow: ShadowBinding,
        actor_subject: str,
        created_at: str,
    ) -> None:
        cls.assert_shadow_binding(companion, shadow)
        session.add(
            V2MaterialEvidenceRuntimeBinding(
                binding_id=companion.binding_id,
                binding_schema_version=companion.binding_schema_version,
                binding_contract_version=companion.binding_contract_version,
                binding_state=companion.state.value,
                ruleset_snapshot_id=companion.ruleset_snapshot_id,
                ruleset_content_sha256=companion.ruleset_content_sha256,
                evidence_snapshot_id=companion.evidence_snapshot_id,
                evidence_content_sha256=companion.evidence_content_sha256,
                evidence_manifest_schema_version=(
                    companion.evidence_manifest_schema_version
                ),
                evidence_canonicalization_version=(
                    companion.evidence_canonicalization_version
                ),
                evidence_contract_version=companion.evidence_contract_version,
                domain_pack_id=companion.domain_pack_id,
                domain_pack_version=companion.domain_pack_version,
                evaluator_version=companion.evaluator_version,
                kernel_version=companion.kernel_version,
                authority=companion.authority.value,
                positive_statement_allowed=False,
                created_at=created_at,
            )
        )
        session.flush()
        payload = {
            "binding_id": companion.binding_id,
            "binding_state": companion.state.value,
            "evidence_snapshot_id": companion.evidence_snapshot_id,
            "ruleset_snapshot_id": companion.ruleset_snapshot_id,
        }
        session.add(
            V2MaterialEvidenceRuntimeAuditEvent(
                event_id=_id("meba"),
                binding_id=companion.binding_id,
                pin_id=None,
                evaluation_id=None,
                event_type="binding_created",
                actor_subject=actor_subject,
                event_payload_json=payload,
                event_sha256=_audit_hash(payload),
                created_at=created_at,
            )
        )

    @staticmethod
    def binding_from_row(
        row: V2MaterialEvidenceRuntimeBinding,
    ) -> EvidenceRuntimeBindingV1:
        try:
            return EvidenceRuntimeBindingV1(
                binding_id=row.binding_id,
                state=EvidenceRuntimeBindingState(row.binding_state),
                ruleset_snapshot_id=row.ruleset_snapshot_id,
                ruleset_content_sha256=row.ruleset_content_sha256,
                evidence_snapshot_id=row.evidence_snapshot_id,
                evidence_content_sha256=row.evidence_content_sha256,
                evidence_manifest_schema_version=(row.evidence_manifest_schema_version),
                evidence_canonicalization_version=(
                    row.evidence_canonicalization_version
                ),
                evidence_contract_version=row.evidence_contract_version,
                domain_pack_id=row.domain_pack_id,
                domain_pack_version=row.domain_pack_version,
                evaluator_version=row.evaluator_version,
                kernel_version=row.kernel_version,
                binding_schema_version=row.binding_schema_version,
                binding_contract_version=row.binding_contract_version,
            )
        except (TypeError, ValueError) as exc:
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.BINDING_DRIFT,
                "persisted runtime evidence binding failed validation",
            ) from exc

    def load_binding(self, binding_id: str) -> EvidenceRuntimeBindingV1:
        with self._session_factory() as session:
            row = session.get(V2MaterialEvidenceRuntimeBinding, binding_id)
            if row is None:
                raise KeyError(binding_id)
            return self.binding_from_row(row)

    @classmethod
    def insert_pin_companion(
        cls,
        session,
        *,
        shadow_pin: ShadowMaterialRulesetPin,
        created_at: str,
    ) -> EvidenceRuntimePinV1:
        row = session.get(V2MaterialEvidenceRuntimeBinding, shadow_pin.binding_id)
        if row is None:
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.UNBOUND,
                "shadow binding has no runtime evidence companion",
            )
        binding = cls.binding_from_row(row)
        if (
            binding.ruleset_snapshot_id != shadow_pin.snapshot_id
            or binding.ruleset_content_sha256 != shadow_pin.content_sha256
            or binding.domain_pack_id != shadow_pin.domain_pack_id
            or binding.domain_pack_version != shadow_pin.domain_pack_version
            or binding.evaluator_version != shadow_pin.evaluator_version
            or binding.kernel_version != shadow_pin.kernel_version
        ):
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.BINDING_DRIFT,
                "runtime evidence binding differs from the shadow pin",
            )
        pin = EvidenceRuntimePinV1(pin_id=shadow_pin.pin_id, binding=binding)
        session.add(
            V2MaterialEvidenceRuntimePin(
                pin_id=pin.pin_id,
                pin_schema_version=pin.pin_schema_version,
                binding_id=binding.binding_id,
                binding_state=binding.state.value,
                ruleset_snapshot_id=binding.ruleset_snapshot_id,
                ruleset_content_sha256=binding.ruleset_content_sha256,
                evidence_snapshot_id=binding.evidence_snapshot_id,
                evidence_content_sha256=binding.evidence_content_sha256,
                authority=binding.authority.value,
                positive_statement_allowed=False,
                created_at=created_at,
            )
        )
        session.flush()
        payload = {
            "binding_id": binding.binding_id,
            "binding_state": binding.state.value,
            "pin_id": pin.pin_id,
        }
        session.add(
            V2MaterialEvidenceRuntimeAuditEvent(
                event_id=_id("meba"),
                binding_id=binding.binding_id,
                pin_id=pin.pin_id,
                evaluation_id=None,
                event_type="pin_created",
                actor_subject="system:material-shadow",
                event_payload_json=payload,
                event_sha256=_audit_hash(payload),
                created_at=created_at,
            )
        )
        return pin

    @classmethod
    def pin_from_rows(
        cls,
        pin_row: V2MaterialEvidenceRuntimePin,
        binding_row: V2MaterialEvidenceRuntimeBinding,
    ) -> EvidenceRuntimePinV1:
        binding = cls.binding_from_row(binding_row)
        if (
            pin_row.binding_id != binding.binding_id
            or pin_row.binding_state != binding.state.value
            or pin_row.ruleset_snapshot_id != binding.ruleset_snapshot_id
            or pin_row.ruleset_content_sha256 != binding.ruleset_content_sha256
            or pin_row.evidence_snapshot_id != binding.evidence_snapshot_id
            or pin_row.evidence_content_sha256 != binding.evidence_content_sha256
            or pin_row.authority != binding.authority.value
            or pin_row.positive_statement_allowed is not False
        ):
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.BINDING_DRIFT,
                "persisted runtime evidence pin differs from its binding",
            )
        return EvidenceRuntimePinV1(
            pin_id=pin_row.pin_id,
            binding=binding,
            pin_schema_version=pin_row.pin_schema_version,
        )

    def load_pin(self, pin_id: str) -> EvidenceRuntimePinV1:
        with self._session_factory() as session:
            pin_row = session.get(V2MaterialEvidenceRuntimePin, pin_id)
            if pin_row is None:
                raise KeyError(pin_id)
            binding_row = session.get(
                V2MaterialEvidenceRuntimeBinding, pin_row.binding_id
            )
            if binding_row is None:
                raise MaterialEvidenceRuntimeIntegrityError(
                    MaterialEvidenceRuntimeErrorCode.BINDING_DRIFT,
                    "runtime evidence pin references a missing binding",
                )
            return self.pin_from_rows(pin_row, binding_row)

    @classmethod
    def insert_evaluation_companion(
        cls,
        session,
        *,
        evaluation_id: str,
        pin: EvidenceRuntimePinV1,
        result: EvidenceRuntimeEvaluationV1,
        ruleset: MaterialRulesetSnapshotV1 | None,
        evidence: EvidenceManifestSnapshotV1 | None,
        created_at: str,
    ) -> None:
        if type(pin) is not EvidenceRuntimePinV1:
            raise TypeError("pin must be EvidenceRuntimePinV1")
        if type(result) is not EvidenceRuntimeEvaluationV1:
            raise TypeError("result must be EvidenceRuntimeEvaluationV1")
        binding = pin.binding
        if (
            result.evidence_binding_state is not binding.state
            or result.ruleset_snapshot_id != binding.ruleset_snapshot_id
            or result.ruleset_content_sha256 != binding.ruleset_content_sha256
            or result.evidence_snapshot_id != binding.evidence_snapshot_id
            or result.evidence_content_sha256 != binding.evidence_content_sha256
        ):
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.BINDING_DRIFT,
                "runtime evidence evaluation differs from its pin",
            )
        session.flush()
        pin_row = session.get(V2MaterialEvidenceRuntimePin, pin.pin_id)
        binding_row = session.get(
            V2MaterialEvidenceRuntimeBinding,
            binding.binding_id,
        )
        if (
            pin_row is None
            or binding_row is None
            or cls.pin_from_rows(pin_row, binding_row) != pin
        ):
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.BINDING_DRIFT,
                "runtime evidence evaluation pin differs from persisted state",
            )
        shadow_row = session.get(V2MaterialShadowEvaluation, evaluation_id)
        if shadow_row is None:
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.TECHNICAL_RESULT_DRIFT,
                "runtime evidence evaluation has no shadow evaluation",
            )
        shadow_matches = tuple(
            (
                match.rule_ref,
                match.verdict,
                match.source_ref,
            )
            for match in session.scalars(
                select(V2MaterialShadowEvaluationMatch)
                .where(V2MaterialShadowEvaluationMatch.evaluation_id == evaluation_id)
                .order_by(
                    V2MaterialShadowEvaluationMatch.rule_ref,
                    V2MaterialShadowEvaluationMatch.verdict,
                    V2MaterialShadowEvaluationMatch.source_ref,
                )
            ).all()
        )
        if (
            shadow_row.pin_id != pin.pin_id
            or shadow_row.evaluation_state != result.evaluation_state
            or shadow_row.verdict != result.verdict
            or shadow_row.decisive_ref != result.decisive_ref
            or shadow_row.result_sha256
            != (result.technical_result_sha256 or result.result_sha256)
            or shadow_row.stable_error_code != result.stable_error_code
            or shadow_matches != tuple(sorted(result.matches))
        ):
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.TECHNICAL_RESULT_DRIFT,
                "persisted shadow evaluation differs from the evidence envelope",
            )
        if result.evaluation_state != "integrity_blocked":
            if type(ruleset) is not MaterialRulesetSnapshotV1:
                raise MaterialEvidenceRuntimeIntegrityError(
                    MaterialEvidenceRuntimeErrorCode.RULESET_DRIFT,
                    "completed evaluation requires its exact ruleset snapshot",
                )
            if type(evidence) is not EvidenceManifestSnapshotV1:
                raise MaterialEvidenceRuntimeIntegrityError(
                    MaterialEvidenceRuntimeErrorCode.EVIDENCE_DRIFT,
                    "completed evaluation requires its exact evidence snapshot",
                )
            resolved = validate_runtime_binding(
                binding,
                ruleset=ruleset,
                evidence=evidence,
            )
            expected_references = resolved.for_rules(
                tuple(rule_ref for rule_ref, _verdict, _source in result.matches)
            )
            if result.references != expected_references:
                raise MaterialEvidenceRuntimeIntegrityError(
                    MaterialEvidenceRuntimeErrorCode.REFERENCE_DRIFT,
                    "evaluation references differ from the exact evidence manifest",
                )
        session.add(
            V2MaterialEvidenceRuntimeEvaluation(
                evaluation_id=evaluation_id,
                pin_id=pin.pin_id,
                binding_state=binding.state.value,
                ruleset_snapshot_id=binding.ruleset_snapshot_id,
                ruleset_content_sha256=binding.ruleset_content_sha256,
                evidence_snapshot_id=binding.evidence_snapshot_id,
                evidence_content_sha256=binding.evidence_content_sha256,
                result_sha256=result.result_sha256,
                stable_error_code=result.stable_error_code,
                authority=binding.authority.value,
                positive_statement_allowed=False,
                created_at=created_at,
            )
        )
        session.flush()
        for reference in result.references:
            for source_ref in reference.source_refs:
                session.add(
                    V2MaterialEvidenceRuntimeEvaluationRef(
                        ref_id=_id("meri"),
                        evaluation_id=evaluation_id,
                        rule_ref=reference.rule_ref,
                        claim_ref=reference.claim_ref,
                        source_ref=source_ref,
                    )
                )
        event_type = (
            "integrity_blocked"
            if result.evaluation_state == "integrity_blocked"
            else "evaluation_created"
        )
        payload = {
            "binding_id": binding.binding_id,
            "evaluation_id": evaluation_id,
            "pin_id": pin.pin_id,
            "result_sha256": result.result_sha256,
            "stable_error_code": result.stable_error_code,
        }
        session.add(
            V2MaterialEvidenceRuntimeAuditEvent(
                event_id=_id("meba"),
                binding_id=binding.binding_id,
                pin_id=pin.pin_id,
                evaluation_id=evaluation_id,
                event_type=event_type,
                actor_subject="system:material-shadow-worker",
                event_payload_json=payload,
                event_sha256=_audit_hash(payload),
                created_at=created_at,
            )
        )


__all__ = ["MaterialEvidenceRuntimeRepository"]
