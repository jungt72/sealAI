"""Architecture enforcer — governed-layer single-writer invariant (S3).

P1-4 PR5b. `NormalizedState`, `AssertedState`, `GovernanceState` and its subclass
`DecisionState` may only be PRODUCED by the reducer chain (`reducers.py`) — see
the architecture rule at the top of `app/agent/state/reducers.py`. Producing them
elsewhere (a direct constructor OR a `.governance/.decision/.normalized/.asserted
.model_copy(...)` content-sync) bypasses the single writer.

This AST enforcer closes the gap the prior regex constructor-checks left open
(`model_copy`): it parses every product module under `backend/app` and fails on
either a direct governed-layer constructor or a governed-layer `model_copy`
outside the sanctioned single-writer modules. Call sites that need a deterministic
governed-layer content-sync use `reducers.produce_governance` /
`reducers.produce_decision` instead.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_APP = REPO_ROOT / "backend" / "app"

GOVERNED_TYPES: frozenset[str] = frozenset(
    {"NormalizedState", "AssertedState", "GovernanceState", "DecisionState"}
)
GOVERNED_ATTRS: frozenset[str] = frozenset(
    {"normalized", "asserted", "governance", "decision"}
)

# The ONLY modules that may produce governed-layer instances (single writer +
# the model definitions themselves).
ALLOWED_FILES: frozenset[str] = frozenset(
    {
        "backend/app/agent/state/reducers.py",
        "backend/app/agent/state/models.py",
    }
)


def _is_test_path(path: Path) -> bool:
    # Test fixtures legitimately build governed-layer states to set up conditions;
    # the single-writer invariant governs PRODUCT runtime code, not test setup.
    return "tests" in path.parts or path.name.startswith("test_")


def _python_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
        and ".pytest_cache" not in path.parts
        and not _is_test_path(path)
    )


def _violations(path: Path) -> list[tuple[int, str]]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    hits: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # 1) direct governed-type constructor call (a Name in GOVERNED_TYPES).
        if isinstance(func, ast.Name) and func.id in GOVERNED_TYPES:
            hits.append((node.lineno, lines[node.lineno - 1].strip()))
        # 2) governed-layer model_copy. The receiver is the governed layer, reached
        #    either as an attribute (`state.governance.model_copy(...)`) or as a
        #    bare local bound from one (`normalized = ...; normalized.model_copy(...)`).
        elif isinstance(func, ast.Attribute) and func.attr == "model_copy":
            receiver = func.value
            receiver_is_governed = (
                isinstance(receiver, ast.Attribute) and receiver.attr in GOVERNED_ATTRS
            ) or (isinstance(receiver, ast.Name) and receiver.id in GOVERNED_ATTRS)
            if receiver_is_governed:
                hits.append((node.lineno, lines[node.lineno - 1].strip()))

    return hits


def test_governed_layer_has_single_writer() -> None:
    violations: list[str] = []
    for path in _python_files(BACKEND_APP):
        relpath = str(path.relative_to(REPO_ROOT))
        if relpath in ALLOWED_FILES:
            continue
        for lineno, code in _violations(path):
            violations.append(f"{relpath}:{lineno}: {code}")

    assert not violations, (
        "Governed-layer instance produced outside the reducer single writer "
        "(use reducers.produce_governance / produce_decision, or move the "
        "production into the reducer chain — see reducers.py architecture rule):\n  "
        + "\n  ".join(violations)
    )
