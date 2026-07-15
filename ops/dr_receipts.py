#!/usr/bin/python3 -I
"""Verify and import externally signed disaster-recovery DSSE receipts.

This module deliberately contains no signing or private-key functionality.  A receipt is
authoritative only while its canonical payload satisfies the active trust policy and enough
role-bound Ed25519 signatures verify.  Imported records are re-verified on every consumption;
the local import metadata is never a replacement for the external signatures.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, NoReturn


SCHEMA_VERSION = 1
PAYLOAD_TYPE = "application/vnd.sealai.dr-receipt.v1+json"
MAX_JSON_BYTES = 256 * 1024
MAX_SIGNATURES = 32
MAX_KEYS = 64
MAX_CLOCK_SKEW_SECONDS = 300
MAX_POLICY_VALIDITY_SECONDS = 366 * 24 * 60 * 60
MAX_RECEIPT_AGE_SECONDS = 35 * 24 * 60 * 60
MAX_RECEIPT_VALIDITY_SECONDS = 35 * 24 * 60 * 60
TOKEN_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SAFE_BASENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")
ROLE_BY_KIND = {
    "offsite_backup": "offsite_attestor",
    "dr_offsite_set": "offsite_attestor",
    "restore_drill": "restore_attestor",
    "qdrant_rebuild_approval": "rebuild_approver",
}
STATUS_BY_KIND = {
    "offsite_backup": "OFFSITE_VERIFIED",
    "dr_offsite_set": "OFFSITE_VERIFIED",
    "restore_drill": "RESTORE_VERIFIED",
    "qdrant_rebuild_approval": "REBUILD_APPROVED",
}


class ReceiptError(RuntimeError):
    """A fail-closed result containing only a stable non-sensitive token."""

    def __init__(self, reason: str) -> None:
        safe = reason if TOKEN_RE.fullmatch(reason) else "receipt_error"
        super().__init__(safe)
        self.reason = safe


@dataclass(frozen=True)
class VerifiedReceipt:
    payload: dict[str, Any]
    envelope: dict[str, Any]
    receipt_id: str
    kind: str
    role: str
    verified_keyids: tuple[str, ...]
    envelope_sha256: str
    policy_sha256: str


def _fail(reason: str) -> NoReturn:
    raise ReceiptError(reason)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _canonical_json(value: Any) -> bytes:
    try:
        rendered = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ReceiptError("noncanonical_json_value") from exc
    return (rendered + "\n").encode("ascii")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("duplicate_json_key")
        result[key] = value
    return result


def _parse_json(raw: bytes, *, reason: str) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda _value: _fail(reason),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReceiptError(reason) from exc


def _verification_time(value: dt.datetime | None) -> dt.datetime:
    observed = _utc_now() if value is None else value
    if (
        not isinstance(observed, dt.datetime)
        or observed.tzinfo is None
        or observed.utcoffset() != dt.timedelta(0)
    ):
        _fail("invalid_verification_time")
    return observed


def _require_object(value: Any, keys: set[str], *, reason: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _fail(reason)
    return value


def _require_sha256(value: Any, *, reason: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        _fail(reason)
    return value


def _parse_time(value: Any, *, reason: str) -> dt.datetime:
    if not isinstance(value, str) or RFC3339_RE.fullmatch(value) is None:
        _fail(reason)
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc
        )
    except ValueError as exc:
        raise ReceiptError(reason) from exc


def _positive_int(value: Any, *, maximum: int, reason: str) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
        or value > maximum
    ):
        _fail(reason)
    return value


def _b64(value: Any, *, expected_bytes: int | None, reason: str) -> bytes:
    if not isinstance(value, str) or not value or len(value) > MAX_JSON_BYTES:
        _fail(reason)
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ReceiptError(reason) from exc
    if base64.b64encode(decoded).decode("ascii") != value:
        _fail(reason)
    if expected_bytes is not None and len(decoded) != expected_bytes:
        _fail(reason)
    return decoded


def _normalized_absolute(path: Path) -> Path:
    raw = str(path)
    if (
        not path.is_absolute()
        or raw != os.path.normpath(raw)
        or "//" in raw
        or any(part in {".", "..", "~"} or part.startswith("~") for part in path.parts)
    ):
        _fail("path_not_normalized_absolute")
    return path


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _same_inode(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_mode,
        left.st_nlink,
        left.st_uid,
        left.st_gid,
        left.st_size,
        left.st_mtime_ns,
        left.st_ctime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_mode,
        right.st_nlink,
        right.st_uid,
        right.st_gid,
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )


def _open_directory(
    path: Path, *, private_leaf: bool, create_leaf: bool = False
) -> int:
    """Walk an absolute directory using no-follow directory descriptors."""

    path = _normalized_absolute(path)
    descriptor = os.open(path.anchor, _directory_flags())
    try:
        for index, part in enumerate(path.parts[1:], start=1):
            final = index == len(path.parts) - 1
            try:
                next_descriptor = os.open(part, _directory_flags(), dir_fd=descriptor)
            except FileNotFoundError:
                if not (final and create_leaf):
                    raise ReceiptError("directory_unavailable") from None
                try:
                    os.mkdir(part, 0o700, dir_fd=descriptor)
                    next_descriptor = os.open(
                        part, _directory_flags(), dir_fd=descriptor
                    )
                except OSError as exc:
                    raise ReceiptError("directory_unavailable") from exc
            except OSError as exc:
                raise ReceiptError("directory_unsafe") from exc
            os.close(descriptor)
            descriptor = next_descriptor
        metadata = os.fstat(descriptor)
        try:
            path_metadata = path.lstat()
        except OSError as exc:
            raise ReceiptError("directory_changed") from exc
        if not stat.S_ISDIR(metadata.st_mode) or not _same_inode(
            metadata, path_metadata
        ):
            _fail("directory_unsafe")
        if private_leaf and (
            metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            _fail("directory_not_private")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _read_bound_file(
    path: Path,
    *,
    private: bool,
    maximum_bytes: int = MAX_JSON_BYTES,
    reason: str,
) -> bytes:
    path = _normalized_absolute(path)
    parent_fd = _open_directory(path.parent, private_leaf=False)
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path.name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise ReceiptError(reason) from exc
        before = os.fstat(descriptor)
        path_state = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        mode = stat.S_IMODE(before.st_mode)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid not in ({os.geteuid()} if private else {0, os.geteuid()})
            or before.st_nlink != 1
            or mode & 0o022
            or (private and mode not in {0o400, 0o600})
            or before.st_size <= 0
            or before.st_size > maximum_bytes
            or not _same_file(before, path_state)
        ):
            _fail(reason)
        remaining = before.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                _fail(reason)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail(reason)
        after = os.fstat(descriptor)
        final_path_state = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if not _same_file(before, after) or not _same_file(after, final_path_state):
            _fail("file_changed_during_read")
        return b"".join(chunks)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def _read_json_file(path: Path, *, private: bool, reason: str) -> Any:
    return _parse_json(
        _read_bound_file(path, private=private, reason=reason), reason=reason
    )


def _validate_policy(
    value: Any, *, now: dt.datetime
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    policy = _require_object(
        value,
        {
            "schema_version",
            "policy_id",
            "valid_from",
            "expires_at",
            "max_receipt_age_seconds",
            "max_receipt_validity_seconds",
            "keys",
            "roles",
        },
        reason="invalid_trust_policy_schema",
    )
    if policy["schema_version"] != SCHEMA_VERSION:
        _fail("invalid_trust_policy_version")
    _require_sha256(policy["policy_id"], reason="invalid_trust_policy_id")
    valid_from = _parse_time(policy["valid_from"], reason="invalid_policy_time")
    expires_at = _parse_time(policy["expires_at"], reason="invalid_policy_time")
    if (
        expires_at <= valid_from
        or (expires_at - valid_from).total_seconds() > MAX_POLICY_VALIDITY_SECONDS
        or now < valid_from - dt.timedelta(seconds=MAX_CLOCK_SKEW_SECONDS)
        or now > expires_at
    ):
        _fail("trust_policy_expired")
    _positive_int(
        policy["max_receipt_age_seconds"],
        maximum=MAX_RECEIPT_AGE_SECONDS,
        reason="invalid_receipt_age_policy",
    )
    _positive_int(
        policy["max_receipt_validity_seconds"],
        maximum=MAX_RECEIPT_VALIDITY_SECONDS,
        reason="invalid_receipt_validity_policy",
    )
    keys_value = policy["keys"]
    if not isinstance(keys_value, list) or not keys_value or len(keys_value) > MAX_KEYS:
        _fail("invalid_trust_keys")
    keys: dict[str, dict[str, Any]] = {}
    for item in keys_value:
        key = _require_object(
            item,
            {"keyid", "algorithm", "public_key_base64", "not_before", "not_after"},
            reason="invalid_trust_key",
        )
        keyid = _require_sha256(key["keyid"], reason="invalid_trust_key_id")
        if keyid in keys or key["algorithm"] != "ed25519":
            _fail("invalid_trust_key")
        public = _b64(
            key["public_key_base64"], expected_bytes=32, reason="invalid_public_key"
        )
        if hashlib.sha256(public).hexdigest() != keyid:
            _fail("public_key_id_mismatch")
        not_before = _parse_time(key["not_before"], reason="invalid_key_time")
        not_after = _parse_time(key["not_after"], reason="invalid_key_time")
        if not_after <= not_before:
            _fail("invalid_key_time")
        keys[keyid] = {**key, "public_key": public, "from": not_before, "to": not_after}
    roles_value = policy["roles"]
    if not isinstance(roles_value, dict) or not roles_value:
        _fail("invalid_trust_roles")
    roles: dict[str, dict[str, Any]] = {}
    for role_name, raw_role in roles_value.items():
        if role_name not in set(ROLE_BY_KIND.values()):
            _fail("invalid_trust_role")
        role = _require_object(
            raw_role, {"threshold", "keyids"}, reason="invalid_trust_role"
        )
        keyids = role["keyids"]
        if (
            not isinstance(keyids, list)
            or not keyids
            or any(
                not isinstance(keyid, str) or SHA256_RE.fullmatch(keyid) is None
                for keyid in keyids
            )
            or len(keyids) != len(set(keyids))
            or any(keyid not in keys for keyid in keyids)
        ):
            _fail("invalid_role_keys")
        threshold = _positive_int(
            role["threshold"], maximum=len(keyids), reason="invalid_role_threshold"
        )
        if threshold < 2:
            _fail("invalid_role_threshold")
        roles[role_name] = {"threshold": threshold, "keyids": tuple(keyids)}
    return policy, keys, roles


def _validate_subject(kind: str, value: Any) -> dict[str, Any]:
    if kind == "offsite_backup":
        subject = _require_object(
            value,
            {
                "backup_name",
                "local_plaintext_sha256",
                "downloaded_ciphertext_sha256",
                "offsite_object_id_sha256",
                "encryption_key_id_sha256",
                "full_download_verified",
                "authenticated_decryption_verified",
            },
            reason="invalid_offsite_subject",
        )
        if (
            not isinstance(subject["backup_name"], str)
            or SAFE_BASENAME_RE.fullmatch(subject["backup_name"]) is None
        ):
            _fail("invalid_backup_name")
        for name in (
            "local_plaintext_sha256",
            "downloaded_ciphertext_sha256",
            "offsite_object_id_sha256",
            "encryption_key_id_sha256",
        ):
            _require_sha256(subject[name], reason="invalid_offsite_subject")
        if (
            subject["full_download_verified"] is not True
            or subject["authenticated_decryption_verified"] is not True
            or subject["downloaded_ciphertext_sha256"]
            == subject["local_plaintext_sha256"]
        ):
            _fail("offsite_verification_incomplete")
        return subject
    if kind == "dr_offsite_set":
        subject = _require_object(
            value,
            {
                "manifest_sha256",
                "set_id_sha256",
                "snapshot_id_sha256",
                "gate_approval_id_sha256",
                "local_evidence_sha256",
                "repository_id_sha256",
                "encryption_key_id_sha256",
                "full_download_verified",
                "authenticated_decryption_verified",
                "restic_read_data_verified",
            },
            reason="invalid_dr_offsite_subject",
        )
        for name in (
            "manifest_sha256",
            "set_id_sha256",
            "snapshot_id_sha256",
            "gate_approval_id_sha256",
            "local_evidence_sha256",
            "repository_id_sha256",
            "encryption_key_id_sha256",
        ):
            _require_sha256(subject[name], reason="invalid_dr_offsite_subject")
        if (
            subject["full_download_verified"] is not True
            or subject["authenticated_decryption_verified"] is not True
            or subject["restic_read_data_verified"] is not True
        ):
            _fail("offsite_verification_incomplete")
        return subject
    if kind == "restore_drill":
        subject = _require_object(
            value,
            {
                "manifest_sha256",
                "set_id_sha256",
                "snapshot_id_sha256",
                "gate_approval_id_sha256",
                "local_evidence_sha256",
                "components",
                "isolated_runner_verified",
                "production_endpoint_accessed",
                "rpo_verified",
                "rto_verified",
            },
            reason="invalid_restore_subject",
        )
        for name in (
            "manifest_sha256",
            "set_id_sha256",
            "snapshot_id_sha256",
            "gate_approval_id_sha256",
            "local_evidence_sha256",
        ):
            _require_sha256(subject[name], reason="invalid_restore_subject")
        if subject["components"] != [
            "configuration",
            "documents",
            "postgres",
            "qdrant",
            "uploads",
        ]:
            _fail("restore_components_incomplete")
        if (
            subject["isolated_runner_verified"] is not True
            or subject["production_endpoint_accessed"] is not False
            or subject["rpo_verified"] is not True
            or subject["rto_verified"] is not True
        ):
            _fail("restore_verification_incomplete")
        return subject
    if kind == "qdrant_rebuild_approval":
        subject = _require_object(
            value,
            {
                "gate_id",
                "plan_sha256",
                "snapshot_sha256",
                "candidate_collections_sha256",
            },
            reason="invalid_rebuild_subject",
        )
        if subject["gate_id"] != "GATE-08":
            _fail("rebuild_gate_mismatch")
        for name in (
            "plan_sha256",
            "snapshot_sha256",
            "candidate_collections_sha256",
        ):
            _require_sha256(subject[name], reason="invalid_rebuild_subject")
        return subject
    _fail("invalid_receipt_kind")


def _validate_payload(
    raw: bytes,
    *,
    expected_kind: str | None,
    now: dt.datetime,
    policy: dict[str, Any],
) -> dict[str, Any]:
    payload = _require_object(
        _parse_json(raw, reason="invalid_receipt_payload"),
        {
            "schema_version",
            "receipt_id",
            "kind",
            "role",
            "status",
            "issued_at",
            "expires_at",
            "subject",
        },
        reason="invalid_receipt_payload_schema",
    )
    if _canonical_json(payload) != raw:
        _fail("noncanonical_receipt_payload")
    if payload["schema_version"] != SCHEMA_VERSION:
        _fail("invalid_receipt_payload_version")
    receipt_id = _require_sha256(payload["receipt_id"], reason="invalid_receipt_id")
    kind = payload["kind"]
    if kind not in ROLE_BY_KIND or (
        expected_kind is not None and kind != expected_kind
    ):
        _fail("receipt_kind_mismatch")
    if (
        payload["role"] != ROLE_BY_KIND[kind]
        or payload["status"] != STATUS_BY_KIND[kind]
    ):
        _fail("receipt_role_status_mismatch")
    issued_at = _parse_time(payload["issued_at"], reason="invalid_receipt_time")
    expires_at = _parse_time(payload["expires_at"], reason="invalid_receipt_time")
    if (
        expires_at <= issued_at
        or (expires_at - issued_at).total_seconds()
        > policy["max_receipt_validity_seconds"]
        or (now - issued_at).total_seconds() > policy["max_receipt_age_seconds"]
        or issued_at > now + dt.timedelta(seconds=MAX_CLOCK_SKEW_SECONDS)
        or now > expires_at
    ):
        _fail("receipt_expired")
    _validate_subject(kind, payload["subject"])
    identity_material = {
        key: value for key, value in payload.items() if key != "receipt_id"
    }
    expected_id = hashlib.sha256(_canonical_json(identity_material)).hexdigest()
    if receipt_id != expected_id:
        _fail("receipt_id_mismatch")
    return payload


def _pae(payload_type: bytes, payload: bytes) -> bytes:
    return b"DSSEv1 %d %s %d %s" % (
        len(payload_type),
        payload_type,
        len(payload),
        payload,
    )


def verify_envelope(
    envelope_value: Any,
    policy_value: Any,
    *,
    expected_kind: str | None = None,
    now: dt.datetime | None = None,
) -> VerifiedReceipt:
    observed_now = _verification_time(now)
    policy, keys, roles = _validate_policy(policy_value, now=observed_now)
    envelope = _require_object(
        envelope_value,
        {"payloadType", "payload", "signatures"},
        reason="invalid_dsse_envelope",
    )
    if envelope["payloadType"] != PAYLOAD_TYPE:
        _fail("invalid_dsse_payload_type")
    payload_raw = _b64(
        envelope["payload"], expected_bytes=None, reason="invalid_dsse_payload"
    )
    if not payload_raw or len(payload_raw) > MAX_JSON_BYTES:
        _fail("invalid_dsse_payload")
    payload = _validate_payload(
        payload_raw,
        expected_kind=expected_kind,
        now=observed_now,
        policy=policy,
    )
    role_name = payload["role"]
    role = roles.get(role_name)
    if role is None:
        _fail("receipt_role_not_trusted")
    signatures = envelope["signatures"]
    if (
        not isinstance(signatures, list)
        or not signatures
        or len(signatures) > MAX_SIGNATURES
    ):
        _fail("invalid_dsse_signatures")
    pae = _pae(PAYLOAD_TYPE.encode("ascii"), payload_raw)
    verified: set[str] = set()
    seen: set[str] = set()
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise ReceiptError("ed25519_verifier_unavailable") from exc
    issued_at = _parse_time(payload["issued_at"], reason="invalid_receipt_time")
    for raw_signature in signatures:
        signature = _require_object(
            raw_signature, {"keyid", "sig"}, reason="invalid_dsse_signature"
        )
        keyid = _require_sha256(signature["keyid"], reason="invalid_signature_keyid")
        if keyid in seen:
            _fail("duplicate_signature_keyid")
        seen.add(keyid)
        signature_bytes = _b64(
            signature["sig"], expected_bytes=64, reason="invalid_ed25519_signature"
        )
        if keyid not in role["keyids"]:
            continue
        key = keys[keyid]
        if not (key["from"] <= issued_at <= key["to"] and observed_now <= key["to"]):
            continue
        try:
            Ed25519PublicKey.from_public_bytes(key["public_key"]).verify(
                signature_bytes, pae
            )
        except InvalidSignature:
            continue
        verified.add(keyid)
    if len(verified) < role["threshold"]:
        _fail("signature_threshold_not_met")
    return VerifiedReceipt(
        payload=payload,
        envelope=envelope,
        receipt_id=payload["receipt_id"],
        kind=payload["kind"],
        role=role_name,
        verified_keyids=tuple(sorted(verified)),
        envelope_sha256=hashlib.sha256(_canonical_json(envelope)).hexdigest(),
        policy_sha256=hashlib.sha256(_canonical_json(policy_value)).hexdigest(),
    )


def verify_envelope_files(
    envelope_path: Path,
    policy_path: Path,
    *,
    expected_kind: str | None = None,
    now: dt.datetime | None = None,
) -> VerifiedReceipt:
    return verify_envelope(
        _read_json_file(envelope_path, private=True, reason="unsafe_dsse_envelope"),
        _read_json_file(policy_path, private=False, reason="unsafe_trust_policy"),
        expected_kind=expected_kind,
        now=now,
    )


def _exclusive_write(directory_fd: int, name: str, payload: bytes) -> None:
    if SAFE_BASENAME_RE.fullmatch(name) is None:
        _fail("invalid_import_name")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
    except FileExistsError as exc:
        raise ReceiptError("receipt_replay_detected") from exc
    except OSError as exc:
        raise ReceiptError("receipt_import_failed") from exc
    try:
        os.fchmod(descriptor, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                _fail("receipt_import_failed")
            offset += written
        os.fsync(descriptor)
    except Exception:
        try:
            os.unlink(name, dir_fd=directory_fd)
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)
    os.fsync(directory_fd)


def import_receipt(
    envelope_path: Path,
    policy_path: Path,
    store: Path,
    *,
    expected_kind: str | None = None,
    now: dt.datetime | None = None,
) -> Path:
    observed_now = _verification_time(now)
    verified = verify_envelope_files(
        envelope_path, policy_path, expected_kind=expected_kind, now=observed_now
    )
    record = {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": verified.receipt_id,
        "kind": verified.kind,
        "role": verified.role,
        "imported_at": observed_now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "envelope_sha256": verified.envelope_sha256,
        "policy_sha256": verified.policy_sha256,
        "verified_keyids": list(verified.verified_keyids),
        "envelope": verified.envelope,
    }
    directory_fd = _open_directory(store, private_leaf=True, create_leaf=True)
    name = f"{verified.receipt_id}.dsse.json"
    try:
        _exclusive_write(directory_fd, name, _canonical_json(record))
    finally:
        os.close(directory_fd)
    return store / name


def verify_imported_receipt(
    receipt_path: Path,
    policy_path: Path,
    *,
    expected_kind: str | None = None,
    now: dt.datetime | None = None,
) -> VerifiedReceipt:
    record = _require_object(
        _read_json_file(receipt_path, private=True, reason="unsafe_imported_receipt"),
        {
            "schema_version",
            "receipt_id",
            "kind",
            "role",
            "imported_at",
            "envelope_sha256",
            "policy_sha256",
            "verified_keyids",
            "envelope",
        },
        reason="invalid_imported_receipt_schema",
    )
    if record["schema_version"] != SCHEMA_VERSION:
        _fail("invalid_imported_receipt_version")
    _parse_time(record["imported_at"], reason="invalid_import_time")
    policy_value = _read_json_file(
        policy_path, private=False, reason="unsafe_trust_policy"
    )
    verified = verify_envelope(
        record["envelope"],
        policy_value,
        expected_kind=expected_kind,
        now=now,
    )
    if (
        record["receipt_id"] != verified.receipt_id
        or record["kind"] != verified.kind
        or record["role"] != verified.role
        or record["envelope_sha256"] != verified.envelope_sha256
        or record["policy_sha256"] != verified.policy_sha256
        or record["verified_keyids"] != list(verified.verified_keyids)
    ):
        _fail("imported_receipt_mismatch")
    return verified


def _path(value: str) -> Path:
    return _normalized_absolute(Path(value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "import"):
        command = commands.add_parser(name)
        command.add_argument("--envelope", required=True, type=_path)
        command.add_argument("--policy", required=True, type=_path)
        command.add_argument("--kind", required=True, choices=tuple(ROLE_BY_KIND))
        if name == "import":
            command.add_argument("--store", required=True, type=_path)
    imported = commands.add_parser("verify-imported")
    imported.add_argument("--receipt", required=True, type=_path)
    imported.add_argument("--policy", required=True, type=_path)
    imported.add_argument("--kind", required=True, choices=tuple(ROLE_BY_KIND))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "verify":
            verified = verify_envelope_files(
                args.envelope, args.policy, expected_kind=args.kind
            )
        elif args.command == "import":
            imported = import_receipt(
                args.envelope,
                args.policy,
                args.store,
                expected_kind=args.kind,
            )
            verified = verify_imported_receipt(
                imported, args.policy, expected_kind=args.kind
            )
        else:
            verified = verify_imported_receipt(
                args.receipt, args.policy, expected_kind=args.kind
            )
        print(
            json.dumps(
                {
                    "kind": verified.kind,
                    "receipt_id": verified.receipt_id,
                    "signatures_verified": len(verified.verified_keyids),
                    "status": "verified",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except ReceiptError as exc:
        print(
            json.dumps(
                {"reason": exc.reason, "status": "blocked"},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
