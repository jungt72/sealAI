"""Architecture enforcer — no seal-type string-branching in the governed core.

P1-4 PR5a (gap-audit C1). The governed core must ASK the pack
(`app.domain.seal_packs`); it must never hardcode `seal_type == "rwdr"` style
branches or per-type field-list dicts in the generically-named plumbing
(CORE_PACK_BOUNDARY.md §3.3). This test parses each core module with `ast` and
fails when a seal-type literal drives control flow outside a **versioned,
documented allowlist**.

What is flagged (in the scanned CORE files only):
  1. `==` / `!=` against a seal-type/path string literal  (e.g. `x == "rwdr"`).
  2. `in` / `not in` a *collection literal* of seal-type strings
     (e.g. `x in {"rwdr", "ms_pump"}`) — a membership branch.
  3. a dict literal mapping seal-type string keys to tuple/list values
     (the per-type field-list anti-pattern, e.g. `_SEALING_TYPE_REQUIRED_FIELDS`).

What is NOT flagged (by design):
  - label PRODUCTION: `return "rwdr"`, `calc_type="rwdr"` assignments, tuples in
    `for token in (...)` classifiers.
  - substring text checks: `"rwdr" in some_text` (comparator is not a collection).
  - dispatch/display tables whose values are NOT tuples/lists
    (`_COCKPIT_PATH_RULES` → dict values, `_SEALING_TYPE_DISPLAY` → str values).
  - tokens too generic to be seal-type-specific (`"static"`, `"hydraulic"`).

Allowlist: each entry is a deliberate, documented owner decision (NOT a way to
green un-routed branches). Inflating it requires the same scrutiny as a doctrine
change (see CORE_PACK_BOUNDARY.md).
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND = REPO_ROOT / "backend"

# Generically-named governed-core modules that must ask the pack, never branch on
# the seal-type string. (The classification STAGE — normalize_seal_type,
# _engineering_path, _derive_engineering_path — produces labels and is allowed;
# its one in-core classifier site is allowlisted below with a reason.)
CORE_FILES: tuple[str, ...] = (
    "backend/app/agent/state/reducers.py",
    "backend/app/agent/domain/challenge_engine.py",
    "backend/app/agent/domain/risk_readiness.py",
    "backend/app/agent/domain/checks_registry.py",
    "backend/app/agent/graph/output_contract_assembly.py",
    "backend/app/agent/v92/calculation_projection.py",
    "backend/app/agent/v92/orchestrator.py",
    "backend/app/api/v1/projections/case_workspace.py",
)

# Unambiguous seal-type / engineering-path / pack tokens. Deliberately excludes
# generic words like "static"/"hydraulic" that also appear as motion/medium terms.
SEAL_TYPE_TOKENS: frozenset[str] = frozenset(
    {
        "rwdr",
        "o_ring",
        "oring",
        "gasket",
        "packing",
        "mechanical_seal",
        "ms_pump",
        "hyd_pneu",
        "unclear_rotary",
        "labyrinth",
        "radial_shaft_seal",
        "rotary_lip_seal",
        "cassette_seal",
        "v_ring",
    }
)

# Versioned allowlist: (relpath, stripped source line) -> documented owner decision.
# Keyed by line CONTENT (robust to line shifts). Every entry is a deliberate core
# check, not an un-routed branch.
ALLOWLIST: dict[tuple[str, str], str] = {
    (
        "backend/app/agent/domain/risk_readiness.py",
        'if path in {"static", "hyd_pneu"}:',
    ): "P1-3/A-499: non-rotary paths drop speed/shaft from critical-missing; "
    "heterogeneous set, no 1:1 pack — documented core check.",
    (
        "backend/app/agent/domain/risk_readiness.py",
        'if path == "ms_pump":',
    ): "P1-3/A-499: ms_pump is not a DomainPack; documented core check.",
    (
        "backend/app/agent/domain/risk_readiness.py",
        'elif speed is None and str(engineering_path or "") in {"rwdr", "ms_pump", "unclear_rotary"}:',
    ): "P1-3/A-499: heterogeneous rotary set {rwdr, ms_pump, unclear_rotary} — "
    "only rwdr is a pack; routing would silently drop the other two. Owner "
    "decision 2026-06-04 (CORE_PACK_BOUNDARY.md §'Residual rwdr risk branches').",
    (
        "backend/app/agent/v92/orchestrator.py",
        'if raw in {"rwdr", "radialwellendichtring"}:',
    ): "Classification STAGE (C3): normalize_seal_type maps raw user input to a "
    "canonical SealType. The boundary explicitly locates seal-type classification "
    "here (it produces the label the rest of the core asks the pack about), not "
    "branching-in-plumbing.",
    (
        "backend/app/agent/v92/orchestrator.py",
        'elif raw in {"o-ring", "oring", "o_ring"}:',
    ): "Classification STAGE (C3): normalize_seal_type raw->canonical mapping "
    "(sibling of the rwdr classifier branch above).",
}


def _seal_constants(node: ast.AST) -> list[str]:
    """Seal-type string constants directly on this expression node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value] if node.value in SEAL_TYPE_TOKENS else []
    return []


def _collection_seal_constants(node: ast.AST) -> list[str]:
    """Seal-type string constants inside a set/tuple/list literal."""
    if isinstance(node, (ast.Set, ast.Tuple, ast.List)):
        found: list[str] = []
        for elt in node.elts:
            found.extend(_seal_constants(elt))
        return found
    return []


def _flagged_lines(path: Path) -> list[tuple[int, str]]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    hits: list[tuple[int, str]] = []

    def record(node: ast.AST) -> None:
        hits.append((node.lineno, lines[node.lineno - 1].strip()))

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op, right in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)):
                    if _seal_constants(node.left) or _seal_constants(right):
                        record(node)
                elif isinstance(op, (ast.In, ast.NotIn)):
                    # membership in a seal-type collection literal (a branch),
                    # NOT a `"rwdr" in some_string` substring text check.
                    if _collection_seal_constants(right):
                        record(node)
        elif isinstance(node, ast.Dict):
            key_is_seal = any(
                key is not None and _seal_constants(key) for key in node.keys
            )
            value_is_seq = any(
                isinstance(value, (ast.Tuple, ast.List)) for value in node.values
            )
            if key_is_seal and value_is_seq:
                record(node)

    return hits


def test_core_has_no_unallowlisted_seal_type_branching() -> None:
    violations: list[str] = []
    for relpath in CORE_FILES:
        path = REPO_ROOT / relpath
        for lineno, code in _flagged_lines(path):
            if (relpath, code) in ALLOWLIST:
                continue
            violations.append(f"{relpath}:{lineno}: {code}")

    assert not violations, (
        "Seal-type string-branching found in the governed core (route it through "
        "app.domain.seal_packs, or add a documented allowlist entry with an owner "
        "decision — see CORE_PACK_BOUNDARY.md):\n  " + "\n  ".join(violations)
    )


def test_detector_catches_synthetic_violations(tmp_path) -> None:
    """The enforcer must actually trip on a fresh seal-type branch (guards against
    a detector that silently passes everything)."""
    synthetic = tmp_path / "synthetic_core.py"
    synthetic.write_text(
        "def f(seal_type, calc_type):\n"
        '    if seal_type == "rwdr":\n'
        "        return 1\n"
        '    if calc_type in {"rwdr", "o_ring"}:\n'
        "        return 2\n"
        '    table = {"rwdr": ("a", "b"), "o_ring": ("c",)}\n'
        "    return table\n",
        encoding="utf-8",
    )
    codes = [code for _lineno, code in _flagged_lines(synthetic)]
    assert any('== "rwdr"' in code for code in codes)  # rule 1
    assert any("in {" in code for code in codes)  # rule 2
    assert any(code.startswith("table = {") for code in codes)  # rule 3
    # And a label-producing / substring line must NOT be flagged:
    benign = tmp_path / "benign_core.py"
    benign.write_text(
        "def g(text):\n"
        '    if "rwdr" in text:\n'  # substring text check — allowed
        '        return "rwdr"\n'  # label production — allowed
        "    return None\n",
        encoding="utf-8",
    )
    assert _flagged_lines(benign) == []


def test_allowlist_has_no_stale_entries() -> None:
    """Every allowlist entry must still correspond to a real flagged line — so a
    routed/removed branch cannot leave a silent, meaningless allowlist behind."""
    flagged: set[tuple[str, str]] = set()
    for relpath in CORE_FILES:
        path = REPO_ROOT / relpath
        for _lineno, code in _flagged_lines(path):
            flagged.add((relpath, code))

    stale = [key for key in ALLOWLIST if key not in flagged]
    assert not stale, (
        "Stale allowlist entries (no longer a flagged core branch — remove them):\n  "
        + "\n  ".join(f"{relpath}: {code}" for relpath, code in stale)
    )
