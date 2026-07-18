#!/usr/bin/env python3
"""Fail-closed same-image runtime credential cutover for GATE-01."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from typing import Any, Callable


PRODUCTION_REPO = Path("/home/thorsten/sealai")
COMPOSE_FILE = PRODUCTION_REPO / "docker-compose.deploy.yml"
FREEZE_STATE = PRODUCTION_REPO / "ops/production-release-state.json"
APPROVAL_PATH = Path("/etc/sealai/approvals/gate-01-credential-cutover.json")
CREDENTIAL_ROOT = Path("/run/sealai/credential-cutover")
INSTALLED_CONTROL = Path("/usr/local/libexec/sealai/credential-cutover.py")
DOCKER = "/usr/bin/docker"
GIT = "/usr/bin/git"
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")
CREDENTIAL_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
SAFE_ENVIRONMENT = {
    "HOME": "/nonexistent",
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
    "DOCKER_HOST": "unix:///var/run/docker.sock",
    "DOCKER_CONFIG": "/nonexistent",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
}


class CredentialCutoverError(RuntimeError):
    """The same-image cutover cannot prove its safety invariants."""


def _fail(message: str) -> None:
    raise CredentialCutoverError(message)


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _read_regular_bytes(path: Path, *, maximum: int = 1024 * 1024) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CredentialCutoverError("required file is unavailable or unsafe") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
            _fail("required file is not regular")
        value = b""
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            value += chunk
    finally:
        os.close(descriptor)
    return value


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(_read_regular_bytes(path)).hexdigest()


def _assert_installed_control(path: Path = Path(__file__)) -> None:
    invoked = Path(os.path.abspath(path))
    if invoked != INSTALLED_CONTROL:
        _fail("apply requires the fixed installed control")
    current = Path(invoked.anchor)
    for part in invoked.parts[1:]:
        current /= part
        metadata = current.lstat()
        is_leaf = current == invoked
        if (
            stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or (is_leaf and not stat.S_ISREG(metadata.st_mode))
            or (not is_leaf and not stat.S_ISDIR(metadata.st_mode))
        ):
            _fail("installed control path is unsafe")


def _read_private_json(path: Path, *, required_uid: int) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise CredentialCutoverError("private approval is unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != required_uid
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > 65536
        ):
            _fail("private approval metadata is unsafe")
        raw = os.read(descriptor, 65537)
    finally:
        os.close(descriptor)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CredentialCutoverError("private approval is invalid") from exc
    if not isinstance(value, dict):
        _fail("private approval root must be an object")
    return value


def _assert_private_directory(path: Path, *, required_uid: int) -> None:
    if required_uid == 0:
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current /= part
            metadata = current.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != 0
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                _fail("credential path ancestry is unsafe")
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != required_uid
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        _fail("credential directory metadata is unsafe")


def _parse_utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        _fail(f"{label} must be an exact UTC timestamp")
    try:
        return dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise CredentialCutoverError(f"{label} is invalid") from exc


def _run(command: list[str], *, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        command,
        env=env or SAFE_ENVIRONMENT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _fail("required runtime command failed")
    return result.stdout


def _git_state(repo: Path = PRODUCTION_REPO) -> tuple[str, bool]:
    head = _run([GIT, "-C", str(repo), "rev-parse", "HEAD"]).strip()
    clean = not _run(
        [GIT, "-C", str(repo), "status", "--porcelain=v1", "--untracked-files=all"]
    ).strip()
    return head, clean


def _container_id(project: str, service: str) -> str:
    output = _run(
        [
            DOCKER,
            "ps",
            "-aq",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            f"label=com.docker.compose.service={service}",
        ]
    ).splitlines()
    identifiers = [line.strip() for line in output if line.strip()]
    if len(identifiers) != 1:
        _fail("approved service does not resolve to exactly one container")
    return identifiers[0]


def _inspect(project: str, service: str) -> dict[str, Any]:
    raw = _run([DOCKER, "inspect", _container_id(project, service)])
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CredentialCutoverError("container inspection is invalid") from exc
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        _fail("container inspection shape is invalid")
    return value[0]


def invariant_snapshot(inspect: dict[str, Any]) -> dict[str, Any]:
    config = inspect.get("Config") or {}
    host = inspect.get("HostConfig") or {}
    network = inspect.get("NetworkSettings") or {}
    labels = config.get("Labels") or {}
    image_id = inspect.get("Image")
    declared_image = config.get("Image")
    if not isinstance(image_id, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", image_id
    ):
        _fail("container image ID is not immutable")
    if not isinstance(declared_image, str) or "@sha256:" not in declared_image:
        _fail("compose image must use an explicit digest")
    mounts = []
    for mount in inspect.get("Mounts") or []:
        mounts.append(
            {
                "type": mount.get("Type"),
                "name": mount.get("Name"),
                "source": mount.get("Source"),
                "destination": mount.get("Destination"),
                "mode": mount.get("Mode"),
                "rw": mount.get("RW"),
                "propagation": mount.get("Propagation"),
            }
        )
    ports = []
    for container_port, bindings in sorted((network.get("Ports") or {}).items()):
        ports.append(
            {
                "container_port": container_port,
                "bindings": sorted(
                    [
                        {
                            "host_ip": binding.get("HostIp"),
                            "host_port": binding.get("HostPort"),
                        }
                        for binding in (bindings or [])
                    ],
                    key=lambda item: (str(item["host_ip"]), str(item["host_port"])),
                ),
            }
        )
    return {
        "image_id": image_id,
        "declared_image": declared_image,
        "command": config.get("Cmd"),
        "entrypoint": config.get("Entrypoint"),
        "mounts": sorted(mounts, key=lambda item: str(item["destination"])),
        "declared_volumes": sorted((config.get("Volumes") or {}).keys()),
        "networks": sorted((network.get("Networks") or {}).keys()),
        "ports": ports,
        "restart_policy": host.get("RestartPolicy"),
        "cap_add": sorted(host.get("CapAdd") or []),
        "cap_drop": sorted(host.get("CapDrop") or []),
        "security_opt": sorted(host.get("SecurityOpt") or []),
        "compose_project": labels.get("com.docker.compose.project"),
        "compose_service": labels.get("com.docker.compose.service"),
    }


def _health_is_ready(inspect: dict[str, Any]) -> bool:
    state = inspect.get("State") or {}
    health = state.get("Health")
    if isinstance(health, dict):
        return health.get("Status") == "healthy"
    return state.get("Status") == "running"


def validate_approval(
    approval: dict[str, Any],
    *,
    now: dt.datetime,
    compose_sha256: str,
    freeze_sha256: str,
) -> list[dict[str, Any]]:
    expected_keys = {
        "schema_version",
        "gate_id",
        "decision",
        "scope",
        "approval_id",
        "approved_at",
        "expires_at",
        "production_git_sha",
        "release_freeze_state_id",
        "release_freeze_state_sha256",
        "compose_project",
        "compose_file_sha256",
        "control_sha256",
        "services",
    }
    if set(approval) != expected_keys:
        _fail("approval fields are not exact")
    if (
        approval.get("schema_version") != 1
        or approval.get("gate_id") != "GATE-01"
        or approval.get("decision") != "APPROVED"
        or approval.get("scope") != "same-image-credential-cutover"
    ):
        _fail("approval does not authorize GATE-01 credential cutover")
    if not NAME_RE.fullmatch(str(approval.get("approval_id", ""))):
        _fail("approval_id is invalid")
    approved_at = _parse_utc(approval.get("approved_at"), "approved_at")
    expires_at = _parse_utc(approval.get("expires_at"), "expires_at")
    if (
        approved_at > now + dt.timedelta(minutes=5)
        or expires_at <= now
        or expires_at > approved_at + dt.timedelta(hours=4)
    ):
        _fail("approval lifetime is invalid")
    if not GIT_SHA_RE.fullmatch(str(approval.get("production_git_sha", ""))):
        _fail("production commit fingerprint is invalid")
    if approval.get("compose_file_sha256") != compose_sha256:
        _fail("compose file fingerprint drift")
    if approval.get("control_sha256") != _file_sha256(Path(__file__)):
        _fail("credential cutover control fingerprint drift")
    if approval.get("release_freeze_state_sha256") != freeze_sha256:
        _fail("release freeze fingerprint drift")
    if not NAME_RE.fullmatch(str(approval.get("compose_project", ""))):
        _fail("compose project is invalid")
    services = approval.get("services")
    if not isinstance(services, list) or not services:
        _fail("approval must contain services")
    names: set[str] = set()
    for service in services:
        if not isinstance(service, dict) or set(service) != {
            "service",
            "expected_fingerprint",
            "allowed_credential_keys",
        }:
            _fail("approved service fields are not exact")
        name = service.get("service")
        keys = service.get("allowed_credential_keys")
        if not isinstance(name, str) or not NAME_RE.fullmatch(name) or name in names:
            _fail("approved service names are invalid or duplicated")
        names.add(name)
        if not isinstance(
            service.get("expected_fingerprint"), str
        ) or not SHA256_RE.fullmatch(service["expected_fingerprint"]):
            _fail("approved service fingerprint is invalid")
        if (
            not isinstance(keys, list)
            or not keys
            or any(
                not isinstance(key, str) or not CREDENTIAL_KEY_RE.fullmatch(key)
                for key in keys
            )
            or len(keys) != len(set(keys))
        ):
            _fail("allowed credential keys are invalid")
    return services


def _read_credentials(
    service: str, keys: list[str], *, required_uid: int
) -> dict[str, str]:
    service_dir = CREDENTIAL_ROOT / service
    for directory in (CREDENTIAL_ROOT, service_dir):
        _assert_private_directory(directory, required_uid=required_uid)
    actual_names = sorted(entry.name for entry in service_dir.iterdir())
    if actual_names != sorted(keys):
        _fail("credential file set is not exact")
    values: dict[str, str] = {}
    for key in keys:
        path = service_dir / key
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != required_uid
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_size < 1
                or metadata.st_size > 65536
            ):
                _fail("credential file metadata is unsafe")
            raw = os.read(descriptor, 65537)
        finally:
            os.close(descriptor)
        if b"\x00" in raw or b"\n" in raw or b"\r" in raw:
            _fail("credential value cannot be represented safely")
        try:
            values[key] = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CredentialCutoverError(
                "credential value encoding is invalid"
            ) from exc
    return values


def execute(
    approval: dict[str, Any],
    *,
    apply: bool,
    now: dt.datetime | None = None,
    inspect_service: Callable[[str, str], dict[str, Any]] = _inspect,
    command_runner: Callable[..., str] = _run,
    required_uid: int = 0,
) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    freeze_raw = _read_regular_bytes(FREEZE_STATE, maximum=65536)
    try:
        freeze = json.loads(freeze_raw)
    except json.JSONDecodeError as exc:
        raise CredentialCutoverError("release freeze state is invalid") from exc
    freeze_body = freeze.get("freeze") if isinstance(freeze, dict) else None
    if not isinstance(freeze_body, dict) or freeze_body.get("active") is not True:
        _fail("release freeze must remain active")
    if approval.get("release_freeze_state_id") != freeze.get("state_id"):
        _fail("approval is bound to another release freeze")
    services = validate_approval(
        approval,
        now=now,
        compose_sha256=_file_sha256(COMPOSE_FILE),
        freeze_sha256=hashlib.sha256(freeze_raw).hexdigest(),
    )
    head, clean = _git_state()
    if not clean or head != approval["production_git_sha"]:
        _fail("production checkout fingerprint drift")
    project = approval["compose_project"]
    before: dict[str, dict[str, Any]] = {}
    environment = dict(SAFE_ENVIRONMENT)
    assigned_values: dict[str, str] = {}
    for service in services:
        name = service["service"]
        inspected = inspect_service(project, name)
        snapshot = invariant_snapshot(inspected)
        if (
            snapshot["compose_project"] != project
            or snapshot["compose_service"] != name
        ):
            _fail("service or compose project drift")
        if not hmac.compare_digest(
            _canonical_sha256(snapshot), service["expected_fingerprint"]
        ):
            _fail("container invariant fingerprint drift")
        if not _health_is_ready(inspected):
            _fail("service health precondition failed")
        before[name] = snapshot
        credentials = _read_credentials(
            name, service["allowed_credential_keys"], required_uid=required_uid
        )
        for key, value in credentials.items():
            if key in assigned_values and not hmac.compare_digest(
                assigned_values[key], value
            ):
                _fail("credential key collision across approved services")
            assigned_values[key] = value
            environment[key] = value
    if not apply:
        return {
            "allowed": True,
            "operation": "credential-cutover",
            "mutation": False,
            "services": sorted(before),
        }
    if required_uid == 0 and os.geteuid() != 0:
        _fail("credential cutover apply requires root")
    if required_uid == 0:
        _assert_installed_control()
    command_runner(
        [
            DOCKER,
            "compose",
            "--project-name",
            project,
            "--file",
            str(COMPOSE_FILE),
            "up",
            "--detach",
            "--no-deps",
            "--force-recreate",
            "--no-build",
            "--pull",
            "never",
            *sorted(before),
        ],
        env=environment,
    )
    for name, expected in before.items():
        deadline = time.monotonic() + 60
        while True:
            inspected = inspect_service(project, name)
            if _health_is_ready(inspected):
                break
            if time.monotonic() >= deadline:
                _fail("service health postcondition failed")
            time.sleep(2)
        if invariant_snapshot(inspected) != expected:
            _fail("post-cutover container invariant drift")
    after_head, after_clean = _git_state()
    if after_head != head or not after_clean:
        _fail("production checkout changed during cutover")
    return {
        "allowed": True,
        "operation": "credential-cutover",
        "mutation": True,
        "services": sorted(before),
        "image_change": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("dry-run", "apply"))
    args = parser.parse_args(argv)
    try:
        approval = _read_private_json(APPROVAL_PATH, required_uid=0)
        result = execute(approval, apply=args.command == "apply")
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CredentialCutoverError, OSError) as exc:
        print(
            json.dumps(
                {"allowed": False, "reason": str(exc)},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 78


if __name__ == "__main__":
    sys.exit(main())
