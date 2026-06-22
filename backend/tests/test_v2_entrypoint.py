"""D — the V2 entrypoint teeth: an UNGATED build (empty gate-tree-hash marker) refuses to start.

A raw `docker compose build backend-v2` (no --build-arg GATE_TREE_HASH) bakes an EMPTY marker, so
the container exits 1 instead of serving ungated code. ops/release-backend-v2.sh bakes a non-empty
marker → the app starts. The marker path is env-overridable (SEALAI_GATE_MARKER) only so this test
need not write to /etc.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "backend" / "docker-entrypoint-v2.sh"


def _run(marker_path: str):
    return subprocess.run(
        ["sh", str(SCRIPT), "echo", "APP-STARTED"],
        env={"PATH": os.environ["PATH"], "SEALAI_GATE_MARKER": marker_path},
        capture_output=True,
        text=True,
    )


def test_empty_marker_refuses_to_start():
    with tempfile.NamedTemporaryFile() as f:  # 0 bytes = ungated build
        r = _run(f.name)
    assert r.returncode == 1
    assert "UNGATED BUILD" in r.stderr
    assert "APP-STARTED" not in r.stdout  # the CMD was never exec'd


def test_set_marker_execs_the_command():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"430a32c055a1737ef7014c809fd9d40467f57897\n")
        f.flush()
        path = f.name
    try:
        r = _run(path)
    finally:
        os.unlink(path)
    assert r.returncode == 0
    assert "APP-STARTED" in r.stdout  # exec "$@" ran the CMD
