#!/usr/bin/env python3
"""Canonical SHA-256 over every path, mode, and byte in a served Git tree."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
GIT_ENV = {
    "HOME": "/nonexistent",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_OPTIONAL_LOCKS": "0",
}
TREE_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


class TreeDigestError(RuntimeError):
    """The exact served tree cannot be read as a regular Git blob tree."""


def _git(
    repo: Path,
    *arguments: str,
    object_directory: Path,
    alternate_object_directory: Path,
) -> bytes:
    environment = {
        **GIT_ENV,
        "GIT_OBJECT_DIRECTORY": str(object_directory),
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(alternate_object_directory),
    }
    result = subprocess.run(
        [
            "/usr/bin/git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            f"safe.directory={repo}",
            "-C",
            str(repo),
            *arguments,
        ],
        capture_output=True,
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        raise TreeDigestError("served tree is unavailable")
    return result.stdout


def _feed(hasher: object, value: bytes) -> None:
    hasher.update(len(value).to_bytes(8, byteorder="big"))
    hasher.update(value)


def served_tree_sha256(repo: Path, tree: str) -> str:
    """Hash a deterministic, length-delimited projection of a Git tree."""
    if TREE_RE.fullmatch(tree) is None:
        raise TreeDigestError("served tree identifier is invalid")
    repo = repo.resolve(strict=True)
    object_path = subprocess.run(
        [
            "/usr/bin/git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            f"safe.directory={repo}",
            "-C",
            str(repo),
            "rev-parse",
            "--git-path",
            "objects",
        ],
        env=GIT_ENV,
        capture_output=True,
        check=False,
    )
    if object_path.returncode != 0:
        raise TreeDigestError("repository object directory is unavailable")
    alternate_object_directory = Path(object_path.stdout.decode().strip())
    if not alternate_object_directory.is_absolute():
        alternate_object_directory = repo / alternate_object_directory
    alternate_object_directory = alternate_object_directory.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="sealai-served-tree-") as temporary:
        object_directory = Path(temporary)
        object_directory.chmod(0o700)
        environment = {
            **GIT_ENV,
            "SEALAI_TREE_HASH_OBJECT_DIR": str(object_directory),
        }
        materialized = subprocess.run(
            ["/bin/bash", "-p", str(repo / "ops" / "tree-hash.sh")],
            cwd=repo,
            env=environment,
            capture_output=True,
            check=False,
        )
        if (
            materialized.returncode != 0
            or materialized.stdout.decode("ascii", errors="replace").strip() != tree
        ):
            raise TreeDigestError("served tree cannot be reproduced exactly")
        _git(
            repo,
            "cat-file",
            "-e",
            f"{tree}^{{tree}}",
            object_directory=object_directory,
            alternate_object_directory=alternate_object_directory,
        )
        records = _git(
            repo,
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            tree,
            object_directory=object_directory,
            alternate_object_directory=alternate_object_directory,
        ).split(b"\0")
        if not records or records[-1] != b"":
            raise TreeDigestError("served tree listing is malformed")

        hasher = hashlib.sha256(b"sealai-served-tree-v1\0")
        seen: set[bytes] = set()
        for record in records[:-1]:
            try:
                metadata, path = record.split(b"\t", 1)
                mode, object_type, object_id = metadata.split(b" ", 2)
            except ValueError as exc:
                raise TreeDigestError("served tree listing is malformed") from exc
            if not path or path in seen or object_type != b"blob":
                raise TreeDigestError("served tree contains an unsupported entry")
            seen.add(path)
            content = _git(
                repo,
                "cat-file",
                "blob",
                object_id.decode("ascii"),
                object_directory=object_directory,
                alternate_object_directory=alternate_object_directory,
            )
            _feed(hasher, mode)
            _feed(hasher, path)
            _feed(hasher, content)
        if not seen:
            raise TreeDigestError("served tree is empty")
        return hasher.hexdigest()


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage: served-tree-sha256.py TREE", file=sys.stderr)
        return 2
    try:
        digest = served_tree_sha256(REPO_ROOT, arguments[0])
    except (OSError, UnicodeError, TreeDigestError):
        print("served-tree-sha256: exact served tree is unavailable", file=sys.stderr)
        return 2
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
