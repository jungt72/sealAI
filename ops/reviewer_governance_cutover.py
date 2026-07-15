#!/usr/bin/env python3
"""GATE-07-bound affiliation import and legacy quarantine tooling.

Dry-run is the default. Apply is append-only, requires an exact dry-run input
hash plus an explicit GATE-07 marker, and never activates a feature or changes
Keycloak. Receipts contain counts and hashes only.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import sys

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sealai_v2.db.engine import make_engine, make_sessionmaker  # noqa: E402
from sealai_v2.db.models import (  # noqa: E402
    V2GovernanceDecision,
    V2GovernanceQuarantine,
    V2IdentityAffiliationRevision,
    V2KnowledgeClaim,
    V2ManufacturerCapabilityProfile,
)
from sealai_v2.governance.affiliations import (  # noqa: E402
    AffiliationGovernanceError,
    AffiliationRecord,
    validate_affiliation_record,
)


class CutoverError(RuntimeError):
    pass


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("ascii")


def _digest(value: object) -> str:
    return sha256(_canonical(value)).hexdigest()


def _fingerprint(value: object, *, key: bytes) -> str:
    if len(key) < 32:
        raise CutoverError("governance fingerprint key must be at least 32 bytes")
    return hmac.new(key, _canonical(value), sha256).hexdigest()


def _require_timestamp(value: str, *, field: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CutoverError(f"invalid {field} timestamp") from exc
    if parsed.tzinfo is None:
        raise CutoverError(f"{field} must include a timezone")


_RECORD_FIELDS = {
    "record_id",
    "subject_ref",
    "organization_ref",
    "relationship",
    "authority_source",
    "authority_reference",
    "authority_version",
    "effective_from",
    "effective_to",
    "status",
    "revision",
    "recorded_at",
    "recorded_by",
    "record_sha256",
}


def load_authority_bundle(path: Path) -> tuple[dict, tuple[AffiliationRecord, ...]]:
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CutoverError("authority bundle is unreadable or invalid") from exc
    if not isinstance(bundle, dict) or set(bundle) != {
        "schema_version",
        "contract_id",
        "authority_version",
        "approved_at",
        "approved_by",
        "records",
    }:
        raise CutoverError("authority bundle fields do not match schema v1")
    if (
        not isinstance(bundle["schema_version"], int)
        or isinstance(bundle["schema_version"], bool)
        or bundle["schema_version"] != 1
        or bundle["contract_id"] != ("sealai.affiliation-authority-import")
    ):
        raise CutoverError("unsupported authority bundle contract")
    if (
        not isinstance(bundle["authority_version"], str)
        or not bundle["authority_version"].strip()
        or len(bundle["authority_version"]) > 64
    ):
        raise CutoverError("authority bundle version is required")
    if (
        not isinstance(bundle["approved_by"], str)
        or not bundle["approved_by"].strip()
        or len(bundle["approved_by"]) > 255
        or not isinstance(bundle["approved_at"], str)
        or not bundle["approved_at"].strip()
        or len(bundle["approved_at"]) > 32
    ):
        raise CutoverError("human authority approval metadata is required")
    _require_timestamp(bundle["approved_at"], field="authority approval")
    raw_records = bundle["records"]
    if not isinstance(raw_records, list) or not 1 <= len(raw_records) <= 10000:
        raise CutoverError("authority bundle record count is outside bounds")
    records: list[AffiliationRecord] = []
    identities: set[str] = set()
    revisions: set[tuple[str, str, str, int]] = set()
    try:
        for raw in raw_records:
            if not isinstance(raw, dict) or set(raw) != _RECORD_FIELDS:
                raise CutoverError("authority record fields do not match schema v1")
            record = AffiliationRecord(**raw)
            validate_affiliation_record(record)
            if record.authority_version != bundle["authority_version"]:
                raise CutoverError("record authority version does not match bundle")
            if record.recorded_by != bundle["approved_by"]:
                raise CutoverError("record authority does not match human approver")
            if record.record_id in identities:
                raise CutoverError("duplicate affiliation record id")
            identities.add(record.record_id)
            revision_key = (
                record.subject_ref,
                record.organization_ref,
                record.relationship,
                record.revision,
            )
            if revision_key in revisions:
                raise CutoverError("duplicate affiliation revision")
            revisions.add(revision_key)
            records.append(record)
    except (AffiliationGovernanceError, TypeError, ValueError) as exc:
        if isinstance(exc, CutoverError):
            raise
        raise CutoverError("authority record failed governance validation") from exc
    return bundle, tuple(records)


def _row_contract(row: V2IdentityAffiliationRevision) -> dict:
    return {
        "record_id": row.id,
        "subject_ref": row.subject_ref,
        "organization_ref": row.organization_ref,
        "relationship": row.relationship,
        "authority_source": row.authority_source,
        "authority_reference": row.authority_reference,
        "authority_version": row.authority_version,
        "effective_from": row.effective_from,
        "effective_to": row.effective_to or "",
        "status": row.status,
        "revision": row.revision,
        "recorded_at": row.recorded_at,
        "recorded_by": row.recorded_by,
        "record_sha256": row.record_sha256,
    }


def apply_authority_bundle(
    session_factory, records: tuple[AffiliationRecord, ...]
) -> int:
    inserted = 0
    with session_factory() as session:
        existing_rows = {
            row.id: row
            for row in session.scalars(
                select(V2IdentityAffiliationRevision)
                .where(
                    V2IdentityAffiliationRevision.id.in_(
                        [record.record_id for record in records]
                    )
                )
                .with_for_update()
            ).all()
        }
        for record in records:
            existing = existing_rows.get(record.record_id)
            if existing is not None:
                expected = {
                    key: value
                    for key, value in record.contract().items()
                    if key != "schema_version"
                }
                expected["record_sha256"] = record.record_sha256
                if _row_contract(existing) != expected:
                    raise CutoverError(
                        "existing affiliation record differs from bundle"
                    )
                continue
            session.add(
                V2IdentityAffiliationRevision(
                    id=record.record_id,
                    subject_ref=record.subject_ref,
                    organization_ref=record.organization_ref,
                    relationship=record.relationship,
                    authority_source=record.authority_source,
                    authority_reference=record.authority_reference,
                    authority_version=record.authority_version,
                    effective_from=record.effective_from,
                    effective_to=record.effective_to or None,
                    status=record.status,
                    revision=record.revision,
                    recorded_at=record.recorded_at,
                    recorded_by=record.recorded_by,
                    record_sha256=record.record_sha256,
                )
            )
            inserted += 1
        session.commit()
    return inserted


@dataclass(frozen=True)
class QuarantineCandidate:
    resource_type: str
    record_fingerprint: str
    reason_code: str

    def contract(self) -> dict:
        return {
            "resource_type": self.resource_type,
            "record_fingerprint": self.record_fingerprint,
            "reason_code": self.reason_code,
        }


def profile_legacy_governance(
    session_factory, *, fingerprint_key: bytes
) -> tuple[QuarantineCandidate, ...]:
    candidates: list[QuarantineCandidate] = []
    with session_factory() as session:
        allowed = {
            (
                row.decision_type,
                row.resource_type,
                row.resource_ref,
                row.resource_version,
                str((row.decision_json or {}).get("binding_sha256", "")),
            )
            for row in session.scalars(
                select(V2GovernanceDecision).where(
                    V2GovernanceDecision.outcome == "allow"
                )
            ).all()
        }
        profiles = session.scalars(
            select(V2ManufacturerCapabilityProfile).where(
                V2ManufacturerCapabilityProfile.status == "verified"
            )
        ).all()
        for row in profiles:
            if (
                "capability_verification",
                "manufacturer_capability",
                row.manufacturer_id,
                row.version,
                "",
            ) in allowed:
                continue
            candidates.append(
                QuarantineCandidate(
                    resource_type="manufacturer_capability",
                    record_fingerprint=_fingerprint(
                        {
                            "resource_type": "manufacturer_capability",
                            "resource_ref": row.manufacturer_id,
                            "resource_version": row.version,
                            "status": row.status,
                        },
                        key=fingerprint_key,
                    ),
                    reason_code="verified_without_server_coi_snapshot",
                )
            )
        claims = session.scalars(
            select(V2KnowledgeClaim).where(
                V2KnowledgeClaim.review_status == "approved",
                V2KnowledgeClaim.review_origin == "human_api",
            )
        ).all()
        allowed_claims = {
            (resource_ref, version, binding_sha256)
            for (
                decision_type,
                resource_type,
                resource_ref,
                version,
                binding_sha256,
            ) in allowed
            if decision_type == "knowledge_approval"
            and resource_type == "knowledge_claim"
        }
        for row in claims:
            if (row.id, row.version, row.authority_fingerprint) in allowed_claims:
                continue
            candidates.append(
                QuarantineCandidate(
                    resource_type="knowledge_claim",
                    record_fingerprint=_fingerprint(
                        {
                            "resource_type": "knowledge_claim",
                            "resource_ref": row.id,
                            "authority_fingerprint": row.authority_fingerprint,
                            "review_status": row.review_status,
                        },
                        key=fingerprint_key,
                    ),
                    reason_code="approved_without_server_coi_snapshot",
                )
            )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.resource_type,
                item.reason_code,
                item.record_fingerprint,
            ),
        )
    )


def apply_quarantine(
    session_factory, candidates: tuple[QuarantineCandidate, ...], *, now: str
) -> int:
    inserted = 0
    with session_factory() as session:
        for candidate in candidates:
            existing = session.scalar(
                select(V2GovernanceQuarantine)
                .where(
                    V2GovernanceQuarantine.resource_type == candidate.resource_type,
                    V2GovernanceQuarantine.record_fingerprint
                    == candidate.record_fingerprint,
                    V2GovernanceQuarantine.reason_code == candidate.reason_code,
                )
                .with_for_update()
            )
            if existing is not None:
                continue
            session.add(
                V2GovernanceQuarantine(
                    resource_type=candidate.resource_type,
                    record_fingerprint=candidate.record_fingerprint,
                    reason_code=candidate.reason_code,
                    detected_at=now,
                    resolution_status="unresolved",
                    resolution_note="",
                )
            )
            inserted += 1
        session.commit()
    return inserted


def _args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("authority", "quarantine"))
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-input-sha256")
    parser.add_argument("--confirm-gate", choices=("GATE-07",))
    parser.add_argument("--detected-at")
    return parser.parse_args(argv)


def _session_factory():
    database_url = os.environ.get("SEALAI_V2_DATABASE_URL", "")
    if not database_url:
        raise CutoverError("SEALAI_V2_DATABASE_URL is required for database access")
    return make_sessionmaker(make_engine(database_url))


def _fingerprint_key() -> bytes:
    value = os.environ.get("SEALAI_GOVERNANCE_FINGERPRINT_KEY", "")
    key = value.encode("utf-8")
    if len(key) < 32:
        raise CutoverError(
            "SEALAI_GOVERNANCE_FINGERPRINT_KEY must contain at least 32 bytes"
        )
    return key


def main(argv: list[str] | None = None) -> int:
    args = _args(argv)
    try:
        if args.apply and (
            args.confirm_gate != "GATE-07" or not args.expected_input_sha256
        ):
            raise CutoverError(
                "--apply requires --confirm-gate GATE-07 and --expected-input-sha256"
            )
        if args.apply and args.mode == "quarantine":
            if not args.detected_at:
                raise CutoverError("quarantine apply requires --detected-at")
            _require_timestamp(args.detected_at, field="quarantine detection")
        if args.mode == "authority":
            if args.bundle is None:
                raise CutoverError("authority mode requires --bundle")
            bundle, records = load_authority_bundle(args.bundle)
            input_sha256 = _digest(bundle)
            if (
                args.expected_input_sha256
                and args.expected_input_sha256 != input_sha256
            ):
                raise CutoverError("authority bundle hash differs from approved input")
            inserted = (
                apply_authority_bundle(_session_factory(), records) if args.apply else 0
            )
            receipt = {
                "schema_version": 1,
                "mode": "apply" if args.apply else "dry-run",
                "operation": "authority_import",
                "input_sha256": input_sha256,
                "authority_version_sha256": _digest(
                    {"authority_version": bundle["authority_version"]}
                ),
                "record_count": len(records),
                "status_counts": dict(
                    sorted(Counter(row.status for row in records).items())
                ),
                "inserted_count": inserted,
                "feature_activation_changed": False,
            }
        else:
            fingerprint_key = _fingerprint_key()
            candidates = profile_legacy_governance(
                _session_factory(), fingerprint_key=fingerprint_key
            )
            input_sha256 = _digest([item.contract() for item in candidates])
            if (
                args.expected_input_sha256
                and args.expected_input_sha256 != input_sha256
            ):
                raise CutoverError(
                    "quarantine profile hash differs from approved input"
                )
            inserted = (
                apply_quarantine(_session_factory(), candidates, now=args.detected_at)
                if args.apply
                else 0
            )
            receipt = {
                "schema_version": 1,
                "mode": "apply" if args.apply else "dry-run",
                "operation": "legacy_quarantine",
                "input_sha256": input_sha256,
                "candidate_count": len(candidates),
                "candidate_type_counts": dict(
                    sorted(Counter(item.resource_type for item in candidates).items())
                ),
                "inserted_count": inserted,
                "source_records_changed": False,
                "feature_activation_changed": False,
            }
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (CutoverError, OSError, ValueError) as exc:
        print(f"reviewer_governance_cutover: {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print("reviewer_governance_cutover: database operation failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
