#!/usr/bin/env python3
"""Canonical SHA-256 of the exact V2 schema/migration program at one commit."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
MIGRATION_PATHS = (
    "backend/sealai_v2/db/migrate.py",
    "backend/sealai_v2/db/models.py",
    "backend/sealai_v2/db/migrations/env.py",
    "backend/sealai_v2/db/migrations/script.py.mako",
    "backend/sealai_v2/db/migrations/versions",
)
GIT_ENV = {
    "HOME": "/nonexistent",
    "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_OPTIONAL_LOCKS": "0",
}


class MigrationDigestError(RuntimeError):
    """The approved migration program cannot be established exactly."""


def _git(repo: Path, *arguments: str) -> bytes:
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
        env=GIT_ENV,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise MigrationDigestError("migration Git object is unavailable")
    return result.stdout


def _feed(hasher: object, value: bytes) -> None:
    hasher.update(len(value).to_bytes(8, "big"))
    hasher.update(value)


def migration_sha256(repo: Path, source_git_sha: str) -> str:
    if GIT_SHA_RE.fullmatch(source_git_sha) is None:
        raise MigrationDigestError("source Git SHA is invalid")
    repo = repo.resolve(strict=True)
    _git(repo, "cat-file", "-e", f"{source_git_sha}^{{commit}}")
    records = _git(
        repo,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        source_git_sha,
        "--",
        *MIGRATION_PATHS,
    ).split(b"\0")
    if not records or records[-1] != b"":
        raise MigrationDigestError("migration tree listing is malformed")
    hasher = hashlib.sha256(b"sealai-v2-database-migrations-v1\0")
    seen: set[bytes] = set()
    for record in records[:-1]:
        try:
            metadata, path = record.split(b"\t", 1)
            mode, kind, object_id = metadata.split(b" ", 2)
        except ValueError as exc:
            raise MigrationDigestError("migration tree listing is malformed") from exc
        if (
            not path
            or path in seen
            or kind != b"blob"
            or mode not in {b"100644", b"100755"}
        ):
            raise MigrationDigestError("migration tree contains an unsupported entry")
        seen.add(path)
        content = _git(repo, "cat-file", "blob", object_id.decode("ascii"))
        _feed(hasher, mode)
        _feed(hasher, path)
        _feed(hasher, content)
    required = {
        b"backend/sealai_v2/db/migrate.py",
        b"backend/sealai_v2/db/models.py",
        b"backend/sealai_v2/db/migrations/env.py",
        b"backend/sealai_v2/db/migrations/script.py.mako",
    }
    versions = {
        path
        for path in seen
        if path.startswith(b"backend/sealai_v2/db/migrations/versions/")
    }
    if not required.issubset(seen) or not versions:
        raise MigrationDigestError("migration tree is incomplete")
    return hasher.hexdigest()


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage: database-migration-sha256.py SOURCE_GIT_SHA", file=sys.stderr)
        return 2
    try:
        digest = migration_sha256(REPO_ROOT, arguments[0])
    except (OSError, UnicodeError, MigrationDigestError):
        print(
            "database-migration-sha256: exact migration program is unavailable",
            file=sys.stderr,
        )
        return 2
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
