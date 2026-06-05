"""Architecture enforcer — governed-layer single-writer invariant (S3).

P1-4 PR5b. `NormalizedState`, `AssertedState`, `GovernanceState` and its subclass
`DecisionState` may only be PRODUCED by the reducer chain (`reducers.py`) — see
the architecture rule at the top of `app/agent/state/reducers.py`. Producing them
elsewhere — a direct constructor, a governed-receiver `.model_copy(...)` /
`.copy(update=)` content-sync, or a `setattr(..., "<governed attr>", ...)` — bypasses
the single writer.

This AST enforcer parses every product module under `backend/app` and fails on any
of those forms outside the sanctioned single-writer modules. Call sites that need a
deterministic governed-layer content-sync use `reducers.produce_governance` /
`reducers.produce_decision` instead. (Dict-subscript writes are intentionally not
flagged — the governed layer is Pydantic, never a dict key; see `_violations`.)
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
        # 2) governed-layer content-sync copy: `.model_copy(...)` OR `.copy(update=)`
        #    (the Pydantic-v1 alias). The receiver is the governed layer, reached
        #    either as an attribute (`state.governance.model_copy(...)`) or as a
        #    bare local bound from one (`normalized = ...; normalized.copy(...)`).
        elif isinstance(func, ast.Attribute) and func.attr in {"model_copy", "copy"}:
            receiver = func.value
            receiver_is_governed = (
                isinstance(receiver, ast.Attribute) and receiver.attr in GOVERNED_ATTRS
            ) or (isinstance(receiver, ast.Name) and receiver.id in GOVERNED_ATTRS)
            if receiver_is_governed:
                hits.append((node.lineno, lines[node.lineno - 1].strip()))
        # 3) setattr(..., "<governed attr>", ...) — a dynamic attribute write to a
        #    governed-layer slot, bypassing the reducer's static assignment.
        elif (
            isinstance(func, ast.Name) and func.id == "setattr" and len(node.args) >= 2
        ):
            attr_arg = node.args[1]
            if isinstance(attr_arg, ast.Constant) and attr_arg.value in GOVERNED_ATTRS:
                hits.append((node.lineno, lines[node.lineno - 1].strip()))

    # NOTE: dict-subscript writes (`state["governance"] = ...`) are deliberately NOT
    # flagged. The governed layer is Pydantic (attribute access), never subscript;
    # the only subscript hits in the tree are plain working-state dict keys
    # (`sealing["asserted"] = ...`) — flagging them would be a false positive, which
    # the zero-FP doctrine forbids (audit 2026-06-05 B5).
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


def test_detector_catches_synthetic_violations(tmp_path) -> None:
    """The enforcer must actually trip on every governed-write form it claims to
    catch (B6 — guards against a detector that silently passes after a refactor)."""
    synthetic = tmp_path / "synthetic_writer.py"
    synthetic.write_text(
        "def f(state):\n"
        "    a = GovernanceState(x=1)\n"  # direct constructor
        "    b = state.governance.model_copy(update={})\n"  # model_copy on governed attr
        "    c = state.decision.copy(update={})\n"  # .copy(update=) on governed attr
        "    setattr(state, 'governance', {})\n"  # setattr to a governed slot
        "    return a, b, c\n",
        encoding="utf-8",
    )
    codes = [code for _lineno, code in _violations(synthetic)]
    assert any("GovernanceState(" in c for c in codes)  # constructor
    assert any(".model_copy(" in c for c in codes)  # model_copy
    assert any(".copy(" in c for c in codes)  # copy(update=)
    assert any("setattr(" in c for c in codes)  # setattr

    # Benign forms must NOT trip: a plain `.copy()` on a non-governed receiver, a
    # non-governed constructor, and a dict-subscript write to an "asserted" key.
    benign = tmp_path / "benign_writer.py"
    benign.write_text(
        "def g(payload, sealing):\n"
        "    d = payload.copy()\n"  # plain receiver — allowed
        "    cfg = SomeConfig(x=1)\n"  # non-governed type — allowed
        "    sealing['asserted'] = {}\n"  # working-state dict key — allowed (not Pydantic)
        "    return d, cfg, sealing\n",
        encoding="utf-8",
    )
    assert _violations(benign) == []
