"""ops/tree-hash.sh — the canonical, side-effect-free hash of the backend-v2 IMAGE build-inputs.

Single source of truth shared by the eval manifest, the V2 deploy wrapper, and the kern-fix-01
backfill (byte-identical). Scope = EVERY input that determines the image content:
`backend/Dockerfile.v2` (the recipe) + everything it COPYs (`backend/sealai_v2` minus `eval/`+`tests/`,
`backend/requirements-v2.txt`, `backend/docker-entrypoint-v2.sh`). Out stays only non-shipped dev
infra (`eval/` — self-referential runs/, never imported by the served app; `tests/`). An image-content
change → new hash → a fresh adjudicated eval is required; an eval/test change does not.

Red-before-green: `test_image_inputs_move_the_hash` fails until the scope covers Dockerfile.v2 /
requirements-v2.txt / docker-entrypoint-v2.sh.
"""

from __future__ import annotations

import contextlib
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ops" / "tree-hash.sh"


def _hash() -> str:
    return subprocess.check_output(
        ["bash", str(SCRIPT)], cwd=str(REPO), text=True
    ).strip()


def _status() -> str:
    return subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=str(REPO), text=True
    )


@contextlib.contextmanager
def _probe_file(relpath: str):
    """A new tracked-eligible file under a dir, removed afterwards."""
    p = REPO / relpath
    p.write_text("probe\n", encoding="utf-8")
    try:
        yield
    finally:
        p.unlink(missing_ok=True)


@contextlib.contextmanager
def _perturb(relpath: str):
    """Append to an EXISTING tracked file, restored byte-exact afterwards (finally runs on failure)."""
    p = REPO / relpath
    orig = p.read_bytes()
    p.write_bytes(orig + b"\n# treehash-probe\n")
    try:
        yield
    finally:
        p.write_bytes(orig)


def test_deterministic_same_content_same_hash():
    assert _hash() == _hash()
    assert len(_hash()) >= 40


def test_served_code_change_moves_the_hash():
    base = _hash()
    with _probe_file("backend/sealai_v2/knowledge/__treehash_probe__.py"):
        assert _hash() != base
    assert _hash() == base


def test_image_inputs_move_the_hash():
    # Dockerfile.v2, the COPYed requirements, and the COPYed entrypoint ALL determine the image.
    base = _hash()
    for f in (
        "backend/Dockerfile.v2",
        "backend/requirements-v2.txt",
        "backend/docker-entrypoint-v2.sh",
    ):
        with _perturb(f):
            assert _hash() != base, f"{f} must be inside the image hash"
    assert _hash() == base


def test_eval_and_tests_are_hash_neutral():
    base = _hash()
    for sub in ("eval", "tests"):
        with _probe_file(f"backend/sealai_v2/{sub}/__treehash_probe__.py"):
            assert _hash() == base, f"{sub}/ change must be hash-neutral"


def test_status_unchanged_after_hash():
    before = _status()
    _hash()
    assert _status() == before
