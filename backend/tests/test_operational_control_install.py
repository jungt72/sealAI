from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops"
sys.path.insert(0, str(OPS))

import bootstrap_gate08_operational_controls as bootstrap  # noqa: E402
import credential_cutover as cutover  # noqa: E402
import permission_manifest as permissions  # noqa: E402
import production_release_gate as gate  # noqa: E402


def _approval(path: Path, **overrides: object) -> Path:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    head = subprocess_git("rev-parse", "HEAD")
    value: dict[str, object] = {
        "schema_version": 1,
        "gate_id": "GATE-08",
        "operation": "operational-control-install",
        "decision": "APPROVED",
        "scope": "p0-operational-control-install",
        "approval_id": "gate08-operational-test",
        "owner": "test-owner",
        "approved_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_git_sha": head,
        "artifact_sha256": {
            relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for relative in sorted(gate.OPERATIONAL_CONTROL_ARTIFACTS)
        },
        "install_targets": dict(gate.OPERATIONAL_CONTROL_TARGETS),
        "target_preconditions": {
            target: {"state": "ABSENT"}
            for target in gate.OPERATIONAL_CONTROL_TARGETS.values()
        },
    }
    value.update(overrides)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def subprocess_git(*arguments: str) -> str:
    import subprocess

    return subprocess.run(
        ["/usr/bin/git", "-C", str(ROOT), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_release_gate_allows_only_exact_operational_control_install(tmp_path: Path):
    approval = _approval(tmp_path / "approval.json")
    schema = json.loads(
        (OPS / "schemas/gate08-operational-controls.schema.json").read_text()
    )
    jsonschema.Draft202012Validator(schema).validate(
        json.loads(approval.read_text(encoding="utf-8"))
    )
    decision = gate.evaluate(
        "operational-control-install",
        operational_approval_path=approval,
        require_versioned=False,
    )
    assert decision.allowed is True
    assert decision.required_gate == "GATE-08"
    assert decision.reason == "gate08_hash_bound_operational_control_install"
    assert decision.install_targets == gate.OPERATIONAL_CONTROL_TARGETS
    assert decision.target_preconditions == {
        target: {"state": "ABSENT"}
        for target in gate.OPERATIONAL_CONTROL_TARGETS.values()
    }
    assert gate.GATE10_LIFT_IMPLEMENTED is True  # owner decision, 2026-07-21
    assert "operational-control-install" not in gate.MUTATING_OPERATIONS
    for operation in sorted(gate.MUTATING_OPERATIONS):
        with pytest.raises(gate.GateDenied):
            gate.evaluate(operation, require_versioned=False)


@pytest.mark.parametrize("mutation", ["source", "hash", "extra", "missing", "expired"])
def test_release_gate_rejects_operational_approval_drift(tmp_path: Path, mutation: str):
    approval = _approval(tmp_path / "approval.json")
    value = json.loads(approval.read_text(encoding="utf-8"))
    if mutation == "source":
        value["source_git_sha"] = "0" * 40
    elif mutation == "hash":
        first = sorted(value["artifact_sha256"])[0]
        value["artifact_sha256"][first] = "0" * 64
    elif mutation == "extra":
        value["artifact_sha256"]["ops/unapproved"] = "0" * 64
    elif mutation == "missing":
        value["artifact_sha256"].pop(next(iter(value["artifact_sha256"])))
    else:
        value["expires_at"] = "2000-01-01T00:00:00Z"
    approval.write_text(json.dumps(value) + "\n", encoding="utf-8")
    with pytest.raises(gate.GateConfigurationError):
        gate.evaluate(
            "operational-control-install",
            operational_approval_path=approval,
            require_versioned=False,
        )


def test_release_gate_rejects_extra_target_and_unsafe_existing_target(
    tmp_path: Path,
):
    approval = _approval(tmp_path / "approval.json")
    value = json.loads(approval.read_text(encoding="utf-8"))
    value["install_targets"]["ops/extra"] = "/usr/local/bin/extra"
    approval.write_text(json.dumps(value) + "\n", encoding="utf-8")
    with pytest.raises(gate.GateConfigurationError, match="target set"):
        gate.evaluate(
            "operational-control-install",
            operational_approval_path=approval,
            require_versioned=False,
        )
    _approval(approval)
    value = json.loads(approval.read_text(encoding="utf-8"))
    target = next(iter(value["target_preconditions"]))
    value["target_preconditions"][target] = {
        "state": "PRESENT",
        "type": "file",
        "sha256": "1" * 64,
        "uid": 0,
        "gid": 0,
        "mode": "0777",
    }
    approval.write_text(json.dumps(value) + "\n", encoding="utf-8")
    with pytest.raises(gate.GateConfigurationError, match="unsafe"):
        gate.evaluate(
            "operational-control-install",
            operational_approval_path=approval,
            require_versioned=False,
        )


def _stage_and_specs(tmp_path: Path) -> tuple[Path, tuple[bootstrap.TargetSpec, ...]]:
    stage = tmp_path / "stage"
    stage.mkdir(mode=0o700, parents=True)
    sources = ("program-a", "program-b", "schema-a", "schema-b")
    target_modes = (0o755, 0o755, 0o644, 0o644)
    specs: list[bootstrap.TargetSpec] = []
    for index, (source, mode) in enumerate(zip(sources, target_modes, strict=True)):
        source_path = stage / source
        source_path.write_text(f"approved-{source}\n", encoding="utf-8")
        source_path.chmod(0o600)
        target = tmp_path / "targets" / ("bin" if index < 2 else "schemas") / source
        specs.append(bootstrap.TargetSpec(source, target, mode))
    return stage, tuple(specs)


def _absent_preconditions(
    specs: tuple[bootstrap.TargetSpec, ...],
) -> dict[str, dict[str, object]]:
    return {str(spec.target): {"state": "ABSENT"} for spec in specs}


def _install(
    tmp_path: Path,
    stage: Path,
    specs: tuple[bootstrap.TargetSpec, ...],
    preconditions: dict[str, dict[str, object]],
    *,
    fault_after: int | None = None,
) -> dict[str, object]:
    return bootstrap.install_from_stage(
        stage,
        specs,
        preconditions,
        approval_id="approval-test",
        owner="test-owner",
        source_sha="a" * 40,
        rollback_root=tmp_path / "evidence" / "rollbacks",
        receipt_root=tmp_path / "evidence" / "receipts",
        required_uid=os.geteuid(),
        required_gid=os.getegid(),
        fault_after=fault_after,
    )


def test_atomic_install_writes_fixed_modes_rollback_and_redacted_receipt(
    tmp_path: Path,
):
    stage, specs = _stage_and_specs(tmp_path)
    receipt = _install(tmp_path, stage, specs, _absent_preconditions(specs))
    assert set(receipt) == {
        "schema_version",
        "operation",
        "required_gate",
        "approval_id",
        "owner",
        "source_git_sha",
        "installed_at",
        "rollback_evidence_id",
        "targets",
    }
    for spec in specs:
        assert spec.target.read_text(encoding="utf-8") == f"approved-{spec.source}\n"
        assert stat.S_IMODE(spec.target.stat().st_mode) == spec.mode
    receipt_files = list((tmp_path / "evidence" / "receipts").iterdir())
    assert len(receipt_files) == 1
    assert stat.S_IMODE(receipt_files[0].stat().st_mode) == 0o600
    serialized = receipt_files[0].read_text(encoding="utf-8")
    assert "credential" not in serialized.lower()
    assert "token" not in serialized.lower()


def test_partial_install_rolls_back_absent_targets(tmp_path: Path):
    stage, specs = _stage_and_specs(tmp_path)
    with pytest.raises(bootstrap.BootstrapDenied, match="rolled back"):
        _install(
            tmp_path,
            stage,
            specs,
            _absent_preconditions(specs),
            fault_after=2,
        )
    assert all(not spec.target.exists() for spec in specs)


def test_partial_install_restores_existing_targets(tmp_path: Path):
    stage, specs = _stage_and_specs(tmp_path)
    preconditions: dict[str, dict[str, object]] = {}
    for spec in specs:
        spec.target.parent.mkdir(parents=True, exist_ok=True)
        spec.target.write_text(f"previous-{spec.source}\n", encoding="utf-8")
        spec.target.chmod(spec.mode)
        preconditions[str(spec.target)] = {
            "state": "PRESENT",
            "type": "file",
            "sha256": hashlib.sha256(spec.target.read_bytes()).hexdigest(),
            "uid": os.geteuid(),
            "gid": os.getegid(),
            "mode": f"0{spec.mode:03o}",
        }
    with pytest.raises(bootstrap.BootstrapDenied, match="rolled back"):
        _install(tmp_path, stage, specs, preconditions, fault_after=3)
    for spec in specs:
        assert spec.target.read_text(encoding="utf-8") == f"previous-{spec.source}\n"
        assert stat.S_IMODE(spec.target.stat().st_mode) == spec.mode


def test_target_drift_and_symlink_stop_before_install(tmp_path: Path):
    stage, specs = _stage_and_specs(tmp_path)
    first = specs[0]
    first.target.parent.mkdir(parents=True)
    first.target.write_text("drift\n", encoding="utf-8")
    first.target.chmod(first.mode)
    with pytest.raises(bootstrap.BootstrapDenied, match="fingerprint drift"):
        _install(tmp_path, stage, specs, _absent_preconditions(specs))
    assert first.target.read_text(encoding="utf-8") == "drift\n"

    first.target.unlink()
    first.target.symlink_to(stage / first.source)
    with pytest.raises(bootstrap.BootstrapDenied, match="unsafe"):
        _install(tmp_path, stage, specs, _absent_preconditions(specs))


def test_source_symlink_and_unsafe_target_mode_are_rejected(tmp_path: Path):
    stage, specs = _stage_and_specs(tmp_path)
    source = stage / specs[0].source
    approved_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    real_source = stage / "real-source"
    source.replace(real_source)
    source.symlink_to(real_source)
    with pytest.raises(bootstrap.BootstrapDenied, match="unsafe"):
        bootstrap._copy_verified(
            source,
            stage / "copied",
            approved_hash,
            required_uid=os.geteuid(),
        )

    stage, specs = _stage_and_specs(tmp_path / "unsafe-target")
    target = specs[0].target
    target.parent.mkdir(parents=True)
    target.write_text("unsafe\n", encoding="utf-8")
    target.chmod(0o777)
    preconditions = _absent_preconditions(specs)
    preconditions[str(target)] = {
        "state": "PRESENT",
        "type": "file",
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "uid": os.geteuid(),
        "gid": os.getegid(),
        "mode": "0777",
    }
    with pytest.raises(bootstrap.BootstrapDenied, match="unsafe"):
        _install(tmp_path / "unsafe-target", stage, specs, preconditions)


def test_failed_rollback_disables_exact_installed_control(monkeypatch, tmp_path: Path):
    stage, specs = _stage_and_specs(tmp_path)

    def rollback_failure(*args, **kwargs):
        raise bootstrap.BootstrapDenied("synthetic rollback failure")

    monkeypatch.setattr(bootstrap, "_rollback_targets", rollback_failure)
    with pytest.raises(bootstrap.BootstrapDenied, match="controls disabled"):
        _install(
            tmp_path,
            stage,
            specs,
            _absent_preconditions(specs),
            fault_after=1,
        )
    assert specs[0].target.exists()
    assert stat.S_IMODE(specs[0].target.stat().st_mode) == 0


def test_controls_accept_only_their_fixed_installed_paths(monkeypatch):
    def fake_lstat(path: Path) -> os.stat_result:
        leaf = path in {cutover.INSTALLED_CONTROL, permissions.INSTALLED_CONTROL}
        mode = (stat.S_IFREG | 0o755) if leaf else (stat.S_IFDIR | 0o755)
        values = [mode, 1, 1, 1, 0, 0, 0, 0, 0, 0]
        return os.stat_result(values)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    cutover._assert_installed_control(cutover.INSTALLED_CONTROL)
    permissions._assert_installed_control(permissions.INSTALLED_CONTROL)
    with pytest.raises(cutover.CredentialCutoverError):
        cutover._assert_installed_control(ROOT / "ops/credential_cutover.py")
    with pytest.raises(permissions.PermissionManifestError):
        permissions._assert_installed_control(ROOT / "ops/permission_manifest.py")


def test_bootstrap_and_installer_do_not_emit_private_approval_values():
    source = (OPS / "bootstrap_gate08_operational_controls.py").read_text()
    installer = (OPS / "install-operational-controls.sh").read_text()
    assert "print(approval" not in source
    assert "print(raw" not in source
    assert "cat " not in installer
    assert "docker" not in installer.lower()
    assert "systemctl" not in installer
    assert 'line.startswith("160000 ")' in source
    assert 'line.startswith("120000 ")' in source
