"""Fail-closed MAT-EVID-01B.v2 evaluation over exact v2 evidence pins."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from sealai_v2.core.material_evidence_binding import (
    EvidenceRuntimeBindingState,
    MaterialEvidenceRuntimeErrorCode,
    MaterialEvidenceRuntimeIntegrityError,
)
from sealai_v2.core.material_evidence_binding_v2 import (
    BoundEvidenceReferenceV2,
    EvidenceRuntimePinV2,
    validate_runtime_binding_v2,
)
from sealai_v2.core.material_evidence_v2 import EvidenceManifestSnapshotV2
from sealai_v2.core.material_rulesets import MaterialRulesetSnapshotV1
from sealai_v2.core.material_shadow import ShadowMaterialInput
from sealai_v2.material_shadow.cache import validate_cache_value
from sealai_v2.material_shadow.evaluator import evaluate_snapshot


_RESULT_DOMAIN_V2 = b"sealai.material-evidence.runtime-result.v2\x00"
_RULESET_SNAPSHOT_ID = re.compile(r"^mss_[0-9a-f]{64}$", re.ASCII)
_EVIDENCE_SNAPSHOT_ID = re.compile(r"^mes_[0-9a-f]{64}$", re.ASCII)
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_TECHNICAL_STATES = frozenset({"blocked", "evaluated", "no_rule_data"})


@dataclass(frozen=True, slots=True)
class EvidenceRuntimeEvaluationV2:
    evaluation_state: str
    verdict: str | None
    decisive_ref: str | None
    matches: tuple[tuple[str, str, str], ...]
    stable_error_code: str
    technical_result_sha256: str | None
    evidence_binding_state: EvidenceRuntimeBindingState
    ruleset_snapshot_id: str
    ruleset_content_sha256: str
    evidence_snapshot_id: str | None
    evidence_content_sha256: str | None
    references: tuple[BoundEvidenceReferenceV2, ...]
    result_sha256: str

    @property
    def positive_statement_allowed(self) -> bool:
        return False

    def __post_init__(self) -> None:
        if type(self.evidence_binding_state) is not EvidenceRuntimeBindingState:
            raise TypeError("evidence_binding_state must be typed")
        if type(self.evaluation_state) is not str or self.evaluation_state not in (
            _TECHNICAL_STATES | {"integrity_blocked"}
        ):
            raise ValueError("unsupported v2 runtime evidence evaluation state")
        if not _RULESET_SNAPSHOT_ID.fullmatch(self.ruleset_snapshot_id):
            raise ValueError("invalid ruleset snapshot identity")
        if not _SHA256.fullmatch(self.ruleset_content_sha256):
            raise ValueError("invalid ruleset content hash")
        if (self.evidence_snapshot_id is None) != (
            self.evidence_content_sha256 is None
        ):
            raise ValueError("evidence snapshot identity must be complete or absent")
        if self.evidence_snapshot_id is not None and (
            not _EVIDENCE_SNAPSHOT_ID.fullmatch(self.evidence_snapshot_id)
            or not _SHA256.fullmatch(self.evidence_content_sha256 or "")
        ):
            raise ValueError("invalid evidence snapshot identity")
        if type(self.matches) is not tuple or type(self.references) is not tuple:
            raise TypeError("matches and references must be immutable tuples")
        if self.references != tuple(sorted(set(self.references))):
            raise ValueError("evidence references must be unique and ordered")
        if type(self.stable_error_code) is not str or not self.stable_error_code:
            raise ValueError("stable_error_code must be non-empty")
        if self.evaluation_state == "integrity_blocked":
            if (
                self.verdict is not None
                or self.decisive_ref is not None
                or self.matches
                or self.references
                or self.technical_result_sha256 is not None
                or self.stable_error_code == "none"
            ):
                raise ValueError("integrity_blocked cannot carry a technical result")
        else:
            if (
                self.evidence_binding_state
                is not EvidenceRuntimeBindingState.BOUND_UNREVIEWED
            ):
                raise ValueError("only bound_unreviewed may carry a technical result")
            if self.stable_error_code != "none" or self.technical_result_sha256 is None:
                raise ValueError("completed bound result requires a technical hash")
            validate_cache_value(self.shadow_projection())
            matched = {rule_ref for rule_ref, _verdict, _source in self.matches}
            referenced = {reference.rule_ref for reference in self.references}
            if referenced != matched:
                raise ValueError(
                    "completed bound result requires evidence for exactly its matches"
                )
        if self.result_sha256 != _result_hash(self._hash_payload()):
            raise ValueError("v2 runtime evidence result hash mismatch")

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "decisive_ref": self.decisive_ref,
            "evaluation_state": self.evaluation_state,
            "evidence_binding_state": self.evidence_binding_state.value,
            "evidence_content_sha256": self.evidence_content_sha256,
            "evidence_snapshot_id": self.evidence_snapshot_id,
            "matches": [
                {"rule_ref": rule_ref, "source_ref": source_ref, "verdict": verdict}
                for rule_ref, verdict, source_ref in self.matches
            ],
            "positive_statement_allowed": False,
            "references": [
                {
                    "claim_ref": ref.claim_ref,
                    "rule_ref": ref.rule_ref,
                    "source_refs": list(ref.source_refs),
                }
                for ref in self.references
            ],
            "ruleset_content_sha256": self.ruleset_content_sha256,
            "ruleset_snapshot_id": self.ruleset_snapshot_id,
            "stable_error_code": self.stable_error_code,
            "technical_result_sha256": self.technical_result_sha256,
            "verdict": self.verdict,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._hash_payload(), "result_sha256": self.result_sha256}

    def shadow_projection(self) -> dict[str, Any]:
        return {
            "decisive_ref": self.decisive_ref,
            "evaluation_state": self.evaluation_state,
            "matches": [
                {"rule_ref": rule_ref, "verdict": verdict, "source_ref": source_ref}
                for rule_ref, verdict, source_ref in self.matches
            ],
            "result_sha256": self.technical_result_sha256 or self.result_sha256,
            "stable_error_code": self.stable_error_code,
            "verdict": self.verdict,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> EvidenceRuntimeEvaluationV2:
        expected = {
            "decisive_ref",
            "evaluation_state",
            "evidence_binding_state",
            "evidence_content_sha256",
            "evidence_snapshot_id",
            "matches",
            "positive_statement_allowed",
            "references",
            "result_sha256",
            "ruleset_content_sha256",
            "ruleset_snapshot_id",
            "stable_error_code",
            "technical_result_sha256",
            "verdict",
        }
        if type(value) is not dict or set(value) != expected:
            raise ValueError("v2 runtime evidence result schema mismatch")
        if value["positive_statement_allowed"] is not False:
            raise ValueError("positive material statement is forbidden")
        if type(value["matches"]) is not list or any(
            type(item) is not dict
            or set(item) != {"rule_ref", "verdict", "source_ref"}
            or any(type(part) is not str for part in item.values())
            for item in value["matches"]
        ):
            raise ValueError("v2 runtime evidence matches are invalid")
        if type(value["references"]) is not list:
            raise ValueError("v2 runtime evidence references are invalid")
        references = tuple(
            BoundEvidenceReferenceV2(
                rule_ref=item["rule_ref"],
                claim_ref=item["claim_ref"],
                source_refs=tuple(item["source_refs"]),
            )
            for item in value["references"]
            if type(item) is dict
            and set(item) == {"rule_ref", "claim_ref", "source_refs"}
            and type(item["source_refs"]) is list
        )
        if len(references) != len(value["references"]):
            raise ValueError("v2 runtime evidence reference schema mismatch")
        return cls(
            evaluation_state=value["evaluation_state"],
            verdict=value["verdict"],
            decisive_ref=value["decisive_ref"],
            matches=tuple(
                (item["rule_ref"], item["verdict"], item["source_ref"])
                for item in value["matches"]
            ),
            stable_error_code=value["stable_error_code"],
            technical_result_sha256=value["technical_result_sha256"],
            evidence_binding_state=EvidenceRuntimeBindingState(
                value["evidence_binding_state"]
            ),
            ruleset_snapshot_id=value["ruleset_snapshot_id"],
            ruleset_content_sha256=value["ruleset_content_sha256"],
            evidence_snapshot_id=value["evidence_snapshot_id"],
            evidence_content_sha256=value["evidence_content_sha256"],
            references=references,
            result_sha256=value["result_sha256"],
        )


def _result_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")
    return hashlib.sha256(_RESULT_DOMAIN_V2 + encoded).hexdigest()


def _build_result(**values: Any) -> EvidenceRuntimeEvaluationV2:
    payload = {
        "decisive_ref": values["decisive_ref"],
        "evaluation_state": values["evaluation_state"],
        "evidence_binding_state": values["evidence_binding_state"].value,
        "evidence_content_sha256": values["evidence_content_sha256"],
        "evidence_snapshot_id": values["evidence_snapshot_id"],
        "matches": [
            {"rule_ref": rule_ref, "source_ref": source_ref, "verdict": verdict}
            for rule_ref, verdict, source_ref in values["matches"]
        ],
        "positive_statement_allowed": False,
        "references": [
            {
                "claim_ref": ref.claim_ref,
                "rule_ref": ref.rule_ref,
                "source_refs": list(ref.source_refs),
            }
            for ref in values["references"]
        ],
        "ruleset_content_sha256": values["ruleset_content_sha256"],
        "ruleset_snapshot_id": values["ruleset_snapshot_id"],
        "stable_error_code": values["stable_error_code"],
        "technical_result_sha256": values["technical_result_sha256"],
        "verdict": values["verdict"],
    }
    return EvidenceRuntimeEvaluationV2(**values, result_sha256=_result_hash(payload))


def evaluate_with_evidence_v2(
    *,
    pin: EvidenceRuntimePinV2,
    ruleset: MaterialRulesetSnapshotV1,
    evidence: EvidenceManifestSnapshotV2 | None,
    material_input: ShadowMaterialInput,
) -> EvidenceRuntimeEvaluationV2:
    try:
        resolved = validate_runtime_binding_v2(
            pin.binding, ruleset=ruleset, evidence=evidence
        )
        if (
            material_input.domain_pack_id != pin.binding.domain_pack_id
            or material_input.domain_pack_version != pin.binding.domain_pack_version
        ):
            raise MaterialEvidenceRuntimeIntegrityError(
                MaterialEvidenceRuntimeErrorCode.DOMAIN_PACK_MISMATCH,
                "material input and v2 runtime evidence domain packs differ",
            )
        technical = validate_cache_value(evaluate_snapshot(ruleset, material_input))
    except MaterialEvidenceRuntimeIntegrityError as exc:
        return integrity_blocked_evaluation_v2(pin, exc.code)
    except Exception:
        return integrity_blocked_evaluation_v2(
            pin, MaterialEvidenceRuntimeErrorCode.INTERNAL
        )
    matches = tuple(
        (item["rule_ref"], item["verdict"], item["source_ref"])
        for item in technical["matches"]
    )
    references = resolved.for_rules(tuple(item[0] for item in matches))
    return _build_result(
        evaluation_state=technical["evaluation_state"],
        verdict=technical["verdict"],
        decisive_ref=technical["decisive_ref"],
        matches=matches,
        stable_error_code="none",
        technical_result_sha256=technical["result_sha256"],
        evidence_binding_state=pin.state,
        ruleset_snapshot_id=pin.binding.ruleset_snapshot_id,
        ruleset_content_sha256=pin.binding.ruleset_content_sha256,
        evidence_snapshot_id=pin.binding.evidence_snapshot_id,
        evidence_content_sha256=pin.binding.evidence_content_sha256,
        references=references,
    )


def integrity_blocked_evaluation_v2(
    pin: EvidenceRuntimePinV2, code: MaterialEvidenceRuntimeErrorCode
) -> EvidenceRuntimeEvaluationV2:
    if type(pin) is not EvidenceRuntimePinV2:
        raise TypeError("pin must be EvidenceRuntimePinV2")
    if type(code) is not MaterialEvidenceRuntimeErrorCode:
        raise TypeError("code must be MaterialEvidenceRuntimeErrorCode")
    return _build_result(
        evaluation_state="integrity_blocked",
        verdict=None,
        decisive_ref=None,
        matches=(),
        stable_error_code=code.value,
        technical_result_sha256=None,
        evidence_binding_state=pin.state,
        ruleset_snapshot_id=pin.binding.ruleset_snapshot_id,
        ruleset_content_sha256=pin.binding.ruleset_content_sha256,
        evidence_snapshot_id=pin.binding.evidence_snapshot_id,
        evidence_content_sha256=pin.binding.evidence_content_sha256,
        references=(),
    )


__all__ = [
    "EvidenceRuntimeEvaluationV2",
    "evaluate_with_evidence_v2",
    "integrity_blocked_evaluation_v2",
]
