from __future__ import annotations

import json

import pytest

from sealai_v2.config.build_identity import (
    create_identity,
    load_identity,
    verify_identity,
)


def test_identity_round_trip_and_marker_binding(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("fastapi==1.0\n", encoding="ascii")
    identity = create_identity(
        tree_hash="a" * 40,
        git_sha="b" * 40,
        requirements_file=requirements,
    )
    identity_path = tmp_path / "identity.json"
    identity_path.write_text(json.dumps(identity), encoding="utf-8")
    marker = tmp_path / "marker"
    marker.write_text("a" * 40, encoding="ascii")
    assert load_identity(identity_path) == identity
    assert verify_identity(identity_path=identity_path, tree_marker=marker) == identity


def test_identity_rejects_partial_commit_and_mismatched_marker(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("x", encoding="ascii")
    with pytest.raises(ValueError, match="git_sha"):
        create_identity(
            tree_hash="a" * 40,
            git_sha="deadbeef",
            requirements_file=requirements,
        )
    identity = create_identity(
        tree_hash="a" * 40,
        git_sha="b" * 40,
        requirements_file=requirements,
    )
    identity_path = tmp_path / "identity.json"
    identity_path.write_text(json.dumps(identity), encoding="utf-8")
    marker = tmp_path / "marker"
    marker.write_text("c" * 40, encoding="ascii")
    with pytest.raises(ValueError, match="does not match"):
        verify_identity(identity_path=identity_path, tree_marker=marker)
