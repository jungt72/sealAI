from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import shlex
import stat
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "ops" / "docker_disk_guard.py"
SPEC = importlib.util.spec_from_file_location("docker_disk_guard", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
guard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = guard
SPEC.loader.exec_module(guard)


def _write_config(tmp_path: Path, **overrides: object) -> tuple[Path, Path, Path]:
    state_dir = tmp_path / "state"
    lock_file = tmp_path / "runtime" / "guard.lock"
    config = {
        "version": 1,
        "volume": str(tmp_path / "volume"),
        "docker_root_dir": str(tmp_path / "volume" / "docker"),
        "state_dir": str(state_dir),
        "lock_file": str(lock_file),
    }
    config.update(overrides)
    config_path = tmp_path / "guard.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    os.chmod(config_path, 0o600)
    return config_path, state_dir, lock_file


def _run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    config_path: Path,
    usage: int,
    command: str = "check",
    *,
    dry_run: bool = False,
) -> tuple[int, dict[str, object]]:
    monkeypatch.setattr(
        guard, "_observe_usage_percent", lambda _volume, _docker_root: usage
    )
    arguments = ["--config", str(config_path)]
    if dry_run:
        arguments.append("--dry-run")
    arguments.append(command)
    exit_code = guard.main(arguments)
    output = capsys.readouterr().out.strip()
    assert len(output.splitlines()) == 1
    return exit_code, json.loads(output)


@pytest.mark.parametrize(
    ("usage", "latched", "expected"),
    [
        (74, False, ("healthy", False)),
        (75, False, ("warning", False)),
        (84, False, ("warning", False)),
        (85, False, ("critical", True)),
        (81, True, ("recovering", True)),
        (80, True, ("warning", False)),
        (74, True, ("healthy", False)),
    ],
)
def test_fixed_thresholds_and_critical_hysteresis(
    usage: int, latched: bool, expected: tuple[str, bool]
) -> None:
    assert guard._classify(usage, latched) == expected


def test_check_writes_only_redacted_bounded_spools_with_strict_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, state_dir, _lock_file = _write_config(tmp_path)

    exit_code, payload = _run(monkeypatch, capsys, config_path, 75)

    assert exit_code == guard.EXIT_WARNING
    assert payload["status"] == "warning"
    assert payload["state_written"] is True
    assert payload["alert_written"] is True
    assert payload["external_alert_delivery"] == "BLOCKED_EXTERNAL"
    rendered = json.dumps(payload)
    assert str(tmp_path) not in rendered
    assert stat.S_IMODE(state_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((state_dir / "alerts").stat().st_mode) == 0o700
    assert stat.S_IMODE((state_dir / "state.json").stat().st_mode) == 0o600
    assert stat.S_IMODE((state_dir / "alerts" / "latest.json").stat().st_mode) == 0o600
    assert str(tmp_path) not in (state_dir / "state.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in (state_dir / "alerts" / "latest.json").read_text(
        encoding="utf-8"
    )
    alert = json.loads(
        (state_dir / "alerts" / "latest.json").read_text(encoding="utf-8")
    )
    assert alert["external_alert_delivery"] == "BLOCKED_EXTERNAL"
    assert sorted(path.name for path in (state_dir / "alerts").iterdir()) == [
        "latest.json"
    ]


def test_dry_run_does_not_create_or_modify_state_or_alert_spools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, state_dir, lock_file = _write_config(tmp_path)

    exit_code, payload = _run(monkeypatch, capsys, config_path, 85, dry_run=True)

    assert exit_code == guard.EXIT_CRITICAL
    assert payload["state_written"] is False
    assert payload["alert_written"] is False
    assert not state_dir.exists()
    assert lock_file.is_file()
    assert stat.S_IMODE(lock_file.stat().st_mode) == 0o600


def test_critical_latch_survives_until_recovery_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, state_dir, _lock_file = _write_config(tmp_path)
    first_exit, _ = _run(monkeypatch, capsys, config_path, 85)
    second_exit, second = _run(monkeypatch, capsys, config_path, 81)
    third_exit, third = _run(monkeypatch, capsys, config_path, 80)

    assert first_exit == guard.EXIT_CRITICAL
    assert second_exit == guard.EXIT_CRITICAL
    assert second["status"] == "recovering"
    assert second["critical_latched"] is True
    assert third_exit == guard.EXIT_WARNING
    assert third["status"] == "warning"
    assert third["critical_latched"] is False
    assert len(list((state_dir / "alerts").iterdir())) == 1


def test_assert_stable_is_read_only_and_honors_existing_latch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, state_dir, _lock_file = _write_config(tmp_path)
    _run(monkeypatch, capsys, config_path, 85)
    before = (state_dir / "state.json").read_bytes()

    exit_code, payload = _run(
        monkeypatch, capsys, config_path, 82, command="assert-stable"
    )

    assert exit_code == guard.EXIT_ASSERT_UNSTABLE
    assert payload["result"] == "blocked"
    assert payload["status"] == "recovering"
    assert (state_dir / "state.json").read_bytes() == before


def test_preflight_requires_fresh_healthy_monitor_state_and_current_sample(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, state_dir, _lock_file = _write_config(tmp_path)
    _run(monkeypatch, capsys, config_path, 40)
    state_file = state_dir / "state.json"
    before = state_file.read_bytes()

    allowed_exit, allowed = _run(
        monkeypatch, capsys, config_path, 40, command="preflight"
    )
    assert allowed_exit == guard.EXIT_OK
    assert allowed["reason_code"] == "preflight_passed"
    assert state_file.read_bytes() == before

    state = json.loads(state_file.read_text(encoding="utf-8"))
    stale = guard._utc_now() - timedelta(
        seconds=guard.PREFLIGHT_STATE_MAX_AGE_SECONDS + 1
    )
    state["observed_at"] = guard._timestamp(stale)
    state_file.write_text(json.dumps(state), encoding="utf-8")
    os.chmod(state_file, 0o600)
    blocked_exit, blocked = _run(
        monkeypatch, capsys, config_path, 40, command="preflight"
    )
    assert blocked_exit == guard.EXIT_PREFLIGHT_BLOCKED
    assert blocked["reason_code"] == "monitor_state_stale"


@pytest.mark.parametrize("command", ["assert-stable", "preflight"])
def test_sustainable_target_allows_eighty_percent_for_both_samples(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, _state_dir, _lock_file = _write_config(tmp_path)
    check_exit, check = _run(monkeypatch, capsys, config_path, 80)
    gate_exit, gate = _run(monkeypatch, capsys, config_path, 80, command=command)

    assert check_exit == guard.EXIT_WARNING
    assert check["status"] == "warning"
    assert check["critical_latched"] is False
    assert gate_exit == guard.EXIT_OK
    assert gate["result"] == "ok"
    assert gate["usage_percent"] == 80
    assert gate["critical_latched"] is False


@pytest.mark.parametrize("command", ["assert-stable", "preflight"])
def test_sustainable_target_blocks_current_eighty_one_after_prior_eighty(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, _state_dir, _lock_file = _write_config(tmp_path)
    check_exit, check = _run(monkeypatch, capsys, config_path, 80)
    gate_exit, gate = _run(monkeypatch, capsys, config_path, 81, command=command)

    expected_exit = (
        guard.EXIT_ASSERT_UNSTABLE
        if command == "assert-stable"
        else guard.EXIT_PREFLIGHT_BLOCKED
    )
    assert check_exit == guard.EXIT_WARNING
    assert check["status"] == "warning"
    assert check["critical_latched"] is False
    assert gate_exit == expected_exit
    assert gate["result"] == "blocked"
    assert gate["reason_code"] == "current_state_above_recovery_target"


@pytest.mark.parametrize("command", ["assert-stable", "preflight"])
def test_sustainable_target_blocks_eighty_four_without_prior_critical_latch(
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, _state_dir, _lock_file = _write_config(tmp_path)
    check_exit, check = _run(monkeypatch, capsys, config_path, 84)
    gate_exit, gate = _run(monkeypatch, capsys, config_path, 84, command=command)

    expected_exit = (
        guard.EXIT_ASSERT_UNSTABLE
        if command == "assert-stable"
        else guard.EXIT_PREFLIGHT_BLOCKED
    )
    assert check_exit == guard.EXIT_WARNING
    assert check["status"] == "warning"
    assert check["critical_latched"] is False
    assert gate_exit == expected_exit
    assert gate["result"] == "blocked"
    assert gate["reason_code"] == "monitor_state_above_recovery_target"


def test_malformed_or_insecure_state_fails_closed_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, state_dir, _lock_file = _write_config(tmp_path)
    state_dir.mkdir(mode=0o700)
    state_file = state_dir / "state.json"
    state_file.write_text("not-json\n", encoding="utf-8")
    os.chmod(state_file, 0o600)
    before = state_file.read_bytes()

    exit_code, payload = _run(monkeypatch, capsys, config_path, 10)

    assert exit_code == guard.EXIT_CONFIG
    assert payload["result"] == "error"
    assert payload["reason_code"] == "invalid_json"
    assert state_file.read_bytes() == before
    assert str(tmp_path) not in json.dumps(payload)

    state_file.write_text("{}", encoding="utf-8")
    os.chmod(state_file, 0o644)
    exit_code, payload = _run(monkeypatch, capsys, config_path, 10)
    assert exit_code == guard.EXIT_CONFIG
    assert payload["reason_code"] == "unsafe_file_permissions"


def test_state_and_alert_directories_require_the_effective_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / "state"
    alert_dir = state_dir / "alerts"
    alert_dir.mkdir(parents=True, mode=0o700)
    os.chmod(state_dir, 0o700)
    os.chmod(alert_dir, 0o700)
    real_euid = os.geteuid()
    monkeypatch.setattr(guard.os, "geteuid", lambda: real_euid + 1)

    for directory in (state_dir, alert_dir):
        with pytest.raises(guard.GuardError, match="unsafe_state_spool_owner"):
            guard._require_secure_directory(directory, create=False)


def test_atomic_state_write_stays_bound_to_the_validated_directory_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_dir = tmp_path / "state"
    moved_state_dir = tmp_path / "validated-state"
    state_dir.mkdir(mode=0o700)
    os.chmod(state_dir, 0o700)
    real_replace = os.replace
    swapped = False

    def swap_directory_then_replace(
        source: str,
        destination: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal swapped
        assert src_dir_fd is not None
        assert dst_dir_fd == src_dir_fd
        if not swapped:
            state_dir.rename(moved_state_dir)
            state_dir.mkdir(mode=0o700)
            os.chmod(state_dir, 0o700)
            swapped = True
        real_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(guard.os, "replace", swap_directory_then_replace)

    guard._atomic_write_json(state_dir / "state.json", {"safe": True})

    assert swapped is True
    assert json.loads((moved_state_dir / "state.json").read_text(encoding="utf-8")) == {
        "safe": True
    }
    assert not (state_dir / "state.json").exists()
    assert list(moved_state_dir.iterdir()) == [moved_state_dir / "state.json"]


def test_lock_contention_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, _state_dir, lock_file = _write_config(tmp_path)
    lock_file.parent.mkdir(mode=0o700)
    with lock_file.open("w", encoding="utf-8") as held:
        os.chmod(lock_file, 0o600)
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        exit_code, payload = _run(monkeypatch, capsys, config_path, 10)

    assert exit_code == guard.EXIT_LOCKED
    assert payload["reason_code"] == "lock_busy"


def test_lock_directory_requires_the_effective_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_dir = tmp_path / "runtime"
    lock_dir.mkdir(mode=0o700)
    os.chmod(lock_dir, 0o700)
    real_euid = os.geteuid()
    monkeypatch.setattr(guard.os, "geteuid", lambda: real_euid + 1)

    with pytest.raises(guard.GuardError, match="lock_directory_unsafe"):
        with guard._exclusive_lock(lock_dir / "guard.lock"):
            pytest.fail("unsafe lock directory must never yield")


def test_threshold_override_and_lock_inside_spool_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, state_dir, _lock_file = _write_config(tmp_path, warning_percent=99)
    exit_code, payload = _run(monkeypatch, capsys, config_path, 10)
    assert exit_code == guard.EXIT_CONFIG
    assert payload["reason_code"] == "invalid_config_schema"

    config_path, _state_dir, _lock_file = _write_config(
        tmp_path, lock_file=str(state_dir / "guard.lock")
    )
    exit_code, payload = _run(monkeypatch, capsys, config_path, 10, dry_run=True)
    assert exit_code == guard.EXIT_CONFIG
    assert payload["reason_code"] == "lock_must_be_outside_state_spool"
    assert not state_dir.exists()


def test_observed_mount_must_back_the_configured_docker_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    volume = tmp_path / "volume"
    docker_root = volume / "docker-data"
    docker_root.mkdir(parents=True)
    real_stat = Path.stat

    def mismatched_stat(path: Path, *args, **kwargs):
        value = real_stat(path, *args, **kwargs)
        if path == docker_root:
            return SimpleNamespace(st_mode=value.st_mode, st_dev=value.st_dev + 1)
        return value

    monkeypatch.setattr(os.path, "ismount", lambda _path: True)
    monkeypatch.setattr(Path, "stat", mismatched_stat)

    with pytest.raises(guard.GuardError, match="docker_root_backing_mismatch"):
        guard._observe_usage_percent(volume, docker_root)


def test_shell_entrypoints_and_systemd_unit_are_non_destructive_and_executable() -> (
    None
):
    guarded_sources = [
        ROOT / "ops" / "docker_disk_guard.py",
        ROOT / "ops" / "docker-disk-guard.sh",
        ROOT / "ops" / "disk_safeguard.sh",
    ]
    forbidden = ("docker builder", "docker image", "docker system", "docker volume")
    for source in guarded_sources:
        content = source.read_text(encoding="utf-8").lower()
        assert all(token not in content for token in forbidden)
        assert os.access(source, os.X_OK)

    service = (ROOT / "ops" / "systemd" / "sealai-disk-guard.service").read_text(
        encoding="utf-8"
    )
    installer = (ROOT / "ops" / "install-disk-guard.sh").read_text(encoding="utf-8")
    assert "ConditionFileIsExecutable" not in service
    assert "ConditionPathExists" not in service
    assert (
        "ExecStart=/usr/local/libexec/sealai/docker-disk-guard.sh "
        "--config /etc/sealai/disk-guard.json check" in service
    )
    assert "SuccessExitStatus=10 20" in service
    assert '"${STAGE_DIR}/ops/docker-disk-guard.sh"' in installer
    assert "/usr/local/libexec/sealai/docker-disk-guard.sh" in installer
    assert "0 * * * * /home/thorsten/sealai/ops/disk_safeguard.sh" in installer
    assert "external alert delivery remains BLOCKED_EXTERNAL" in installer


def test_production_storage_lease_has_fixed_root_mediated_paths() -> None:
    lease_path = ROOT / "ops" / "production-storage-lease.sh"
    content = lease_path.read_text(encoding="utf-8")
    wrapper = (ROOT / "ops" / "docker-disk-guard.sh").read_text(encoding="utf-8")

    assert "/run/lock/sealai-storage-mutation.lock" in content
    assert "/usr/local/libexec/sealai/docker-disk-guard.sh" in content
    assert "/etc/sealai/disk-guard.json" in content
    assert "regular file:660:root:thorsten" in content
    assert "/usr/bin/sudo -n --" in content
    assert "${DOCKER_DISK_GUARD" not in content
    assert wrapper.startswith("#!/bin/bash -p\n")
    assert "readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin" in wrapper
    assert (
        "exec /usr/bin/python3 -I /usr/local/libexec/sealai/docker_disk_guard.py"
        in wrapper
    )


def test_production_build_pull_paths_gate_storage_before_mutation() -> None:
    cases = {
        "release-backend.sh": "docker build",
        "release-frontend.sh": "> frontend/.env.production.local",
        "release-backend-v2.sh": 'mkdir -p "${RUNTIME_DIR}"',
        "promote-local-backend-image.sh": 'docker push "$BACKEND_IMAGE_TAG"',
        "keycloak_upgrade_preflight.sh": "docker run",
        "upgrade_infra.sh": 'mkdir -p "$backup_dir"',
    }
    for name, first_mutation in cases.items():
        content = (ROOT / "ops" / name).read_text(encoding="utf-8")
        release_gate = content.index("production_release_gate.py")
        storage_gate = content.index("production-storage-lease.sh")
        acquisition = content.index("acquire_production_storage_lease")
        mutation = content.index(first_mutation)
        assert release_gate < storage_gate < acquisition < mutation, name

    installer = (ROOT / "ops" / "install-disk-guard.sh").read_text(encoding="utf-8")
    gate = installer.index("production_release_gate_check")
    operation = installer.index("remediation-control-install", gate)
    first_mutation = installer.index('STAGE_DIR="$(mktemp')
    assert gate < operation < first_mutation
    assert "PRODUCTION_RELEASE_GATE_DECISION" in installer
    assert "ops/production-storage-lease.sh" in installer
    assert "/etc/tmpfiles.d/sealai-storage-mutation.conf" in installer
    assert "/etc/sudoers.d/sealai-storage-preflight" in installer
    assert installer.index("systemctl daemon-reload") < installer.index(
        "systemctl enable --now sealai-disk-guard.timer"
    )
    assert installer.index("systemctl enable --now") < installer.index(
        "systemctl start sealai-disk-guard.service"
    )
    assert "test -s /var/lib/sealai-disk-guard/state.json" in installer


@pytest.mark.skipif(
    not Path("/proc/self/fd").exists(), reason="production lease targets Linux /proc"
)
def test_storage_lease_blocks_parallel_callers_and_is_inherited_reentrant(
    tmp_path: Path,
) -> None:
    lease = ROOT / "ops" / "production-storage-lease.sh"
    lock = tmp_path / "storage.lock"
    config = tmp_path / "guard.json"
    fake_guard = tmp_path / "guard.sh"
    lock.touch(mode=0o600)
    config.write_text("{}\n", encoding="utf-8")
    config.chmod(0o600)
    fake_guard.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    fake_guard.chmod(0o755)
    expected = subprocess.run(
        ["/usr/bin/stat", "-Lc", "%F:%a:%U:%G", str(lock)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    quoted = {
        "lease": shlex.quote(str(lease)),
        "lock": shlex.quote(str(lock)),
        "guard": shlex.quote(str(fake_guard)),
        "config": shlex.quote(str(config)),
        "expected": shlex.quote(expected),
    }
    acquire = (
        f"source {quoted['lease']}; "
        f"_acquire_storage_lease {quoted['lock']} {quoted['guard']} "
        f"{quoted['config']} {quoted['expected']} direct"
    )
    holder = subprocess.Popen(
        ["/bin/bash", "-c", acquire + "; printf 'ready\\n'; read -r _"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None
    assert holder.stdout.readline().strip() == "ready"
    blocked = subprocess.run(
        ["/bin/bash", "-c", acquire],
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode == 75
    assert "mutation_lock_busy" in blocked.stderr

    assert holder.stdin is not None
    holder.stdin.write("release\n")
    holder.stdin.flush()
    assert holder.wait(timeout=5) == 0

    nested = subprocess.run(
        [
            "/bin/bash",
            "-c",
            acquire + "; /bin/bash -c " + shlex.quote(acquire),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert nested.returncode == 0, nested.stderr
