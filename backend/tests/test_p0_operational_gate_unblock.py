from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys

import jsonschema
import pytest


ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "ops"
sys.path.insert(0, str(OPS))

import credential_cutover as cutover  # noqa: E402
import gate08_legacy_unit_retirement as legacy  # noqa: E402
import permission_manifest as permissions  # noqa: E402
import production_release_gate as release_gate  # noqa: E402


def _inspect_fixture() -> dict[str, object]:
    return {
        "Image": "sha256:" + "1" * 64,
        "Config": {
            "Image": "ghcr.io/example/backend@sha256:" + "2" * 64,
            "Cmd": ["python", "-m", "service"],
            "Entrypoint": ["/entrypoint"],
            "Volumes": {"/data": {}},
            "Labels": {
                "com.docker.compose.project": "sealai",
                "com.docker.compose.service": "backend-v2",
            },
        },
        "HostConfig": {
            "RestartPolicy": {"Name": "unless-stopped", "MaximumRetryCount": 0},
            "CapAdd": ["CHOWN"],
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges:true"],
        },
        "Mounts": [
            {
                "Type": "volume",
                "Name": "sealai_backend-data",
                "Source": "/var/lib/docker/volumes/sealai_backend-data/_data",
                "Destination": "/data",
                "Mode": "rw",
                "RW": True,
                "Propagation": "",
            }
        ],
        "NetworkSettings": {
            "Networks": {"sealai_internal": {}},
            "Ports": {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8000"}]},
        },
        "State": {"Status": "running", "Health": {"Status": "healthy"}},
    }


def _cutover_approval(snapshot: dict[str, object]) -> dict[str, object]:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    return {
        "schema_version": 1,
        "gate_id": "GATE-01",
        "decision": "APPROVED",
        "scope": "same-image-credential-cutover",
        "approval_id": "gate01-test",
        "approved_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "production_git_sha": "a" * 40,
        "release_freeze_state_id": "freeze-test",
        "release_freeze_state_sha256": "0" * 64,
        "compose_project": "sealai",
        "compose_file_sha256": "0" * 64,
        "control_sha256": cutover._file_sha256(Path(cutover.__file__)),
        "services": [
            {
                "service": "backend-v2",
                "expected_fingerprint": cutover._canonical_sha256(snapshot),
                "allowed_credential_keys": ["DATABASE_PASSWORD"],
            }
        ],
    }


@pytest.mark.parametrize(
    ("field", "mutate"),
    [
        ("image", lambda value: value.__setitem__("Image", "sha256:" + "3" * 64)),
        (
            "mount",
            lambda value: value["Mounts"][0].__setitem__("Destination", "/other"),
        ),
        (
            "network",
            lambda value: value["NetworkSettings"].__setitem__(
                "Networks", {"other": {}}
            ),
        ),
        (
            "port",
            lambda value: value["NetworkSettings"]["Ports"]["8000/tcp"][0].__setitem__(
                "HostPort", "9000"
            ),
        ),
        (
            "service",
            lambda value: value["Config"]["Labels"].__setitem__(
                "com.docker.compose.service", "other"
            ),
        ),
    ],
)
def test_credential_fingerprint_rejects_runtime_invariant_drift(field, mutate):
    inspected = _inspect_fixture()
    original = cutover._canonical_sha256(cutover.invariant_snapshot(inspected))
    changed = copy.deepcopy(inspected)
    mutate(changed)
    assert (
        cutover._canonical_sha256(cutover.invariant_snapshot(changed)) != original
    ), field


def test_credential_snapshot_rejects_non_digest_image_reference():
    inspected = _inspect_fixture()
    inspected["Config"]["Image"] = "ghcr.io/example/backend:latest"
    with pytest.raises(cutover.CredentialCutoverError, match="digest"):
        cutover.invariant_snapshot(inspected)


def test_credential_files_are_exact_private_regular_files(monkeypatch, tmp_path):
    root = tmp_path / "credentials"
    service = root / "backend-v2"
    service.mkdir(parents=True)
    root.chmod(0o700)
    service.chmod(0o700)
    credential = service / "DATABASE_PASSWORD"
    credential.write_text("synthetic-runtime-value", encoding="utf-8")
    credential.chmod(0o600)
    monkeypatch.setattr(cutover, "CREDENTIAL_ROOT", root)

    assert cutover._read_credentials(
        "backend-v2", ["DATABASE_PASSWORD"], required_uid=os.geteuid()
    ) == {"DATABASE_PASSWORD": "synthetic-runtime-value"}

    credential.unlink()
    credential.symlink_to(service / "elsewhere")
    with pytest.raises((cutover.CredentialCutoverError, OSError)):
        cutover._read_credentials(
            "backend-v2", ["DATABASE_PASSWORD"], required_uid=os.geteuid()
        )


def test_credential_file_set_rejects_unapproved_file(monkeypatch, tmp_path):
    root = tmp_path / "credentials"
    service = root / "backend-v2"
    service.mkdir(parents=True)
    root.chmod(0o700)
    service.chmod(0o700)
    for name in ("DATABASE_PASSWORD", "UNAPPROVED"):
        path = service / name
        path.write_text("synthetic", encoding="utf-8")
        path.chmod(0o600)
    monkeypatch.setattr(cutover, "CREDENTIAL_ROOT", root)
    with pytest.raises(cutover.CredentialCutoverError, match="not exact"):
        cutover._read_credentials(
            "backend-v2", ["DATABASE_PASSWORD"], required_uid=os.geteuid()
        )


def _prepare_cutover_execution(monkeypatch, tmp_path, inspected):
    compose = tmp_path / "docker-compose.deploy.yml"
    compose.write_text("services: {}\n", encoding="utf-8")
    freeze = tmp_path / "production-release-state.json"
    freeze.write_text(
        json.dumps({"state_id": "freeze-test", "freeze": {"active": True}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(cutover, "COMPOSE_FILE", compose)
    monkeypatch.setattr(cutover, "FREEZE_STATE", freeze)
    monkeypatch.setattr(cutover, "_git_state", lambda: ("a" * 40, True))
    monkeypatch.setattr(
        cutover,
        "_read_credentials",
        lambda service, keys, required_uid: {keys[0]: "synthetic-runtime-value"},
    )
    approval = _cutover_approval(cutover.invariant_snapshot(inspected))
    approval["compose_file_sha256"] = hashlib.sha256(compose.read_bytes()).hexdigest()
    approval["release_freeze_state_sha256"] = hashlib.sha256(
        freeze.read_bytes()
    ).hexdigest()
    return approval


def test_credential_cutover_apply_uses_same_image_flags_and_redacts_values(
    monkeypatch, tmp_path
):
    inspected = _inspect_fixture()
    approval = _prepare_cutover_execution(monkeypatch, tmp_path, inspected)
    commands = []

    def runner(command, *, env=None):
        commands.append((command, env))
        return ""

    result = cutover.execute(
        approval,
        apply=True,
        inspect_service=lambda project, service: copy.deepcopy(inspected),
        command_runner=runner,
        required_uid=os.geteuid(),
    )
    command, environment = commands[0]
    assert command[-1] == "backend-v2"
    assert all(
        flag in command
        for flag in ("--no-deps", "--force-recreate", "--no-build", "--pull", "never")
    )
    assert not any(token in command for token in ("build", "pull", "migration"))
    assert environment["DATABASE_PASSWORD"] == "synthetic-runtime-value"
    assert "synthetic-runtime-value" not in json.dumps(result)
    assert result["image_change"] is False


def test_credential_cutover_rejects_production_commit_and_health_drift(
    monkeypatch, tmp_path
):
    inspected = _inspect_fixture()
    approval = _prepare_cutover_execution(monkeypatch, tmp_path, inspected)
    monkeypatch.setattr(cutover, "_git_state", lambda: ("b" * 40, True))
    with pytest.raises(cutover.CredentialCutoverError, match="checkout"):
        cutover.execute(
            approval,
            apply=False,
            inspect_service=lambda project, service: inspected,
            required_uid=os.geteuid(),
        )
    monkeypatch.setattr(cutover, "_git_state", lambda: ("a" * 40, True))
    unhealthy = copy.deepcopy(inspected)
    unhealthy["State"]["Health"]["Status"] = "unhealthy"
    with pytest.raises(cutover.CredentialCutoverError, match="health"):
        cutover.execute(
            approval,
            apply=False,
            inspect_service=lambda project, service: unhealthy,
            required_uid=os.geteuid(),
        )


def test_credential_approval_is_exact_and_short_lived():
    inspected = _inspect_fixture()
    snapshot = cutover.invariant_snapshot(inspected)
    approval = _cutover_approval(snapshot)
    approval["unexpected"] = True
    with pytest.raises(cutover.CredentialCutoverError, match="not exact"):
        cutover.validate_approval(
            approval,
            now=dt.datetime.now(dt.timezone.utc),
            compose_sha256="0" * 64,
            freeze_sha256="0" * 64,
        )


def test_mutating_controls_refuse_checkout_execution():
    with pytest.raises(cutover.CredentialCutoverError, match="fixed installed"):
        cutover._assert_installed_control(Path(cutover.__file__))
    with pytest.raises(permissions.PermissionManifestError, match="fixed installed"):
        permissions._assert_installed_control(Path(permissions.__file__))


def _permission_request(path: Path, mode: str) -> dict[str, object]:
    return {
        "batch": "GATE-02A",
        "objects": [
            {
                "path": str(path),
                "runtime_consumers": ["backend-v2"],
                "target_uid": os.geteuid(),
                "target_gid": os.getegid(),
                "target_mode": mode,
            }
        ],
    }


def test_permission_manifest_generate_validate_apply_and_rollback(tmp_path):
    target = tmp_path / "runtime.env"
    target.write_text("synthetic fixture\n", encoding="utf-8")
    target.chmod(0o600)
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(_permission_request(target, "0640")), encoding="utf-8"
    )
    manifest = permissions.generate_manifest(request)
    opened = permissions.validate_manifest(manifest)
    for descriptor, _, _ in opened:
        os.close(descriptor)
    rollback_path = tmp_path / "rollback.json"
    rollback = permissions.apply_manifest(manifest, rollback_path, require_root=False)
    assert stat_mode(target) == 0o640
    assert rollback_path.stat().st_mode & 0o777 == 0o600
    permissions.apply_manifest(
        rollback, tmp_path / "rollback-of-rollback.json", require_root=False
    )
    assert stat_mode(target) == 0o600


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_permission_batch_drift_stops_before_first_target_mutation(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    for path in (first, second):
        path.write_text("synthetic\n", encoding="utf-8")
        path.chmod(0o600)
    request_value = _permission_request(first, "0640")
    request_value["objects"].append(_permission_request(second, "0640")["objects"][0])
    request = tmp_path / "request.json"
    request.write_text(json.dumps(request_value), encoding="utf-8")
    manifest = permissions.generate_manifest(request)
    second.write_text("drifted\n", encoding="utf-8")
    rollback = tmp_path / "rollback.json"
    with pytest.raises(permissions.PermissionManifestError, match="drift"):
        permissions.apply_manifest(manifest, rollback, require_root=False)
    assert stat_mode(first) == 0o600
    assert not rollback.exists()


def test_permission_manifest_rejects_symlink_and_inode_replacement(tmp_path):
    target = tmp_path / "target"
    target.write_text("synthetic\n", encoding="utf-8")
    target.chmod(0o600)
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(_permission_request(target, "0640")), encoding="utf-8"
    )
    manifest = permissions.generate_manifest(request)
    replacement = tmp_path / "replacement"
    replacement.write_text("synthetic\n", encoding="utf-8")
    replacement.chmod(0o600)
    replacement.replace(target)
    with pytest.raises(permissions.PermissionManifestError, match="drift"):
        permissions.validate_manifest(manifest)
    target.unlink()
    target.symlink_to(replacement)
    with pytest.raises(permissions.PermissionManifestError, match="symlink"):
        permissions.validate_manifest(manifest)


class FakeSystemd:
    def __init__(
        self,
        *,
        fail_disable: bool = False,
        service_active_state: str = "failed",
        timer_state: tuple[str, str] = ("active", "enabled"),
    ):
        self.calls: list[list[str]] = []
        self.fail_disable = fail_disable
        timer_active_state, timer_unit_file_state = timer_state
        self.states = {
            legacy.LEGACY_TIMER: {
                "LoadState": "loaded",
                "ActiveState": timer_active_state,
                "UnitFileState": timer_unit_file_state,
                "FragmentPath": str(legacy.EXPECTED_FRAGMENTS[legacy.LEGACY_TIMER]),
            },
            legacy.LEGACY_SERVICE: {
                "LoadState": "loaded",
                "ActiveState": service_active_state,
                "UnitFileState": "static",
                "FragmentPath": str(legacy.EXPECTED_FRAGMENTS[legacy.LEGACY_SERVICE]),
            },
        }

    def __call__(self, command):
        self.calls.append(command)
        if "stop" in command:
            self.states[legacy.LEGACY_TIMER]["ActiveState"] = "inactive"
            return ""
        if "disable" in command:
            if self.fail_disable:
                raise legacy.LegacyUnitError("synthetic disable failure")
            self.states[legacy.LEGACY_TIMER]["UnitFileState"] = "disabled"
            return ""
        unit = command[-1]
        if "--property=MainPID" in command:
            return "MainPID=0\nControlPID=0\n"
        return "".join(f"{key}={value}\n" for key, value in self.states[unit].items())


def _legacy_manifest(
    timer: Path,
    service: Path,
    *,
    service_active_state: str = "failed",
    timer_state: tuple[str, str] = ("active", "enabled"),
) -> dict[str, object]:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    timer_active_state, timer_unit_file_state = timer_state
    return {
        "schema_version": 1,
        "gate_id": "GATE-08",
        "decision": "APPROVED",
        "scope": "legacy-disk-guard-unit-retirement",
        "approval_id": "gate08-test",
        "approved_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "units": [
            {
                "unit_name": legacy.LEGACY_TIMER,
                "load_state": "loaded",
                "active_state": timer_active_state,
                "unit_file_state": timer_unit_file_state,
                "fragment_path": str(timer),
                "fragment_sha256": hashlib.sha256(timer.read_bytes()).hexdigest(),
            },
            {
                "unit_name": legacy.LEGACY_SERVICE,
                "load_state": "loaded",
                "active_state": service_active_state,
                "unit_file_state": "static",
                "fragment_path": str(service),
                "fragment_sha256": hashlib.sha256(service.read_bytes()).hexdigest(),
            },
        ],
    }


def _prepare_legacy(
    monkeypatch,
    tmp_path,
    *,
    service_active_state: str = "failed",
    timer_state: tuple[str, str] = ("active", "enabled"),
):
    timer = tmp_path / legacy.LEGACY_TIMER
    service = tmp_path / legacy.LEGACY_SERVICE
    timer.write_text("[Timer]\nOnCalendar=hourly\n", encoding="utf-8")
    service.write_text("[Service]\nType=oneshot\n", encoding="utf-8")
    timer.chmod(0o644)
    service.chmod(0o644)
    monkeypatch.setattr(
        legacy,
        "EXPECTED_FRAGMENTS",
        {legacy.LEGACY_TIMER: timer, legacy.LEGACY_SERVICE: service},
    )
    return _legacy_manifest(
        timer,
        service,
        service_active_state=service_active_state,
        timer_state=timer_state,
    )


@pytest.mark.parametrize(
    "service_active_state", sorted(legacy.SAFE_LEGACY_SERVICE_ACTIVE_STATES)
)
@pytest.mark.parametrize("timer_state", sorted(legacy.SAFE_LEGACY_TIMER_STATES))
def test_gate08_dry_run_and_apply_are_exact(
    monkeypatch, tmp_path, timer_state, service_active_state
):
    manifest = _prepare_legacy(
        monkeypatch,
        tmp_path,
        service_active_state=service_active_state,
        timer_state=timer_state,
    )
    systemd = FakeSystemd(
        service_active_state=service_active_state, timer_state=timer_state
    )
    dry = legacy.execute(
        manifest,
        apply=False,
        runner=systemd,
        required_uid=os.geteuid(),
    )
    assert dry["mutation"] is False
    assert not any("stop" in call or "disable" in call for call in systemd.calls)
    systemd.calls.clear()
    evidence = tmp_path / "evidence"
    result = legacy.execute(
        manifest,
        apply=True,
        evidence_root=evidence,
        runner=systemd,
        required_uid=os.geteuid(),
    )
    assert result["legacy_timer_active"] is False
    assert [
        call[1]
        for call in systemd.calls
        if len(call) > 1 and call[1] in {"stop", "disable"}
    ] == ["stop", "disable"]
    evidence_files = list((evidence / "gate08-test").iterdir())
    assert len(evidence_files) == 4
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in evidence_files)


def test_gate08_never_reactivates_legacy_timer_after_partial_failure(
    monkeypatch, tmp_path
):
    manifest = _prepare_legacy(monkeypatch, tmp_path)
    systemd = FakeSystemd(fail_disable=True)
    with pytest.raises(legacy.LegacyUnitError):
        legacy.execute(
            manifest,
            apply=True,
            evidence_root=tmp_path / "evidence",
            runner=systemd,
            required_uid=os.geteuid(),
        )
    flattened = [token for call in systemd.calls for token in call]
    assert "start" not in flattened
    assert "enable" not in flattened


def test_gate08_rejects_any_unit_or_fragment_hash_drift(monkeypatch, tmp_path):
    manifest = _prepare_legacy(monkeypatch, tmp_path)
    systemd = FakeSystemd()
    manifest["units"][0]["unit_name"] = "unapproved.timer"
    with pytest.raises(legacy.LegacyUnitError, match="unit set"):
        legacy.validate_manifest(
            manifest,
            now=dt.datetime.now(dt.timezone.utc),
            runner=systemd,
            required_uid=os.geteuid(),
        )
    manifest = _prepare_legacy(monkeypatch, tmp_path)
    manifest["units"][0]["fragment_sha256"] = "0" * 64
    with pytest.raises(legacy.LegacyUnitError, match="hash drift"):
        legacy.validate_manifest(
            manifest,
            now=dt.datetime.now(dt.timezone.utc),
            runner=systemd,
            required_uid=os.geteuid(),
        )


@pytest.mark.parametrize(
    "service_active_state",
    ["active", "activating", "deactivating", "reloading", "bogus"],
)
def test_gate08_rejects_legacy_service_in_active_or_transitional_state(
    monkeypatch, tmp_path, service_active_state
):
    manifest = _prepare_legacy(
        monkeypatch, tmp_path, service_active_state=service_active_state
    )
    systemd = FakeSystemd(service_active_state=service_active_state)
    with pytest.raises(legacy.LegacyUnitError, match="safe-to-retire state"):
        legacy.validate_manifest(
            manifest,
            now=dt.datetime.now(dt.timezone.utc),
            runner=systemd,
            required_uid=os.geteuid(),
        )


@pytest.mark.parametrize(
    "timer_state",
    [
        ("activating", "enabled"),
        ("active", "disabled"),
        ("inactive", "enabled"),
        ("failed", "static"),
    ],
)
def test_gate08_rejects_legacy_timer_in_unknown_state(
    monkeypatch, tmp_path, timer_state
):
    manifest = _prepare_legacy(monkeypatch, tmp_path, timer_state=timer_state)
    systemd = FakeSystemd(timer_state=timer_state)
    with pytest.raises(legacy.LegacyUnitError, match="known safe state"):
        legacy.validate_manifest(
            manifest,
            now=dt.datetime.now(dt.timezone.utc),
            runner=systemd,
            required_uid=os.geteuid(),
        )


def test_gate08_installer_orders_retirement_before_new_timer_activation():
    installer = (OPS / "install-disk-guard.sh").read_text(encoding="utf-8")
    retirement = installer.index("gate08_legacy_unit_retirement.py")
    # The only systemd-analyze verify call left checks the *installed* unit files
    # (their ExecStart target must already exist on disk for verify to pass at
    # all) -- a second, earlier call against the staged-but-not-yet-installed
    # copy was removed because it could never succeed.
    installed_verify = installer.index(
        "/etc/systemd/system/sealai-disk-guard.service", retirement
    )
    daemon_reload = installer.index("systemctl daemon-reload")
    enable_new = installer.index("systemctl enable --now sealai-disk-guard.timer")
    assert retirement < installed_verify < daemon_reload < enable_new
    assert installer.count("systemd-analyze verify") == 1
    assert "systemctl start sealai-docker-disk-guard" not in installer
    assert "systemctl enable sealai-docker-disk-guard" not in installer


@pytest.mark.parametrize(
    ("document", "schema"),
    [
        (
            OPS / "tls-acme-gate-contracts.json",
            OPS / "schemas/tls-acme-gate-contracts.schema.json",
        ),
    ],
)
def test_checked_in_contracts_validate_against_json_schema(document, schema):
    jsonschema.Draft202012Validator(json.loads(schema.read_text())).validate(
        json.loads(document.read_text())
    )


def test_permission_and_approval_schemas_compile():
    for path in (
        OPS / "schemas/permission-manifest.schema.json",
        OPS / "schemas/credential-cutover-approval.schema.json",
        OPS / "schemas/gate08-legacy-units.schema.json",
        OPS / "schemas/gate08-operational-controls.schema.json",
    ):
        jsonschema.Draft202012Validator.check_schema(json.loads(path.read_text()))


def test_tls_d0_is_public_identifier_only_and_subgates_are_separate():
    contract = json.loads((OPS / "tls-acme-gate-contracts.json").read_text())
    gates = {gate["gate_id"]: gate for gate in contract["gates"]}
    assert set(gates) == {
        "GATE-01D0",
        "GATE-01D1",
        "GATE-01D2",
        "GATE-01D3",
        "GATE-01D4",
        "GATE-02D",
        "GATE-02E",
    }
    assert "GATE-02E" in permissions.BATCHES
    assert gates["GATE-01D0"]["mutation"] is False
    assert "private_key_bytes" in gates["GATE-01D0"]["forbidden_inputs"]
    assert gates["GATE-01D4"]["required_predecessors"] == ["GATE-01D0", "GATE-01D3"]


def test_release_freeze_remains_active_credential_cutover_stays_out_of_scope():
    # GATE10_LIFT_IMPLEMENTED flipped to True 2026-07-21 (owner decision) -- freeze.active
    # is a SEPARATE field and is untouched by that, so it stays True here regardless.
    state = json.loads((OPS / "production-release-state.json").read_text())
    assert state["freeze"]["active"] is True
    assert release_gate.GATE10_LIFT_IMPLEMENTED is True
    assert "credential-cutover" not in release_gate.MUTATING_OPERATIONS


def test_redis_emergency_runbook_is_read_only_and_has_exact_outcome():
    runbook = (ROOT / "docs/ops/redis-p0-emergency-review.md").read_text()
    assert "REDIS_P0_EMERGENCY_REVIEW" in runbook
    assert "used_memory / maxmemory" in runbook
    assert "INFO memory" in runbook
    assert "CONFIG SET" in runbook
    assert "does not authorize Redis remediation" in runbook


def test_control_sources_do_not_log_secret_values():
    source = (OPS / "credential_cutover.py").read_text(encoding="utf-8")
    assert "print(values" not in source
    assert "print(raw" not in source
    assert "capture_output=True" in source
