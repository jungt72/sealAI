#!/usr/bin/env python3
"""Fingerprint and retire only the two legacy GATE-08 systemd units."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Callable


LEGACY_TIMER = "sealai-docker-disk-guard.timer"
LEGACY_SERVICE = "sealai-docker-disk-guard.service"
LEGACY_UNITS = (LEGACY_TIMER, LEGACY_SERVICE)
EXPECTED_FRAGMENTS = {
    LEGACY_TIMER: Path("/etc/systemd/system/sealai-docker-disk-guard.timer"),
    LEGACY_SERVICE: Path("/etc/systemd/system/sealai-docker-disk-guard.service"),
}
DEFAULT_MANIFEST = Path("/etc/sealai/approvals/gate-08-legacy-units.json")
DEFAULT_EVIDENCE_ROOT = Path("/var/lib/sealai-disk-guard/legacy-unit-evidence")
SYSTEMCTL = "/usr/bin/systemctl"
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
APPROVAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class LegacyUnitError(RuntimeError):
    """The legacy unit transition cannot be proven safe."""


def _fail(message: str) -> None:
    raise LegacyUnitError(message)


def _run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        _fail("systemd operation failed")
    return result.stdout


def _private_json(path: Path, *, required_uid: int) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != required_uid
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > 65536
        ):
            _fail("legacy unit manifest metadata is unsafe")
        raw = os.read(descriptor, 65537)
    finally:
        os.close(descriptor)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LegacyUnitError("legacy unit manifest is invalid") from exc
    if not isinstance(value, dict):
        _fail("legacy unit manifest root must be an object")
    return value


def _parse_timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        _fail(f"{label} must be an exact UTC timestamp")
    try:
        return dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise LegacyUnitError(f"{label} is invalid") from exc


def _fragment_bytes(path: Path, *, required_uid: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != required_uid
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or metadata.st_size > 1024 * 1024
        ):
            _fail("legacy unit fragment metadata is unsafe")
        raw = b""
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            raw += chunk
    finally:
        os.close(descriptor)
    return raw


def query_unit(
    unit: str, *, runner: Callable[[list[str]], str] = _run
) -> dict[str, str]:
    if unit not in LEGACY_UNITS:
        _fail("unexpected legacy unit")
    raw = runner(
        [
            SYSTEMCTL,
            "show",
            "--no-pager",
            "--property=LoadState",
            "--property=ActiveState",
            "--property=UnitFileState",
            "--property=FragmentPath",
            unit,
        ]
    )
    values: dict[str, str] = {}
    for line in raw.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {
            "LoadState",
            "ActiveState",
            "UnitFileState",
            "FragmentPath",
        }:
            values[key] = value
    if set(values) != {"LoadState", "ActiveState", "UnitFileState", "FragmentPath"}:
        _fail("systemd unit fingerprint is incomplete")
    return {
        "unit_name": unit,
        "load_state": values["LoadState"],
        "active_state": values["ActiveState"],
        "unit_file_state": values["UnitFileState"],
        "fragment_path": values["FragmentPath"],
    }


def validate_manifest(
    manifest: dict[str, Any],
    *,
    now: dt.datetime,
    runner: Callable[[list[str]], str] = _run,
    required_uid: int = 0,
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    if set(manifest) != {
        "schema_version",
        "gate_id",
        "decision",
        "scope",
        "approval_id",
        "approved_at",
        "expires_at",
        "units",
    }:
        _fail("legacy unit manifest fields are not exact")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("gate_id") != "GATE-08"
        or manifest.get("decision") != "APPROVED"
        or manifest.get("scope") != "legacy-disk-guard-unit-retirement"
        or not APPROVAL_ID_RE.fullmatch(str(manifest.get("approval_id", "")))
    ):
        _fail("legacy unit retirement is not approved")
    approved_at = _parse_timestamp(manifest.get("approved_at"), "approved_at")
    expires_at = _parse_timestamp(manifest.get("expires_at"), "expires_at")
    if (
        approved_at > now + dt.timedelta(minutes=5)
        or expires_at <= now
        or expires_at > approved_at + dt.timedelta(hours=4)
    ):
        _fail("legacy unit approval lifetime is invalid")
    units = manifest.get("units")
    if not isinstance(units, list) or len(units) != 2:
        _fail("legacy unit manifest must contain exactly two units")
    by_name: dict[str, dict[str, Any]] = {}
    fragments: dict[str, bytes] = {}
    expected_fields = {
        "unit_name",
        "load_state",
        "active_state",
        "unit_file_state",
        "fragment_path",
        "fragment_sha256",
    }
    for expected in units:
        if not isinstance(expected, dict) or set(expected) != expected_fields:
            _fail("legacy unit fingerprint fields are not exact")
        unit = expected.get("unit_name")
        if unit not in LEGACY_UNITS or unit in by_name:
            _fail("legacy unit set is not exact")
        by_name[unit] = expected
    if set(by_name) != set(LEGACY_UNITS):
        _fail("legacy unit set is not exact")
    if (
        by_name[LEGACY_TIMER].get("load_state") != "loaded"
        or by_name[LEGACY_TIMER].get("active_state") != "active"
        or by_name[LEGACY_TIMER].get("unit_file_state") != "enabled"
    ):
        _fail("legacy timer approval does not match the known active/enabled state")
    if (
        by_name[LEGACY_SERVICE].get("load_state") != "loaded"
        or by_name[LEGACY_SERVICE].get("active_state") != "failed"
    ):
        _fail("legacy service approval does not match the known failed state")
    actual_values: list[dict[str, Any]] = []
    for unit in LEGACY_UNITS:
        expected = by_name[unit]
        fragment = EXPECTED_FRAGMENTS[unit]
        if expected.get("fragment_path") != str(fragment):
            _fail("legacy fragment path is not the fixed path")
        raw = _fragment_bytes(fragment, required_uid=required_uid)
        digest = hashlib.sha256(raw).hexdigest()
        if (
            not isinstance(expected.get("fragment_sha256"), str)
            or not SHA256_RE.fullmatch(expected["fragment_sha256"])
            or expected["fragment_sha256"] != digest
        ):
            _fail("legacy fragment hash drift")
        actual = query_unit(unit, runner=runner)
        if actual != {name: expected[name] for name in actual}:
            _fail("legacy unit state drift")
        actual_values.append(expected)
        fragments[unit] = raw
    return actual_values, fragments


def _write_private(path: Path, raw: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _prepare_evidence_root(path: Path, *, required_uid: int) -> None:
    parent = path.parent.lstat()
    if (
        stat.S_ISLNK(parent.st_mode)
        or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid not in {0, required_uid}
        or stat.S_IMODE(parent.st_mode) & 0o022
    ):
        _fail("evidence parent is unsafe")
    if path.exists() or path.is_symlink():
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != required_uid
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            _fail("evidence root is unsafe")
        return
    path.mkdir(mode=0o700)


def execute(
    manifest: dict[str, Any],
    *,
    apply: bool,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    now: dt.datetime | None = None,
    runner: Callable[[list[str]], str] = _run,
    required_uid: int = 0,
) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    before, fragments = validate_manifest(
        manifest, now=now, runner=runner, required_uid=required_uid
    )
    if not apply:
        return {
            "allowed": True,
            "operation": "legacy-unit-retirement",
            "mutation": False,
            "units": list(LEGACY_UNITS),
        }
    if required_uid == 0 and os.geteuid() != 0:
        _fail("legacy unit retirement apply requires root")
    runner([SYSTEMCTL, "stop", LEGACY_TIMER])
    runner([SYSTEMCTL, "disable", LEGACY_TIMER])
    timer_after = query_unit(LEGACY_TIMER, runner=runner)
    if (
        timer_after["active_state"] != "inactive"
        or timer_after["unit_file_state"] != "disabled"
    ):
        _fail("legacy timer neutralization failed")
    pid_raw = runner(
        [
            SYSTEMCTL,
            "show",
            "--no-pager",
            "--property=MainPID",
            "--property=ControlPID",
            LEGACY_SERVICE,
        ]
    )
    pids = dict(
        line.partition("=")[::2] for line in pid_raw.splitlines() if "=" in line
    )
    if pids != {"MainPID": "0", "ControlPID": "0"}:
        _fail("legacy guard process is still running")

    _prepare_evidence_root(evidence_root, required_uid=required_uid)
    evidence_dir = evidence_root / manifest["approval_id"]
    evidence_dir.mkdir(mode=0o700)
    for unit, raw in fragments.items():
        _write_private(evidence_dir / unit, raw)
    _write_private(
        evidence_dir / "status-before.json",
        (json.dumps(before, sort_keys=True, indent=2) + "\n").encode(),
    )
    _write_private(
        evidence_dir / "status-after.json",
        (
            json.dumps(
                [timer_after, query_unit(LEGACY_SERVICE, runner=runner)],
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode(),
    )
    return {
        "allowed": True,
        "operation": "legacy-unit-retirement",
        "mutation": True,
        "legacy_timer_active": False,
        "legacy_timer_enabled": False,
        "evidence_id": manifest["approval_id"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("dry-run", "apply"))
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    args = parser.parse_args(argv)
    try:
        manifest = _private_json(args.manifest, required_uid=0)
        result = execute(
            manifest,
            apply=args.command == "apply",
            evidence_root=args.evidence_root,
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (LegacyUnitError, OSError) as exc:
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
