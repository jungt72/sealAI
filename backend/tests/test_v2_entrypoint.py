"""D — the V2 entrypoint teeth: an UNGATED build (empty gate-tree-hash marker) refuses to start.

A raw `docker compose build backend-v2` (no --build-arg GATE_TREE_HASH) bakes an EMPTY marker, so
the container exits 1 instead of serving unidentified code. ops/release-backend-v2.sh bakes a
non-empty marker for both candidate and final stages. The marker path is env-overridable
(SEALAI_GATE_MARKER) only so this test need not write to /etc.
"""

from __future__ import annotations

import os
import json
import pathlib
import subprocess
import sys
import tempfile

from sealai_v2.config.build_identity import create_identity

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "backend" / "docker-entrypoint-v2.sh"


def _run(marker_path: str, identity_path: str):
    return subprocess.run(
        ["sh", str(SCRIPT), "echo", "APP-STARTED"],
        env={
            "PATH": f"{pathlib.Path(sys.executable).parent}:{os.environ['PATH']}",
            "PYTHONPATH": str(REPO / "backend"),
            "SEALAI_GATE_MARKER": marker_path,
            "SEALAI_RELEASE_IDENTITY": identity_path,
        },
        capture_output=True,
        text=True,
    )


def test_empty_marker_refuses_to_start():
    with tempfile.NamedTemporaryFile() as marker, tempfile.NamedTemporaryFile() as identity:
        r = _run(marker.name, identity.name)
    assert r.returncode == 1
    assert "UNGATED BUILD" in r.stderr
    assert "APP-STARTED" not in r.stdout  # the CMD was never exec'd


def test_set_marker_execs_the_command():
    tree_hash = "430a32c055a1737ef7014c809fd9d40467f57897"
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        marker = root / "marker"
        requirements = root / "requirements.txt"
        identity_path = root / "identity.json"
        marker.write_text(tree_hash, encoding="ascii")
        requirements.write_text("fastapi==1.0\n", encoding="ascii")
        identity = create_identity(
            tree_hash=tree_hash,
            git_sha="a" * 40,
            requirements_file=requirements,
        )
        identity_path.write_text(json.dumps(identity), encoding="utf-8")
        r = _run(str(marker), str(identity_path))
    assert r.returncode == 0
    assert "APP-STARTED" in r.stdout  # exec "$@" ran the CMD


def test_mismatched_release_identity_refuses_to_start():
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        marker = root / "marker"
        requirements = root / "requirements.txt"
        identity_path = root / "identity.json"
        marker.write_text("b" * 40, encoding="ascii")
        requirements.write_text("fastapi==1.0\n", encoding="ascii")
        identity = create_identity(
            tree_hash="c" * 40,
            git_sha="a" * 40,
            requirements_file=requirements,
        )
        identity_path.write_text(json.dumps(identity), encoding="utf-8")
        r = _run(str(marker), str(identity_path))
    assert r.returncode == 1
    assert "INVALID RELEASE IDENTITY" in r.stderr
