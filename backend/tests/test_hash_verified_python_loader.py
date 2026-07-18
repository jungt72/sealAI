from __future__ import annotations

import datetime as dt
import hashlib
import os
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops"
sys.path.insert(0, str(OPS))

import hash_verified_python_loader as loader  # noqa: E402
import production_release_gate as gate  # noqa: E402


def _identity() -> tuple[int, int]:
    return os.geteuid(), os.getegid()


def _approval_value(bootstrap_hash: str, **overrides: object) -> dict[str, object]:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    value: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "GATE-08",
        "operation": "operational-control-install",
        "decision": "APPROVED",
        "scope": "p0-operational-control-install",
        "approval_id": "loader-test-approval",
        "owner": "test-owner",
        "approved_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_git_sha": "a" * 40,
        "artifact_sha256": {
            artifact: bootstrap_hash for artifact in sorted(loader.APPROVED_ARTIFACTS)
        },
        "install_targets": dict(loader.INSTALL_TARGETS),
        "target_preconditions": {
            target: {"state": "ABSENT"} for target in loader.TARGET_MODES
        },
    }
    value.update(overrides)
    return value


def _candidate(path: Path, sentinel: Path, marker: str = "verified") -> bytes:
    content = (
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text({marker!r}, encoding='utf-8')\n"
    ).encode()
    path.write_bytes(content)
    path.chmod(0o600)
    return content


def _execute(
    candidate: Path,
    expected_hash: str,
    run_root: Path,
) -> int:
    uid, gid = _identity()
    return loader._verify_and_execute(
        candidate,
        expected_hash,
        ("--source-repository", "/approved/source", "--apply"),
        run_root=run_root,
        required_uid=uid,
        required_gid=gid,
    )


def test_hash_mismatch_never_loads_candidate_top_level_code(tmp_path: Path):
    candidate = tmp_path / "bootstrap.py"
    sentinel = tmp_path / "candidate-executed"
    _candidate(candidate, sentinel)

    with pytest.raises(loader.LoaderDenied, match="approved bootstrap hash mismatch"):
        _execute(candidate, "0" * 64, tmp_path)

    assert not sentinel.exists()
    assert not list(tmp_path.glob("sealai-operational-loader.*"))


def test_correct_hash_executes_only_root_private_staged_copy(tmp_path: Path):
    candidate = tmp_path / "bootstrap.py"
    sentinel = tmp_path / "candidate-executed"
    content = _candidate(candidate, sentinel)

    assert _execute(candidate, hashlib.sha256(content).hexdigest(), tmp_path) == 0
    assert sentinel.read_text(encoding="utf-8") == "verified"
    assert not list(tmp_path.glob("sealai-operational-loader.*"))


def test_open_descriptor_survives_candidate_path_exchange(tmp_path: Path):
    candidate = tmp_path / "bootstrap.py"
    original_sentinel = tmp_path / "original-executed"
    replacement_sentinel = tmp_path / "replacement-executed"
    original = _candidate(candidate, original_sentinel, "original")
    expected = hashlib.sha256(original).hexdigest()
    uid, gid = _identity()
    descriptor = loader._open_candidate(
        candidate,
        required_uid=uid,
        required_gid=gid,
    )
    replacement = tmp_path / "replacement.py"
    _candidate(replacement, replacement_sentinel, "replacement")
    replacement.replace(candidate)
    try:
        approved_bytes = loader._read_verified_descriptor(descriptor, expected)
    finally:
        os.close(descriptor)

    assert (
        loader._stage_and_execute(
            approved_bytes,
            expected,
            ("--source-repository", "/approved/source", "--apply"),
            run_root=tmp_path,
            required_uid=uid,
            required_gid=gid,
        )
        == 0
    )
    assert original_sentinel.read_text(encoding="utf-8") == "original"
    assert not replacement_sentinel.exists()


def test_checkout_path_change_after_hash_does_not_change_stage(tmp_path: Path):
    candidate = tmp_path / "bootstrap.py"
    approved_sentinel = tmp_path / "approved-executed"
    changed_sentinel = tmp_path / "changed-executed"
    approved = _candidate(candidate, approved_sentinel, "approved")
    expected = hashlib.sha256(approved).hexdigest()
    uid, gid = _identity()
    descriptor = loader._open_candidate(
        candidate,
        required_uid=uid,
        required_gid=gid,
    )
    try:
        approved_bytes = loader._read_verified_descriptor(descriptor, expected)
    finally:
        os.close(descriptor)
    _candidate(candidate, changed_sentinel, "changed")

    assert (
        loader._stage_and_execute(
            approved_bytes,
            expected,
            ("--source-repository", "/approved/source", "--apply"),
            run_root=tmp_path,
            required_uid=uid,
            required_gid=gid,
        )
        == 0
    )
    assert approved_sentinel.read_text(encoding="utf-8") == "approved"
    assert not changed_sentinel.exists()


def test_candidate_symlink_and_writable_file_are_rejected(tmp_path: Path):
    uid, gid = _identity()
    real = tmp_path / "real.py"
    real.write_text("pass\n", encoding="utf-8")
    real.chmod(0o600)
    linked = tmp_path / "linked.py"
    linked.symlink_to(real)
    with pytest.raises(loader.LoaderDenied, match="unsafe"):
        loader._open_candidate(linked, required_uid=uid, required_gid=gid)

    real.chmod(0o622)
    with pytest.raises(loader.LoaderDenied, match="unsafe"):
        loader._open_candidate(real, required_uid=uid, required_gid=gid)


def test_approval_symlink_wrong_mode_and_wrong_owner_are_rejected(tmp_path: Path):
    uid, gid = _identity()
    approval = tmp_path / "approval.json"
    approval.write_text("{}\n", encoding="utf-8")
    approval.chmod(0o600)
    linked = tmp_path / "approval-link.json"
    linked.symlink_to(approval)
    with pytest.raises(loader.LoaderDenied, match="unsafe"):
        loader._read_approval(linked, required_uid=uid, required_gid=gid)

    approval.chmod(0o644)
    with pytest.raises(loader.LoaderDenied, match="unsafe"):
        loader._read_approval(approval, required_uid=uid, required_gid=gid)

    approval.chmod(0o600)
    wrong_uid = uid + 1 if uid != 0 else 1
    with pytest.raises(loader.LoaderDenied, match="unsafe"):
        loader._read_approval(approval, required_uid=wrong_uid, required_gid=gid)


@pytest.mark.parametrize(
    "mutation",
    [
        "expired",
        "missing-bootstrap",
        "extra-artifact",
        "wrong-artifact",
        "boolean-schema-version",
        "boolean-owner-id",
    ],
)
def test_approval_contract_rejects_expiry_and_artifact_drift(mutation: str):
    value = _approval_value("1" * 64)
    hashes = value["artifact_sha256"]
    assert isinstance(hashes, dict)
    if mutation == "expired":
        value["expires_at"] = "2000-01-01T00:00:00Z"
    elif mutation == "missing-bootstrap":
        hashes.pop(loader.BOOTSTRAP_ARTIFACT)
    elif mutation == "extra-artifact":
        hashes["ops/unapproved.py"] = "2" * 64
    elif mutation == "wrong-artifact":
        hashes[loader.BOOTSTRAP_ARTIFACT] = "not-a-canonical-sha256"
    elif mutation == "boolean-schema-version":
        value["schema_version"] = True
    else:
        target = next(iter(loader.TARGET_MODES))
        value["target_preconditions"][target] = {
            "state": "PRESENT",
            "type": "file",
            "sha256": "3" * 64,
            "uid": False,
            "gid": 0,
            "mode": loader.TARGET_MODES[target],
        }

    with pytest.raises(loader.LoaderDenied):
        loader._validate_approval(value)


def test_loader_rejects_wrong_installed_path_and_mode(tmp_path: Path):
    uid, gid = _identity()
    installed = tmp_path / "installed-loader.py"
    installed.write_text("pass\n", encoding="utf-8")
    installed.chmod(0o755)
    with pytest.raises(loader.LoaderDenied, match="fixed installed path"):
        loader._verify_loader(
            tmp_path / "other.py",
            installed_path=installed,
            required_uid=uid,
            required_gid=gid,
        )

    installed.chmod(0o700)
    with pytest.raises(loader.LoaderDenied, match="unsafe"):
        loader._verify_loader(
            installed,
            installed_path=installed,
            required_uid=uid,
            required_gid=gid,
        )

    installed.chmod(0o755)
    wrong_uid = uid + 1 if uid != 0 else 1
    with pytest.raises(loader.LoaderDenied, match="unsafe"):
        loader._verify_loader(
            installed,
            installed_path=installed,
            required_uid=wrong_uid,
            required_gid=gid,
        )


def test_loader_argument_contract_is_exact():
    valid = [
        "--approval",
        str(loader.APPROVAL_PATH),
        "--artifact-key",
        loader.BOOTSTRAP_ARTIFACT,
        "--candidate",
        "/root/checkout/ops/bootstrap_gate08_operational_controls.py",
        "--",
        "--source-repository",
        "/approved/source",
        "--apply",
    ]
    candidate, forwarded = loader._parse_arguments(valid)
    assert candidate == Path(valid[5])
    assert forwarded == ("--source-repository", "/approved/source", "--apply")

    for mutated in (
        [*valid, "--extra"],
        [*valid[:1], "/tmp/approval.json", *valid[2:]],
        [*valid[:3], "ops/other.py", *valid[4:]],
        [*valid[:6], "--wrong", *valid[7:]],
        [*valid[:9], "--dry-run"],
    ):
        with pytest.raises(loader.LoaderDenied, match="fixed contract"):
            loader._parse_arguments(mutated)


def test_stage_hash_mismatch_stops_execution_and_cleans_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    sentinel = tmp_path / "executed"
    approved = (
        "from pathlib import Path\n"
        f"Path({str(sentinel)!r}).write_text('bad', encoding='utf-8')\n"
    ).encode()
    expected = hashlib.sha256(approved).hexdigest()
    original = loader._read_verified_descriptor

    def reject_stage(descriptor: int, claimed: str) -> bytes:
        if Path(f"/dev/fd/{descriptor}").exists():
            raise loader.LoaderDenied("root-private bootstrap stage hash mismatch")
        return original(descriptor, claimed)

    monkeypatch.setattr(loader, "_read_verified_descriptor", reject_stage)
    uid, gid = _identity()
    with pytest.raises(loader.LoaderDenied, match="stage hash mismatch"):
        loader._stage_and_execute(
            approved,
            expected,
            ("--source-repository", "/approved/source", "--apply"),
            run_root=tmp_path,
            required_uid=uid,
            required_gid=gid,
        )
    assert not sentinel.exists()
    assert not list(tmp_path.glob("sealai-operational-loader.*"))


def test_failure_execution_cleans_stage(tmp_path: Path):
    approved = b"raise SystemExit(19)\n"
    expected = hashlib.sha256(approved).hexdigest()
    uid, gid = _identity()
    assert (
        loader._stage_and_execute(
            approved,
            expected,
            ("--source-repository", "/approved/source", "--apply"),
            run_root=tmp_path,
            required_uid=uid,
            required_gid=gid,
        )
        == 19
    )
    assert not list(tmp_path.glob("sealai-operational-loader.*"))


def test_wrapper_has_no_direct_checkout_bootstrap_execution():
    wrapper = (OPS / "install-operational-controls.sh").read_text(encoding="utf-8")
    remediation_installer = (OPS / "install-disk-guard.sh").read_text(encoding="utf-8")
    assert 'exec /usr/bin/python3 -I "${BOOTSTRAP}"' not in wrapper
    assert 'exec "${LOADER}"' in wrapper
    assert str(loader.INSTALLED_LOADER) in wrapper
    assert "--artifact-key ops/bootstrap_gate08_operational_controls.py" in wrapper
    assert "trusted loader unavailable" in wrapper
    assert "ops/hash_verified_python_loader.py" in gate.REMEDIATION_CONTROL_ARTIFACTS
    assert "ops/hash_verified_python_loader.py" in remediation_installer
    assert str(loader.INSTALLED_LOADER) in remediation_installer
    assert '"${STAGE_DIR}/ops/hash_verified_python_loader.py"' in remediation_installer
    assert "regular file:755:root:root" in remediation_installer
    assert f"sha256sum {loader.INSTALLED_LOADER}" in remediation_installer


def test_loader_messages_and_environment_do_not_expose_approval_values():
    source = (OPS / "hash_verified_python_loader.py").read_text(encoding="utf-8")
    marker = "synthetic-never-log-this-value"
    value = _approval_value("1" * 64, owner=marker)
    assert loader._validate_approval(value) == "1" * 64
    assert "print(approval" not in source
    assert "print(raw" not in source
    assert "os.environ" not in source
    assert loader.CHILD_ENV == {
        "HOME": "/root",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "PYTHONNOUSERSITE": "1",
    }
    assert marker not in source
