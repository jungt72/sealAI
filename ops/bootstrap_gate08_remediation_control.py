#!/usr/bin/python3 -I
"""Minimal hash-bound root bootstrap for the narrow GATE-08 control install."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from typing import Any, NoReturn, Sequence


RECEIPT = Path("/etc/sealai/approvals/gate-08-remediation-control.json")
SELF_ARTIFACT = "ops/bootstrap_gate08_remediation_control.py"
GATE_ARTIFACT = "ops/production_release_gate.py"
STATE_ARTIFACT = "ops/production-release-state.json"
RECEIPT_KEYS = {
    "schema_version",
    "gate_id",
    "decision",
    "scope",
    "approval_id",
    "approved_by",
    "approved_at",
    "expires_at",
    "source_git_sha",
    "artifact_sha256",
}
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
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
    "GIT_ALLOW_PROTOCOL": "file",
    "GIT_PROTOCOL_FROM_USER": "0",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_OPTIONAL_LOCKS": "0",
}


class BootstrapDenied(RuntimeError):
    """Authorization or source integrity could not be proven."""


def _deny(message: str) -> NoReturn:
    raise BootstrapDenied(message)


def _secure_lstat(path: Path, *, directory: bool) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError:
        _deny("trusted path is unavailable")
    if (
        stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or (directory and not stat.S_ISDIR(metadata.st_mode))
        or (not directory and not stat.S_ISREG(metadata.st_mode))
    ):
        _deny("trusted path owner, mode, or topology is unsafe")
    return metadata


def _verify_chain(path: Path, *, leaf_directory: bool) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for index, part in enumerate((absolute.anchor, *absolute.parts[1:])):
        if index:
            current /= part
        _secure_lstat(
            current,
            directory=leaf_directory if current == absolute else True,
        )


def _safe_digest(path: Path) -> str:
    _verify_chain(path, leaf_directory=False)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _deny("trusted file cannot be opened safely")
    digest = hashlib.sha256()
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
        ):
            _deny("opened trusted file is unsafe")
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest()


def _read_receipt() -> tuple[dict[str, Any], bytes]:
    _verify_chain(RECEIPT, leaf_directory=False)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(RECEIPT, flags)
    except OSError:
        _deny("private receipt is unavailable")
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > 64 * 1024
        ):
            _deny("private receipt is unsafe")
        raw = os.read(descriptor, 64 * 1024 + 1)
    finally:
        os.close(descriptor)
    try:
        receipt = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        _deny("private receipt is invalid")
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_KEYS:
        _deny("private receipt schema is not exact")
    return receipt, raw


def _timestamp(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        _deny("private receipt timestamp is invalid")
    try:
        return dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _deny("private receipt timestamp is invalid")


def _validate_receipt(receipt: dict[str, Any]) -> tuple[str, dict[str, str]]:
    if (
        receipt.get("schema_version") != 1
        or receipt.get("gate_id") != "GATE-08"
        or receipt.get("decision") != "APPROVED"
        or receipt.get("scope") != "p0-remediation-control-install"
        or not isinstance(receipt.get("approval_id"), str)
        or not receipt["approval_id"].strip()
        or not isinstance(receipt.get("approved_by"), str)
        or not receipt["approved_by"].strip()
    ):
        _deny("private receipt does not authorize this bootstrap")
    approved_at = _timestamp(receipt.get("approved_at"))
    expires_at = _timestamp(receipt.get("expires_at"))
    now = dt.datetime.now(dt.timezone.utc)
    if (
        approved_at > now + dt.timedelta(minutes=5)
        or expires_at <= now
        or expires_at > approved_at + dt.timedelta(hours=4)
    ):
        _deny("private receipt is expired or over-broad")
    source_sha = receipt.get("source_git_sha")
    if not isinstance(source_sha, str) or not GIT_SHA_RE.fullmatch(source_sha):
        _deny("approved source commit is invalid")
    hashes = receipt.get("artifact_sha256")
    if not isinstance(hashes, dict):
        _deny("receipt artifact hashes are invalid")
    for required in (SELF_ARTIFACT, GATE_ARTIFACT, STATE_ARTIFACT):
        value = hashes.get(required)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            _deny("required trust-bootstrap hash is invalid")
    return source_sha, {str(key): str(value) for key, value in hashes.items()}


def _git(
    hooks: Path,
    arguments: Sequence[str],
    *,
    checkout: Path | None = None,
    extra_config: Sequence[str] = (),
) -> subprocess.CompletedProcess[str]:
    command = [
        "/usr/bin/git",
        "-c",
        f"core.hooksPath={hooks}",
        "-c",
        "core.alternateRefsCommand=/bin/false",
        "-c",
        "protocol.file.allow=always",
    ]
    for entry in extra_config:
        command.extend(("-c", entry))
    if checkout is not None:
        command.extend(("-C", str(checkout)))
    result = subprocess.run(
        [*command, *arguments],
        env=GIT_ENV,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _deny("isolated Git operation failed")
    return result


def _verify_git_tree(git_directory: Path) -> None:
    _verify_chain(git_directory, leaf_directory=True)
    for root, directories, files in os.walk(
        git_directory, topdown=True, followlinks=False
    ):
        root_path = Path(root)
        _secure_lstat(root_path, directory=True)
        for name in directories:
            _secure_lstat(root_path / name, directory=True)
        for name in files:
            _secure_lstat(root_path / name, directory=False)


def _prepare_checkout(
    source: Path, checkout: Path, hooks: Path, source_sha: str
) -> None:
    # Git >=2.35.2 (CVE-2022-24765 mitigation) refuses to operate on a repository not
    # owned by the running UID -- the candidate source is expected to be user-writable
    # (root never executes its code, only reads committed blobs after the receipt-bound
    # hash check below), so root cloning it trips "detected dubious ownership" without
    # this explicit, narrowly-scoped exception. Passed on the command line for this one
    # clone invocation only -- GIT_CONFIG_NOSYSTEM/GIT_CONFIG_GLOBAL=/dev/null still
    # block any persistent or ambient safe.directory config from affecting this process.
    _git(
        hooks,
        (
            "clone",
            "--no-local",
            "--no-checkout",
            "--no-recurse-submodules",
            "--depth=1",
            "--single-branch",
            "--no-tags",
            "--",
            str(source),
            str(checkout),
        ),
        extra_config=(f"safe.directory={source}",),
    )
    if (
        _git(hooks, ("rev-parse", "HEAD"), checkout=checkout).stdout.strip()
        != source_sha
    ):
        _deny("candidate HEAD does not match receipt")
    _git(hooks, ("cat-file", "-e", f"{source_sha}^{{commit}}"), checkout=checkout)
    tree = _git(hooks, ("ls-tree", "-r", source_sha), checkout=checkout).stdout
    if any(line.startswith("160000 ") for line in tree.splitlines()):
        _deny("approved commit contains a submodule")
    _git(
        hooks,
        ("checkout", "--detach", "--force", source_sha, "--"),
        checkout=checkout,
    )
    if (
        _git(hooks, ("rev-parse", "HEAD"), checkout=checkout).stdout.strip()
        != source_sha
    ):
        _deny("checked-out commit does not match receipt")
    status = _git(
        hooks,
        ("status", "--porcelain=v1", "--untracked-files=all"),
        checkout=checkout,
    ).stdout
    if status:
        _deny("root checkout is not clean")
    try:
        (checkout / ".git/objects/info/alternates").lstat()
    except FileNotFoundError:
        pass
    else:
        _deny("object alternates are forbidden")
    _verify_chain(checkout, leaf_directory=True)
    _verify_git_tree(checkout / ".git")


def _run_gate(checkout: Path, source_sha: str, receipt_hashes: dict[str, str]) -> None:
    gate = subprocess.run(
        [
            "/usr/bin/python3",
            "-I",
            str(checkout / GATE_ARTIFACT),
            "check",
            "remediation-control-install",
        ],
        env=CHILD_ENV,
        capture_output=True,
        text=True,
        check=False,
    )
    if gate.returncode != 0:
        _deny("verified remediation release gate denied")
    try:
        decision = json.loads(gate.stdout)
    except json.JSONDecodeError:
        _deny("verified remediation release gate output is invalid")
    if (
        not isinstance(decision, dict)
        or decision.get("allowed") is not True
        or decision.get("operation") != "remediation-control-install"
        or decision.get("required_gate") != "GATE-08"
        or decision.get("source_git_sha") != source_sha
        or decision.get("artifact_sha256") != receipt_hashes
    ):
        _deny("verified remediation release gate decision is not exact")


def _arguments(argv: Sequence[str]) -> Path:
    if list(argv) == ["--help"]:
        print(
            "Usage: bootstrap_gate08_remediation_control.py "
            "--source-repository ABSOLUTE_LOCAL_PATH --apply"
        )
        raise SystemExit(0)
    if len(argv) != 3 or argv[0] != "--source-repository" or argv[2] != "--apply":
        _deny("invalid bootstrap arguments")
    if not argv[1].startswith("/") or "\n" in argv[1] or "\r" in argv[1]:
        _deny("source repository must be one absolute local path")
    try:
        source = Path(argv[1]).resolve(strict=True)
    except OSError:
        _deny("source repository is unavailable")
    if not source.is_dir():
        _deny("source repository is not a directory")
    return source


def main(argv: Sequence[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if list(arguments) == ["--help"]:
        _arguments(arguments)
    if os.geteuid() != 0:
        _deny("root is required")
    os.umask(0o077)
    source = _arguments(arguments)
    receipt, receipt_raw = _read_receipt()
    source_sha, receipt_hashes = _validate_receipt(receipt)
    if _safe_digest(Path(__file__)) != receipt_hashes[SELF_ARTIFACT]:
        _deny("executing bootstrap hash does not match receipt")

    root_stage = Path(tempfile.mkdtemp(prefix="sealai-gate08-root.", dir="/run"))
    os.chown(root_stage, 0, 0)
    root_stage.chmod(0o700)
    try:
        hooks = root_stage / "empty-hooks"
        hooks.mkdir(mode=0o700)
        checkout = root_stage / "checkout"
        _prepare_checkout(source, checkout, hooks, source_sha)
        receipt_after, receipt_raw_after = _read_receipt()
        sha_after, hashes_after = _validate_receipt(receipt_after)
        if receipt_raw_after != receipt_raw or sha_after != source_sha:
            _deny("private receipt changed during bootstrap")
        if hashes_after != receipt_hashes:
            _deny("private receipt hashes changed during bootstrap")
        for trusted in (GATE_ARTIFACT, STATE_ARTIFACT):
            if _safe_digest(checkout / trusted) != receipt_hashes[trusted]:
                _deny("trusted control hash does not match receipt")
        _run_gate(checkout, source_sha, receipt_hashes)
        installer = subprocess.run(
            [
                "/bin/bash",
                "--noprofile",
                "--norc",
                str(checkout / "ops/install-disk-guard.sh"),
                "--apply",
            ],
            env=CHILD_ENV,
            check=False,
        )
        if installer.returncode != 0:
            _deny("verified remediation installer failed")
    finally:
        shutil.rmtree(root_stage, ignore_errors=True)
    return 0


def _terminate(_signal: int, _frame: object) -> NoReturn:
    raise SystemExit(143)


if __name__ == "__main__":
    signal.signal(signal.SIGHUP, _terminate)
    signal.signal(signal.SIGTERM, _terminate)
    try:
        raise SystemExit(main())
    except BootstrapDenied as exc:
        print(f"gate08 bootstrap: {exc}", file=sys.stderr)
        raise SystemExit(78) from None
