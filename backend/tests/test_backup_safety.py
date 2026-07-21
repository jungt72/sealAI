"""Fail-closed contracts for target-aware backup capacity and retention."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "ops" / "backup_safety.py"
GIB = 1024**3


def _module():
    spec = importlib.util.spec_from_file_location("backup_safety", HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _backup(module, directory: Path, name: str, byte: bytes = b"x") -> Path:
    path = directory / name
    path.write_bytes(byte * 2048)
    os.chmod(path, 0o600)
    module.write_checksum(path)
    return path


def _receipt(module, backup: Path, *, digest: str | None = None) -> Path:
    actual = module.verify_local_backup(backup)
    claimed = actual if digest is None else digest
    receipt = module.receipt_path(backup)
    receipt.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "backup_name": backup.name,
                "local_plaintext_sha256": claimed,
                "downloaded_ciphertext_sha256": "2" * 64,
                "decrypted_plaintext_sha256": claimed,
                "offsite_verified": True,
                "offsite_ciphertext_object_id_sha256": "1" * 64,
                "encryption_key_id_sha256": "3" * 64,
                "verified_at": module._utc_now()
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                "verification_method": "full-download-decrypt-sha256",
            }
        ),
        encoding="utf-8",
    )
    os.chmod(receipt, 0o600)
    return receipt


def test_thresholds_are_fixed_at_critical_85_and_recovery_80() -> None:
    module = _module()

    at_critical = module.evaluate_preflight(
        total_bytes=100 * GIB,
        free_bytes=15 * GIB,
        estimated_write_bytes=0,
        minimum_reserve_bytes=3 * GIB,
        was_critical=False,
    )
    assert at_critical["allowed"] is False
    assert at_critical["reason"] == "critical_threshold"

    above_recovery = module.evaluate_preflight(
        total_bytes=100 * GIB,
        free_bytes=16 * GIB,
        estimated_write_bytes=0,
        minimum_reserve_bytes=3 * GIB,
        was_critical=True,
    )
    assert above_recovery["allowed"] is False
    assert above_recovery["reason"] == "recovery_threshold"

    recovered = module.evaluate_preflight(
        total_bytes=100 * GIB,
        free_bytes=20 * GIB,
        estimated_write_bytes=0,
        minimum_reserve_bytes=3 * GIB,
        was_critical=True,
    )
    assert recovered["allowed"] is True
    assert recovered["state"] == "normal"


def test_preflight_blocks_projected_critical_and_missing_reserve() -> None:
    module = _module()

    projected = module.evaluate_preflight(
        total_bytes=100 * GIB,
        free_bytes=20 * GIB,
        estimated_write_bytes=6 * GIB,
        minimum_reserve_bytes=3 * GIB,
        was_critical=False,
    )
    assert projected["allowed"] is False
    assert projected["reason"] == "projected_critical"

    no_reserve = module.evaluate_preflight(
        total_bytes=16 * GIB,
        free_bytes=4 * GIB,
        estimated_write_bytes=2 * GIB,
        minimum_reserve_bytes=3 * GIB,
        was_critical=False,
    )
    assert no_reserve["allowed"] is False
    assert no_reserve["reason"] == "reserve_unavailable"


@pytest.mark.parametrize("reserve", (0, 2 * GIB, 3 * GIB - 1))
def test_preflight_rejects_reserve_below_global_stop_condition(reserve: int) -> None:
    module = _module()

    with pytest.raises(
        module.SafetyError, match="minimum_reserve_below_stop_condition"
    ):
        module.evaluate_preflight(
            total_bytes=16 * GIB,
            free_bytes=4 * GIB,
            estimated_write_bytes=GIB + GIB // 2,
            minimum_reserve_bytes=reserve,
            was_critical=False,
        )


def test_preflight_measures_nearest_existing_target_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _module()
    target = tmp_path / "not-created" / "postgres"
    measured: list[Path] = []

    def disk_usage(path: Path) -> SimpleNamespace:
        measured.append(Path(path))
        return SimpleNamespace(total=100 * GIB, used=20 * GIB, free=80 * GIB)

    monkeypatch.setattr(module.shutil, "disk_usage", disk_usage)
    args = argparse.Namespace(
        component="backup_postgres",
        target_dir=str(target),
        estimated_write_bytes=str(GIB),
        minimum_reserve_bytes=str(3 * GIB),
        state_dir=str(tmp_path / "state"),
    )
    assert module.run_preflight(args) == 0
    assert measured == [tmp_path]
    assert not target.exists()
    state_files = list((tmp_path / "state").glob("target-*.json"))
    assert len(state_files) == 1
    assert (tmp_path / "state").stat().st_mode & 0o777 == 0o700
    assert state_files[0].stat().st_mode & 0o777 == 0o600

    event = capsys.readouterr().out
    assert json.loads(event)["status"] == "ok"
    assert str(target) not in event


@pytest.mark.parametrize(
    "target",
    (
        "relative/backup",
        "~/backup",
        "/safe/~/backup",
        "/safe/./backup",
        "/safe/link/../backup",
        "/safe//backup",
        "//safe/backup",
        "/safe/backup/",
    ),
)
def test_target_path_must_already_be_normalized_and_absolute(target: str) -> None:
    module = _module()

    with pytest.raises(module.SafetyError, match="path_not_normalized_absolute"):
        module._validated_path_argument(target)


def test_target_path_validation_preserves_the_exact_accepted_string(
    tmp_path: Path,
) -> None:
    module = _module()
    target = str(tmp_path / "future" / "backup")

    validated = module._validated_path_argument(target)

    assert str(validated) == target


def test_preflight_rejects_unsafe_state_directory_and_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    monkeypatch.setattr(
        module.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=100 * GIB, used=20 * GIB, free=80 * GIB),
    )
    target = tmp_path / "backup-target"
    args = argparse.Namespace(
        component="backup_postgres",
        target_dir=str(target),
        estimated_write_bytes=str(GIB),
        minimum_reserve_bytes=str(3 * GIB),
        state_dir=str(tmp_path / "state"),
    )

    state_dir = Path(args.state_dir)
    state_dir.mkdir(mode=0o700)
    os.chmod(state_dir, 0o755)
    with pytest.raises(module.SafetyError, match="state_directory_unsafe"):
        module.run_preflight(args)

    os.chmod(state_dir, 0o700)
    assert module.run_preflight(args) == 0
    state_file = next(state_dir.glob("target-*.json"))
    os.chmod(state_file, 0o644)
    with pytest.raises(module.SafetyError, match="invalid_state_file"):
        module.run_preflight(args)


def test_preflight_rejects_symlinked_state_directory(tmp_path: Path) -> None:
    module = _module()
    real = tmp_path / "real-state"
    real.mkdir(mode=0o700)
    link = tmp_path / "linked-state"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(module.SafetyError, match="state_directory_unsafe"):
        module._secure_private_directory(link, create=True)


def test_target_filesystem_identity_rejects_symlinked_ancestor(tmp_path: Path) -> None:
    module = _module()
    real = tmp_path / "real-target-parent"
    real.mkdir()
    linked = tmp_path / "linked-target-parent"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(module.SafetyError, match="target_has_symlink"):
        module._nearest_existing_directory(linked / "backup")


def test_local_checksum_verification_detects_tampering(tmp_path: Path) -> None:
    module = _module()
    backup = _backup(module, tmp_path, "postgres-all-old.sql.gz")
    assert module.checksum_path(backup).stat().st_mode & 0o777 == 0o600
    module.verify_local_backup(backup)

    backup.write_bytes(b"changed" * 512)
    with pytest.raises(module.SafetyError, match="checksum_mismatch"):
        module.verify_local_backup(backup)


def test_bound_backup_revalidates_the_exact_open_inode(tmp_path: Path) -> None:
    module = _module()
    backup = _backup(module, tmp_path, "qdrant.snapshot", byte=b"q")
    expected = module.verify_local_backup(backup)
    expected_bytes = backup.stat().st_size
    descriptor = os.open(backup, os.O_RDONLY)
    try:
        module.fcntl.flock(descriptor, module.fcntl.LOCK_EX | module.fcntl.LOCK_NB)
        assert (
            module.verify_bound_backup(backup, descriptor, expected_bytes, expected)
            == expected
        )

        replacement = tmp_path / "replacement"
        replacement.write_bytes(b"q" * 2048)
        os.chmod(replacement, 0o600)
        os.replace(replacement, backup)
        with pytest.raises(module.SafetyError, match="bound_backup_changed"):
            module.verify_bound_backup(backup, descriptor, expected_bytes, expected)
    finally:
        os.close(descriptor)


def test_bound_backup_rejects_a_second_hardlink(tmp_path: Path) -> None:
    module = _module()
    backup = _backup(module, tmp_path, "qdrant.snapshot", byte=b"q")
    expected = module.verify_local_backup(backup)
    alias = tmp_path / "qdrant-alias.snapshot"
    os.link(backup, alias)
    descriptor = os.open(backup, os.O_RDONLY)
    try:
        module.fcntl.flock(descriptor, module.fcntl.LOCK_EX | module.fcntl.LOCK_NB)
        with pytest.raises(module.SafetyError, match="bound_backup_changed"):
            module.verify_bound_backup(
                backup, descriptor, backup.stat().st_size, expected
            )
    finally:
        os.close(descriptor)


def test_remote_delete_gate_binds_receipt_digest_to_open_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    args = argparse.Namespace(
        backup=str(tmp_path / "qdrant.snapshot"),
        receipt=str(tmp_path / "receipt.json"),
        policy="verified-offsite",
        backup_fd="9",
        expected_bytes="2048",
        expected_sha256="a" * 64,
        component="backup_qdrant",
    )
    monkeypatch.setattr(module, "verify_local_backup", lambda _backup: "a" * 64)
    monkeypatch.setattr(
        module, "verify_offsite_receipt", lambda _backup, _receipt: "b" * 64
    )
    monkeypatch.setattr(
        module,
        "verify_bound_backup",
        lambda _backup, _fd, _bytes, _digest: "a" * 64,
    )

    with pytest.raises(module.SafetyError, match="receipt_bound_backup_mismatch"):
        module.run_remote_delete_eligible(args)


def test_checksum_fsyncs_backup_inode_before_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    backup = tmp_path / "qdrant.snapshot"
    backup.write_bytes(b"q" * 2048)
    os.chmod(backup, 0o600)
    backup_identity = (backup.stat().st_dev, backup.stat().st_ino)
    sidecar = module.checksum_path(backup)
    synced: list[tuple[int, int]] = []
    real_fsync = module.os.fsync

    def tracked_fsync(descriptor: int) -> None:
        metadata = module.os.fstat(descriptor)
        identity = (metadata.st_dev, metadata.st_ino)
        if identity == backup_identity:
            assert not sidecar.exists()
        synced.append(identity)
        real_fsync(descriptor)

    monkeypatch.setattr(module.os, "fsync", tracked_fsync)

    module.write_checksum(backup)

    assert synced[0] == backup_identity
    assert sidecar.is_file()


def test_checksum_fails_closed_before_sidecar_when_backup_fsync_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    backup = tmp_path / "qdrant.snapshot"
    backup.write_bytes(b"q" * 2048)
    os.chmod(backup, 0o600)
    backup_identity = (backup.stat().st_dev, backup.stat().st_ino)
    real_fsync = module.os.fsync

    def fail_backup_fsync(descriptor: int) -> None:
        metadata = module.os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) == backup_identity:
            raise OSError("simulated fsync failure")
        real_fsync(descriptor)

    monkeypatch.setattr(module.os, "fsync", fail_backup_fsync)

    with pytest.raises(module.SafetyError, match="backup_fsync_failed"):
        module.write_checksum(backup)

    assert not module.checksum_path(backup).exists()


def test_checksum_rejects_path_replacement_during_backup_fsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    backup = tmp_path / "qdrant.snapshot"
    backup.write_bytes(b"q" * 2048)
    os.chmod(backup, 0o600)
    backup_identity = (backup.stat().st_dev, backup.stat().st_ino)
    real_fsync = module.os.fsync
    replaced = False

    def replace_during_fsync(descriptor: int) -> None:
        nonlocal replaced
        metadata = module.os.fstat(descriptor)
        if not replaced and (metadata.st_dev, metadata.st_ino) == backup_identity:
            replacement = tmp_path / "replacement"
            replacement.write_bytes(b"r" * 2048)
            os.chmod(replacement, 0o600)
            os.replace(replacement, backup)
            replaced = True
        real_fsync(descriptor)

    monkeypatch.setattr(module.os, "fsync", replace_during_fsync)

    with pytest.raises(module.SafetyError, match="backup_changed"):
        module.write_checksum(backup)

    assert not module.checksum_path(backup).exists()


def test_expected_source_size_and_checksum_must_both_match(tmp_path: Path) -> None:
    module = _module()
    backup = tmp_path / "qdrant.snapshot.partial"
    backup.write_bytes(b"q" * 2048)
    os.chmod(backup, 0o600)
    digest = module._sha256(backup)

    assert module.verify_expected_backup(backup, 2048, digest) == digest
    with pytest.raises(module.SafetyError, match="expected_size_mismatch"):
        module.verify_expected_backup(backup, 2049, digest)
    with pytest.raises(module.SafetyError, match="expected_checksum_mismatch"):
        module.verify_expected_backup(backup, 2048, "0" * 64)


def test_offsite_receipt_requires_matching_verified_sha256(tmp_path: Path) -> None:
    module = _module()
    backup = _backup(module, tmp_path, "postgres-all-old.sql.gz")
    _receipt(module, backup)
    module.verify_offsite_receipt(backup)

    _receipt(module, backup, digest="0" * 64)
    with pytest.raises(module.SafetyError, match="receipt_checksum_mismatch"):
        module.verify_offsite_receipt(backup)


def test_offsite_receipt_expires_after_24_hours(tmp_path: Path) -> None:
    module = _module()
    backup = _backup(module, tmp_path, "postgres-all-old.sql.gz")
    receipt = _receipt(module, backup)
    data = json.loads(receipt.read_text(encoding="utf-8"))
    stale_time = module._utc_now().replace(microsecond=0) - module.dt.timedelta(
        hours=25
    )
    data["verified_at"] = stale_time.isoformat().replace("+00:00", "Z")
    receipt.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(receipt, 0o600)

    with pytest.raises(module.SafetyError, match="receipt_stale"):
        module.verify_offsite_receipt(backup)


def test_offsite_receipt_rejects_boolean_version_and_duplicate_keys(
    tmp_path: Path,
) -> None:
    module = _module()
    backup = _backup(module, tmp_path, "postgres-all-old.sql.gz")
    receipt = _receipt(module, backup)
    data = json.loads(receipt.read_text(encoding="utf-8"))
    data["schema_version"] = True
    receipt.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(receipt, 0o600)
    with pytest.raises(module.SafetyError, match="receipt_invalid"):
        module.verify_offsite_receipt(backup)

    _receipt(module, backup)
    content = receipt.read_text(encoding="utf-8")
    duplicate = content.replace(
        '"schema_version": 2', '"schema_version": 2, "schema_version": 2'
    )
    receipt.write_text(duplicate, encoding="utf-8")
    os.chmod(receipt, 0o600)
    with pytest.raises(module.SafetyError, match="receipt_invalid"):
        module.verify_offsite_receipt(backup)


def test_receipt_writer_binds_ciphertext_and_decrypted_plaintext_atomically(
    tmp_path: Path,
) -> None:
    module = _module()
    backup = _backup(module, tmp_path, "postgres-all-old.sql.gz")
    ciphertext = tmp_path / "downloaded-ciphertext"
    ciphertext.write_bytes(b"encrypted:" + (b"c" * 2048))
    os.chmod(ciphertext, 0o600)
    decrypted = tmp_path / "decrypted-plaintext"
    decrypted.write_bytes(backup.read_bytes())
    os.chmod(decrypted, 0o600)

    receipt = module.write_offsite_receipt(
        backup, ciphertext, decrypted, "1" * 64, "3" * 64
    )
    assert receipt.stat().st_mode & 0o777 == 0o600
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["verification_method"] == "full-download-decrypt-sha256"
    assert data["downloaded_ciphertext_sha256"] != data["local_plaintext_sha256"]
    assert data["decrypted_plaintext_sha256"] == data["local_plaintext_sha256"]
    assert data["encryption_key_id_sha256"] == "3" * 64
    module.verify_offsite_receipt(backup, receipt)


def test_receipt_writer_rejects_reused_inode_and_bad_decryption(
    tmp_path: Path,
) -> None:
    module = _module()
    backup = _backup(module, tmp_path, "postgres-all-old.sql.gz")
    ciphertext = tmp_path / "downloaded-ciphertext"
    ciphertext.write_bytes(b"encrypted:" + (b"c" * 2048))
    os.chmod(ciphertext, 0o600)
    linked = tmp_path / "not-a-download"
    linked.hardlink_to(backup)
    with pytest.raises(module.SafetyError, match="offsite_evidence_not_distinct"):
        module.write_offsite_receipt(backup, ciphertext, linked, "1" * 64, "3" * 64)

    linked.unlink()
    linked.write_bytes(b"different" * 1024)
    os.chmod(linked, 0o600)
    with pytest.raises(module.SafetyError, match="offsite_decryption_mismatch"):
        module.write_offsite_receipt(backup, ciphertext, linked, "1" * 64, "3" * 64)


def test_receipt_rejects_plaintext_claimed_as_ciphertext(tmp_path: Path) -> None:
    module = _module()
    backup = _backup(module, tmp_path, "postgres-all-old.sql.gz")
    receipt = _receipt(module, backup)
    data = json.loads(receipt.read_text(encoding="utf-8"))
    data["downloaded_ciphertext_sha256"] = data["local_plaintext_sha256"]
    receipt.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(receipt, 0o600)

    with pytest.raises(module.SafetyError, match="receipt_ciphertext_invalid"):
        module.verify_offsite_receipt(backup)


def test_age_without_verified_offsite_receipt_never_deletes(tmp_path: Path) -> None:
    module = _module()
    backup = _backup(module, tmp_path, "postgres-all-old.sql.gz")
    old = time.time() - (40 * 86400)
    os.utime(backup, (old, old))

    result = module.prune_backups(
        target_dir=tmp_path,
        pattern="postgres-all-*.sql.gz",
        retention_days=14,
        minimum_local_copies=1,
        now=time.time(),
    )
    assert result["deleted"] == 0
    assert result["skipped_without_receipt"] == 1
    assert backup.exists()


def test_retention_preserves_minimum_good_local_copies(tmp_path: Path) -> None:
    module = _module()
    now = time.time()
    backups: list[Path] = []
    for index, age_days in enumerate((40, 35, 30), start=1):
        backup = _backup(module, tmp_path, f"postgres-all-{index}.sql.gz")
        _receipt(module, backup)
        old = now - (age_days * 86400)
        os.utime(backup, (old, old))
        backups.append(backup)

    result = module.prune_backups(
        target_dir=tmp_path,
        pattern="postgres-all-*.sql.gz",
        retention_days=14,
        minimum_local_copies=2,
        now=now,
    )
    assert result["deleted"] == 1
    assert sum(path.exists() for path in backups) == 2
    assert not backups[0].exists()

    second = module.prune_backups(
        target_dir=tmp_path,
        pattern="postgres-all-*.sql.gz",
        retention_days=14,
        minimum_local_copies=2,
        now=now,
    )
    assert second["deleted"] == 0
    assert sum(path.exists() for path in backups) == 2


def test_retention_never_removes_only_good_local_copy(tmp_path: Path) -> None:
    module = _module()
    backup = _backup(module, tmp_path, "qdrant-old.snapshot")
    _receipt(module, backup)
    old = time.time() - (40 * 86400)
    os.utime(backup, (old, old))

    result = module.prune_backups(
        target_dir=tmp_path,
        pattern="qdrant-*.snapshot",
        retention_days=14,
        minimum_local_copies=1,
        now=time.time(),
    )
    assert result["deleted"] == 0
    assert result["retained_minimum"] == 1
    assert backup.exists()


def test_retention_fails_closed_when_target_lock_is_busy(tmp_path: Path) -> None:
    module = _module()
    with module._retention_lock(tmp_path):
        with pytest.raises(module.SafetyError, match="retention_lock_busy"):
            module.prune_backups(
                target_dir=tmp_path,
                pattern="postgres-all-*.sql.gz",
                retention_days=14,
                minimum_local_copies=1,
            )


def test_retention_rejects_unsafe_target_mode_and_symlink(tmp_path: Path) -> None:
    module = _module()
    os.chmod(tmp_path, 0o755)
    with pytest.raises(module.SafetyError, match="invalid_retention_target"):
        module.prune_backups(
            target_dir=tmp_path,
            pattern="postgres-all-*.sql.gz",
            retention_days=14,
            minimum_local_copies=1,
        )

    os.chmod(tmp_path, 0o700)
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(module.SafetyError, match="invalid_retention_target"):
        module.prune_backups(
            target_dir=linked,
            pattern="postgres-all-*.sql.gz",
            retention_days=14,
            minimum_local_copies=1,
        )


@pytest.mark.parametrize(
    "pattern",
    ("*", "postgres**.gz", "postgres-?.gz", "postgres-[ab]*.gz", "*.gz"),
)
def test_retention_rejects_broad_or_multi_class_patterns(
    tmp_path: Path, pattern: str
) -> None:
    module = _module()
    with pytest.raises(module.SafetyError, match="invalid_retention_pattern"):
        module.prune_backups(
            target_dir=tmp_path,
            pattern=pattern,
            retention_days=14,
            minimum_local_copies=1,
        )


def test_retention_reverifies_remaining_copies_before_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    now = time.time()
    backups: list[Path] = []
    for index in range(3):
        backup = _backup(module, tmp_path, f"postgres-all-{index}.sql.gz")
        _receipt(module, backup)
        old = now - ((40 - index) * 86400)
        os.utime(backup, (old, old))
        backups.append(backup)

    original = module._pinned_verified_local_backups
    calls = 0

    def reverify(directory_fd: int, pattern: str):
        nonlocal calls
        calls += 1
        pinned = original(directory_fd, pattern)
        if calls == 1:
            backups[-1].write_bytes(b"corrupted" * 512)
        return pinned

    monkeypatch.setattr(module, "_pinned_verified_local_backups", reverify)
    with pytest.raises(module.SafetyError):
        module.prune_backups(
            target_dir=tmp_path,
            pattern="postgres-all-*.sql.gz",
            retention_days=14,
            minimum_local_copies=2,
            now=now,
        )
    assert calls >= 1
    assert all(backup.exists() for backup in backups)


def test_retention_does_not_count_hardlink_names_as_independent_copies(
    tmp_path: Path,
) -> None:
    module = _module()
    first = _backup(module, tmp_path, "postgres-all-first.sql.gz")
    second = tmp_path / "postgres-all-second.sql.gz"
    second.hardlink_to(first)
    module.write_checksum(second)

    verified = module._verified_local_backups(tmp_path, "postgres-all-*.sql.gz")
    assert verified == []


def test_structured_errors_do_not_echo_arbitrary_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _module()
    untrusted_value = "arbitrary value that must not be logged"
    rc = module.main(
        [
            "event",
            "--component",
            "backup_run",
            "--event",
            "backup_run",
            "--status",
            "error",
            "--reason",
            untrusted_value,
        ]
    )
    assert rc == 1
    output = capsys.readouterr().out
    assert untrusted_value not in output
    assert json.loads(output)["reason"] == "invalid_reason"


def test_production_env_is_private_inert_data_and_selects_only_profile_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    assert module.PRODUCTION_ENV_FILE == Path("/home/thorsten/sealai/.env.prod")
    sentinel = tmp_path / "unrequested-must-stay-inert"
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "POSTGRES_USER=backup_user\n"
        "POSTGRES_PASSWORD='literal!value'\n"
        "SEALAI_V2_QDRANT_COLLECTION=collection_v2\n"
        "DATABASE_URL=postgresql://sealai:${POSTGRES_PASSWORD}@postgres/sealai\n"
        "LANGGRAPH_V2_REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0\n"
        f"UNRELATED_SECRET=$(/usr/bin/touch {sentinel})\n",
        encoding="utf-8",
    )
    os.chmod(env_file, 0o600)
    monkeypatch.setattr(module, "PRODUCTION_ENV_FILE", env_file)

    assert module.read_production_env("postgres") == (
        ("POSTGRES_USER", "backup_user"),
        ("POSTGRES_PASSWORD", "literal!value"),
    )
    assert module.read_production_env("qdrant") == (
        ("SEALAI_V2_QDRANT_COLLECTION", "collection_v2"),
    )
    assert not sentinel.exists()


def test_production_env_rejects_dynamic_value_before_any_target_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    sentinel = tmp_path / "must-not-exist"
    target = tmp_path / "backup-target"
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        f"POSTGRES_PASSWORD=$(/usr/bin/touch {sentinel})\n", encoding="utf-8"
    )
    os.chmod(env_file, 0o600)
    monkeypatch.setattr(module, "PRODUCTION_ENV_FILE", env_file)

    with pytest.raises(module.SafetyError, match="production_env_dynamic_value"):
        module.read_production_env("postgres")

    assert not sentinel.exists()
    assert not target.exists()


@pytest.mark.parametrize(
    "content,reason",
    (
        ("POSTGRES_PASSWORD=one\nPOSTGRES_PASSWORD=two\n", "duplicate"),
        ("export POSTGRES_PASSWORD=value\n", "syntax"),
        ("POSTGRES_PASSWORD=${OTHER}\n", "dynamic"),
        ("POSTGRES_PASSWORD=has whitespace\n", "syntax"),
    ),
)
def test_production_env_fails_closed_on_ambiguous_syntax(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: str,
    reason: str,
) -> None:
    module = _module()
    env_file = tmp_path / ".env.prod"
    env_file.write_text(content, encoding="utf-8")
    os.chmod(env_file, 0o600)
    monkeypatch.setattr(module, "PRODUCTION_ENV_FILE", env_file)

    with pytest.raises(module.SafetyError, match=reason):
        module.read_production_env("postgres")


def test_production_env_rejects_symlink_and_non_private_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    real = tmp_path / "real-env"
    real.write_text("POSTGRES_PASSWORD=value\n", encoding="utf-8")
    os.chmod(real, 0o600)
    linked = tmp_path / ".env.prod"
    linked.symlink_to(real)
    monkeypatch.setattr(module, "PRODUCTION_ENV_FILE", linked)
    with pytest.raises(module.SafetyError, match="production_env_unsafe"):
        module.read_production_env("postgres")

    linked.unlink()
    real.rename(linked)
    os.chmod(linked, 0o640)
    with pytest.raises(module.SafetyError, match="production_env_unsafe"):
        module.read_production_env("postgres")


def test_lifecycle_lock_is_nontruncating_private_and_inode_bound(
    tmp_path: Path,
) -> None:
    module = _module()
    os.chmod(tmp_path, 0o700)
    lock = tmp_path / ".backup-lifecycle.lock"
    lock.write_text("preserve-lock-evidence", encoding="utf-8")
    os.chmod(lock, 0o600)

    target_fd, lock_fd = module._acquire_target_lifecycle(tmp_path)
    try:
        module._validate_lifecycle_bindings(tmp_path, target_fd, lock_fd)
        assert lock.read_text(encoding="utf-8") == "preserve-lock-evidence"
        assert os.fstat(lock_fd).st_nlink == 1
        assert os.fstat(lock_fd).st_dev == os.fstat(target_fd).st_dev

        original = tmp_path.with_name(f"{tmp_path.name}-original")
        tmp_path.rename(original)
        tmp_path.mkdir(mode=0o700)
        with pytest.raises(module.SafetyError, match="lifecycle_binding_changed"):
            module._validate_lifecycle_bindings(tmp_path, target_fd, lock_fd)
    finally:
        os.close(lock_fd)
        os.close(target_fd)


def test_lifecycle_lock_rejects_hardlink_alias(tmp_path: Path) -> None:
    module = _module()
    os.chmod(tmp_path, 0o700)
    lock = tmp_path / ".backup-lifecycle.lock"
    lock.touch(mode=0o600)
    os.chmod(lock, 0o600)
    os.link(lock, tmp_path / "lock-alias")

    with pytest.raises(module.SafetyError, match="lifecycle_lock_unsafe"):
        module._acquire_target_lifecycle(tmp_path)


def test_bound_preflight_measures_opened_target_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _module()
    os.chmod(tmp_path, 0o700)
    target_fd, lock_fd = module._acquire_target_lifecycle(tmp_path)
    observed: list[int] = []

    def statvfs(descriptor: int) -> SimpleNamespace:
        observed.append(descriptor)
        return SimpleNamespace(
            f_frsize=1,
            f_bsize=1,
            f_blocks=100 * GIB,
            f_bavail=80 * GIB,
        )

    monkeypatch.setattr(module.os, "fstatvfs", statvfs)
    args = argparse.Namespace(
        component="backup_postgres",
        target_dir=str(tmp_path),
        target_fd=str(target_fd),
        lock_fd=str(lock_fd),
        estimated_write_bytes=str(GIB),
        minimum_reserve_bytes=str(3 * GIB),
        state_dir=str(tmp_path / "state"),
    )
    try:
        assert module.run_bound_preflight(args) == 0
        assert observed == [target_fd]
        event = json.loads(capsys.readouterr().out)
        assert event["metrics"]["bound_target"] is True
    finally:
        os.close(lock_fd)
        os.close(target_fd)


def test_orchestrator_log_and_lock_are_nontruncating_and_fd_bound(
    tmp_path: Path,
) -> None:
    module = _module()
    os.chmod(tmp_path, 0o700)
    log = tmp_path / "backup.log"
    log.write_text("existing-log\n", encoding="utf-8")
    os.chmod(log, 0o600)

    directory_fd, log_fd, lock_fd = module._acquire_orchestrator_bindings(log)
    try:
        module._validate_orchestrator_bindings(log, directory_fd, log_fd, lock_fd)
        assert log.read_text(encoding="utf-8") == "existing-log\n"
        assert os.fstat(log_fd).st_nlink == 1
        assert os.fstat(lock_fd).st_nlink == 1
    finally:
        os.close(lock_fd)
        os.close(log_fd)
        os.close(directory_fd)


def test_lifecycle_reexec_preserves_offsite_policy_and_capacity_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    os.chmod(tmp_path, 0o700)
    receipt = tmp_path / "receipt.json"
    captured: dict[str, str] = {}
    monkeypatch.setenv("BASH_ENV", str(tmp_path / "poison-bash-env"))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "poison-pythonpath"))

    class ExecCalled(RuntimeError):
        pass

    def capture_exec(_script: Path, _argv: list[str], environment: dict[str, str]):
        captured.update(environment)
        raise ExecCalled

    monkeypatch.setattr(module.os, "execve", capture_exec)
    settings = {
        "RETENTION_DAYS": "30",
        "BACKUP_MIN_LOCAL_COPIES": "3",
        "BACKUP_MIN_FREE_BYTES": "9876543210",
        "BACKUP_ESTIMATED_BYTES": "12345678901",
        "BACKUP_SAFETY_STATE_DIR": str(tmp_path / "state"),
        "BACKEND_CONTAINER": "backend-v2",
        "QDRANT_CONTAINER": "qdrant",
        "QDRANT_INTERNAL_URL": "http://qdrant:6333",
        "QDRANT_REMOTE_DELETE_POLICY": "verified-offsite",
        "QDRANT_OFFSITE_RECEIPT": str(receipt),
    }
    args = argparse.Namespace(
        target_dir=str(tmp_path),
        writer="qdrant",
        setting=[f"{key}={value}" for key, value in settings.items()],
    )

    with pytest.raises(ExecCalled):
        module.run_with_lifecycle(args)
    try:
        assert captured["QDRANT_REMOTE_DELETE_POLICY"] == "verified-offsite"
        assert captured["QDRANT_OFFSITE_RECEIPT"] == str(receipt)
        assert captured["BACKUP_ESTIMATED_BYTES"] == "12345678901"
        assert captured["BACKUP_MIN_FREE_BYTES"] == "9876543210"
        assert "PYTHONPATH" not in captured
        assert "BASH_ENV" not in captured
    finally:
        os.close(int(captured["SEALAI_BACKUP_LIFECYCLE_FD"]))
        os.close(int(captured["SEALAI_BACKUP_TARGET_FD"]))


def test_orchestrator_reexec_preserves_allowlisted_runtime_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    os.chmod(tmp_path, 0o700)
    log = tmp_path / "backup.log"
    receipt = tmp_path / "receipt.json"
    monkeypatch.setattr(module, "ORCHESTRATOR_LOG", log)
    captured: dict[str, str] = {}
    monkeypatch.setenv("BASH_ENV", str(tmp_path / "poison-bash-env"))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "poison-pythonpath"))

    class ExecCalled(RuntimeError):
        pass

    def capture_exec(_script: Path, _argv: list[str], environment: dict[str, str]):
        captured.update(environment)
        raise ExecCalled

    monkeypatch.setattr(module.os, "execve", capture_exec)
    settings = {
        "RETENTION_DAYS": "30",
        "BACKUP_MIN_LOCAL_COPIES": "3",
        "BACKUP_MIN_FREE_BYTES": "9876543210",
        "BACKUP_SAFETY_STATE_DIR": str(tmp_path / "state"),
        "POSTGRES_BACKUP_ESTIMATED_BYTES": "11111111111",
        "QDRANT_BACKUP_ESTIMATED_BYTES": "12345678901",
        "POSTGRES_CONTAINER": "postgres",
        "BACKEND_CONTAINER": "backend-v2",
        "QDRANT_CONTAINER": "qdrant",
        "QDRANT_INTERNAL_URL": "http://qdrant:6333",
        "QDRANT_REMOTE_DELETE_POLICY": "verified-offsite",
        "QDRANT_OFFSITE_RECEIPT": str(receipt),
    }
    args = argparse.Namespace(
        setting=[f"{key}={value}" for key, value in settings.items()]
    )

    with pytest.raises(ExecCalled):
        module.run_with_orchestrator_lock(args)
    try:
        assert captured["QDRANT_REMOTE_DELETE_POLICY"] == "verified-offsite"
        assert captured["QDRANT_OFFSITE_RECEIPT"] == str(receipt)
        assert captured["QDRANT_BACKUP_ESTIMATED_BYTES"] == "12345678901"
        assert captured["BACKUP_MIN_FREE_BYTES"] == "9876543210"
        assert "PYTHONPATH" not in captured
        assert "BASH_ENV" not in captured
    finally:
        os.close(int(captured["SEALAI_BACKUP_RUN_LOCK_FD"]))
        os.close(int(captured["SEALAI_BACKUP_LOG_FD"]))
        os.close(int(captured["SEALAI_BACKUP_LOG_DIR_FD"]))


def test_runtime_settings_reject_offsite_downgrade_and_untrusted_values(
    tmp_path: Path,
) -> None:
    module = _module()
    base = {
        "RETENTION_DAYS": "14",
        "BACKUP_MIN_LOCAL_COPIES": "2",
        "BACKUP_MIN_FREE_BYTES": "3221225472",
        "BACKUP_ESTIMATED_BYTES": "1073741824",
        "BACKUP_SAFETY_STATE_DIR": str(tmp_path / "state"),
        "BACKEND_CONTAINER": "backend-v2",
        "QDRANT_CONTAINER": "qdrant",
        "QDRANT_INTERNAL_URL": "http://qdrant:6333",
        "QDRANT_REMOTE_DELETE_POLICY": "verified-offsite",
        "QDRANT_OFFSITE_RECEIPT": "",
    }
    with pytest.raises(module.SafetyError, match="runtime_setting_invalid"):
        module._validated_runtime_settings(
            [f"{key}={value}" for key, value in base.items()],
            module.WRITER_SETTINGS["qdrant"],
        )

    base["QDRANT_OFFSITE_RECEIPT"] = str(tmp_path / "receipt")
    base["QDRANT_INTERNAL_URL"] = "http://attacker.invalid"
    with pytest.raises(module.SafetyError, match="runtime_setting_invalid"):
        module._validated_runtime_settings(
            [f"{key}={value}" for key, value in base.items()],
            module.WRITER_SETTINGS["qdrant"],
        )


def test_backup_entrypoints_ignore_exported_functions_and_python_poisoning(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "poison-ran"
    python_marker = tmp_path / "pythonpath-ran"
    poison_bin = tmp_path / "bin"
    poison_bin.mkdir()
    for command in ("python3", "docker", "mkdir"):
        executable = poison_bin / command
        executable.write_text(f"#!/bin/sh\n/usr/bin/touch '{marker}'\nexit 0\n")
        executable.chmod(0o755)
    poison_python = tmp_path / "python-poison"
    poison_python.mkdir()
    (poison_python / "argparse.py").write_text(
        f"from pathlib import Path\nPath({str(python_marker)!r}).touch()\n",
        encoding="utf-8",
    )
    bash_env = tmp_path / "bash-env"
    bash_env.write_text(f"/usr/bin/touch {marker!s}\n", encoding="utf-8")

    for name in (
        "backup_postgres.sh",
        "backup_qdrant.sh",
        "backup_v2_database.sh",
        "backup_run.sh",
    ):
        marker.unlink(missing_ok=True)
        python_marker.unlink(missing_ok=True)
        script = REPO_ROOT / "ops" / name
        command = f"""
source() {{ /usr/bin/touch {marker!s}; }}
safe_helper() {{ /usr/bin/touch {marker!s}; return 0; }}
acquire_production_storage_lease() {{ /usr/bin/touch {marker!s}; return 0; }}
docker() {{ /usr/bin/touch {marker!s}; return 0; }}
mkdir() {{ /usr/bin/touch {marker!s}; return 0; }}
export -f source safe_helper acquire_production_storage_lease docker mkdir
export PATH={poison_bin!s}
export PYTHONPATH={poison_python!s}
export BASH_ENV={bash_env!s}
exec {script!s}
"""
        result = subprocess.run(
            ["/bin/bash", "-c", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0, name
        assert not marker.exists(), name
        assert not python_marker.exists(), name


def test_shell_scripts_preflight_before_writes_and_use_safe_retention() -> None:
    scripts = {
        name: (REPO_ROOT / "ops" / name).read_text(encoding="utf-8")
        for name in (
            "backup_postgres.sh",
            "backup_qdrant.sh",
            "backup_v2_database.sh",
        )
    }
    for name, script in scripts.items():
        lease_call = script.index("acquire_production_storage_lease >&2")
        target_call = script.index("\nsafe_helper preflight")
        lifecycle_call = script.index("run-with-lifecycle")
        bound_call = script.index("safe_helper preflight-bound")
        assert lease_call < target_call < lifecycle_call < bound_call
        assert bound_call < script.index("mktemp", bound_call)
        assert (
            "readonly PRODUCTION_STORAGE_LEASE_LIB="
            "/usr/local/libexec/sealai/production-storage-lease.sh" in script
        )
        assert "PRODUCTION_STORAGE_LEASE_LIB=${" not in script
        assert 'source "${PRODUCTION_STORAGE_LEASE_LIB}"' in script
        assert "DOCKER_DISK_GUARD_WRAPPER" not in script
        assert "DOCKER_DISK_GUARD_CONFIG" not in script
        assert "docker_data_preflight" not in script
        assert 'readonly SAFETY_HELPER="${SCRIPT_DIR}/backup_safety.py"' in script
        assert "BACKUP_SAFETY_HELPER" not in script
        assert script.startswith("#!/bin/bash -p\n")
        assert "readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin" in script
        assert "umask 077" in script
        assert "/usr/bin/env -i HOME=" in script
        assert '/usr/bin/python3 -I "${SAFETY_HELPER}"' in script
        assert "PYTHONPATH" in script
        assert "ENV_FILE" not in script
        assert 'source "${ENV_FILE}"' not in script
        assert "read-production-env --profile" in script
        assert "/usr/bin/timeout --signal=TERM --kill-after=" in script
        assert script.count("\nTARGET_DIR=") == 1
        component = name.removesuffix(".sh")
        assert f'safe_helper event --component {component} "$@" >&2' in script
        assert "mktemp" in script
        assert "trap cleanup EXIT" in script
        assert "validate-lifecycle" in script
        assert "SEALAI_BACKUP_LIFECYCLE_FD" in script
        assert 'BOUND_TARGET_DIR="/proc/self/fd/${TARGET_DIRECTORY_FD}"' in script
        assert "acquire_lifecycle_lock" not in script
        assert "publish_no_clobber" in script
        assert 'ln -- "${' in script
        assert "mv --" not in script
        assert "safe_helper prune" in script
        assert "find " not in script

    assert scripts["backup_postgres.sh"].index("safe_helper preflight") < scripts[
        "backup_postgres.sh"
    ].index("pg_dumpall")
    assert scripts["backup_v2_database.sh"].index("safe_helper preflight") < scripts[
        "backup_v2_database.sh"
    ].index("pg_dump --format=custom")
    assert scripts["backup_qdrant.sh"].index("safe_helper preflight") < scripts[
        "backup_qdrant.sh"
    ].index("-X POST")

    qdrant = scripts["backup_qdrant.sh"]
    assert "readonly DOCKER_DATA_FILESYSTEM=/mnt/sealai-data" in qdrant
    assert "DOCKER_DATA_FILESYSTEM=${" not in qdrant
    data_capacity = qdrant.index('--target-dir "${DOCKER_DATA_FILESYSTEM}"')
    target_capacity = qdrant.index('--target-dir "${TARGET_DIR}"')
    assert qdrant.index("acquire_production_storage_lease >&2") < data_capacity
    assert data_capacity < target_capacity < qdrant.index("-X POST")
    exact_capacity = qdrant.index('--estimated-write-bytes "${SNAPSHOT_SIZE}"')
    assert qdrant.index("unset SNAPSHOT_METADATA") < exact_capacity
    assert qdrant.rfind("safe_helper preflight-bound", 0, exact_capacity) >= 0
    assert exact_capacity < qdrant.index(" docker cp \\")

    v2_database = scripts["backup_v2_database.sh"]
    assert "database_name_invalid" in v2_database
    assert "^[A-Za-z_][A-Za-z0-9_.-]{0,62}$" in v2_database


def test_backup_run_uses_non_overridable_repo_helper() -> None:
    script = (REPO_ROOT / "ops" / "backup_run.sh").read_text(encoding="utf-8")
    assert 'readonly SAFETY_HELPER="${DIR}/backup_safety.py"' in script
    assert "BACKUP_SAFETY_HELPER" not in script
    assert "set -euo pipefail" in script
    assert script.startswith("#!/bin/bash -p\n")
    assert "readonly LOG_FILE=/home/thorsten/sealai-backups/backup.log" in script
    assert "LOG_FILE=${" not in script
    assert "run-with-orchestrator-lock" in script
    assert "validate-orchestrator" in script
    assert '>&"${LOG_FD}"' in script
    assert "/usr/bin/env -i HOME=" in script
    assert '/usr/bin/python3 -I "${SAFETY_HELPER}"' in script
    assert "/usr/bin/timeout --signal=TERM --kill-after=60s" in script
    assert "fatal_event" in script
    assert HELPER.read_text(encoding="utf-8").startswith("#!/usr/bin/python3 -I\n")


def test_global_storage_lease_is_reentrant_and_installed_fail_closed() -> None:
    lease = (REPO_ROOT / "ops" / "production-storage-lease.sh").read_text(
        encoding="utf-8"
    )
    installer = (REPO_ROOT / "ops" / "install-disk-guard.sh").read_text(
        encoding="utf-8"
    )
    assert "-e /proc/self/fd/9" in lease
    assert "inherited_identity" in lease
    assert "flock -n 9" in lease
    assert "inherited_lock_invalid" in lease
    assert "inherited_lock_not_owned" in lease
    assert "install -m 0644" in installer
    assert "/usr/local/libexec/sealai/production-storage-lease.sh" in installer
    assert "/run/lock/sealai-storage-mutation.lock" in installer
    assert "regular empty file:660:root:thorsten" in installer


def test_qdrant_delete_is_after_local_verification_gate() -> None:
    script = (REPO_ROOT / "ops" / "backup_qdrant.sh").read_text(encoding="utf-8")
    assert 'payload.get("status") != "ok"' in script
    assert 'result.get("size")' in script
    assert 'result.get("checksum")' in script
    assert script.index("verify-expected") < script.index("\npublish_no_clobber\n")
    assert script.index("write-checksum") < script.index("remote-delete-eligible")
    assert script.index("verify-local") < script.index("remote-delete-eligible")
    assert script.index("remote-delete-eligible") < script.index("-X DELETE")
    remote_gate = script.index("REMOTE_GATE=(")
    delete = script.index("-X DELETE", remote_gate)
    binding_release = script.index("\nrelease_backup_binding\n", delete)
    lifecycle_release = script.index("\nrelease_lifecycle_lock\n", delete)
    assert remote_gate < delete < binding_release < lifecycle_release
    assert '--backup-fd "${BACKUP_BINDING_FD}"' in script
    assert '--expected-bytes "${SNAPSHOT_SIZE}"' in script
    assert '--expected-sha256 "${SNAPSHOT_CHECKSUM}"' in script
    assert 'flock -n "${BACKUP_BINDING_FD}"' in script
    assert '"${COLLECTION}" == "."' in script
    assert '"${SNAPSHOT_NAME}" == ".."' in script
    assert 'payload.get("result") is not True' in script
    assert 'QDRANT_INTERNAL_URL}" != "http://qdrant:6333"' in script
    assert script.index("qdrant_endpoint_invalid") < script.index("-X POST")
    assert "--connect-timeout 30 --max-time 540" in script
    assert script.count("/usr/bin/timeout --signal=TERM") >= 5
    assert (
        '--setting "QDRANT_REMOTE_DELETE_POLICY=${QDRANT_REMOTE_DELETE_POLICY}"'
        in script
    )
    assert '--setting "QDRANT_OFFSITE_RECEIPT=${QDRANT_OFFSITE_RECEIPT}"' in script
    assert script.index("\nset -euo pipefail\n") < script.index("write-checksum")
    assert "snapshot_delete_unconfirmed" in script
    assert "verified-local" in script
    assert "verified-offsite" in script
    assert "response was" not in script.lower()


def test_pre_migration_stdout_is_reserved_for_artifact_path() -> None:
    script = (REPO_ROOT / "ops" / "backup_v2_database.sh").read_text(encoding="utf-8")
    assert 'event --component backup_v2_database "$@" >&2' in script
    assert '--state-dir "${BACKUP_SAFETY_STATE_DIR}" >&2' in script
    assert script.rstrip().endswith("printf '%s\\n' \"${canonical_file}\"")


def test_logrotate_policy_is_bounded_compressed_and_private() -> None:
    policy = (REPO_ROOT / "ops" / "logrotate" / "sealai-backups").read_text(
        encoding="utf-8"
    )
    assert "/home/thorsten/sealai-backups/backup.log" in policy
    assert "weekly" in policy
    assert "maxsize 10M" in policy
    assert "rotate 14" in policy
    assert "compress" in policy
    assert "create 0600 thorsten thorsten" in policy


def test_offsite_transport_is_explicitly_blocked_external() -> None:
    runbook = (REPO_ROOT / "docs" / "runbooks" / "backup-storage-safety.md").read_text(
        encoding="utf-8"
    )
    assert "BLOCKED_EXTERNAL" in runbook
    assert "write-receipt" in runbook
    assert "/usr/bin/env -i HOME=/home/thorsten" in runbook
    assert "/usr/bin/python3 -I /home/thorsten/sealai/ops/backup_safety.py" in runbook
    assert "TLS with certificate verification" in runbook
    assert "least-privilege IAM" in runbook
    assert "customer-controlled KMS" in runbook
    assert "client-side authenticated" in runbook
    assert "key creation, rotation, revocation" in runbook
    assert "isolated restore-key test" in runbook
    assert "downloaded_ciphertext_sha256" in runbook
    assert "decrypted_plaintext_sha256" in runbook
    assert "encryption_key_id_sha256" in runbook


def test_restore_runbook_gates_destructive_paths_on_checksums() -> None:
    restore = (REPO_ROOT / "ops" / "RESTORE.md").read_text(encoding="utf-8")
    assert restore.count("sha256sum -c") >= 4
    assert "psql -v ON_ERROR_STOP=1" in restore
    assert "recover?wait=true" in restore
    assert "recover?checksum=" not in restore
    assert '\\"checksum\\":\\"${SNAPSHOT_SHA}\\"' in restore
    assert 'response.get("status") != "ok"' in restore
    assert 'response.get("result") is not True' in restore
    assert "-fsS -X PUT" in restore
