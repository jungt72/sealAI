"""Architecture enforcer — the ``sealai_v2`` ↔ ``app`` import boundary (V2.0 Phase 0).

The V2.0 migration runs Option B: ``backend/sealai_v2/`` lives as a sibling of
``backend/app/`` during coexistence. The two trees must stay mechanically
decoupled so that (a) neither leaks into the other while both ship, and (b) the
green-field tree can be deleted cleanly if abandoned. The rule, both directions:

  * no module under ``sealai_v2.*`` may import ``app`` / ``app.*``;
  * no module under ``app.*`` may import ``sealai_v2`` / ``sealai_v2.*``.

This is the keystone test (build-spec §11: the old orchestration + the G1
refactor are retired; the new tree is a clean module set). It is deliberately
**self-contained** — it does NOT import the G1 enforcer
(``test_core_analysis_purity.py``), which is itself slated for removal. The AST
mechanism is the same proven, dependency-free pattern used by its siblings here,
so it runs with/without conftest and needs no runtime stack.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
V2_ROOT = REPO_ROOT / "backend" / "sealai_v2"
APP_ROOT = REPO_ROOT / "backend" / "app"


def _py_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _absolute_imports(path: Path) -> list[str]:
    """Absolute imported module dotted-paths (relative `from .x` imports are self → skipped)."""
    mods: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import within the same tree — self, allowed
            if node.module:
                mods.append(node.module)
    return mods


def _imports_prefix(module: str, top: str) -> bool:
    """True iff `module` is `top` itself or a submodule `top.<x>` (exact-segment match)."""
    return module == top or module.startswith(top + ".")


def test_v2_does_not_import_app() -> None:
    """(a) Nothing under sealai_v2/ may reach the old ``app`` tree."""
    files = _py_files(V2_ROOT)
    assert files, "expected backend/sealai_v2/ to exist with modules"
    violations: list[str] = []
    for path in files:
        rel = str(path.relative_to(REPO_ROOT))
        for module in _absolute_imports(path):
            if _imports_prefix(module, "app"):
                violations.append(f"{rel}: imports old-tree module {module!r}")
    assert not violations, (
        "sealai_v2 must not import app.* (V2.0 Option-B boundary, build-spec §11) — the "
        "green-field tree stays decoupled from the retired runtime:\n  "
        + "\n  ".join(violations)
    )


def test_app_does_not_import_sealai_v2() -> None:
    """(b) Nothing under app/ may reach the green-field ``sealai_v2`` tree."""
    files = _py_files(APP_ROOT)
    assert files, "expected backend/app/ to exist with modules"
    violations: list[str] = []
    for path in files:
        rel = str(path.relative_to(REPO_ROOT))
        for module in _absolute_imports(path):
            if _imports_prefix(module, "sealai_v2"):
                violations.append(f"{rel}: imports green-field module {module!r}")
    assert not violations, (
        "app must not import sealai_v2.* (V2.0 Option-B boundary, build-spec §11) — coexistence "
        "stays one-way-isolated so v2 is cleanly deletable:\n  "
        + "\n  ".join(violations)
    )


def test_boundary_prefix_match_is_segment_exact() -> None:
    """Guard the rule's edges: only true sub-packages match, lookalikes do not."""
    # real violations
    assert _imports_prefix("app", "app")
    assert _imports_prefix("app.services.rag", "app")
    assert _imports_prefix("sealai_v2", "sealai_v2")
    assert _imports_prefix("sealai_v2.api.main", "sealai_v2")
    # lookalikes that must NOT be flagged
    assert not _imports_prefix("appdirs", "app")
    assert not _imports_prefix("application", "app")
    assert not _imports_prefix("sealai_v2_legacy", "sealai_v2")
    assert not _imports_prefix("fastapi", "app")


def test_detector_catches_synthetic_violations(tmp_path) -> None:
    """Anti-false-pass: the AST detector must trip on real cross-tree imports in BOTH
    directions, while leaving benign / relative imports alone."""
    # v2-side file reaching into app.*
    v2_like = tmp_path / "synthetic_v2.py"
    v2_like.write_text(
        "import app\n"
        "from app.services.rag.rag_orchestrator import hybrid_retrieve\n"
        "import appdirs\n"  # lookalike — allowed
        "from fastapi import FastAPI\n"  # third-party — allowed
        "from . import core\n",  # relative/self — allowed
        encoding="utf-8",
    )
    v2_mods = _absolute_imports(v2_like)
    assert [m for m in v2_mods if _imports_prefix(m, "app")] == [
        "app",
        "app.services.rag.rag_orchestrator",
    ]
    assert "appdirs" in v2_mods and not _imports_prefix("appdirs", "app")

    # app-side file reaching into sealai_v2.*
    app_like = tmp_path / "synthetic_app.py"
    app_like.write_text(
        "from sealai_v2.api.main import app as v2app\n"
        "import sealai_v2\n"
        "import sealai_v2_legacy\n",  # lookalike — allowed
        encoding="utf-8",
    )
    app_mods = _absolute_imports(app_like)
    assert [m for m in app_mods if _imports_prefix(m, "sealai_v2")] == [
        "sealai_v2.api.main",
        "sealai_v2",
    ]
    assert "sealai_v2_legacy" in app_mods and not _imports_prefix(
        "sealai_v2_legacy", "sealai_v2"
    )
