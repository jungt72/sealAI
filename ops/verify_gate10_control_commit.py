#!/usr/bin/python3 -I
"""Root-run, independent re-verification of a GATE-10 deploy control commit.

Reuses production_release_gate.py's own already-hardened logic rather than
duplicating it: REPO_ROOT in that script is derived from __file__, so running
the checked-out copy as a subprocess re-executes every existing check (two-
commit binding, all 7 manifest hashes, Cosign/Sigstore image attestation)
against a root-verified copy of the exact control commit, closing the gap
where the VPS previously just trusted whatever CI claimed over SSH.
"""

from __future__ import annotations

import hmac
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
from typing import NoReturn, Sequence


SOURCE_REPOSITORY = Path("/home/thorsten/sealai")
GATE_ARTIFACT = "ops/production_release_gate.py"
MANIFEST_ARTIFACT = "ops/production-release-manifest.json"
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST_RE = re.compile(r"^[A-Za-z0-9._:/-]+@sha256:[0-9a-f]{64}$")
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


class VerificationDenied(RuntimeError):
    """The control commit, its gate decision, or its image digest could not be proven genuine."""


def _deny(message: str) -> NoReturn:
    raise VerificationDenied(message)


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


def _git(
    hooks: Path,
    arguments: Sequence[str],
    *,
    checkout: Path | None = None,
    config_global: Path | None = None,
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
    if checkout is not None:
        command.extend(("-C", str(checkout)))
    env = (
        GIT_ENV
        if config_global is None
        else {**GIT_ENV, "GIT_CONFIG_GLOBAL": str(config_global)}
    )
    result = subprocess.run(
        [*command, *arguments],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _deny("isolated Git operation failed")
    return result


def _prepare_checkout(
    source: Path, checkout: Path, hooks: Path, control_sha: str, source_sha: str
) -> None:
    # Git >=2.35.2 (CVE-2022-24765 mitigation) refuses to operate on a repository not
    # owned by the running UID -- verified empirically against git 2.43 that this
    # local-transport clone path only honors safe.directory from a config *file*,
    # never `-c` on the command line. Same fix as bootstrap_gate08_remediation_control.py,
    # hardened through two real fix cycles earlier today -- reused verbatim, not
    # re-derived.
    safe_directory_config = checkout.parent / "safe-directory.gitconfig"
    safe_directory_config.write_text(
        f"[safe]\n\tdirectory = {source}\n\tdirectory = {source / '.git'}\n",
        encoding="utf-8",
    )
    safe_directory_config.chmod(0o600)
    try:
        _git(
            hooks,
            (
                "clone",
                "--no-local",
                "--no-checkout",
                "--no-recurse-submodules",
                # depth=2, not 1: the gate's own two-commit diff (control commit vs. its
                # source parent) needs real tree/blob objects for both commits, not just
                # the control commit's metadata.
                "--depth=2",
                "--single-branch",
                "--no-tags",
                "--",
                str(source),
                str(checkout),
            ),
            config_global=safe_directory_config,
        )
    finally:
        safe_directory_config.unlink(missing_ok=True)
    if (
        _git(hooks, ("rev-parse", "HEAD"), checkout=checkout).stdout.strip()
        != control_sha
    ):
        _deny("candidate HEAD does not match supplied control commit")
    _git(hooks, ("cat-file", "-e", f"{control_sha}^{{commit}}"), checkout=checkout)
    tree = _git(hooks, ("ls-tree", "-r", control_sha), checkout=checkout).stdout
    if any(line.startswith("160000 ") for line in tree.splitlines()):
        _deny("control commit contains a submodule")
    lineage = _git(
        hooks, ("rev-list", "--parents", "-n", "1", control_sha), checkout=checkout
    ).stdout.split()
    if len(lineage) != 2 or lineage[1] != source_sha:
        _deny("control commit parent does not match supplied source commit")
    _git(
        hooks,
        ("checkout", "--detach", "--force", control_sha, "--"),
        checkout=checkout,
    )
    if (
        _git(hooks, ("rev-parse", "HEAD"), checkout=checkout).stdout.strip()
        != control_sha
    ):
        _deny("checked-out commit does not match supplied control commit")
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


def _run_gate(checkout: Path, source_sha: str) -> None:
    gate = subprocess.run(
        ["/usr/bin/python3", "-I", str(checkout / GATE_ARTIFACT), "check", "deploy"],
        env=CHILD_ENV,
        capture_output=True,
        text=True,
        check=False,
    )
    if gate.returncode != 0:
        _deny("verified production release gate denied the control commit")
    try:
        decision = json.loads(gate.stdout)
    except json.JSONDecodeError:
        _deny("verified production release gate output is invalid")
    if (
        not isinstance(decision, dict)
        or set(decision)
        != {
            "allowed",
            "operation",
            "reason",
            "state_id",
            "required_gate",
            "source_git_sha",
        }
        or decision.get("allowed") is not True
        or decision.get("operation") != "deploy"
        or decision.get("reason") != "gate10_approved_manifest_bound"
        or decision.get("required_gate") != "GATE-10"
        or decision.get("source_git_sha") != source_sha
    ):
        _deny("verified production release gate decision is not exact")


def _read_manifest_backend_image_digest(checkout: Path) -> str:
    manifest_path = checkout / MANIFEST_ARTIFACT
    _verify_chain(manifest_path, leaf_directory=False)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(manifest_path, flags)
    except OSError:
        _deny("verified release manifest is unavailable")
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or metadata.st_size > 256 * 1024
        ):
            _deny("verified release manifest is unsafe")
        raw = os.read(descriptor, 256 * 1024 + 1)
    finally:
        os.close(descriptor)
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        _deny("verified release manifest is invalid")
    if not isinstance(manifest, dict):
        _deny("verified release manifest root must be an object")
    hashes = manifest.get("hashes")
    if not isinstance(hashes, dict):
        _deny("verified release manifest hashes are invalid")
    digest = hashes.get("backend_image_digest")
    if not isinstance(digest, str) or not IMAGE_DIGEST_RE.fullmatch(digest):
        _deny("verified release manifest backend image digest is invalid")
    return digest


def _arguments(argv: Sequence[str]) -> tuple[str, str, str]:
    if list(argv) == ["--help"]:
        print(
            "Usage: verify_gate10_control_commit.py --control-sha SHA "
            "--source-sha SHA --backend-image REF@sha256:DIGEST"
        )
        raise SystemExit(0)
    if (
        len(argv) != 6
        or argv[0] != "--control-sha"
        or argv[2] != "--source-sha"
        or argv[4] != "--backend-image"
    ):
        _deny("invalid verifier arguments")
    control_sha, source_sha, backend_image = argv[1], argv[3], argv[5]
    if not GIT_SHA_RE.fullmatch(control_sha):
        _deny("control commit is invalid")
    if not GIT_SHA_RE.fullmatch(source_sha):
        _deny("source commit is invalid")
    if not IMAGE_DIGEST_RE.fullmatch(backend_image):
        _deny("backend image reference is invalid")
    return control_sha, source_sha, backend_image


def main(argv: Sequence[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if list(arguments) == ["--help"]:
        _arguments(arguments)
    if os.geteuid() != 0:
        _deny("root is required")
    os.umask(0o077)
    control_sha, source_sha, backend_image = _arguments(arguments)

    if not SOURCE_REPOSITORY.is_dir():
        _deny("source repository is unavailable")

    root_stage = Path(tempfile.mkdtemp(prefix="sealai-gate10-verify.", dir="/run"))
    os.chown(root_stage, 0, 0)
    root_stage.chmod(0o700)
    try:
        hooks = root_stage / "empty-hooks"
        hooks.mkdir(mode=0o700)
        checkout = root_stage / "checkout"
        _prepare_checkout(SOURCE_REPOSITORY, checkout, hooks, control_sha, source_sha)
        _run_gate(checkout, source_sha)
        approved_digest = _read_manifest_backend_image_digest(checkout)
        if not hmac.compare_digest(approved_digest, backend_image):
            _deny("backend image digest does not match the approved release manifest")
    finally:
        shutil.rmtree(root_stage, ignore_errors=True)

    print(
        json.dumps(
            {
                "allowed": True,
                "operation": "deploy",
                "reason": "gate10_control_commit_verified",
                "control_git_sha": control_sha,
                "source_git_sha": source_sha,
                "backend_image_digest": backend_image,
            }
        )
    )
    return 0


def _terminate(_signal: int, _frame: object) -> NoReturn:
    raise SystemExit(143)


if __name__ == "__main__":
    signal.signal(signal.SIGHUP, _terminate)
    signal.signal(signal.SIGTERM, _terminate)
    try:
        raise SystemExit(main())
    except VerificationDenied as exc:
        print(f"gate10 control commit verification: {exc}", file=sys.stderr)
        raise SystemExit(78) from None
