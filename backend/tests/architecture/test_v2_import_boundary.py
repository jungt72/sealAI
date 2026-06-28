"""Architecture enforcer — the lone sealai_v2 tree must not import a legacy app.*.

V1 is retired (2026-06-25): the old LangGraph backend (backend/app/ and its
siblings) has been deleted from the tree. backend/sealai_v2/ is now the sole
backend and the product. The coexistence boundary that once guarded both
directions collapses to a single, still-meaningful invariant:

  * no module under sealai_v2.* may import app / app.*.

This guards against a regression where a legacy app.* import is reintroduced
into the green-field tree (e.g. by copy-pasting from V1 history). The AST
mechanism is the same proven, dependency-free pattern used by its siblings here,
so it runs with/without conftest and needs no runtime stack. It is deliberately
**self-contained** — it imports no other enforcer.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
V2_ROOT = REPO_ROOT / "backend" / "sealai_v2"


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
    """Nothing under sealai_v2/ may reach a legacy ``app`` tree (V1 retired)."""
    files = _py_files(V2_ROOT)
    assert files, "expected backend/sealai_v2/ to exist with modules"
    violations: list[str] = []
    for path in files:
        rel = str(path.relative_to(REPO_ROOT))
        for module in _absolute_imports(path):
            if _imports_prefix(module, "app"):
                violations.append(f"{rel}: imports legacy module {module!r}")
    assert not violations, (
        "sealai_v2 must not import app.* — V1 is retired and the green-field tree "
        "stays free of any reintroduced legacy import:\n  " + "\n  ".join(violations)
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
    """Anti-false-pass: the AST detector must trip on a real ``app.*`` import in the
    v2 tree, while leaving benign / lookalike / relative imports alone."""
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
