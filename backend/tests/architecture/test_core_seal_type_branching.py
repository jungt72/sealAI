"""Architecture enforcer — no seal-type string-branching in the governed core.

P1-4 PR5a (gap-audit C1). The governed core must ASK the pack
(`app.domain.seal_packs`); it must never hardcode `seal_type == "rwdr"` style
branches or per-type field-list dicts in the generically-named plumbing
(CORE_PACK_BOUNDARY.md §3.3). This test parses each core module with `ast` and
fails when a seal-type literal drives control flow outside a **versioned,
documented allowlist**.

What is flagged (anywhere in the scanned core packages):
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

# Deny-by-default: scan EVERY product module under the governed-core packages, not a
# fixed file list (audit 2026-06-05 B3 — services/, mcp/, communication/, most of
# graph/, all of domain/ were previously unscanned). Any seal-type string-branch in
# these packages is flagged unless it carries a documented allowlist entry below.
# (Frontend .tsx seal-type branches are a separate finding, audit B4.)
CORE_PACKAGES: tuple[str, ...] = (
    "backend/app/agent",
    "backend/app/services",
    "backend/app/api",
    "backend/app/mcp",
)


def _core_files() -> list[Path]:
    """Every product .py under the core packages (tests / caches excluded)."""
    files: list[Path] = []
    for pkg in CORE_PACKAGES:
        for path in (REPO_ROOT / pkg).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if "tests" in path.parts or path.name.startswith("test_"):
                continue
            files.append(path)
    return sorted(files)


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
        'elif speed is None and str(engineering_path or "") in { "rwdr", "ms_pump", "unclear_rotary", }:',
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
    # ── Deny-by-default walk (B3, 2026-06-05): newly-scanned legitimate sites.
    #    Each is a domain/scope/classification/norm check — NOT generically-named
    #    plumbing that should ask the pack. One reason per entry (no bulk grant).
    (
        "backend/app/services/norm_modules/din_3760_iso_6194.py",
        'if engineering_path == "rwdr":',
    ): "Norm self-scoping: DIN 3760 / ISO 6194 IS the radial-shaft-seal norm; "
    "applies_to() declares the norm's own applicability — not pack plumbing.",
    (
        "backend/app/services/norm_modules/din_3760_iso_6194.py",
        'return seal_kind in {"rwdr", "radial_shaft_seal"} or motion_type == "rotary"',
    ): "Norm self-scoping (same applies_to()): the DIN 3760 / ISO 6194 module "
    "declares the seal kinds it covers; documented norm check, not dispatch.",
    (
        "backend/app/services/rwdr_mvp_brief.py",
        'scope_confirmation_required = scope != "rwdr"',
    ): "Scope guard (AGENTS.md: 'scope guard wins over all other logic'): the RWDR "
    "MVP brief marks non-rwdr scope for confirmation — not pack-field plumbing.",
    (
        "backend/app/api/v1/projections/ptfe_rwdr_enrichment.py",
        'if path == "rwdr":',
    ): "Domain-specific projection: the PTFE-RWDR enrichment module applies only to "
    "the rwdr path it is named for; gating on its own domain, not type dispatch.",
    (
        "backend/app/services/compatibility_inquiry_service.py",
        'if word_key in {"wdr", "rwdr", "as"}:',
    ): "Classification STAGE: keyword extraction of seal designations from user "
    "text (sibling of normalize_seal_type) — produces a label, not a pack branch.",
    (
        "backend/app/agent/communication/technical_case_challenge.py",
        'if domain != "rwdr":',
    ): "Classification STAGE in the COMMUNICATION layer (distinct from the "
    "P1-4-routed domain challenge_engine): rwdr-vs-generic detection selecting the "
    "composer path; the else branch builds a generic technical-case plan.",
    (
        "backend/app/agent/communication/technical_case_challenge.py",
        'if plan.detected_domain == "rwdr":',
    ): "Communication wording keyed on the already-classified domain (with a generic "
    "else branch) — message composition, not pack-field plumbing.",
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
        # Record the full statement span (start..end_lineno) collapsed to a single
        # normalized line, so the allowlist stays stable across ruff line-wrapping
        # (a long branch wrapped across lines must still match its allowlist key).
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        code = " ".join(
            lines[i].strip() for i in range(node.lineno - 1, end) if lines[i].strip()
        )
        hits.append((node.lineno, code))

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
    for path in _core_files():
        relpath = str(path.relative_to(REPO_ROOT))
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
    for path in _core_files():
        relpath = str(path.relative_to(REPO_ROOT))
        for _lineno, code in _flagged_lines(path):
            flagged.add((relpath, code))

    stale = [key for key in ALLOWLIST if key not in flagged]
    assert not stale, (
        "Stale allowlist entries (no longer a flagged core branch — remove them):\n  "
        + "\n  ".join(f"{relpath}: {code}" for relpath, code in stale)
    )
