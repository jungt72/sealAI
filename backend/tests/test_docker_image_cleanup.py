from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "ops" / "docker_image_cleanup.py"
SPEC = importlib.util.spec_from_file_location("docker_image_cleanup", MODULE_PATH)
assert SPEC and SPEC.loader
cleanup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cleanup
SPEC.loader.exec_module(cleanup)

REPOSITORY = "ghcr.io/jungt72/sealai-backend-v2"
IMAGE_A = "sha256:" + "a" * 64
IMAGE_B = "sha256:" + "b" * 64
PRODUCTION = "sha256:" + "c" * 64
ROLLBACK_ONE = "sha256:" + "d" * 64
ROLLBACK_TWO = "sha256:" + "e" * 64
DIGEST_A = REPOSITORY + "@sha256:" + "1" * 64
DIGEST_B = REPOSITORY + "@sha256:" + "2" * 64
TAG_A = REPOSITORY + ":old-a"
TAG_B = REPOSITORY + ":old-b"
PRODUCTION_REF = REPOSITORY + ":production"
HOSTNAME = "production.example"
MACHINE_ID_SHA256 = "f" * 64
COMMIT = "3" * 40
TREE = "4" * 40
DEVICE = "8:1"
DOCKER_ROOT = "/mnt/sealai-volume/docker-data"
TARGET_FILESYSTEM = "/mnt/sealai-volume"
CORE_IMAGE_IDS = {
    "backend-v2": PRODUCTION,
    "backend-v2-worker": PRODUCTION,
    "sealai-frontend-1": "sha256:" + "0" * 64,
    "nginx": "sha256:" + "1" * 64,
    "keycloak": "sha256:" + "2" * 64,
    "postgres": "sha256:" + "3" * 64,
    "redis": "sha256:" + "4" * 64,
    "qdrant": "sha256:" + "5" * 64,
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def host_probe() -> Any:
    return cleanup.HostBinding(HOSTNAME, MACHINE_ID_SHA256)


def filesystem_snapshot(
    *, used_percent: int = 95, free_bytes: int | None = None
) -> Any:
    total = 100 * 1024**3
    used = total * used_percent // 100
    free = total - used if free_bytes is None else free_bytes
    return cleanup.FilesystemSnapshot(total, used, free, DEVICE)


def filesystem_probe(_docker_root: Path, _target: Path) -> Any:
    return filesystem_snapshot()


def image_object(
    image_id: str,
    digest: str,
    tag: str,
    *,
    labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    labels_value = labels or {}
    return {
        "type": "docker_image",
        "id": image_id,
        "expected_repo_digests": [digest],
        "expected_repo_tags": [tag],
        "expected_labels_sha256": cleanup._canonical_sha256(labels_value),
        "estimated_reclaim_bytes": 1024,
        "active_dependency": False,
        "safe_to_remove": True,
        "backup_required": False,
        "recovery": {"kind": "registry_digest", "reference": digest},
    }


def protection() -> dict[str, Any]:
    return {
        "role_attestations": {
            "production_desired": {"status": "PRESENT", "image_ids": [PRODUCTION]},
            "staging": {"status": "NONE_APPROVED", "image_ids": []},
            "rollback_primary": {"status": "PRESENT", "image_ids": [ROLLBACK_ONE]},
            "rollback_secondary": {"status": "PRESENT", "image_ids": [ROLLBACK_TWO]},
            "legacy_v1": {"status": "NONE_APPROVED", "image_ids": []},
            "foreign_workloads": {"status": "NONE_APPROVED", "image_ids": []},
        }
    }


def write_manifest(
    path: Path,
    *,
    objects: list[dict[str, Any]] | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    candidates = objects or [image_object(IMAGE_A, DIGEST_A, TAG_A)]
    captured_at = now or utc_now()
    checkout = {
        "path": str(cleanup.PRODUCTION_CHECKOUT),
        "branch": "main",
        "commit": COMMIT,
        "tree": TREE,
        "clean": True,
    }
    fingerprint = cleanup._canonical_sha256(
        {
            "hostname": HOSTNAME,
            "machine_id_sha256": MACHINE_ID_SHA256,
            "checkout_path": checkout["path"],
            "branch": checkout["branch"],
            "commit": checkout["commit"],
            "tree": checkout["tree"],
            "clean": checkout["clean"],
        }
    )
    commands = [
        [*cleanup.REMOVE_COMMAND_PREFIX, candidate["id"]] for candidate in candidates
    ]
    protection_value = protection()
    protection_sha256 = cleanup._canonical_sha256(protection_value["role_attestations"])
    host_binding = cleanup.HostBinding(HOSTNAME, MACHINE_ID_SHA256)
    checkout_binding = cleanup.CheckoutBinding(
        path=cleanup.PRODUCTION_CHECKOUT,
        branch="main",
        commit=COMMIT,
        tree=TREE,
        clean=True,
        fingerprint_sha256=fingerprint,
    )
    storage_binding = cleanup.StorageBinding(
        docker_root_dir=Path(DOCKER_ROOT),
        target_filesystem=Path(TARGET_FILESYSTEM),
        device_major_minor=DEVICE,
        minimum_free_bytes=cleanup.MINIMUM_FREE_BYTES,
        target_max_used_percent=cleanup.TARGET_MAX_USED_PERCENT,
    )
    core_bindings = [
        cleanup.CoreContainerBinding(name, CORE_IMAGE_IDS[name])
        for name in cleanup.CORE_CONTAINERS
    ]
    production_fingerprint = cleanup._production_fingerprint(
        host_binding,
        checkout_binding,
        storage_binding,
        core_bindings,
        protection_sha256,
    )

    def timestamp(value: dt.datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    value = {
        "schema_version": cleanup.SCHEMA_VERSION,
        "gate_id": "GATE-03",
        "purpose": "synthetic approved unit-test batch",
        "minimum_reclaim_bytes": 1,
        "operation": {
            "operation_id": "cleanup:test-001",
            "host": {
                "hostname": HOSTNAME,
                "machine_id_sha256": MACHINE_ID_SHA256,
            },
            "checkout": {**checkout, "fingerprint_sha256": fingerprint},
            "docker_storage": {
                "docker_root_dir": DOCKER_ROOT,
                "target_filesystem": TARGET_FILESYSTEM,
                "device_major_minor": DEVICE,
                "minimum_free_bytes": cleanup.MINIMUM_FREE_BYTES,
                "target_max_used_percent": cleanup.TARGET_MAX_USED_PERCENT,
            },
            "core_containers": {
                name: {"image_id": CORE_IMAGE_IDS[name]}
                for name in cleanup.CORE_CONTAINERS
            },
            "production_fingerprint_sha256": production_fingerprint,
            "command": {
                "argv_prefix": list(cleanup.REMOVE_COMMAND_PREFIX),
                "ordered_image_ids": [candidate["id"] for candidate in candidates],
                "commands_sha256": cleanup._canonical_sha256(commands),
            },
        },
        "recovery_evidence": {
            "backup": {
                "kind": "encrypted_offsite_restore_verified",
                "status": "VERIFIED",
                "evidence_id": "backup:test-001",
                "evidence_sha256": "5" * 64,
                "verified_at": timestamp(captured_at - dt.timedelta(minutes=5)),
                "valid_until": timestamp(captured_at + dt.timedelta(hours=3)),
            },
            "rollback": {
                "kind": "registry_digest_pull_verified",
                "status": "EXECUTABLE_VERIFIED",
                "evidence_id": "rollback:test-001",
                "evidence_sha256": "6" * 64,
                "verified_at": timestamp(captured_at - dt.timedelta(minutes=5)),
                "valid_until": timestamp(captured_at + dt.timedelta(hours=3)),
            },
        },
        "protection": protection_value,
        "objects": candidates,
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    return value


def write_approval(
    path: Path,
    manifest: Any,
    *,
    now: dt.datetime | None = None,
    expires_after: dt.timedelta = dt.timedelta(hours=1),
) -> Path:
    approved_at = now or utc_now()
    value = {
        "schema_version": cleanup.SCHEMA_VERSION,
        "gate_id": "GATE-03",
        "decision": "APPROVED",
        "approval_id": "approval:test-001",
        "approved_by": "test-owner",
        "approved_at": approved_at.isoformat().replace("+00:00", "Z"),
        "manifest_sha256": manifest.digest,
        "expires_at": (approved_at + expires_after).isoformat().replace("+00:00", "Z"),
        "operation_id": manifest.operation.operation_id,
        "approved_hostname": manifest.operation.host.hostname,
        "approved_machine_id_sha256": manifest.operation.host.machine_id_sha256,
        "repository_fingerprint_sha256": manifest.operation.checkout.fingerprint_sha256,
        "production_fingerprint_sha256": manifest.operation.production_fingerprint_sha256,
        "commands_sha256": manifest.operation.command_sha256,
        "protection_sha256": manifest.protection_sha256,
        "backup_evidence_sha256": manifest.backup_evidence.evidence_sha256,
        "rollback_evidence_sha256": manifest.rollback_evidence.evidence_sha256,
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)
    return path


class DockerRunner:
    def __init__(self, *, referenced: set[str] | None = None) -> None:
        self.referenced = referenced or set()
        self.commands: list[list[str]] = []
        self.images: dict[str, dict[str, Any]] = {}
        self.references: dict[str, str] = {}
        self.checkout_commit = COMMIT
        self.checkout_tree = TREE
        self.checkout_dirty = False
        self.core_healthy = True
        self.removed_count = 0
        self.remove_returncode = 0
        self.after_remove: Any = None
        self._add(IMAGE_A, [DIGEST_A], [TAG_A], {})
        self._add(IMAGE_B, [DIGEST_B], [TAG_B], {})
        self._add(PRODUCTION, [], [PRODUCTION_REF], {})
        self._add(ROLLBACK_ONE, [], [REPOSITORY + ":rollback-pre-one"], {})
        self._add(ROLLBACK_TWO, [], [REPOSITORY + ":rollback-pre-two"], {})

    def _add(
        self,
        image_id: str,
        digests: list[str],
        tags: list[str],
        labels: dict[str, str],
    ) -> None:
        value = {
            "Id": image_id,
            "RepoDigests": digests,
            "RepoTags": tags,
            "Config": {"Labels": labels},
        }
        self.images[image_id] = value
        for reference in [*digests, *tags]:
            self.references[reference] = image_id

    def __call__(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        command = list(command)
        self.commands.append(command)
        git_prefix = [
            cleanup.GIT_BINARY,
            *cleanup.GIT_SAFE_CONFIG_ARGS,
            "-C",
            str(cleanup.PRODUCTION_CHECKOUT),
        ]
        if command == [*git_prefix, "rev-parse", "--show-toplevel"]:
            return subprocess.CompletedProcess(
                command, 0, str(cleanup.PRODUCTION_CHECKOUT) + "\n", ""
            )
        if command == [*git_prefix, "symbolic-ref", "--short", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, "main\n", "")
        if command == [*git_prefix, "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(
                command, 0, self.checkout_commit + "\n", ""
            )
        if command == [*git_prefix, "rev-parse", "HEAD^{tree}"]:
            return subprocess.CompletedProcess(
                command, 0, self.checkout_tree + "\n", ""
            )
        if command == [
            *git_prefix,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ]:
            status_value = (
                " M ops/docker_image_cleanup.py\n" if self.checkout_dirty else ""
            )
            return subprocess.CompletedProcess(command, 0, status_value, "")
        if command == [
            cleanup.DOCKER_BINARY,
            "info",
            "--format",
            "{{json .DockerRootDir}}",
        ]:
            return subprocess.CompletedProcess(
                command, 0, json.dumps(DOCKER_ROOT) + "\n", ""
            )
        if command == [
            cleanup.DOCKER_BINARY,
            "container",
            "ls",
            "--all",
            "--quiet",
        ]:
            identifiers = "\n".join(
                f"container-{index}" for index, _ in enumerate(self.referenced)
            )
            return subprocess.CompletedProcess(command, 0, identifiers, "")
        if command[:3] == [cleanup.DOCKER_BINARY, "container", "inspect"]:
            if command[3:] == list(cleanup.CORE_CONTAINERS):
                health = "healthy" if self.core_healthy else "unhealthy"
                value = [
                    {
                        "Name": "/" + name,
                        "Image": CORE_IMAGE_IDS[name],
                        "State": {
                            "Running": True,
                            "Status": "running",
                            "Health": {"Status": health},
                        },
                    }
                    for name in cleanup.CORE_CONTAINERS
                ]
                return subprocess.CompletedProcess(command, 0, json.dumps(value), "")
            value = [{"Image": image_id} for image_id in sorted(self.referenced)]
            return subprocess.CompletedProcess(command, 0, json.dumps(value), "")
        if command[:2] == [cleanup.DOCKER_BINARY, "compose"]:
            return subprocess.CompletedProcess(command, 0, PRODUCTION_REF + "\n", "")
        if command[:3] == [cleanup.DOCKER_BINARY, "image", "inspect"]:
            reference = command[-1]
            image_id = self.references.get(reference, reference)
            value = self.images.get(image_id)
            if value is None:
                return subprocess.CompletedProcess(command, 1, "", "not found")
            return subprocess.CompletedProcess(command, 0, json.dumps([value]), "")
        if command[:3] == [cleanup.DOCKER_BINARY, "manifest", "inspect"]:
            return subprocess.CompletedProcess(command, 0, "{}", "")
        if command[:4] == [
            cleanup.DOCKER_BINARY,
            "image",
            "rm",
            "--no-prune",
        ]:
            image_id = command[-1]
            value = self.images.pop(image_id, None)
            if value is None:
                return subprocess.CompletedProcess(command, 1, "", "missing")
            if self.remove_returncode:
                return subprocess.CompletedProcess(
                    command, self.remove_returncode, "", "partial failure"
                )
            self.removed_count += 1
            if self.after_remove is not None:
                self.after_remove(self)
            return subprocess.CompletedProcess(command, 0, "removed", "")
        raise AssertionError(f"unexpected command: {command}")


def validate_runtime(manifest: Any, runner: Any) -> None:
    cleanup.validate_runtime(
        manifest,
        runner,
        host_probe=host_probe,
        filesystem_probe=filesystem_probe,
        now=utc_now(),
    )


def test_runner_sanitizes_git_environment_but_preserves_docker_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setenv("GIT_DIR", "/tmp/attacker-controlled")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "/tmp/attacker-helper")
    monkeypatch.setenv("GIT_SSH_COMMAND", "/tmp/attacker-ssh")
    monkeypatch.setenv("DOCKER_CONFIG", "/secure/docker-auth")

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(cleanup.subprocess, "run", fake_run)
    cleanup._run([cleanup.GIT_BINARY, "--version"])

    environment = captured["env"]
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert {key for key in environment if key.startswith("GIT_")} == {
        "GIT_CONFIG_NOSYSTEM",
        "GIT_CONFIG_GLOBAL",
    }
    assert environment["DOCKER_CONFIG"] == "/secure/docker-auth"
    assert environment["DOCKER_HOST"] == cleanup.LOCAL_DOCKER_HOST


def test_checkout_probes_disable_hooks_and_fsmonitor(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    write_manifest(path)
    manifest = cleanup.load_manifest(path)
    runner = DockerRunner()

    validate_runtime(manifest, runner)

    git_commands = [
        command for command in runner.commands if command[0] == cleanup.GIT_BINARY
    ]
    safe_prefix = [
        cleanup.GIT_BINARY,
        "--no-optional-locks",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-C",
        str(cleanup.PRODUCTION_CHECKOUT),
    ]
    assert len(git_commands) == 5
    assert all(command[: len(safe_prefix)] == safe_prefix for command in git_commands)


def test_manifest_is_one_private_allowlisted_batch(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    value = write_manifest(path)
    value["objects"][0]["type"] = "docker_volume"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(cleanup.CleanupError, match="exact Docker image id"):
        cleanup.load_manifest(path)

    objects = [image_object(IMAGE_A, DIGEST_A, TAG_A)] * 11
    write_manifest(path, objects=objects)
    with pytest.raises(cleanup.CleanupError, match="one to ten"):
        cleanup.load_manifest(path)

    write_manifest(path)
    path.chmod(0o644)
    with pytest.raises(cleanup.CleanupError, match="unsafe"):
        cleanup.load_manifest(path)


def test_manifest_exactly_binds_commands_and_recovery_evidence(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    value = write_manifest(path)
    value["operation"]["command"]["ordered_image_ids"] = [IMAGE_B]
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(cleanup.CleanupError, match="exact batch"):
        cleanup.load_manifest(path)

    value = write_manifest(path)
    value["recovery_evidence"]["backup"]["status"] = "UNVERIFIED"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(cleanup.CleanupError, match="backup evidence is not verified"):
        cleanup.load_manifest(path)


def test_protection_requires_two_distinct_rollbacks_and_exact_compose_set(
    tmp_path: Path,
) -> None:
    path = tmp_path / "plan.json"
    value = write_manifest(path)
    value["protection"]["role_attestations"]["rollback_secondary"]["image_ids"] = [
        ROLLBACK_ONE
    ]
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(cleanup.CleanupError, match="distinct"):
        cleanup.load_manifest(path)

    write_manifest(path)
    manifest = cleanup.load_manifest(path)
    runner = DockerRunner()
    runner.references[PRODUCTION_REF] = IMAGE_B
    with pytest.raises(cleanup.CleanupError, match="production desired"):
        validate_runtime(manifest, runner)


def test_runtime_blocks_stopped_container_and_tag_or_label_drift(
    tmp_path: Path,
) -> None:
    path = tmp_path / "plan.json"
    write_manifest(path)
    manifest = cleanup.load_manifest(path)
    with pytest.raises(cleanup.CleanupError, match="protected"):
        validate_runtime(manifest, DockerRunner(referenced={IMAGE_A}))

    runner = DockerRunner()
    runner.images[IMAGE_A]["RepoTags"] = [REPOSITORY + ":latest"]
    with pytest.raises(cleanup.CleanupError, match="tags changed"):
        validate_runtime(manifest, runner)

    runner = DockerRunner()
    runner.images[IMAGE_A]["Config"]["Labels"] = {
        "com.docker.compose.project": "sealai-staging"
    }
    with pytest.raises(cleanup.CleanupError, match="labels changed"):
        validate_runtime(manifest, runner)


def test_registry_recovery_must_be_reachable(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    write_manifest(path)
    manifest = cleanup.load_manifest(path)
    runner = DockerRunner()
    original = runner.__call__

    def unavailable(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if list(command)[:3] == [cleanup.DOCKER_BINARY, "manifest", "inspect"]:
            return subprocess.CompletedProcess(command, 1, "", "unavailable")
        return original(command)

    with pytest.raises(cleanup.CleanupError, match="registry recovery"):
        validate_runtime(manifest, unavailable)


def test_approval_is_private_hash_bound_and_short_lived(tmp_path: Path) -> None:
    manifest_path = tmp_path / "plan.json"
    write_manifest(manifest_path)
    manifest = cleanup.load_manifest(manifest_path)
    approval_path = write_approval(tmp_path / "approval.json", manifest)

    approval = cleanup.validate_approval(approval_path, manifest)
    assert approval.approval_id == "approval:test-001"

    approval_path.chmod(0o644)
    with pytest.raises(cleanup.CleanupError, match="unsafe"):
        cleanup.validate_approval(approval_path, manifest)
    approval_path.chmod(0o600)
    value = json.loads(approval_path.read_text(encoding="utf-8"))
    value["manifest_sha256"] = hashlib.sha256(b"other").hexdigest()
    approval_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(cleanup.CleanupError, match="bound"):
        cleanup.validate_approval(approval_path, manifest)

    write_approval(approval_path, manifest)
    value = json.loads(approval_path.read_text(encoding="utf-8"))
    value["backup_evidence_sha256"] = "9" * 64
    approval_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(cleanup.CleanupError, match="exact operation"):
        cleanup.validate_approval(approval_path, manifest)


def test_execute_removes_exactly_the_single_approved_batch(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    write_manifest(
        path,
        objects=[
            image_object(IMAGE_A, DIGEST_A, TAG_A),
            image_object(IMAGE_B, DIGEST_B, TAG_B),
        ],
    )
    manifest = cleanup.load_manifest(path)
    approval = cleanup.validate_approval(
        write_approval(tmp_path / "approval.json", manifest), manifest
    )
    runner = DockerRunner()

    outcome = cleanup.execute_batch(
        manifest,
        approval,
        runner,
        host_probe=host_probe,
        filesystem_probe=filesystem_probe,
        now_provider=utc_now,
    )
    assert outcome.removed_count == 2
    assert outcome.target_reached is False
    assert outcome.remaining_count == 0
    removals = [
        command
        for command in runner.commands
        if command[:3] == [cleanup.DOCKER_BINARY, "image", "rm"]
    ]
    assert removals == [
        [cleanup.DOCKER_BINARY, "image", "rm", "--no-prune", IMAGE_A],
        [cleanup.DOCKER_BINARY, "image", "rm", "--no-prune", IMAGE_B],
    ]
    assert all("prune" not in command[:3] for command in runner.commands)


def test_nonzero_image_rm_is_reported_as_indeterminate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    now = utc_now()
    path = tmp_path / "plan.json"
    write_manifest(path, now=now)
    manifest = cleanup.load_manifest(path)
    approval = cleanup.validate_approval(
        write_approval(tmp_path / "approval.json", manifest, now=now),
        manifest,
        now=now,
    )
    runner = DockerRunner()
    runner.remove_returncode = 1

    with pytest.raises(cleanup.CleanupError, match="exact image removal failed"):
        cleanup.execute_batch(
            manifest,
            approval,
            runner,
            host_probe=host_probe,
            filesystem_probe=filesystem_probe,
            now_provider=lambda: now,
        )

    assert IMAGE_A not in runner.images
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events == [
        {
            "event": "storage_cleanup_batch",
            "reason": "exact image removal failed",
            "remaining_count": 1,
            "removal_outcome_unknown": True,
            "removed_count": 0,
            "status": "indeterminate",
            "stopped_before_image_id": IMAGE_A,
            "timestamp": events[0]["timestamp"],
        }
    ]


def test_keyboard_interrupt_during_image_rm_is_reported_as_indeterminate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    now = utc_now()
    path = tmp_path / "plan.json"
    write_manifest(path, now=now)
    manifest = cleanup.load_manifest(path)
    approval = cleanup.validate_approval(
        write_approval(tmp_path / "approval.json", manifest, now=now),
        manifest,
        now=now,
    )
    base_runner = DockerRunner()

    def interrupting_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if list(command)[:4] == list(cleanup.REMOVE_COMMAND_PREFIX):
            base_runner.images.pop(IMAGE_A, None)
            raise KeyboardInterrupt
        return base_runner(command)

    with pytest.raises(KeyboardInterrupt):
        cleanup.execute_batch(
            manifest,
            approval,
            interrupting_runner,
            host_probe=host_probe,
            filesystem_probe=filesystem_probe,
            now_provider=lambda: now,
        )

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[-1]["status"] == "indeterminate"
    assert events[-1]["removal_outcome_unknown"] is True
    assert events[-1]["stopped_before_image_id"] == IMAGE_A
    assert events[-1]["reason"] == (
        "process interrupted or failed after a removal attempt"
    )


def test_interrupt_after_successful_rm_books_the_removal_before_reporting_partial(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = utc_now()
    path = tmp_path / "plan.json"
    write_manifest(path, now=now)
    manifest = cleanup.load_manifest(path)
    approval = cleanup.validate_approval(
        write_approval(tmp_path / "approval.json", manifest, now=now),
        manifest,
        now=now,
    )
    runner = DockerRunner()

    @cleanup.contextlib.contextmanager
    def interrupt_on_boundary_exit():
        yield
        raise cleanup.RemovalInterrupted(cleanup.signal.SIGTERM)

    monkeypatch.setattr(cleanup, "removal_signal_boundary", interrupt_on_boundary_exit)
    with pytest.raises(cleanup.RemovalInterrupted):
        cleanup.execute_batch(
            manifest,
            approval,
            runner,
            host_probe=host_probe,
            filesystem_probe=filesystem_probe,
            now_provider=lambda: now,
        )

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[-1]["status"] == "partial"
    assert events[-1]["removed_count"] == 1
    assert events[-1]["remaining_count"] == 0
    assert events[-1]["removal_outcome_unknown"] is False
    assert events[-1]["stopped_before_image_id"] is None


def test_incomplete_batch_and_unobserved_minimum_reclaim_are_nonzero(
    tmp_path: Path,
) -> None:
    path = tmp_path / "plan.json"
    write_manifest(path)
    manifest = cleanup.load_manifest(path)

    assert cleanup.classify_batch_outcome(
        manifest,
        cleanup.BatchOutcome(1, 0, False, 100, 200),
    ) == ("insufficient_reclaim", 3, 100)

    demanding = replace(manifest, minimum_reclaim_bytes=200)
    assert cleanup.classify_batch_outcome(
        demanding,
        cleanup.BatchOutcome(1, 0, True, 100, 200),
    ) == ("minimum_reclaim_not_observed", 3, 100)

    assert cleanup.classify_batch_outcome(
        demanding,
        cleanup.BatchOutcome(0, 1, True, 100, 100),
    ) == ("target_reached", 0, 0)


@pytest.mark.parametrize(
    ("failure_mode", "message"),
    [
        ("low_space", "below 3 GiB"),
        ("unhealthy", "fixed core container"),
        ("fingerprint", "fingerprint drifted"),
    ],
)
def test_execute_removes_nothing_when_initial_checkpoint_is_unsafe(
    tmp_path: Path, failure_mode: str, message: str
) -> None:
    now = utc_now()
    path = tmp_path / "plan.json"
    write_manifest(path, now=now)
    manifest = cleanup.load_manifest(path)
    approval = cleanup.validate_approval(
        write_approval(tmp_path / "approval.json", manifest, now=now),
        manifest,
        now=now,
    )
    runner = DockerRunner()
    probe = filesystem_probe
    if failure_mode == "low_space":

        def low_space_probe(_root: Path, _target: Path) -> Any:
            return filesystem_snapshot(free_bytes=cleanup.MINIMUM_FREE_BYTES - 1)

        probe = low_space_probe
    elif failure_mode == "unhealthy":
        runner.core_healthy = False
    else:
        runner.checkout_commit = "7" * 40

    with pytest.raises(cleanup.CleanupError, match=message):
        cleanup.execute_batch(
            manifest,
            approval,
            runner,
            host_probe=host_probe,
            filesystem_probe=probe,
            now_provider=lambda: now,
        )

    assert not any(
        command[:4] == list(cleanup.REMOVE_COMMAND_PREFIX)
        for command in runner.commands
    )


def test_execute_stops_after_one_image_when_target_reaches_80_percent(
    tmp_path: Path,
) -> None:
    now = utc_now()
    path = tmp_path / "plan.json"
    write_manifest(
        path,
        now=now,
        objects=[
            image_object(IMAGE_A, DIGEST_A, TAG_A),
            image_object(IMAGE_B, DIGEST_B, TAG_B),
        ],
    )
    manifest = cleanup.load_manifest(path)
    approval = cleanup.validate_approval(
        write_approval(tmp_path / "approval.json", manifest, now=now),
        manifest,
        now=now,
    )
    runner = DockerRunner()

    def capacity(_root: Path, _target: Path) -> Any:
        return filesystem_snapshot(used_percent=80 if runner.removed_count else 95)

    outcome = cleanup.execute_batch(
        manifest,
        approval,
        runner,
        host_probe=host_probe,
        filesystem_probe=capacity,
        now_provider=lambda: now,
    )

    assert outcome == cleanup.BatchOutcome(
        removed_count=1,
        remaining_count=1,
        target_reached=True,
        initial_free_bytes=5 * 1024**3,
        final_free_bytes=20 * 1024**3,
    )
    removals = [
        command
        for command in runner.commands
        if command[:4] == list(cleanup.REMOVE_COMMAND_PREFIX)
    ]
    assert removals == [[*cleanup.REMOVE_COMMAND_PREFIX, IMAGE_A]]


@pytest.mark.parametrize(
    ("drift", "message"),
    [
        ("fingerprint", "fingerprint drifted"),
        ("expiry", "approval expired"),
        ("health", "fixed core container"),
        ("protection", "rollback role lacks runtime rollback evidence"),
        ("low_space", "below 3 GiB"),
    ],
)
def test_post_removal_drift_stops_the_second_image_and_reports_partial(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    drift: str,
    message: str,
) -> None:
    now = utc_now()
    path = tmp_path / "plan.json"
    write_manifest(
        path,
        now=now,
        objects=[
            image_object(IMAGE_A, DIGEST_A, TAG_A),
            image_object(IMAGE_B, DIGEST_B, TAG_B),
        ],
    )
    manifest = cleanup.load_manifest(path)
    approval = cleanup.validate_approval(
        write_approval(tmp_path / "approval.json", manifest, now=now),
        manifest,
        now=now,
    )
    runner = DockerRunner()
    if drift == "fingerprint":
        runner.after_remove = lambda current: setattr(
            current, "checkout_commit", "7" * 40
        )
    elif drift == "health":
        runner.after_remove = lambda current: setattr(current, "core_healthy", False)
    elif drift == "protection":

        def invalidate_rollback(current: DockerRunner) -> None:
            current.images[ROLLBACK_ONE]["RepoTags"] = [REPOSITORY + ":old"]

        runner.after_remove = invalidate_rollback

    def capacity(_root: Path, _target: Path) -> Any:
        if drift == "low_space" and runner.removed_count:
            return filesystem_snapshot(free_bytes=cleanup.MINIMUM_FREE_BYTES - 1)
        return filesystem_snapshot()

    def checkpoint_time() -> dt.datetime:
        if drift == "expiry" and runner.removed_count:
            return now + dt.timedelta(minutes=90)
        return now

    with pytest.raises(cleanup.CleanupError, match=message):
        cleanup.execute_batch(
            manifest,
            approval,
            runner,
            host_probe=host_probe,
            filesystem_probe=capacity,
            now_provider=checkpoint_time,
        )

    removals = [
        command
        for command in runner.commands
        if command[:4] == list(cleanup.REMOVE_COMMAND_PREFIX)
    ]
    assert removals == [[*cleanup.REMOVE_COMMAND_PREFIX, IMAGE_A]]
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    partial = [event for event in events if event.get("status") == "partial"]
    assert partial == [
        {
            "event": "storage_cleanup_batch",
            "reason": partial[0]["reason"],
            "removal_outcome_unknown": False,
            "remaining_count": 1,
            "removed_count": 1,
            "status": "partial",
            "stopped_before_image_id": IMAGE_B,
            "timestamp": partial[0]["timestamp"],
        }
    ]


def test_storage_mutation_lock_is_nonblocking_and_owner_bound(tmp_path: Path) -> None:
    lock_path = tmp_path / "storage.lock"
    lock_path.touch(mode=0o600)
    with lock_path.open("r+") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(cleanup.CleanupError, match="busy"):
            with cleanup.storage_mutation_lock(
                lock_path,
                expected_uid=os.geteuid(),
                expected_gid=os.getegid(),
                expected_mode=0o600,
            ):
                pass


def test_malformed_utf8_fails_closed_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "plan.json"
    path.write_bytes(b"\xff\xfe")
    path.chmod(0o600)

    assert cleanup.main(["plan", str(path)]) == 2
    output = capsys.readouterr().out
    assert "Traceback" not in output
    assert json.loads(output)["status"] == "denied"


def test_cleanup_program_is_executable() -> None:
    assert stat.S_IMODE(MODULE_PATH.stat().st_mode) & stat.S_IXUSR
