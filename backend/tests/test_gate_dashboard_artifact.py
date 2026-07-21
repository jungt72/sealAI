"""GATE-10 P1 phase 4: dashboard_artifact_sha256, the last of the seven
required_manifest_hashes.

Unlike test_gate10_artifact_binding.py's fields, the dashboard candidate is not
git-tracked content -- it is frontend-v2's own gitignored `npm run build` output.
These tests exercise `_directory_sha256`/`_dashboard_artifact_sha256` directly against
throwaway temp directories, never against the real frontend-v2/.build/dashboard-candidate
(which may or may not exist on a given machine -- these tests must not depend on that).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
OPS = REPO / "ops"
sys.path.insert(0, str(OPS))

import production_release_gate as gate  # noqa: E402


def test_fails_closed_when_candidate_directory_is_missing(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(gate.GateConfigurationError, match="does not exist"):
        gate._directory_sha256(missing)


def test_fails_closed_when_candidate_directory_is_empty(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(gate.GateConfigurationError, match="is empty"):
        gate._directory_sha256(empty)


def test_rejects_a_symlink_inside_the_candidate_directory(tmp_path: Path):
    root = tmp_path / "candidate"
    root.mkdir()
    real_file = tmp_path / "outside.txt"
    real_file.write_text("not part of the candidate\n", encoding="utf-8")
    (root / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (root / "sneaky-link").symlink_to(real_file)

    with pytest.raises(gate.GateConfigurationError, match="symlink"):
        gate._directory_sha256(root)


def test_hash_is_deterministic_regardless_of_creation_order(tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "index.html").write_text("one\n", encoding="utf-8")
    (a / "assets").mkdir()
    (a / "assets" / "app.js").write_text("two\n", encoding="utf-8")
    # same content, files created in the opposite order
    (b / "assets").mkdir()
    (b / "assets" / "app.js").write_text("two\n", encoding="utf-8")
    (b / "index.html").write_text("one\n", encoding="utf-8")

    assert gate._directory_sha256(a) == gate._directory_sha256(b)


def test_hash_moves_when_file_content_changes(tmp_path: Path):
    root = tmp_path / "candidate"
    root.mkdir()
    target = root / "index.html"
    target.write_text("<html>v1</html>\n", encoding="utf-8")
    base = gate._directory_sha256(root)

    target.write_text("<html>v2</html>\n", encoding="utf-8")
    assert gate._directory_sha256(root) != base


def test_hash_moves_when_a_file_is_renamed_with_identical_bytes(tmp_path: Path):
    """Content-addressing must bind the path too, not just the bytes -- otherwise
    renaming index.html to something nginx never serves would go unnoticed."""

    root = tmp_path / "candidate"
    root.mkdir()
    (root / "index.html").write_text("same bytes\n", encoding="utf-8")
    base = gate._directory_sha256(root)

    (root / "index.html").rename(root / "renamed.html")
    assert gate._directory_sha256(root) != base


def test_dashboard_artifact_sha256_reads_the_configured_relative_path(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    candidate = tmp_path.joinpath(*gate.DASHBOARD_CANDIDATE_RELPATH)
    candidate.mkdir(parents=True)
    (candidate / "index.html").write_text("<html></html>\n", encoding="utf-8")

    assert gate._dashboard_artifact_sha256() == gate._directory_sha256(candidate)


def test_registered_in_source_derived_verifiers():
    assert gate._SOURCE_DERIVED_HASH_VERIFIERS["dashboard_artifact_sha256"] is (
        gate._dashboard_artifact_sha256
    )
