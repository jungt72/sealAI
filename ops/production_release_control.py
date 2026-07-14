#!/usr/bin/python3 -I
"""Root-trusted staging and one-shot GATE-08 deployment authorization.

This program is installed under ``/usr/local/libexec/sealai`` by the separately
approved remediation-control transaction.  It never contacts a network and it
never executes a file from the operator-owned production checkout.  A local Git
repository is accepted only as an object source; the exact Gate-10 control
commit is copied into a new root-owned, non-writable checkout and fully verified
before another process may execute it.

The checked-in production freeze remains authoritative.  A GATE-08 receipt is a
second, per-deployment approval and can never replace or lift GATE-10.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, NoReturn, Sequence


CONTROL_ROOT = Path("/var/lib/sealai/release-control")
CONTROL_RELEASES = CONTROL_ROOT / "releases"
EVIDENCE_ROOT = Path("/var/lib/sealai/release-evidence")
PROMOTION_EVIDENCE = EVIDENCE_ROOT / "promotion-evidence.json"
ROLLBACK_PLAN = EVIDENCE_ROOT / "rollback-plan.json"
RUNS_DIR = EVIDENCE_ROOT / "runs"
APPROVAL_PATH = Path("/etc/sealai/approvals/gate-08-production-deployment.json")
CONSUMED_ROOT = Path("/var/lib/sealai/deployment-receipts/consumed")
DASHBOARD_RELEASE_ROOT = Path("/var/lib/sealai/dashboard-releases")
INSTALLED_DASHBOARD_TOOL = Path("/usr/local/libexec/sealai/dashboard_release.py")
DEPLOYMENT_TARGET = "sealingai-production"
DEPLOYMENT_OPERATION = "backend-v2-promote"
DEPLOY_USER = "thorsten"
MAX_DOCUMENT_BYTES = 256 * 1024
MAX_RESULTS_BYTES = 64 * 1024 * 1024
MAX_GIT_PACK_BYTES = 1024 * 1024 * 1024

GATE_DOCUMENT_PATHS = frozenset(
    {
        "ops/production-release-state.json",
        "ops/production-release-gate10-approval.json",
        "ops/production-release-manifest.json",
    }
)
RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "gate_id",
        "decision",
        "scope",
        "approval_id",
        "approved_by",
        "approved_at",
        "expires_at",
        "deployment_target",
        "operation",
        "single_use",
        "control_git_sha",
        "source_git_sha",
        "release_manifest_sha256",
        "promotion_evidence_sha256",
        "backend_image_digest",
    }
)
GATE10_DECISION_KEYS = frozenset(
    {
        "allowed",
        "operation",
        "reason",
        "state_id",
        "required_gate",
        "source_git_sha",
        "release_hashes",
    }
)
RELEASE_HASH_KEYS = frozenset(
    {
        "served_tree_sha256",
        "backend_image_digest",
        "frontend_image_digest",
        "dashboard_artifact_sha256",
        "database_migration_sha256",
        "rollback_plan_sha256",
        "evidence_manifest_sha256",
    }
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_RE = re.compile(
    r"^ghcr\.io/jungt72/sealai-backend-v2:"
    r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}@sha256:[0-9a-f]{64}$"
)
APPROVAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RELEASE_ID_RE = re.compile(r"^[0-9a-f]{40}-[0-9a-f]{64}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
RUN_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

CHILD_ENV = {
    "HOME": "/root",
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
}
GIT_ENV = {
    **CHILD_ENV,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_PROTOCOL_FROM_USER": "0",
    "GIT_ALLOW_PROTOCOL": "file",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_OPTIONAL_LOCKS": "0",
}


class ControlDenied(RuntimeError):
    """The trusted release-control proof is incomplete or unsafe."""


def _deny(message: str) -> NoReturn:
    raise ControlDenied(message)


def _parse_timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or UTC_RE.fullmatch(value) is None:
        _deny(f"{label} is not an exact UTC timestamp")
    try:
        return dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _deny(f"{label} is not an exact UTC timestamp")


def _parse_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                _deny(f"{label} contains duplicate JSON keys")
            value[key] = item
        return value

    def reject_constant(_value: str) -> None:
        _deny(f"{label} contains a non-finite number")

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate,
            parse_constant=reject_constant,
        )
    except ControlDenied:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        _deny(f"{label} is not unambiguous UTF-8 JSON")
    if not isinstance(value, dict):
        _deny(f"{label} root is not an object")
    return value


def _safe_read(
    path: Path,
    *,
    trusted_uids: frozenset[int],
    exact_mode: int | None = None,
    max_bytes: int = MAX_DOCUMENT_BYTES,
) -> bytes:
    verify_trusted_path(path, leaf_directory=False, trusted_uids=trusted_uids)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _deny("trusted document is unavailable")
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid not in trusted_uids
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or (exact_mode is not None and stat.S_IMODE(metadata.st_mode) != exact_mode)
            or metadata.st_size <= 0
            or metadata.st_size > max_bytes
        ):
            _deny("trusted document metadata is unsafe")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if not raw or len(raw) > max_bytes:
            _deny("trusted document size is unsafe")
        return raw
    finally:
        os.close(descriptor)


def verify_trusted_path(
    path: Path, *, leaf_directory: bool, trusted_uids: frozenset[int]
) -> None:
    """Reject every symlink and every untrusted/writable path component."""
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for index, part in enumerate((absolute.anchor, *absolute.parts[1:])):
        if index:
            current /= part
        try:
            metadata = current.lstat()
        except OSError:
            _deny("trusted path is unavailable")
        is_leaf = current == absolute
        directory = leaf_directory if is_leaf else True
        if (
            stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid not in trusted_uids
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or (directory and not stat.S_ISDIR(metadata.st_mode))
            or (not directory and not stat.S_ISREG(metadata.st_mode))
        ):
            _deny("trusted path owner, mode, or topology is unsafe")


def _validate_receipt(
    value: dict[str, Any],
    *,
    now: dt.datetime,
    control_sha: str,
    source_sha: str,
    backend_image: str,
) -> dict[str, Any]:
    if set(value) != RECEIPT_KEYS:
        _deny("GATE-08 deployment receipt schema is not exact")
    if (
        type(value.get("schema_version")) is not int
        or value["schema_version"] != 1
        or value.get("gate_id") != "GATE-08"
        or value.get("decision") != "APPROVED"
        or value.get("scope") != "production-deployment"
        or value.get("deployment_target") != DEPLOYMENT_TARGET
        or value.get("operation") != DEPLOYMENT_OPERATION
        or value.get("single_use") is not True
    ):
        _deny("GATE-08 receipt does not authorize this deployment operation")
    approval_id = value.get("approval_id")
    if (
        not isinstance(approval_id, str)
        or APPROVAL_ID_RE.fullmatch(approval_id) is None
    ):
        _deny("GATE-08 approval_id is invalid")
    if (
        not isinstance(value.get("approved_by"), str)
        or not value["approved_by"].strip()
    ):
        _deny("GATE-08 approved_by is invalid")
    approved_at = _parse_timestamp(value.get("approved_at"), "approved_at")
    expires_at = _parse_timestamp(value.get("expires_at"), "expires_at")
    if approved_at > now + dt.timedelta(minutes=5):
        _deny("GATE-08 receipt is future-dated")
    if (
        expires_at <= approved_at
        or expires_at <= now
        or expires_at > approved_at + dt.timedelta(hours=1)
    ):
        _deny("GATE-08 receipt is expired or over-broad")
    if value.get("control_git_sha") != control_sha:
        _deny("GATE-08 receipt is bound to another control commit")
    if value.get("source_git_sha") != source_sha:
        _deny("GATE-08 receipt is bound to another source commit")
    if value.get("backend_image_digest") != backend_image.rsplit("@", 1)[1]:
        _deny("GATE-08 receipt is bound to another backend image")
    for key in ("release_manifest_sha256", "promotion_evidence_sha256"):
        if (
            not isinstance(value.get(key), str)
            or SHA256_RE.fullmatch(value[key]) is None
        ):
            _deny(f"GATE-08 {key} is invalid")
    return value


def load_receipt(
    path: Path,
    *,
    now: dt.datetime,
    control_sha: str,
    source_sha: str,
    backend_image: str,
    trusted_uids: frozenset[int],
    exact_mode: int = 0o600,
) -> tuple[dict[str, Any], bytes, str]:
    raw = _safe_read(
        path,
        trusted_uids=trusted_uids,
        exact_mode=exact_mode,
        max_bytes=64 * 1024,
    )
    value = _validate_receipt(
        _parse_json(raw, "GATE-08 deployment receipt"),
        now=now,
        control_sha=control_sha,
        source_sha=source_sha,
        backend_image=backend_image,
    )
    return value, raw, hashlib.sha256(raw).hexdigest()


def _git(
    repo: Path | None, arguments: Sequence[str], *, check: bool = True
) -> subprocess.CompletedProcess[bytes]:
    command = [
        "/usr/bin/git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.alternateRefsCommand=/bin/false",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "protocol.file.allow=always",
    ]
    if repo is not None:
        command.extend(("-c", f"safe.directory={repo}", "-C", str(repo)))
    result = subprocess.run(
        [*command, *arguments],
        env=GIT_ENV,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        _deny("isolated local Git operation failed")
    return result


def _export_git_pack(
    source: Path,
    pack_path: Path,
    *,
    control_sha: str,
    source_uid: int,
    source_gid: int,
) -> None:
    """Export candidate objects only after dropping out of root privilege."""
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(pack_path, flags, 0o600)
    except OSError:
        _deny("isolated Git pack destination is unavailable")
    git_command = [
        "/usr/bin/git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.alternateRefsCommand=/bin/false",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "pack.threads=1",
        "-c",
        "pack.windowMemory=64m",
        "-c",
        "pack.deltaCacheSize=64m",
        "-c",
        f"safe.directory={source}",
        "-C",
        str(source),
        "pack-objects",
        "--quiet",
        "--stdout",
        "--revs",
    ]
    command = [
        "/bin/bash",
        "-p",
        "-c",
        'ulimit -f "$1"; shift; exec "$@"',
        "sealai-git-pack-export",
        str(MAX_GIT_PACK_BYTES // 1024),
        *git_command,
    ]
    if os.geteuid() == 0:
        command = [
            "/usr/bin/setpriv",
            f"--reuid={source_uid}",
            f"--regid={source_gid}",
            "--clear-groups",
            "--no-new-privs",
            "--inh-caps=-all",
            "--ambient-caps=-all",
            "--bounding-set=-all",
            *command,
        ]
    try:
        result = subprocess.run(
            command,
            input=(control_sha + "\n").encode("ascii"),
            stdout=descriptor,
            stderr=subprocess.PIPE,
            env=GIT_ENV,
            check=False,
        )
        os.fsync(descriptor)
    except OSError:
        _deny("unprivileged Git object export failed")
    finally:
        os.close(descriptor)
    try:
        metadata = pack_path.lstat()
    except OSError:
        _deny("isolated Git pack is unavailable")
    if (
        result.returncode != 0
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size <= 0
        or metadata.st_size > MAX_GIT_PACK_BYTES
    ):
        _deny("unprivileged Git object export failed")


def _index_git_pack(checkout: Path, pack_path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(pack_path, flags)
    except OSError:
        _deny("isolated Git pack is unavailable")
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size <= 0
            or metadata.st_size > MAX_GIT_PACK_BYTES
        ):
            _deny("isolated Git pack metadata is unsafe")
        result = subprocess.run(
            [
                "/usr/bin/git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "core.alternateRefsCommand=/bin/false",
                "-c",
                "core.fsmonitor=false",
                "-c",
                f"safe.directory={checkout}",
                "-C",
                str(checkout),
                "index-pack",
                "--stdin",
            ],
            stdin=descriptor,
            env=GIT_ENV,
            capture_output=True,
            check=False,
        )
    finally:
        os.close(descriptor)
    if result.returncode != 0:
        _deny("isolated Git pack import failed")


def _normalize_root_tree(root: Path, *, uid: int) -> None:
    for directory, directories, files in os.walk(
        root, topdown=False, followlinks=False
    ):
        directory_path = Path(directory)
        for name in files:
            path = directory_path / name
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != uid
            ):
                _deny("staged checkout contains an unsupported file")
            executable = bool(stat.S_IMODE(metadata.st_mode) & 0o111)
            path.chmod(0o755 if executable else 0o644)
        for name in directories:
            path = directory_path / name
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != uid
            ):
                _deny("staged checkout contains an unsupported directory")
            path.chmod(0o755)
        if directory_path.lstat().st_uid != uid:
            _deny("staged checkout directory owner is unsafe")
        directory_path.chmod(0o755)


def _verify_git_checkout(checkout: Path, control_sha: str, source_sha: str) -> None:
    if _git(checkout, ("rev-parse", "HEAD")).stdout.decode().strip() != control_sha:
        _deny("staged checkout HEAD does not match the approved control commit")
    lineage = (
        _git(checkout, ("rev-list", "--parents", "-n", "1", "HEAD"))
        .stdout.decode()
        .strip()
        .split()
    )
    if lineage != [control_sha, source_sha]:
        _deny("staged checkout does not have the exact two-commit lineage")
    changed = {
        line
        for line in _git(
            checkout,
            ("diff", "--name-only", "--no-renames", source_sha, control_sha, "--"),
        )
        .stdout.decode()
        .splitlines()
        if line
    }
    if changed != GATE_DOCUMENT_PATHS:
        _deny("Gate-10 control commit changed files outside the fixed document set")
    tree = _git(checkout, ("ls-tree", "-r", "-z", "HEAD")).stdout.split(b"\0")
    if not tree or tree[-1] != b"":
        _deny("staged checkout tree listing is malformed")
    for record in tree[:-1]:
        try:
            metadata, path = record.split(b"\t", 1)
            mode, kind, _object_id = metadata.split(b" ", 2)
        except ValueError:
            _deny("staged checkout tree listing is malformed")
        if not path or kind != b"blob" or mode not in {b"100644", b"100755"}:
            _deny("staged checkout contains a symlink, submodule, or special mode")
    if _git(checkout, ("status", "--porcelain=v1", "--untracked-files=all")).stdout:
        _deny("staged checkout is not clean")


def _verify_manifest_binding(
    checkout: Path,
    receipt: dict[str, Any],
    *,
    trusted_uids: frozenset[int],
) -> dict[str, Any]:
    manifest_path = checkout / "ops/production-release-manifest.json"
    raw = _safe_read(manifest_path, trusted_uids=trusted_uids)
    if not hmac.compare_digest(
        hashlib.sha256(raw).hexdigest(), receipt["release_manifest_sha256"]
    ):
        _deny("staged release manifest does not match the GATE-08 receipt")
    manifest = _parse_json(raw, "Gate-10 release manifest")
    if manifest.get("source_git_sha") != receipt["source_git_sha"]:
        _deny("Gate-10 manifest is bound to another source commit")
    hashes = manifest.get("hashes")
    if not isinstance(hashes, dict) or set(hashes) != RELEASE_HASH_KEYS:
        _deny("Gate-10 manifest release hashes are not exact")
    if hashes.get("backend_image_digest") != receipt["backend_image_digest"]:
        _deny("Gate-10 manifest backend digest does not match GATE-08")
    if hashes.get("evidence_manifest_sha256") != receipt["promotion_evidence_sha256"]:
        _deny("Gate-10 manifest evidence digest does not match GATE-08")
    return manifest


def verify_stage(
    checkout: Path,
    *,
    control_sha: str,
    source_sha: str,
    receipt: dict[str, Any],
    trusted_uids: frozenset[int],
) -> dict[str, Any]:
    expected = CONTROL_RELEASES / control_sha
    if trusted_uids == frozenset({0}) and checkout != expected:
        _deny("release-control checkout is not at the fixed control path")
    verify_trusted_path(checkout, leaf_directory=True, trusted_uids=trusted_uids)
    verify_trusted_path(
        checkout / ".git", leaf_directory=True, trusted_uids=trusted_uids
    )
    _verify_git_checkout(checkout, control_sha, source_sha)
    return _verify_manifest_binding(checkout, receipt, trusted_uids=trusted_uids)


def stage_control(
    source: Path,
    destination: Path,
    *,
    control_sha: str,
    source_sha: str,
    receipt: dict[str, Any],
    trusted_uid: int,
    source_uid: int | None = None,
    source_gid: int | None = None,
) -> None:
    """Materialize one exact local commit without running source-controlled code."""
    if destination.exists() or destination.is_symlink():
        _deny("release-control destination already exists")
    try:
        source = source.resolve(strict=True)
    except OSError:
        _deny("local source repository is unavailable")
    if not source.is_dir():
        _deny("local source repository is not a directory")
    parent = destination.parent
    verify_trusted_path(
        parent, leaf_directory=True, trusted_uids=frozenset({0, trusted_uid})
    )
    temporary = Path(tempfile.mkdtemp(prefix=".control-stage-", dir=parent))
    checkout = temporary / "checkout"
    pack_path = temporary / "candidate.pack"
    try:
        _git(None, ("init", "--quiet", str(checkout)))
        _export_git_pack(
            source,
            pack_path,
            control_sha=control_sha,
            source_uid=os.geteuid() if source_uid is None else source_uid,
            source_gid=os.getegid() if source_gid is None else source_gid,
        )
        _index_git_pack(checkout, pack_path)
        _git(checkout, ("checkout", "--quiet", "--detach", control_sha, "--"))
        _verify_git_checkout(checkout, control_sha, source_sha)
        _normalize_root_tree(checkout, uid=trusted_uid)
        verify_trusted_path(
            checkout, leaf_directory=True, trusted_uids=frozenset({0, trusted_uid})
        )
        _verify_manifest_binding(
            checkout, receipt, trusted_uids=frozenset({0, trusted_uid})
        )
        os.replace(checkout, destination)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def validate_gate10_decision(
    value: dict[str, Any],
    *,
    receipt: dict[str, Any],
    source_sha: str,
    backend_image: str,
) -> dict[str, str]:
    if set(value) != GATE10_DECISION_KEYS:
        _deny("Gate-10 success decision schema is not exact")
    if (
        value.get("allowed") is not True
        or value.get("operation") != "deploy"
        or value.get("reason") != "gate10_approved_manifest_bound"
        or value.get("required_gate") != "GATE-10"
        or value.get("source_git_sha") != source_sha
        or not isinstance(value.get("state_id"), str)
        or not value["state_id"].strip()
    ):
        _deny("Gate-10 decision does not authorize this exact deployment")
    hashes = value.get("release_hashes")
    if not isinstance(hashes, dict) or set(hashes) != RELEASE_HASH_KEYS:
        _deny("Gate-10 decision release hashes are not exact")
    for name, item in hashes.items():
        pattern = DIGEST_RE if name.endswith("_image_digest") else SHA256_RE
        if not isinstance(item, str) or pattern.fullmatch(item) is None:
            _deny("Gate-10 decision contains an invalid release hash")
    if hashes["backend_image_digest"] != backend_image.rsplit("@", 1)[1]:
        _deny("requested image does not match the Gate-10 backend digest")
    if hashes["backend_image_digest"] != receipt["backend_image_digest"]:
        _deny("Gate-10 backend digest does not match GATE-08")
    if hashes["evidence_manifest_sha256"] != receipt["promotion_evidence_sha256"]:
        _deny("Gate-10 evidence digest does not match GATE-08")
    return {str(key): str(item) for key, item in hashes.items()}


def verify_evidence_bundle(
    release_hashes: dict[str, str], *, trusted_uids: frozenset[int]
) -> None:
    verify_trusted_path(EVIDENCE_ROOT, leaf_directory=True, trusted_uids=trusted_uids)
    verify_trusted_path(RUNS_DIR, leaf_directory=True, trusted_uids=trusted_uids)
    evidence = _safe_read(PROMOTION_EVIDENCE, trusted_uids=trusted_uids)
    rollback = _safe_read(ROLLBACK_PLAN, trusted_uids=trusted_uids)
    if not hmac.compare_digest(
        hashlib.sha256(evidence).hexdigest(),
        release_hashes["evidence_manifest_sha256"],
    ):
        _deny("fixed promotion evidence does not match Gate-10")
    if not hmac.compare_digest(
        hashlib.sha256(rollback).hexdigest(), release_hashes["rollback_plan_sha256"]
    ):
        _deny("fixed rollback plan does not match Gate-10")
    promotion = _parse_json(evidence, "promotion evidence")
    payload = promotion.get("payload")
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, dict) or set(results) != {
        "run_label",
        "results_sha256",
    }:
        _deny("promotion evidence has no exact results binding")
    run_label = results.get("run_label")
    results_sha256 = results.get("results_sha256")
    if (
        not isinstance(run_label, str)
        or RUN_LABEL_RE.fullmatch(run_label) is None
        or not isinstance(results_sha256, str)
        or SHA256_RE.fullmatch(results_sha256) is None
    ):
        _deny("promotion evidence results binding is invalid")
    run_dir = RUNS_DIR / run_label
    verify_trusted_path(run_dir, leaf_directory=True, trusted_uids=trusted_uids)
    run_results = _safe_read(
        run_dir / "results.json",
        trusted_uids=trusted_uids,
        max_bytes=MAX_RESULTS_BYTES,
    )
    if not hmac.compare_digest(hashlib.sha256(run_results).hexdigest(), results_sha256):
        _deny("fixed promotion result does not match the approved evidence")


def _dashboard_tool(
    arguments: Sequence[str], *, tool: Path = INSTALLED_DASHBOARD_TOOL
) -> dict[str, Any]:
    verify_trusted_path(
        tool, leaf_directory=False, trusted_uids=frozenset({0, os.geteuid()})
    )
    result = subprocess.run(
        ["/usr/bin/python3", "-I", str(tool), *arguments],
        env=CHILD_ENV,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or len(result.stdout) > MAX_DOCUMENT_BYTES:
        _deny("installed dashboard release verifier denied the artifact")
    return _parse_json(result.stdout, "dashboard verifier output")


def verify_dashboard_release(
    *,
    source_git_sha: str,
    artifact_sha256: str,
    trusted_uids: frozenset[int],
    release_root: Path = DASHBOARD_RELEASE_ROOT,
    tool: Path = INSTALLED_DASHBOARD_TOOL,
) -> tuple[str, dict[str, Any]]:
    release_id = f"{source_git_sha}-{artifact_sha256}"
    if RELEASE_ID_RE.fullmatch(release_id) is None:
        _deny("Gate-10 dashboard release identity is invalid")
    verify_trusted_path(release_root, leaf_directory=True, trusted_uids=trusted_uids)
    verify_trusted_path(
        release_root / "artifacts", leaf_directory=True, trusted_uids=trusted_uids
    )
    release = release_root / "artifacts" / release_id
    verify_trusted_path(release, leaf_directory=True, trusted_uids=trusted_uids)
    value = _dashboard_tool(("verify", "--release", str(release)), tool=tool)
    if (
        value.get("result") != "ok"
        or value.get("operation") != "dashboard-verify"
        or value.get("mutation_performed") is not False
        or value.get("release_id") != release_id
        or value.get("source_git_sha") != source_git_sha
        or value.get("artifact_sha256") != artifact_sha256
    ):
        _deny("dashboard artifact does not match Gate-10")
    return release_id, value


def _dashboard_link(root: Path, name: str, *, missing_ok: bool) -> str | None:
    if name not in {"current", "rollback"}:
        _deny("dashboard link name is invalid")
    path = root / name
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return None
        _deny(f"dashboard {name} link is missing")
    if not stat.S_ISLNK(metadata.st_mode) or metadata.st_uid != os.geteuid():
        _deny(f"dashboard {name} link is unsafe")
    target = os.readlink(path)
    if (
        not target.startswith("artifacts/")
        or RELEASE_ID_RE.fullmatch(target.removeprefix("artifacts/")) is None
    ):
        _deny(f"dashboard {name} target is unsafe")
    return target


def _verify_dashboard_target(
    target: str,
    *,
    trusted_uids: frozenset[int],
    release_root: Path,
    tool: Path,
) -> str:
    release_id = target.removeprefix("artifacts/")
    if RELEASE_ID_RE.fullmatch(release_id) is None:
        _deny("dashboard release target is invalid")
    source_git_sha, artifact_sha256 = release_id.split("-", maxsplit=1)
    verify_dashboard_release(
        source_git_sha=source_git_sha,
        artifact_sha256=artifact_sha256,
        trusted_uids=trusted_uids,
        release_root=release_root,
        tool=tool,
    )
    return release_id


def _atomic_dashboard_link(root: Path, name: str, target: str) -> None:
    if name not in {"current", "rollback"} or not target.startswith("artifacts/"):
        _deny("dashboard atomic link request is invalid")
    if RELEASE_ID_RE.fullmatch(target.removeprefix("artifacts/")) is None:
        _deny("dashboard atomic link target is invalid")
    pending = root / f".{name}.{os.getpid()}.{os.urandom(12).hex()}.tmp"
    try:
        os.symlink(target, pending)
        metadata = pending.lstat()
        if not stat.S_ISLNK(metadata.st_mode) or os.readlink(pending) != target:
            _deny("dashboard atomic link staging failed")
        os.replace(pending, root / name)
        descriptor = os.open(
            root,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        _deny("dashboard atomic link switch failed")
    finally:
        try:
            pending.unlink()
        except FileNotFoundError:
            pass


def _remove_dashboard_link(root: Path, name: str) -> None:
    _dashboard_link(root, name, missing_ok=False)
    try:
        (root / name).unlink()
        descriptor = os.open(
            root,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        _deny("dashboard atomic link removal failed")


def activate_dashboard_release(
    *,
    source_git_sha: str,
    artifact_sha256: str,
    trusted_uids: frozenset[int],
    release_root: Path = DASHBOARD_RELEASE_ROOT,
    tool: Path = INSTALLED_DASHBOARD_TOOL,
) -> dict[str, Any]:
    release_id, _ = verify_dashboard_release(
        source_git_sha=source_git_sha,
        artifact_sha256=artifact_sha256,
        trusted_uids=trusted_uids,
        release_root=release_root,
        tool=tool,
    )
    target = f"artifacts/{release_id}"
    current = _dashboard_link(release_root, "current", missing_ok=True)
    previous_rollback = _dashboard_link(release_root, "rollback", missing_ok=True)
    if current == target:
        if previous_rollback is not None:
            _verify_dashboard_target(
                previous_rollback,
                trusted_uids=trusted_uids,
                release_root=release_root,
                tool=tool,
            )
        return {"activated": True, "changed": False, "release_id": release_id}
    if current is not None:
        _verify_dashboard_target(
            current,
            trusted_uids=trusted_uids,
            release_root=release_root,
            tool=tool,
        )
    if previous_rollback is not None:
        _verify_dashboard_target(
            previous_rollback,
            trusted_uids=trusted_uids,
            release_root=release_root,
            tool=tool,
        )
    if current is not None:
        _atomic_dashboard_link(release_root, "rollback", current)
    try:
        _atomic_dashboard_link(release_root, "current", target)
        if _dashboard_link(release_root, "current", missing_ok=False) != target:
            _deny("dashboard current verification failed")
        verify_dashboard_release(
            source_git_sha=source_git_sha,
            artifact_sha256=artifact_sha256,
            trusted_uids=trusted_uids,
            release_root=release_root,
            tool=tool,
        )
    except ControlDenied:
        if current is not None:
            _atomic_dashboard_link(release_root, "current", current)
        else:
            _remove_dashboard_link(release_root, "current")
        if previous_rollback is not None:
            _atomic_dashboard_link(release_root, "rollback", previous_rollback)
        elif current is not None:
            _remove_dashboard_link(release_root, "rollback")
        raise
    return {
        "activated": True,
        "changed": True,
        "release_id": release_id,
        "previous_current": current,
    }


def rollback_dashboard_release(
    *,
    trusted_uids: frozenset[int],
    release_root: Path = DASHBOARD_RELEASE_ROOT,
    tool: Path = INSTALLED_DASHBOARD_TOOL,
) -> dict[str, Any]:
    verify_trusted_path(release_root, leaf_directory=True, trusted_uids=trusted_uids)
    current = _dashboard_link(release_root, "current", missing_ok=False)
    rollback = _dashboard_link(release_root, "rollback", missing_ok=False)
    if current == rollback:
        _deny("dashboard rollback target equals current")
    _verify_dashboard_target(
        current,
        trusted_uids=trusted_uids,
        release_root=release_root,
        tool=tool,
    )
    release_id = _verify_dashboard_target(
        rollback,
        trusted_uids=trusted_uids,
        release_root=release_root,
        tool=tool,
    )
    try:
        _atomic_dashboard_link(release_root, "current", rollback)
        _atomic_dashboard_link(release_root, "rollback", current)
        if _dashboard_link(release_root, "current", missing_ok=False) != rollback:
            _deny("dashboard rollback exposure verification failed")
    except ControlDenied:
        _atomic_dashboard_link(release_root, "current", current)
        _atomic_dashboard_link(release_root, "rollback", rollback)
        raise
    return {"rolled_back": True, "release_id": release_id}


def consume_receipt(
    receipt: dict[str, Any],
    raw: bytes,
    *,
    expected_receipt_sha256: str,
    consumed_root: Path,
    trusted_uid: int,
) -> Path:
    actual = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual, expected_receipt_sha256):
        _deny("GATE-08 receipt changed before consumption")
    verify_trusted_path(
        consumed_root,
        leaf_directory=True,
        trusted_uids=frozenset({0, trusted_uid}),
    )
    target = consumed_root / f"{receipt['approval_id']}.json"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError:
        _deny("GATE-08 deployment receipt was already consumed")
    except OSError:
        _deny("GATE-08 receipt consumption store is unavailable")
    record = {
        "approval_id": receipt["approval_id"],
        "backend_image_digest": receipt["backend_image_digest"],
        "operation": receipt["operation"],
        "promotion_evidence_sha256": receipt["promotion_evidence_sha256"],
        "release_manifest_sha256": receipt["release_manifest_sha256"],
        "receipt_sha256": actual,
        "source_git_sha": receipt["source_git_sha"],
        "control_git_sha": receipt["control_git_sha"],
    }
    payload = (
        json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("ascii")
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _deny("GATE-08 receipt consumption write failed")
            view = view[written:]
        os.fsync(descriptor)
    except OSError:
        _deny("GATE-08 receipt consumption write failed")
    finally:
        os.close(descriptor)
    try:
        directory = os.open(
            consumed_root,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        _deny("GATE-08 receipt consumption directory sync failed")
    return target


def assert_receipt_consumed(
    receipt: dict[str, Any], raw: bytes, *, trusted_uids: frozenset[int]
) -> None:
    path = CONSUMED_ROOT / f"{receipt['approval_id']}.json"
    consumed_raw = _safe_read(
        path,
        trusted_uids=trusted_uids,
        exact_mode=0o600,
        max_bytes=64 * 1024,
    )
    value = _parse_json(consumed_raw, "consumed GATE-08 receipt")
    expected = {
        "approval_id": receipt["approval_id"],
        "backend_image_digest": receipt["backend_image_digest"],
        "control_git_sha": receipt["control_git_sha"],
        "operation": receipt["operation"],
        "promotion_evidence_sha256": receipt["promotion_evidence_sha256"],
        "receipt_sha256": hashlib.sha256(raw).hexdigest(),
        "release_manifest_sha256": receipt["release_manifest_sha256"],
        "source_git_sha": receipt["source_git_sha"],
    }
    if value != expected:
        _deny("consumed GATE-08 receipt record does not match authorization")


def _require_root() -> None:
    if os.geteuid() != 0:
        _deny("root is required for installed production release control")


def _common_identity(args: argparse.Namespace) -> tuple[str, str, str]:
    control_sha = str(args.control_sha)
    source_sha = str(args.source_sha)
    backend_image = str(args.backend_image)
    if (
        GIT_SHA_RE.fullmatch(control_sha) is None
        or GIT_SHA_RE.fullmatch(source_sha) is None
    ):
        _deny("full control and source Git SHAs are required")
    if IMAGE_RE.fullmatch(backend_image) is None:
        _deny("one digest-pinned backend image is required")
    return control_sha, source_sha, backend_image


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in (
        "stage",
        "verify-stage",
        "authorize",
        "consume",
        "activate-dashboard",
    ):
        command = commands.add_parser(name)
        command.add_argument("--control-sha", required=True)
        command.add_argument("--source-sha", required=True)
        command.add_argument("--backend-image", required=True)
        if name == "stage":
            command.add_argument("--source-repository", required=True)
            command.add_argument("--apply", action="store_true", required=True)
        if name in {"authorize", "activate-dashboard"}:
            command.add_argument("--gate10-decision-file", required=True)
        if name == "consume":
            command.add_argument("--expected-receipt-sha256", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _require_root()
    os.umask(0o077)
    control_sha, source_sha, backend_image = _common_identity(args)
    now = dt.datetime.now(dt.timezone.utc)
    receipt, raw, receipt_hash = load_receipt(
        APPROVAL_PATH,
        now=now,
        control_sha=control_sha,
        source_sha=source_sha,
        backend_image=backend_image,
        trusted_uids=frozenset({0}),
    )
    checkout = CONTROL_RELEASES / control_sha
    if args.command == "stage":
        try:
            deployment_identity = pwd.getpwnam(DEPLOY_USER)
        except KeyError:
            _deny("deployment account is unavailable")
        stage_control(
            Path(args.source_repository),
            checkout,
            control_sha=control_sha,
            source_sha=source_sha,
            receipt=receipt,
            trusted_uid=0,
            source_uid=deployment_identity.pw_uid,
            source_gid=deployment_identity.pw_gid,
        )
        print(json.dumps({"staged": True, "control_git_sha": control_sha}))
        return 0
    manifest = verify_stage(
        checkout,
        control_sha=control_sha,
        source_sha=source_sha,
        receipt=receipt,
        trusted_uids=frozenset({0}),
    )
    if args.command == "verify-stage":
        print(
            json.dumps(
                {
                    "verified": True,
                    "receipt_sha256": receipt_hash,
                    "release_manifest_sha256": receipt["release_manifest_sha256"],
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command in {"authorize", "activate-dashboard"}:
        decision_raw = _safe_read(
            Path(args.gate10_decision_file),
            trusted_uids=frozenset({0}),
            exact_mode=0o600,
            max_bytes=64 * 1024,
        )
        decision = _parse_json(decision_raw, "Gate-10 decision")
        release_hashes = validate_gate10_decision(
            decision,
            receipt=receipt,
            source_sha=source_sha,
            backend_image=backend_image,
        )
        if manifest["hashes"] != release_hashes:
            _deny("trusted Gate-10 decision and staged manifest disagree")
        verify_evidence_bundle(release_hashes, trusted_uids=frozenset({0}))
        verify_dashboard_release(
            source_git_sha=source_sha,
            artifact_sha256=release_hashes["dashboard_artifact_sha256"],
            trusted_uids=frozenset({0}),
        )
        if args.command == "activate-dashboard":
            assert_receipt_consumed(receipt, raw, trusted_uids=frozenset({0}))
            result = activate_dashboard_release(
                source_git_sha=source_sha,
                artifact_sha256=release_hashes["dashboard_artifact_sha256"],
                trusted_uids=frozenset({0}),
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        print(
            json.dumps(
                {
                    "authorized": True,
                    "receipt_sha256": receipt_hash,
                    "source_git_sha": source_sha,
                    "backend_image_digest": release_hashes["backend_image_digest"],
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command == "consume":
        if SHA256_RE.fullmatch(args.expected_receipt_sha256) is None:
            _deny("expected receipt SHA-256 is invalid")
        consume_receipt(
            receipt,
            raw,
            expected_receipt_sha256=args.expected_receipt_sha256,
            consumed_root=CONSUMED_ROOT,
            trusted_uid=0,
        )
        print(json.dumps({"consumed": True, "approval_id": receipt["approval_id"]}))
        return 0
    _deny("unsupported release-control command")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ControlDenied as exc:
        print(
            json.dumps(
                {
                    "component": "sealai-production-release-control",
                    "allowed": False,
                    "reason": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(78) from None
