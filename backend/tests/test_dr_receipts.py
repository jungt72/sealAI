from __future__ import annotations

import base64
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "ops" / "dr_receipts.py"


def _load():
    spec = importlib.util.spec_from_file_location("dr_receipts_test", HELPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


receipts = _load()
NOW = dt.datetime(2026, 7, 15, 12, 0, tzinfo=dt.timezone.utc)


def _write(path: Path, value: object, *, mode: int = 0o600) -> None:
    path.write_bytes(receipts._canonical_json(value))
    path.chmod(mode)


def _keys(count: int = 3):
    result = []
    for _ in range(count):
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        result.append((hashlib.sha256(public).hexdigest(), private, public))
    return result


def _policy(keys) -> dict:
    keyids = [keyid for keyid, _, _ in keys]
    return {
        "schema_version": 1,
        "policy_id": hashlib.sha256(b"test-policy-v1").hexdigest(),
        "valid_from": "2026-07-15T00:00:00Z",
        "expires_at": "2026-08-15T00:00:00Z",
        "max_receipt_age_seconds": 86400,
        "max_receipt_validity_seconds": 3600,
        "keys": [
            {
                "keyid": keyid,
                "algorithm": "ed25519",
                "public_key_base64": base64.b64encode(public).decode("ascii"),
                "not_before": "2026-07-15T00:00:00Z",
                "not_after": "2026-08-15T00:00:00Z",
            }
            for keyid, _, public in keys
        ],
        "roles": {
            "offsite_attestor": {"threshold": 2, "keyids": keyids[:2]},
            "restore_attestor": {"threshold": 2, "keyids": keyids[1:]},
            "rebuild_approver": {"threshold": 2, "keyids": keyids[:2]},
        },
    }


def _offsite_payload(*, backup_name: str = "postgres.sql.gz") -> dict:
    payload = {
        "schema_version": 1,
        "kind": "offsite_backup",
        "role": "offsite_attestor",
        "status": "OFFSITE_VERIFIED",
        "issued_at": "2026-07-15T11:55:00Z",
        "expires_at": "2026-07-15T12:55:00Z",
        "subject": {
            "backup_name": backup_name,
            "local_plaintext_sha256": "1" * 64,
            "downloaded_ciphertext_sha256": "2" * 64,
            "offsite_object_id_sha256": "3" * 64,
            "encryption_key_id_sha256": "4" * 64,
            "full_download_verified": True,
            "authenticated_decryption_verified": True,
        },
    }
    payload["receipt_id"] = hashlib.sha256(
        receipts._canonical_json(payload)
    ).hexdigest()
    return payload


def _envelope(payload: dict, signers) -> dict:
    raw = receipts._canonical_json(payload)
    pae = receipts._pae(receipts.PAYLOAD_TYPE.encode("ascii"), raw)
    return {
        "payloadType": receipts.PAYLOAD_TYPE,
        "payload": base64.b64encode(raw).decode("ascii"),
        "signatures": [
            {
                "keyid": keyid,
                "sig": base64.b64encode(private.sign(pae)).decode("ascii"),
            }
            for keyid, private, _ in signers
        ],
    }


def test_threshold_signed_dsse_verifies_only_for_bound_role() -> None:
    keys = _keys()
    policy = _policy(keys)
    envelope = _envelope(_offsite_payload(), keys[:2])

    verified = receipts.verify_envelope(
        envelope, policy, expected_kind="offsite_backup", now=NOW
    )
    assert verified.role == "offsite_attestor"
    assert verified.verified_keyids == tuple(sorted(keyid for keyid, _, _ in keys[:2]))

    with pytest.raises(receipts.ReceiptError, match="receipt_kind_mismatch"):
        receipts.verify_envelope(
            envelope, policy, expected_kind="restore_drill", now=NOW
        )


def test_wrong_role_unknown_and_duplicate_signatures_do_not_meet_threshold() -> None:
    keys = _keys()
    policy = _policy(keys)
    payload = _offsite_payload()
    with pytest.raises(receipts.ReceiptError, match="signature_threshold_not_met"):
        receipts.verify_envelope(
            _envelope(payload, (keys[0], keys[2])),
            policy,
            expected_kind="offsite_backup",
            now=NOW,
        )

    duplicate = _envelope(payload, (keys[0], keys[0]))
    with pytest.raises(receipts.ReceiptError, match="duplicate_signature_keyid"):
        receipts.verify_envelope(
            duplicate, policy, expected_kind="offsite_backup", now=NOW
        )


def test_policy_requires_two_valid_distinct_role_keys_and_utc_clock() -> None:
    keys = _keys()
    policy = _policy(keys)
    envelope = _envelope(_offsite_payload(), keys[:2])

    policy["roles"]["offsite_attestor"]["threshold"] = 1
    with pytest.raises(receipts.ReceiptError, match="invalid_role_threshold"):
        receipts.verify_envelope(
            envelope, policy, expected_kind="offsite_backup", now=NOW
        )

    policy = _policy(keys)
    policy["roles"]["offsite_attestor"]["keyids"] = [
        keys[0][0],
        {"not": "hashable"},
    ]
    with pytest.raises(receipts.ReceiptError, match="invalid_role_keys"):
        receipts.verify_envelope(
            envelope, policy, expected_kind="offsite_backup", now=NOW
        )

    with pytest.raises(receipts.ReceiptError, match="invalid_verification_time"):
        receipts.verify_envelope(
            envelope,
            _policy(keys),
            expected_kind="offsite_backup",
            now=NOW.replace(tzinfo=None),
        )


def test_payload_tamper_noncanonical_payload_and_private_key_fields_are_rejected() -> (
    None
):
    keys = _keys()
    policy = _policy(keys)
    payload = _offsite_payload()
    envelope = _envelope(payload, keys[:2])

    tampered_payload = dict(payload)
    tampered_payload["subject"] = {**payload["subject"], "backup_name": "other.gz"}
    tampered = dict(envelope)
    tampered["payload"] = base64.b64encode(
        receipts._canonical_json(tampered_payload)
    ).decode("ascii")
    with pytest.raises(receipts.ReceiptError, match="receipt_id_mismatch"):
        receipts.verify_envelope(
            tampered, policy, expected_kind="offsite_backup", now=NOW
        )

    noncanonical = dict(envelope)
    noncanonical["payload"] = base64.b64encode(
        json.dumps(payload, indent=2).encode("ascii")
    ).decode("ascii")
    with pytest.raises(receipts.ReceiptError, match="noncanonical_receipt_payload"):
        receipts.verify_envelope(
            noncanonical, policy, expected_kind="offsite_backup", now=NOW
        )

    policy["keys"][0]["private_key_base64"] = "forbidden"
    with pytest.raises(receipts.ReceiptError, match="invalid_trust_key"):
        receipts.verify_envelope(
            envelope, policy, expected_kind="offsite_backup", now=NOW
        )

    invalid_json = dict(envelope)
    invalid_json["payload"] = base64.b64encode(b'{"value":NaN}\n').decode("ascii")
    with pytest.raises(receipts.ReceiptError, match="invalid_receipt_payload"):
        receipts.verify_envelope(
            invalid_json, _policy(keys), expected_kind="offsite_backup", now=NOW
        )


def test_import_is_private_exclusive_durable_and_reverified(tmp_path: Path) -> None:
    keys = _keys()
    policy = _policy(keys)
    envelope = _envelope(_offsite_payload(), keys[:2])
    envelope_path = tmp_path / "incoming.dsse.json"
    policy_path = tmp_path / "policy.json"
    _write(envelope_path, envelope)
    _write(policy_path, policy, mode=0o644)
    store = tmp_path / "store"

    imported = receipts.import_receipt(
        envelope_path,
        policy_path,
        store,
        expected_kind="offsite_backup",
        now=NOW,
    )
    assert stat_mode(imported) == 0o600
    assert stat_mode(store) == 0o700
    assert (
        receipts.verify_imported_receipt(
            imported, policy_path, expected_kind="offsite_backup", now=NOW
        ).receipt_id
        == _offsite_payload()["receipt_id"]
    )

    with pytest.raises(receipts.ReceiptError, match="receipt_replay_detected"):
        receipts.import_receipt(
            envelope_path,
            policy_path,
            store,
            expected_kind="offsite_backup",
            now=NOW,
        )

    record = json.loads(imported.read_text(encoding="ascii"))
    record["verified_keyids"] = record["verified_keyids"][:1]
    _write(imported, record)
    with pytest.raises(receipts.ReceiptError, match="imported_receipt_mismatch"):
        receipts.verify_imported_receipt(
            imported, policy_path, expected_kind="offsite_backup", now=NOW
        )


def test_symlink_policy_envelope_and_imported_receipt_fail_closed(
    tmp_path: Path,
) -> None:
    keys = _keys()
    policy = _policy(keys)
    envelope = _envelope(_offsite_payload(), keys[:2])
    real_envelope = tmp_path / "real-envelope.json"
    real_policy = tmp_path / "real-policy.json"
    _write(real_envelope, envelope)
    _write(real_policy, policy)
    envelope_link = tmp_path / "envelope.json"
    policy_link = tmp_path / "policy.json"
    envelope_link.symlink_to(real_envelope)
    policy_link.symlink_to(real_policy)

    with pytest.raises(receipts.ReceiptError, match="unsafe_dsse_envelope"):
        receipts.verify_envelope_files(
            envelope_link, real_policy, expected_kind="offsite_backup", now=NOW
        )
    with pytest.raises(receipts.ReceiptError, match="unsafe_trust_policy"):
        receipts.verify_envelope_files(
            real_envelope, policy_link, expected_kind="offsite_backup", now=NOW
        )


def test_expired_policy_receipt_and_key_fail_closed() -> None:
    keys = _keys()
    payload = _offsite_payload()
    envelope = _envelope(payload, keys[:2])
    policy = _policy(keys)
    later = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
    with pytest.raises(receipts.ReceiptError, match="trust_policy_expired"):
        receipts.verify_envelope(
            envelope, policy, expected_kind="offsite_backup", now=later
        )

    with pytest.raises(receipts.ReceiptError, match="receipt_expired"):
        receipts.verify_envelope(
            envelope,
            policy,
            expected_kind="offsite_backup",
            now=dt.datetime(2026, 7, 16, 13, 0, tzinfo=dt.timezone.utc),
        )


def stat_mode(path: Path) -> int:
    return os.stat(path, follow_symlinks=False).st_mode & 0o777
