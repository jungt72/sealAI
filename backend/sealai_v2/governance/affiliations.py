"""Versioned affiliation snapshots and fail-closed conflict resolution.

Affiliations come only from a separately governed human authority register.
JWT organization claims, request bodies, and reviewer attestations are not
authority. Every accepted decision binds immutable before/after snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Iterable

AFFILIATION_CONTRACT_VERSION = "sealai.affiliation-authority.1"
ALLOWED_AUTHORITY_SOURCES = frozenset(
    {
        "owner_attested_identity_roster",
        "independent_hr_register",
        "contractual_affiliation_register",
    }
)
ALLOWED_RELATIONSHIPS = frozenset(
    {
        "employee",
        "owner",
        "board_member",
        "contractor",
        "advisor",
        "auditor",
    }
)
ALLOWED_STATUSES = frozenset({"active", "revoked", "quarantined"})
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}")
_SNAPSHOT_FIELDS = {
    "schema_version",
    "authority_contract_version",
    "subject_ref",
    "captured_at",
    "purpose",
    "resource_type",
    "resource_ref",
    "resource_version",
    "roles",
    "affiliations",
}
_SNAPSHOT_AFFILIATION_FIELDS = {
    "record_id",
    "record_revision",
    "record_sha256",
    "organization_ref",
    "relationship",
    "authority_source",
    "authority_reference",
    "authority_version",
    "effective_from",
    "effective_to",
}


class AffiliationGovernanceError(RuntimeError):
    pass


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return sha256(_canonical_json(value).encode("ascii")).hexdigest()


def _timestamp(value: str, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise AffiliationGovernanceError(f"invalid {field} timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AffiliationGovernanceError(f"invalid {field} timestamp") from exc
    if parsed.tzinfo is None:
        raise AffiliationGovernanceError(f"{field} must include a timezone")
    return parsed


@dataclass(frozen=True)
class AffiliationRecord:
    record_id: str
    subject_ref: str
    organization_ref: str
    relationship: str
    authority_source: str
    authority_reference: str
    authority_version: str
    effective_from: str
    effective_to: str
    status: str
    revision: int
    recorded_at: str
    recorded_by: str
    record_sha256: str

    def contract(self) -> dict:
        return {
            "schema_version": 1,
            "record_id": self.record_id,
            "subject_ref": self.subject_ref,
            "organization_ref": self.organization_ref,
            "relationship": self.relationship,
            "authority_source": self.authority_source,
            "authority_reference": self.authority_reference,
            "authority_version": self.authority_version,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "status": self.status,
            "revision": self.revision,
            "recorded_at": self.recorded_at,
            "recorded_by": self.recorded_by,
        }


def affiliation_record_sha256(**fields) -> str:
    record = AffiliationRecord(record_sha256="", **fields)
    return _digest(record.contract())


def build_affiliation_record(**fields) -> AffiliationRecord:
    return AffiliationRecord(
        **fields,
        record_sha256=affiliation_record_sha256(**fields),
    )


def validate_affiliation_record(record: AffiliationRecord) -> None:
    string_limits = {
        "record_id": 64,
        "subject_ref": 255,
        "organization_ref": 255,
        "relationship": 32,
        "authority_source": 64,
        "authority_reference": 255,
        "authority_version": 64,
        "effective_from": 32,
        "effective_to": 32,
        "status": 32,
        "recorded_at": 32,
        "recorded_by": 255,
        "record_sha256": 64,
    }
    if any(
        not isinstance(getattr(record, field), str)
        or len(getattr(record, field)) > maximum
        for field, maximum in string_limits.items()
    ):
        raise AffiliationGovernanceError("affiliation record types are invalid")
    if not isinstance(record.revision, int) or isinstance(record.revision, bool):
        raise AffiliationGovernanceError("affiliation revision must be an integer")
    if _HEX_SHA256.fullmatch(record.record_id) is None:
        raise AffiliationGovernanceError("invalid affiliation record id")
    if not record.subject_ref.strip() or not record.organization_ref.strip():
        raise AffiliationGovernanceError(
            "affiliation subject and organization are required"
        )
    if record.status not in ALLOWED_STATUSES:
        raise AffiliationGovernanceError("invalid affiliation status")
    if record.relationship not in ALLOWED_RELATIONSHIPS:
        raise AffiliationGovernanceError("invalid affiliation relationship")
    if record.authority_source not in ALLOWED_AUTHORITY_SOURCES:
        raise AffiliationGovernanceError("untrusted affiliation authority source")
    if not record.authority_reference.strip() or not record.authority_version.strip():
        raise AffiliationGovernanceError(
            "affiliation authority reference is incomplete"
        )
    if not record.recorded_by.strip() or record.recorded_by == record.subject_ref:
        raise AffiliationGovernanceError(
            "affiliation authority must be recorded by a separate human"
        )
    if record.revision < 1:
        raise AffiliationGovernanceError("affiliation revision must be positive")
    if record.record_sha256 != _digest(record.contract()):
        raise AffiliationGovernanceError("affiliation record integrity mismatch")
    starts = _timestamp(record.effective_from, field="affiliation effective_from")
    ends = (
        _timestamp(record.effective_to, field="affiliation effective_to")
        if record.effective_to
        else None
    )
    _timestamp(record.recorded_at, field="affiliation recorded_at")
    if ends is not None and ends <= starts:
        raise AffiliationGovernanceError("affiliation validity interval is invalid")


@dataclass(frozen=True)
class AffiliationSnapshot:
    subject_ref: str
    captured_at: str
    purpose: str
    resource_type: str
    resource_ref: str
    resource_version: int
    roles: tuple[str, ...]
    affiliations: tuple[dict, ...]
    authority_contract_version: str = AFFILIATION_CONTRACT_VERSION

    def contract(self) -> dict:
        return {
            "schema_version": 1,
            "authority_contract_version": self.authority_contract_version,
            "subject_ref": self.subject_ref,
            "captured_at": self.captured_at,
            "purpose": self.purpose,
            "resource_type": self.resource_type,
            "resource_ref": self.resource_ref,
            "resource_version": self.resource_version,
            "roles": list(self.roles),
            "affiliations": [dict(item) for item in self.affiliations],
        }

    @property
    def snapshot_sha256(self) -> str:
        return _digest(self.contract())

    @property
    def organization_refs(self) -> frozenset[str]:
        return frozenset(str(item["organization_ref"]) for item in self.affiliations)


def affiliation_snapshot_from_contract(contract: dict) -> AffiliationSnapshot:
    if set(contract) != _SNAPSHOT_FIELDS or contract.get("schema_version") != 1:
        raise AffiliationGovernanceError("unsupported affiliation snapshot schema")
    resource_version = contract.get("resource_version")
    roles = contract.get("roles")
    affiliations = contract.get("affiliations")
    snapshot_string_fields = (
        "authority_contract_version",
        "subject_ref",
        "captured_at",
        "purpose",
        "resource_type",
        "resource_ref",
    )
    if (
        not isinstance(resource_version, int)
        or isinstance(resource_version, bool)
        or any(
            not isinstance(contract.get(field), str) for field in snapshot_string_fields
        )
        or not isinstance(roles, list)
        or any(not isinstance(item, str) for item in roles)
        or not isinstance(affiliations, list)
        or any(not isinstance(item, dict) for item in affiliations)
    ):
        raise AffiliationGovernanceError(
            "stored affiliation snapshot types are invalid"
        )
    snapshot = AffiliationSnapshot(
        authority_contract_version=str(contract.get("authority_contract_version", "")),
        subject_ref=str(contract.get("subject_ref", "")),
        captured_at=str(contract.get("captured_at", "")),
        purpose=str(contract.get("purpose", "")),
        resource_type=str(contract.get("resource_type", "")),
        resource_ref=str(contract.get("resource_ref", "")),
        resource_version=resource_version,
        roles=tuple(roles),
        affiliations=tuple(dict(item) for item in affiliations),
    )
    if snapshot.authority_contract_version != AFFILIATION_CONTRACT_VERSION:
        raise AffiliationGovernanceError("unsupported affiliation authority contract")
    if (
        not snapshot.subject_ref
        or not snapshot.purpose
        or not snapshot.resource_type
        or not snapshot.resource_ref
        or snapshot.resource_version < 1
        or not snapshot.roles
        or not snapshot.affiliations
    ):
        raise AffiliationGovernanceError("stored affiliation snapshot is incomplete")
    _timestamp(snapshot.captured_at, field="snapshot")
    if tuple(sorted(set(snapshot.roles))) != snapshot.roles or any(
        not role.strip() for role in snapshot.roles
    ):
        raise AffiliationGovernanceError(
            "stored affiliation snapshot roles are invalid"
        )
    for affiliation in snapshot.affiliations:
        if set(affiliation) != _SNAPSHOT_AFFILIATION_FIELDS:
            raise AffiliationGovernanceError(
                "stored affiliation snapshot record is malformed"
            )
        record_revision = affiliation["record_revision"]
        string_fields = _SNAPSHOT_AFFILIATION_FIELDS - {"record_revision"}
        if (
            any(not isinstance(affiliation[field], str) for field in string_fields)
            or not str(affiliation["organization_ref"]).strip()
            or str(affiliation["relationship"]) not in ALLOWED_RELATIONSHIPS
            or str(affiliation["authority_source"]) not in ALLOWED_AUTHORITY_SOURCES
            or not str(affiliation["authority_reference"]).strip()
            or not str(affiliation["authority_version"]).strip()
            or not isinstance(record_revision, int)
            or isinstance(record_revision, bool)
            or record_revision < 1
            or _HEX_SHA256.fullmatch(str(affiliation["record_id"])) is None
            or _HEX_SHA256.fullmatch(str(affiliation["record_sha256"])) is None
        ):
            raise AffiliationGovernanceError(
                "stored affiliation snapshot record is invalid"
            )
        starts = _timestamp(
            str(affiliation["effective_from"]),
            field="snapshot affiliation effective_from",
        )
        if affiliation["effective_to"]:
            ends = _timestamp(
                str(affiliation["effective_to"]),
                field="snapshot affiliation effective_to",
            )
            if ends <= starts:
                raise AffiliationGovernanceError(
                    "stored affiliation snapshot validity interval is invalid"
                )
    return snapshot


@dataclass(frozen=True)
class ConflictResolution:
    outcome: str
    reason_code: str
    first_snapshot_sha256: str
    second_snapshot_sha256: str
    shared_organization_sha256: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return self.outcome == "allow"

    def contract(self) -> dict:
        return {
            "schema_version": 1,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "first_snapshot_sha256": self.first_snapshot_sha256,
            "second_snapshot_sha256": self.second_snapshot_sha256,
            "shared_organization_sha256": list(self.shared_organization_sha256),
        }

    @property
    def decision_sha256(self) -> str:
        return _digest(self.contract())


def capture_affiliation_snapshot(
    records: Iterable[AffiliationRecord],
    *,
    subject_ref: str,
    roles: Iterable[str],
    captured_at: str,
    purpose: str,
    resource_type: str,
    resource_ref: str,
    resource_version: int,
    expected_organization: str = "",
) -> AffiliationSnapshot:
    subject = subject_ref.strip()
    if not subject:
        raise AffiliationGovernanceError("affiliation subject is required")
    instant = _timestamp(captured_at, field="snapshot")
    if not purpose.strip() or not resource_type.strip() or not resource_ref.strip():
        raise AffiliationGovernanceError("snapshot resource binding is incomplete")
    if resource_version < 1:
        raise AffiliationGovernanceError("snapshot resource version must be positive")

    latest: dict[tuple[str, str], AffiliationRecord] = {}
    for record in records:
        if record.subject_ref != subject:
            raise AffiliationGovernanceError("cross-subject affiliation record")
        validate_affiliation_record(record)
        recorded = _timestamp(record.recorded_at, field="affiliation recorded_at")
        if recorded > instant:
            raise AffiliationGovernanceError(
                "affiliation was not yet recorded at snapshot time"
            )
        starts = _timestamp(record.effective_from, field="affiliation effective_from")
        if starts > instant:
            continue
        key = (record.organization_ref, record.relationship)
        prior = latest.get(key)
        if prior is None or record.revision > prior.revision:
            latest[key] = record
        elif record.revision == prior.revision and record.record_id != prior.record_id:
            raise AffiliationGovernanceError("ambiguous affiliation revision")

    active = {
        key: record
        for key, record in latest.items()
        if record.status == "active"
        and (
            not record.effective_to
            or _timestamp(record.effective_to, field="affiliation effective_to")
            > instant
        )
    }
    if not active:
        raise AffiliationGovernanceError(
            "no current human-authoritative affiliation is available"
        )
    if expected_organization and expected_organization not in {
        record.organization_ref for record in active.values()
    }:
        raise AffiliationGovernanceError(
            "subject is not authoritatively affiliated with the governed organization"
        )

    affiliations = tuple(
        {
            "record_id": record.record_id,
            "record_revision": record.revision,
            "record_sha256": record.record_sha256,
            "organization_ref": record.organization_ref,
            "relationship": record.relationship,
            "authority_source": record.authority_source,
            "authority_reference": record.authority_reference,
            "authority_version": record.authority_version,
            "effective_from": record.effective_from,
            "effective_to": record.effective_to,
        }
        for record in sorted(
            active.values(),
            key=lambda item: (
                item.organization_ref,
                item.relationship,
                item.revision,
            ),
        )
    )
    return AffiliationSnapshot(
        subject_ref=subject,
        captured_at=captured_at,
        purpose=purpose,
        resource_type=resource_type,
        resource_ref=resource_ref,
        resource_version=resource_version,
        roles=tuple(sorted({str(role).strip() for role in roles if str(role).strip()})),
        affiliations=affiliations,
    )


def require_governed_role(
    snapshot: AffiliationSnapshot,
    *,
    required_role: str,
    incompatible_roles: Iterable[str],
) -> None:
    roles = set(snapshot.roles)
    if required_role not in roles:
        raise AffiliationGovernanceError("required governance role is absent")
    overlap = roles & set(incompatible_roles)
    if overlap:
        raise AffiliationGovernanceError(
            "governance actor holds an incompatible authority role"
        )


def resolve_independence(
    first: AffiliationSnapshot,
    second: AffiliationSnapshot,
    *,
    required_second_role: str,
    incompatible_second_roles: Iterable[str],
) -> ConflictResolution:
    first_hash = first.snapshot_sha256
    second_hash = second.snapshot_sha256
    if first.authority_contract_version != second.authority_contract_version:
        return ConflictResolution(
            "block", "authority_contract_mismatch", first_hash, second_hash
        )
    if first.subject_ref == second.subject_ref:
        return ConflictResolution("block", "self_review", first_hash, second_hash)
    try:
        require_governed_role(
            second,
            required_role=required_second_role,
            incompatible_roles=incompatible_second_roles,
        )
    except AffiliationGovernanceError as exc:
        reason = (
            "required_role_missing"
            if "required governance role" in str(exc)
            else "incompatible_role_overlap"
        )
        return ConflictResolution("block", reason, first_hash, second_hash)
    shared = first.organization_refs & second.organization_refs
    if shared:
        return ConflictResolution(
            "block",
            "shared_affiliation",
            first_hash,
            second_hash,
            tuple(sorted(_digest({"organization_ref": value}) for value in shared)),
        )
    return ConflictResolution("allow", "no_shared_affiliation", first_hash, second_hash)
