"""The Stage-A partial recovery is exact, one-shot, and fail closed."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops"
INSTALLER = OPS / "install-disk-guard.sh"
RECOVERY = OPS / "resume-disk-guard-install.sh"
BOOTSTRAP = OPS / "bootstrap_gate08_remediation_resume.py"
RUNBOOK = ROOT / "docs/ops/stage-a-partial-recovery.md"
SCHEMA = OPS / "schemas/gate08-remediation-resume.schema.json"
sys.path.insert(0, str(OPS))

import bootstrap_gate08_remediation_resume as bootstrap  # noqa: E402
import gate08_partial_recovery as recovery  # noqa: E402
import production_release_gate as gate  # noqa: E402


def _artifact_hashes() -> dict[str, str]:
    return {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in sorted(gate.REMEDIATION_RESUME_ARTIFACTS)
    }


def _approval(*, decision: str = "APPROVED") -> dict[str, object]:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    evidence = {
        "sealai-docker-disk-guard.service": (
            "967a4e8b7ec66a589d15fa487eb1e0923835a22a361f4001048430b9442fc780"
        ),
        "sealai-docker-disk-guard.timer": (
            "b2286df5aded8dfb22c37d0b256a97cf9ce8c05fee4d40852d3b5d7594fdf18b"
        ),
        "status-before.json": (
            "5e728b73a68e2cdcb09c0186bb3e0c7f7e7672c5f701cda8d85fd412d26b971d"
        ),
        "status-after.json": (
            "7056c1840fdee27df8c8dbc1bcf12fda9af82a0fcc0bf1a2d8e62dc16d7c3c9b"
        ),
    }
    return {
        "schema_version": 1,
        "gate_id": "GATE-08",
        "operation": "remediation-control-resume",
        "decision": decision,
        "scope": "p0-stage-a-partial-recovery",
        "approval_id": "gate08-stage-a-recovery-test",
        "approved_by": "test-owner",
        "approved_at": now.isoformat().replace("+00:00", "Z"),
        "expires_at": (now + dt.timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "source_git_sha": subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "artifact_sha256": _artifact_hashes(),
        "incident": {
            "failed_source_git_sha": "c905780b54c1f5d27c6c6cea46d12fabdd69ddf8",
            "failed_operation": "remediation-control-install",
            "failure_class": "SYSTEMD_VERIFY_BEFORE_DEPENDENCY_INSTALL",
            "failed_at_phase": ("AFTER_LEGACY_UNIT_RETIREMENT_BEFORE_CRON_RETIREMENT"),
        },
        "legacy_evidence": {
            "evidence_id": recovery.EVIDENCE_ID,
            "evidence_directory": str(recovery.EVIDENCE_DIRECTORY),
            "expected_files": [
                {
                    "path": path,
                    "sha256": digest,
                    "mode": "0600",
                    "uid": 0,
                    "gid": 0,
                }
                for path, digest in sorted(evidence.items())
            ],
        },
        "evidence_status_before_sha256": evidence["status-before.json"],
        "evidence_status_after_sha256": evidence["status-after.json"],
        "legacy_timer_fragment_sha256": evidence["sealai-docker-disk-guard.timer"],
        "legacy_service_fragment_sha256": evidence["sealai-docker-disk-guard.service"],
        "production": {
            "repository": "/home/thorsten/sealai",
            "commit": recovery.PRODUCTION_SHA,
            "worktree_state": "CLEAN",
            "docker_root_dir": "/mnt/sealai-volume/docker-data",
            "backend_container_id": (
                "f029cf6b2e86ac795d6e1d743ff12a7f7984069621207a8dbbc9e425b8474c92"
            ),
            "worker_container_id": (
                "0b934acce68fa60d55be98a8b3f203e9de193230d42e26e0829d3a0822418e92"
            ),
            "backend_image_digest": (
                "sha256:597a75e7cc7b3a1e9e6b99a1ff79db0bdc552d2b4819905d6e31be3b7a723d79"
            ),
            "worker_image_digest": (
                "sha256:597a75e7cc7b3a1e9e6b99a1ff79db0bdc552d2b4819905d6e31be3b7a723d79"
            ),
            "release_freeze_active": True,
            "required_release_gate": "GATE-10",
            "gate10_lift_implemented": False,
        },
        "storage_policy": {
            "path_groups": dict(recovery.STORAGE_PATH_GROUPS),
            "minimum_available_bytes": {
                "rootfs": 16 * 1024 * 1024,
                "runfs": 16 * 1024 * 1024,
                "dockerfs": 64 * 1024 * 1024,
            },
            "minimum_free_inodes": {
                "rootfs": 1024,
                "runfs": 1024,
                "dockerfs": 1024,
            },
            "maximum_usage_percent": {
                "rootfs": 97,
                "runfs": 97,
                "dockerfs": 97,
            },
            "fixed_safety_reserve_bytes": {
                "rootfs": 16 * 1024 * 1024,
                "runfs": 16 * 1024 * 1024,
                "dockerfs": 64 * 1024 * 1024,
            },
        },
        "current_partial_state": {
            "legacy_timer": {
                "load_state": "loaded",
                "active_state": "inactive",
                "unit_file_state": "disabled",
                "fragment_path": str(recovery.LEGACY_FRAGMENTS[recovery.LEGACY_TIMER]),
                "fragment_sha256": evidence["sealai-docker-disk-guard.timer"],
            },
            "legacy_service": {
                "load_state": "loaded",
                "active_state": "failed",
                "unit_file_state": "static",
                "main_pid": 0,
                "control_pid": 0,
                "fragment_path": str(
                    recovery.LEGACY_FRAGMENTS[recovery.LEGACY_SERVICE]
                ),
                "fragment_sha256": evidence["sealai-docker-disk-guard.service"],
            },
            "legacy_cron_exact_count": 1,
        },
        "new_targets": {target: "ABSENT" for target in sorted(recovery.ALL_TARGETS)},
    }


def _statuses(*, after: bool) -> list[dict[str, object]]:
    return [
        {
            "unit_name": recovery.LEGACY_TIMER,
            "load_state": "loaded",
            "active_state": "inactive" if after else "active",
            "unit_file_state": "disabled" if after else "enabled",
            "fragment_path": str(recovery.LEGACY_FRAGMENTS[recovery.LEGACY_TIMER]),
        },
        {
            "unit_name": recovery.LEGACY_SERVICE,
            "load_state": "loaded",
            "active_state": "failed",
            "unit_file_state": "static",
            "fragment_path": str(recovery.LEGACY_FRAGMENTS[recovery.LEGACY_SERVICE]),
        },
    ]


def _unit_output(**properties: object) -> str:
    return "\n".join(f"{name}={value}" for name, value in properties.items())


def _evidence_fixture(tmp_path: Path) -> tuple[dict[str, object], Path]:
    directory = tmp_path / recovery.EVIDENCE_ID
    directory.mkdir(mode=0o700)
    values = {
        "sealai-docker-disk-guard.service": b"[Service]\n",
        "sealai-docker-disk-guard.timer": b"[Timer]\n",
        "status-before.json": (
            json.dumps(_statuses(after=False), sort_keys=True, indent=2) + "\n"
        ).encode(),
        "status-after.json": (
            json.dumps(_statuses(after=True), sort_keys=True, indent=2) + "\n"
        ).encode(),
    }
    approval = _approval()
    expected = []
    for name, raw in sorted(values.items()):
        path = directory / name
        path.write_bytes(raw)
        path.chmod(0o600)
        digest = hashlib.sha256(raw).hexdigest()
        expected.append(
            {"path": name, "sha256": digest, "mode": "0600", "uid": 0, "gid": 0}
        )
    approval["legacy_evidence"] = {
        "evidence_id": recovery.EVIDENCE_ID,
        "evidence_directory": str(recovery.EVIDENCE_DIRECTORY),
        "expected_files": expected,
    }
    by_name = {item["path"]: item["sha256"] for item in expected}
    approval["evidence_status_before_sha256"] = by_name["status-before.json"]
    approval["evidence_status_after_sha256"] = by_name["status-after.json"]
    approval["legacy_timer_fragment_sha256"] = by_name["sealai-docker-disk-guard.timer"]
    approval["legacy_service_fragment_sha256"] = by_name[
        "sealai-docker-disk-guard.service"
    ]
    approval["current_partial_state"]["legacy_timer"]["fragment_sha256"] = by_name[
        "sealai-docker-disk-guard.timer"
    ]
    approval["current_partial_state"]["legacy_service"]["fragment_sha256"] = by_name[
        "sealai-docker-disk-guard.service"
    ]
    return approval, directory


def _stage(tmp_path: Path) -> Path:
    stage = tmp_path / "stage"
    for relative in set(recovery.TARGETS_BY_SOURCE) | {
        "ops/production-release-state.json",
        "ops/production_release_gate.py",
        "ops/schemas/gate08-remediation-resume.schema.json",
    }:
        source = ROOT / relative
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    return stage


def _installed_tree(tmp_path: Path) -> tuple[Path, Path]:
    stage = _stage(tmp_path)
    root = tmp_path / "installed-root"
    root.mkdir(mode=0o700)
    for spec in recovery.TARGET_SPECS:
        target = root / spec.path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        current = target.parent
        while current != root:
            current.chmod(0o755)
            current = current.parent
        shutil.copyfile(stage / spec.source, target)
        target.chmod(int(spec.mode, 8))
    return stage, root


def _storage_snapshots() -> list[dict[str, object]]:
    values = []
    for identity, mount, paths in (
        (1, "/", ["/", "/etc", "/usr/local", "/var/lib/sealai-disk-guard"]),
        (2, "/run", ["/run"]),
        (3, "/mnt/sealai-volume/docker-data", ["/mnt/sealai-volume/docker-data"]),
    ):
        values.append(
            {
                "device_id": identity,
                "filesystem_id": identity,
                "mount_id": identity,
                "device_major_minor": f"0:{identity}",
                "mount_point": mount,
                "paths": paths,
                "total_bytes": 10**10,
                "free_bytes": 5 * 10**9,
                "available_bytes": 4 * 10**9,
                "total_inodes": 10**6,
                "free_inodes": 5 * 10**5,
                "usage_percent": 50,
            }
        )
    return values


def _storage_requirements(required: int = 1024) -> dict[str, dict[str, int]]:
    return {
        group: {"calculated_required_bytes": required}
        for group in recovery.STORAGE_GROUPS
    }


def test_recovery_schema_and_exact_bound_approval_validate():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    approval = _approval()
    jsonschema.validate(approval, schema)
    assert recovery.validate_approval_contract(approval) is approval

    without_optional_usage = _approval()
    del without_optional_usage["storage_policy"]["maximum_usage_percent"]
    jsonschema.validate(without_optional_usage, schema)
    assert recovery.validate_approval_contract(without_optional_usage)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("current_partial_state", "legacy_timer", "active_state"), "active"),
        (("current_partial_state", "legacy_service", "main_pid"), 123),
        (("current_partial_state", "legacy_cron_exact_count"), 0),
        (("production", "commit"), "0" * 40),
        (("production", "release_freeze_active"), False),
        (("production", "gate10_lift_implemented"), True),
        (("storage_policy", "minimum_free_inodes", "rootfs"), 0),
    ],
)
def test_recovery_contract_rejects_nonincident_partial_states(path, value):
    approval = _approval()
    current = approval
    for key in path[:-1]:
        current = current[key]
    current[path[-1]] = value
    with pytest.raises(recovery.RecoveryError):
        recovery.validate_approval_contract(approval)


def test_legacy_evidence_is_exact_private_hashed_and_semantic(tmp_path: Path):
    approval, directory = _evidence_fixture(tmp_path)
    recovery.validate_approval_contract(approval)
    digests = recovery.validate_evidence(
        approval,
        evidence_directory=directory,
        required_uid=os.getuid(),
        required_gid=os.getgid(),
    )
    assert set(digests) == recovery.EVIDENCE_FILES

    (directory / "status-after.json").write_text("[]\n", encoding="utf-8")
    with pytest.raises(recovery.RecoveryError, match="hash drift"):
        recovery.validate_evidence(
            approval,
            evidence_directory=directory,
            required_uid=os.getuid(),
            required_gid=os.getgid(),
        )


def test_status_before_and_after_semantics_cannot_be_relabelled(tmp_path: Path):
    approval, directory = _evidence_fixture(tmp_path)
    before = directory / "status-before.json"
    before.write_text(
        json.dumps(_statuses(after=True), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(before.read_bytes()).hexdigest()
    for item in approval["legacy_evidence"]["expected_files"]:
        if item["path"] == "status-before.json":
            item["sha256"] = digest
    approval["evidence_status_before_sha256"] = digest
    with pytest.raises(recovery.RecoveryError, match="bound transition"):
        recovery.validate_evidence(
            approval,
            evidence_directory=directory,
            required_uid=os.getuid(),
            required_gid=os.getgid(),
        )


def test_timer_accepts_exact_common_properties_without_pid_fields():
    state = recovery._unit_state(
        recovery.LEGACY_TIMER,
        command_runner=lambda _arguments: _unit_output(
            LoadState="loaded",
            ActiveState="inactive",
            UnitFileState="disabled",
            FragmentPath=str(recovery.LEGACY_FRAGMENTS[recovery.LEGACY_TIMER]),
        ),
    )
    assert state == {
        "load_state": "loaded",
        "active_state": "inactive",
        "unit_file_state": "disabled",
        "fragment_path": str(recovery.LEGACY_FRAGMENTS[recovery.LEGACY_TIMER]),
    }
    assert "main_pid" not in state
    assert "control_pid" not in state


def test_timer_queries_only_common_systemd_properties():
    captured = None

    def runner(arguments):
        nonlocal captured
        captured = tuple(arguments)
        return _unit_output(
            LoadState="loaded",
            ActiveState="inactive",
            UnitFileState="disabled",
            FragmentPath=str(recovery.LEGACY_FRAGMENTS[recovery.LEGACY_TIMER]),
        )

    recovery._unit_state(recovery.LEGACY_TIMER, command_runner=runner)
    assert captured == (
        "/usr/bin/systemctl",
        "show",
        "--no-pager",
        "--property=LoadState",
        "--property=ActiveState",
        "--property=UnitFileState",
        "--property=FragmentPath",
        recovery.LEGACY_TIMER,
    )


@pytest.mark.parametrize("missing", ["FragmentPath", "UnitFileState"])
def test_timer_rejects_missing_common_property(missing: str):
    properties = {
        "LoadState": "loaded",
        "ActiveState": "inactive",
        "UnitFileState": "disabled",
        "FragmentPath": str(recovery.LEGACY_FRAGMENTS[recovery.LEGACY_TIMER]),
    }
    del properties[missing]
    with pytest.raises(recovery.RecoveryError, match="query is incomplete"):
        recovery._unit_state(
            recovery.LEGACY_TIMER,
            command_runner=lambda _arguments: _unit_output(**properties),
        )


def test_service_accepts_all_common_and_pid_properties():
    state = recovery._unit_state(
        recovery.LEGACY_SERVICE,
        command_runner=lambda _arguments: _unit_output(
            MainPID="0",
            ControlPID="0",
            LoadState="loaded",
            ActiveState="failed",
            FragmentPath=str(recovery.LEGACY_FRAGMENTS[recovery.LEGACY_SERVICE]),
            UnitFileState="static",
        ),
    )
    assert state == {
        "load_state": "loaded",
        "active_state": "failed",
        "unit_file_state": "static",
        "fragment_path": str(recovery.LEGACY_FRAGMENTS[recovery.LEGACY_SERVICE]),
        "main_pid": 0,
        "control_pid": 0,
    }


def test_service_queries_common_and_pid_systemd_properties():
    captured = None

    def runner(arguments):
        nonlocal captured
        captured = tuple(arguments)
        return _unit_output(
            LoadState="loaded",
            ActiveState="failed",
            UnitFileState="static",
            FragmentPath=str(recovery.LEGACY_FRAGMENTS[recovery.LEGACY_SERVICE]),
            MainPID="0",
            ControlPID="0",
        )

    recovery._unit_state(recovery.LEGACY_SERVICE, command_runner=runner)
    assert captured[-3:] == (
        "--property=MainPID",
        "--property=ControlPID",
        recovery.LEGACY_SERVICE,
    )
    assert captured[3:-3] == tuple(
        f"--property={name}" for name in recovery.COMMON_UNIT_PROPERTIES
    )


@pytest.mark.parametrize("missing", ["MainPID", "ControlPID"])
def test_service_rejects_missing_pid_property(missing: str):
    properties = {
        "LoadState": "loaded",
        "ActiveState": "failed",
        "UnitFileState": "static",
        "FragmentPath": str(recovery.LEGACY_FRAGMENTS[recovery.LEGACY_SERVICE]),
        "MainPID": "0",
        "ControlPID": "0",
    }
    del properties[missing]
    with pytest.raises(recovery.RecoveryError, match="query is incomplete"):
        recovery._unit_state(
            recovery.LEGACY_SERVICE,
            command_runner=lambda _arguments: _unit_output(**properties),
        )


def test_service_rejects_non_numeric_pid():
    with pytest.raises(recovery.RecoveryError, match="PID is invalid"):
        recovery._unit_state(
            recovery.LEGACY_SERVICE,
            command_runner=lambda _arguments: _unit_output(
                LoadState="loaded",
                ActiveState="failed",
                UnitFileState="static",
                FragmentPath=str(recovery.LEGACY_FRAGMENTS[recovery.LEGACY_SERVICE]),
                MainPID="not-a-pid",
                ControlPID="0",
            ),
        )


def test_unknown_unit_name_is_rejected_before_command_execution():
    def unexpected_runner(_arguments):
        pytest.fail("unknown unit reached the command runner")

    with pytest.raises(recovery.RecoveryError, match="unsupported legacy unit"):
        recovery._unit_state("unknown.service", command_runner=unexpected_runner)


def test_validate_live_partial_state_never_reads_timer_pid_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    approval = _approval()
    repository = tmp_path / "production"
    (repository / ".git").mkdir(parents=True)
    monkeypatch.setattr(recovery, "PRODUCTION_REPOSITORY", repository)
    fragment = b"bound legacy fragment\n"
    fragment_hash = hashlib.sha256(fragment).hexdigest()
    approval["current_partial_state"]["legacy_timer"]["fragment_sha256"] = fragment_hash
    approval["current_partial_state"]["legacy_service"]["fragment_sha256"] = (
        fragment_hash
    )

    class TimerState(dict):
        def __getitem__(self, key):
            if key in {"main_pid", "control_pid"}:
                raise AssertionError("timer PID field was read")
            return super().__getitem__(key)

    def unit_state(unit: str):
        if unit == recovery.LEGACY_TIMER:
            return TimerState(
                load_state="loaded",
                active_state="inactive",
                unit_file_state="disabled",
                fragment_path=str(recovery.LEGACY_FRAGMENTS[unit]),
            )
        assert unit == recovery.LEGACY_SERVICE
        return {
            "load_state": "loaded",
            "active_state": "failed",
            "unit_file_state": "static",
            "fragment_path": str(recovery.LEGACY_FRAGMENTS[unit]),
            "main_pid": 0,
            "control_pid": 0,
        }

    def command(arguments):
        if arguments[:3] == ("/usr/bin/git", "-C", str(repository)):
            return (
                recovery.PRODUCTION_SHA
                if arguments[-2:] == ("rev-parse", "HEAD")
                else ""
            )
        if arguments[:2] == ("/usr/bin/docker", "info"):
            return approval["production"]["docker_root_dir"]
        if arguments[:2] == ("/usr/bin/docker", "inspect"):
            name = arguments[-1]
            if name == "backend-v2":
                return "|".join(
                    (
                        approval["production"]["backend_container_id"],
                        approval["production"]["backend_image_digest"],
                    )
                )
            return "|".join(
                (
                    approval["production"]["worker_container_id"],
                    approval["production"]["worker_image_digest"],
                )
            )
        pytest.fail(f"unexpected command: {arguments}")

    def process(arguments, **_kwargs):
        if arguments[0] == "/usr/bin/crontab":
            return SimpleNamespace(
                returncode=0, stdout=recovery.LEGACY_CRON_LINE + "\n"
            )
        assert arguments[0] == "/usr/bin/pgrep"
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr(recovery, "_unit_state", unit_state)
    monkeypatch.setattr(recovery, "_command", command)
    monkeypatch.setattr(recovery, "_read_regular", lambda *_args, **_kwargs: fragment)
    monkeypatch.setattr(
        recovery, "validate_target_preconditions", lambda _targets: None
    )
    monkeypatch.setattr(recovery, "validate_evidence", lambda _approval: {})
    monkeypatch.setattr(recovery.subprocess, "run", process)
    result = recovery.validate_live_partial_state(approval)
    assert result["legacy_cron"] == recovery.LEGACY_CRON_LINE + "\n"


def test_observed_production_timer_without_pid_properties_is_accepted():
    output = "\n".join(
        (
            "LoadState=loaded",
            "ActiveState=inactive",
            "FragmentPath=/etc/systemd/system/sealai-docker-disk-guard.timer",
            "UnitFileState=disabled",
        )
    )
    state = recovery._unit_state(
        recovery.LEGACY_TIMER, command_runner=lambda _arguments: output
    )
    assert state["active_state"] == "inactive"
    assert set(state) == {
        "load_state",
        "active_state",
        "unit_file_state",
        "fragment_path",
    }


def test_observed_production_service_with_zero_pids_is_accepted():
    output = "\n".join(
        (
            "MainPID=0",
            "ControlPID=0",
            "LoadState=loaded",
            "ActiveState=failed",
            "FragmentPath=/etc/systemd/system/sealai-docker-disk-guard.service",
            "UnitFileState=static",
        )
    )
    state = recovery._unit_state(
        recovery.LEGACY_SERVICE, command_runner=lambda _arguments: output
    )
    assert state["main_pid"] == state["control_pid"] == 0


def test_fresh_run_verifies_exact_dependencies_before_first_legacy_mutation():
    source = INSTALLER.read_text(encoding="utf-8")
    synthetic_verify = source.index("validate-stage")
    target_preconditions = source.index("fresh target precondition drift")
    legacy_dry_run = source.index("dry-run", target_preconditions)
    legacy_apply = source.index("apply", legacy_dry_run)
    cron_mutation = source.index('crontab -u "${LEGACY_CRON_USER}" "${CRON_AFTER}"')
    first_live_install = source.index(
        "install -d -m 0755 -o root -g root /usr/local/libexec"
    )
    assert synthetic_verify < target_preconditions < legacy_dry_run < legacy_apply
    assert legacy_apply < cron_mutation < first_live_install
    assert (
        source.index("systemd-analyze verify", first_live_install) > first_live_install
    )


def test_missing_staged_payload_fails_before_any_live_target(tmp_path: Path):
    stage = _stage(tmp_path)
    (stage / "ops/docker-disk-guard.sh").unlink()
    with pytest.raises(recovery.RecoveryError, match="unavailable"):
        recovery.build_synthetic_root(stage, tmp_path / "validation-root")
    assert not (tmp_path / "legacy-retired-sentinel").exists()


def test_synthetic_root_contains_exact_later_installed_bytes(tmp_path: Path):
    stage = _stage(tmp_path)
    root = tmp_path / "validation-root"
    hashes = recovery.build_synthetic_root(stage, root)
    assert recovery.SYNTHETIC_REQUIRED_TARGETS <= set(hashes)
    for spec in recovery.TARGET_SPECS:
        assert (stage / spec.source).read_bytes() == (
            root / spec.path.lstrip("/")
        ).read_bytes()


def test_target_postconditions_are_exact_and_receipt_complete(tmp_path: Path):
    stage, root = _installed_tree(tmp_path)
    targets = recovery.verify_installed_targets(
        stage,
        root=root,
        required_uid=os.getuid(),
        required_gid=os.getgid(),
    )
    assert len(targets) == len(recovery.TARGET_SPECS)
    assert {item["path"] for item in targets} == set(recovery.TARGETS_BY_PATH)
    assert all(
        set(item) == {"path", "sha256", "uid", "gid", "mode"}
        and item["uid"] == os.getuid()
        and item["gid"] == os.getgid()
        and item["mode"] == recovery.TARGETS_BY_PATH[item["path"]].mode
        for item in targets
    )


@pytest.mark.parametrize("drift", ["mode", "symlink", "hash", "ancestor"])
def test_target_postconditions_reject_filesystem_drift(tmp_path: Path, drift: str):
    stage, root = _installed_tree(tmp_path)
    spec = recovery.TARGET_SPECS[0]
    target = root / spec.path.lstrip("/")
    if drift == "mode":
        target.chmod(0o600 if spec.mode != "0600" else 0o644)
    elif drift == "symlink":
        target.unlink()
        target.symlink_to(stage / spec.source)
    elif drift == "hash":
        target.write_bytes(b"drift\n")
        target.chmod(int(spec.mode, 8))
    else:
        target.parent.chmod(0o775)
    with pytest.raises(recovery.RecoveryError):
        recovery.verify_installed_targets(
            stage,
            root=root,
            required_uid=os.getuid(),
            required_gid=os.getgid(),
        )


@pytest.mark.parametrize(("uid_offset", "gid_offset"), [(1, 0), (0, 1)])
def test_target_metadata_rejects_wrong_owner_or_group(uid_offset: int, gid_offset: int):
    spec = recovery.TARGET_SPECS[0]
    metadata = SimpleNamespace(
        st_mode=stat.S_IFREG | int(spec.mode, 8),
        st_uid=os.getuid() + uid_offset,
        st_gid=os.getgid() + gid_offset,
    )
    with pytest.raises(recovery.RecoveryError, match="metadata drift"):
        recovery._validate_target_metadata(
            metadata,
            spec,
            required_uid=os.getuid(),
            required_gid=os.getgid(),
            label="test target",
        )


def test_target_metadata_drift_between_postinstall_and_receipt_fails(tmp_path: Path):
    stage, root = _installed_tree(tmp_path)
    first = recovery.verify_installed_targets(
        stage,
        root=root,
        required_uid=os.getuid(),
        required_gid=os.getgid(),
    )
    spec = recovery.TARGET_SPECS[0]
    (root / spec.path.lstrip("/")).chmod(0o600 if spec.mode != "0600" else 0o644)
    with pytest.raises(recovery.RecoveryError, match="metadata drift"):
        recovery.verify_installed_targets(
            stage,
            root=root,
            required_uid=os.getuid(),
            required_gid=os.getgid(),
        )
    assert first


@pytest.mark.parametrize(
    "failure_step", ["temp_create", "install", "hash", "metadata", "rename", "fsync"]
)
def test_atomic_install_cleans_only_its_temp_on_every_failure(
    tmp_path: Path, failure_step: str
):
    stage = _stage(tmp_path)
    root = tmp_path / "atomic-root"
    root.mkdir(mode=0o700)
    spec = recovery.TARGET_SPECS[0]
    target = root / spec.path.lstrip("/")
    target.parent.mkdir(parents=True, mode=0o755)
    current = target.parent
    while current != root:
        current.chmod(0o755)
        current = current.parent

    def fail_at(
        step: str,
        _spec: recovery.TargetSpec,
        _temporary: Path | None,
        _target: Path,
    ) -> None:
        if step == failure_step:
            raise recovery.RecoveryError(f"simulated {step} failure")

    with pytest.raises(recovery.RecoveryError, match="simulated"):
        recovery.install_target_atomic(
            spec,
            stage,
            root=root,
            required_uid=os.getuid(),
            required_gid=os.getgid(),
            failure_hook=fail_at,
        )
    assert not list(target.parent.glob("*.recovery.*"))
    assert target.exists() is (failure_step == "fsync")


def test_atomic_install_success_keeps_target_and_no_temp(tmp_path: Path):
    stage = _stage(tmp_path)
    root = tmp_path / "atomic-success-root"
    root.mkdir(mode=0o700)
    spec = recovery.TARGET_SPECS[0]
    target = root / spec.path.lstrip("/")
    target.parent.mkdir(parents=True, mode=0o755)
    current = target.parent
    while current != root:
        current.chmod(0o755)
        current = current.parent
    result = recovery.install_target_atomic(
        spec,
        stage,
        root=root,
        required_uid=os.getuid(),
        required_gid=os.getgid(),
    )
    assert target.is_file()
    assert result["path"] == spec.path
    assert not list(target.parent.glob("*.recovery.*"))


def test_atomic_install_failure_preserves_unrelated_file(tmp_path: Path):
    stage = _stage(tmp_path)
    root = tmp_path / "atomic-unrelated-root"
    root.mkdir(mode=0o700)
    spec = recovery.TARGET_SPECS[0]
    target = root / spec.path.lstrip("/")
    target.parent.mkdir(parents=True, mode=0o755)
    current = target.parent
    while current != root:
        current.chmod(0o755)
        current = current.parent
    unrelated = target.parent / ".owner-created.recovery.keep"
    unrelated.write_bytes(b"keep\n")

    def fail_install(
        step: str,
        _spec: recovery.TargetSpec,
        _temporary: Path | None,
        _target: Path,
    ) -> None:
        if step == "install":
            raise recovery.RecoveryError("simulated install failure")

    with pytest.raises(recovery.RecoveryError, match="simulated"):
        recovery.install_target_atomic(
            spec,
            stage,
            root=root,
            required_uid=os.getuid(),
            required_gid=os.getgid(),
            failure_hook=fail_install,
        )
    assert unrelated.read_bytes() == b"keep\n"
    assert not list(target.parent.glob(f".{target.name}.recovery.*"))


@pytest.mark.skipif(
    sys.platform != "linux"
    or not all(
        Path(path).exists()
        for path in (
            "/usr/bin/systemd-analyze",
            "/usr/bin/systemd-tmpfiles",
            "/usr/sbin/visudo",
        )
    ),
    reason="target-version systemd validation requires the Ubuntu CI toolchain",
)
def test_ubuntu_toolchain_verifies_the_synthetic_root(tmp_path: Path):
    result = recovery.validate_stage(
        _stage(tmp_path),
        tmp_path / "validation-root",
        actual_docker_root="/mnt/sealai-volume/docker-data",
    )
    assert recovery.SYNTHETIC_REQUIRED_TARGETS <= set(result["validated_targets"])


def test_target_drift_and_second_recovery_are_rejected(tmp_path: Path):
    targets = {target: "ABSENT" for target in recovery.ALL_TARGETS}
    recovery.validate_target_preconditions(
        targets, path_factory=lambda target: tmp_path / target.lstrip("/")
    )
    existing = tmp_path / sorted(recovery.ALL_TARGETS)[0].lstrip("/")
    existing.parent.mkdir(parents=True)
    existing.write_text("already installed\n", encoding="utf-8")
    with pytest.raises(recovery.RecoveryError, match="TARGET_PRECONDITION_DRIFT"):
        recovery.validate_target_preconditions(
            targets, path_factory=lambda target: tmp_path / target.lstrip("/")
        )


def test_storage_snapshot_collection_deduplicates_shared_filesystems():
    identities = {
        path: 1 if group == "rootfs" else 2 if group == "runfs" else 3
        for path, group in recovery.STORAGE_PATH_GROUPS.items()
    }

    def fake_stat(path: str) -> SimpleNamespace:
        return SimpleNamespace(st_dev=identities[path])

    def fake_statvfs(path: str) -> SimpleNamespace:
        identity = identities[path]
        return SimpleNamespace(
            f_fsid=identity,
            f_frsize=4096,
            f_bsize=4096,
            f_blocks=1_000_000,
            f_bfree=500_000,
            f_bavail=400_000,
            f_files=1_000_000,
            f_ffree=500_000,
        )

    def fake_mount(path: str) -> dict[str, object]:
        identity = identities[path]
        return {
            "mount_id": identity,
            "device_major_minor": f"0:{identity}",
            "mount_point": next(
                mount
                for group_identity, mount in (
                    (1, "/"),
                    (2, "/run"),
                    (3, "/mnt/sealai-volume/docker-data"),
                )
                if group_identity == identity
            ),
        }

    snapshots = recovery.collect_filesystem_snapshots(
        tuple(recovery.STORAGE_PATH_GROUPS),
        stat_fn=fake_stat,
        statvfs_fn=fake_statvfs,
        mount_resolver=fake_mount,
    )
    assert len(snapshots) == 3
    rootfs = next(item for item in snapshots if item["mount_id"] == 1)
    assert rootfs["paths"] == [
        "/",
        "/etc",
        "/usr/local",
        "/var/lib/sealai-disk-guard",
    ]


def test_storage_preflight_rejects_wrong_mount_binding():
    approval = _approval()
    snapshots = _storage_snapshots()
    snapshots[0]["paths"].remove("/etc")
    misplaced = dict(snapshots[0])
    misplaced.update(
        {
            "device_id": 4,
            "filesystem_id": 4,
            "mount_id": 4,
            "device_major_minor": "0:4",
            "mount_point": "/etc",
            "paths": ["/etc"],
        }
    )
    with pytest.raises(recovery.RecoveryError, match="STORAGE_PREFLIGHT_FAILED"):
        recovery.validate_storage_snapshots(
            approval, [*snapshots, misplaced], _storage_requirements()
        )


@pytest.mark.parametrize("metric", ["available_bytes", "free_inodes"])
def test_storage_preflight_rejects_insufficient_capacity(metric: str):
    approval = _approval()
    snapshots = _storage_snapshots()
    snapshots[0][metric] = 0
    with pytest.raises(recovery.RecoveryError, match="STORAGE_PREFLIGHT_FAILED"):
        recovery.validate_storage_snapshots(
            approval, snapshots, _storage_requirements()
        )


def test_storage_preflight_rejects_docker_root_drift(tmp_path: Path):
    with pytest.raises(recovery.RecoveryError, match="STORAGE_PREFLIGHT_FAILED"):
        recovery.run_storage_preflight(
            _approval(),
            tmp_path,
            actual_docker_root="/var/lib/docker",
        )


def test_storage_preflight_accepts_calculated_reserve_and_records_components():
    approval = _approval()
    requirements = recovery.calculate_storage_requirements(ROOT, approval)
    result = recovery.validate_storage_snapshots(
        approval, _storage_snapshots(), requirements
    )
    assert len(result["filesystems"]) == 3
    assert {
        "private_stage_bytes",
        "synthetic_validation_root_bytes",
        "target_installation_bytes",
        "rollback_bytes",
        "transaction_and_cron_evidence_bytes",
        "fixed_safety_reserve_bytes",
        "calculated_required_bytes",
    } <= set(requirements["rootfs"])
    assert (
        requirements["rootfs"]["calculated_required_bytes"]
        > requirements["rootfs"]["fixed_safety_reserve_bytes"]
    )


def test_release_gate_allows_only_exact_hash_bound_recovery(tmp_path: Path):
    approval = _approval()
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(approval) + "\n", encoding="utf-8")
    path.chmod(0o600)
    decision = gate.evaluate(
        "remediation-control-resume",
        remediation_resume_approval_path=path,
        require_versioned=False,
    )
    assert decision.allowed is True
    assert decision.required_gate == "GATE-08"
    assert decision.reason == "gate08_hash_bound_remediation_control_resume"
    assert decision.artifact_sha256 == approval["artifact_sha256"]

    approval["artifact_sha256"][sorted(approval["artifact_sha256"])[0]] = "0" * 64
    path.write_text(json.dumps(approval) + "\n", encoding="utf-8")
    with pytest.raises(gate.GateConfigurationError, match="hash mismatch"):
        gate.evaluate(
            "remediation-control-resume",
            remediation_resume_approval_path=path,
            require_versioned=False,
        )


def test_recovery_runner_never_repeats_legacy_retirement_or_fallback():
    source = RECOVERY.read_text(encoding="utf-8")
    assert "gate08_legacy_unit_retirement.py" not in source
    assert "systemctl stop sealai-docker-disk-guard.timer" not in source
    assert "systemctl disable sealai-docker-disk-guard.timer" not in source
    assert "RECOVERY_FAILED_BEFORE_CRON_RETIREMENT" in source
    assert "RECOVERY_PARTIAL_STOPPED_NO_DESTRUCTIVE_FALLBACK" in source
    assert "rollback_before_cron" in source
    assert source.count("LEGACY_CRON_LINE=") == 1
    assert 'crontab -u "${LEGACY_CRON_USER}" "${CRON_AFTER}"' in source
    assert 'crontab -u "${LEGACY_CRON_USER}" "${CRON_BEFORE}"' not in source
    assert "atomic_install()" not in source
    assert source.count("install-targets --stage-dir") == 1
    assert source.count("verify-targets --stage-dir") == 2
    assert 'target_value.get("targets")' in source
    assert '{"path", "sha256", "uid", "gid", "mode"}' in source


def test_pre_cron_rollback_uses_manifest_and_refuses_hash_drift(tmp_path: Path):
    source = RECOVERY.read_text(encoding="utf-8")
    function = source[source.index("rollback_before_cron()") :]
    block = re.search(r"<<'PY'\n(.*?)\nPY", function, re.DOTALL)
    assert block is not None
    rollback = block.group(1)
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.write_bytes(b"first\n")
    second.write_bytes(b"second\n")
    hashes = {
        str(first): hashlib.sha256(first.read_bytes()).hexdigest(),
        str(second): hashlib.sha256(second.read_bytes()).hexdigest(),
    }
    manifest = tmp_path / "rollback.json"
    manifest.write_text(
        json.dumps(
            {
                "operation": "remediation-control-resume",
                "legacy_reactivation_allowed": False,
                "cron_reactivation_allowed": False,
                "target_preconditions": {path: "ABSENT" for path in hashes},
                "staged_target_sha256": hashes,
            }
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-I", "-", str(manifest)],
        input=rollback,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert not first.exists()
    assert not second.exists()

    first.write_bytes(b"drifted\n")
    result = subprocess.run(
        [sys.executable, "-I", "-", str(manifest)],
        input=rollback,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert first.exists()


def test_recovery_phase_order_is_fail_closed():
    source = RECOVERY.read_text(encoding="utf-8")
    positions = [source.index(f"# R{phase}:") for phase in range(8)]
    assert positions == sorted(positions)
    assert source.index("systemd-analyze verify", positions[4]) < positions[5]
    assert source.index("systemctl daemon-reload") > positions[5]
    assert source.index("systemctl enable --now") > positions[5]
    storage = source.index("storage-preflight --approval")
    lock = source.index("exec 8>/run/lock/sealai-stage-a-recovery.lock")
    private_stage = source.index(
        'STAGE_DIR="$(mktemp -d /run/sealai-remediation-resume.XXXXXX)"'
    )
    assert storage < lock < private_stage


def test_bootstrap_has_fixed_gate_runner_and_no_direct_checkout_fallback():
    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert '"remediation-control-resume"' in source
    assert 'RUNNER_ARTIFACT = "ops/resume-disk-guard-install.sh"' in source
    assert "gate08_legacy_unit_retirement" not in source
    assert "shell=True" not in source
    assert "--no-local" in source
    assert "--no-recurse-submodules" in source
    assert '"GIT_ALLOW_PROTOCOL": "file"' in source
    assert "protocol.file.allow=always" in source
    assert "--source-repository ABSOLUTE_LOCAL_PATH --apply" in source


def test_bootstrap_rejects_pending_wrong_source_and_missing_trust_hash():
    approval = _approval(decision="PENDING_OWNER_APPROVAL")
    with pytest.raises(bootstrap.BootstrapDenied):
        bootstrap._validate_receipt(approval)
    approval = _approval()
    approval["source_git_sha"] = "wrong"
    with pytest.raises(bootstrap.BootstrapDenied):
        bootstrap._validate_receipt(approval)
    approval = _approval()
    del approval["artifact_sha256"][bootstrap.RUNNER_ARTIFACT]
    with pytest.raises(bootstrap.BootstrapDenied):
        bootstrap._validate_receipt(approval)


def test_documented_candidate_loader_is_hash_before_exec_and_toc_tou_safe():
    source = RUNBOOK.read_text(encoding="utf-8")
    block = re.search(
        r"```bash\n(set -Eeuo pipefail.*?)/usr/bin/python3 -I \"\$\{STAGED_BOOTSTRAP\}\" \\\n+  --source-repository.*?\n```",
        source,
        re.DOTALL,
    )
    assert block is not None
    loader = block.group(1)
    syntax = subprocess.run(
        ["/bin/bash", "-n"], input=loader, text=True, capture_output=True
    )
    assert syntax.returncode == 0, syntax.stderr
    opened = loader.index("source_fd = os.open(candidate, flags)")
    copied = loader.index("os.read(source_fd", opened)
    compared = loader.index("hmac.compare_digest", copied)
    executable = loader.index('/usr/bin/chmod 0700 "${STAGED_BOOTSTRAP}"', compared)
    assert opened < copied < compared < executable
    assert 'getattr(os, "O_NOFOLLOW", 0)' in loader
    assert "source_stat.st_uid != 0" in loader
    assert "stat.S_IMODE(source_stat.st_mode) != 0o600" in loader
    assert '"${CANDIDATE_BOOTSTRAP}"' not in loader[executable:]


def test_shell_and_python_entrypoints_compile():
    for path in (INSTALLER, RECOVERY, OPS / "production-release-gate-check.sh"):
        result = subprocess.run(
            ["/bin/bash", "-n", str(path)], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
    for path in (BOOTSTRAP, OPS / "gate08_partial_recovery.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
