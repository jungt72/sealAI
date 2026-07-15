"""Canonical Gate-10 database migration digest tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ops/database-migration-sha256.py"
SPEC = importlib.util.spec_from_file_location("database_migration_sha256", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _make_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "migration-repo"
    versions = repo / "backend/sealai_v2/db/migrations/versions"
    versions.mkdir(parents=True)
    for relative in (
        "backend/sealai_v2/db/migrate.py",
        "backend/sealai_v2/db/models.py",
        "backend/sealai_v2/db/migrations/env.py",
        "backend/sealai_v2/db/migrations/script.py.mako",
        "backend/sealai_v2/db/migrations/versions/0001.py",
    ):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative}\n", encoding="utf-8")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Migration Test")
    _git(repo, "config", "user.email", "migration@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_migration_digest_is_deterministic_and_commit_bound(tmp_path: Path) -> None:
    repo, first = _make_repo(tmp_path)
    first_digest = MODULE.migration_sha256(repo, first)
    assert first_digest == MODULE.migration_sha256(repo, first)
    assert len(first_digest) == 64

    version = repo / "backend/sealai_v2/db/migrations/versions/0002.py"
    version.write_text("# second migration\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "second")
    second = _git(repo, "rev-parse", "HEAD")

    assert MODULE.migration_sha256(repo, second) != first_digest
    assert MODULE.migration_sha256(repo, first) == first_digest


def test_migration_digest_ignores_non_schema_files(tmp_path: Path) -> None:
    repo, source = _make_repo(tmp_path)
    before = MODULE.migration_sha256(repo, source)
    (repo / "README.md").write_text("unrelated\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "docs")
    docs = _git(repo, "rev-parse", "HEAD")

    assert MODULE.migration_sha256(repo, docs) == before
