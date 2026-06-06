"""Architecture enforcer — manufacturer matching stays DORMANT & CONTAINED.

V1.8 Wave 0 (decision C + the CONTAINED-branch verify of the live matching path).
AGENTS.md scope guard: "RWDR MVP must keep manufacturer matching, shortlists, winner
selection, product/material recommendations … disabled." Two distinct surfaces exist in
the tree, both must stay inert:

  1. The DORMANT TRIO of services (P4 groundwork, no live caller today):
       app/services/capability_service.py
       app/services/manufacturer_fit_matrix_service.py   (ranking: fit_score)
       app/services/problem_first_matching_service.py
     They import each other; nothing else may import them (no route / mode / module /
     Proposal / envelope path), unless behind the default-OFF flag.

  2. The LIVE matching_node path (governed TERMINATE path) computes match_candidates /
     winner_candidate_id / recommendation_identity INTERNALLY, but it is structurally
     walled off from every user surface — verified V1–V4 (see
     docs/audit/v18_wave0_mfr_match_report.md):
       * the browser-bound DTO `PartnerMatchingSummary` (extra="forbid") does NOT declare
         those identity fields → stripped at the wire;
       * the backend never emits a `manufacturer_fit_matrix` field, so the latent frontend
         ManufacturerFitPanel can never light up.

These tests make that containment DURABLE — a future patch that re-exposes matching to a
user surface (or wires the trio without the flag) trips here, not in production.

Like the other enforcers in this package, the assertions are **source-based (ast)**: they
must run identically with conftest, without it (`--noconftest` in CI), and never depend on
importing heavy app modules.

Audit-gap note: the V1.8 deep audit scanned only the dormant trio and missed the live
matching_node path; this test family + the Wave 0 report close that gap.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
APP = REPO_ROOT / "backend" / "app"

# The dormant trio, by module-name leaf. They may import EACH OTHER; no other product
# module may import them (that would be a live activation of disabled matching).
TRIO: frozenset[str] = frozenset(
    {
        "capability_service",
        "manufacturer_fit_matrix_service",
        "problem_first_matching_service",
    }
)

# Matching-identity fields that must never reach a user-facing (serialized) DTO. They live
# in the internal MatchingState / manufacturer_rfq handover only.
FORBIDDEN_WIRE_FIELDS: frozenset[str] = frozenset(
    {
        "winner_candidate_id",
        "recommendation_identity",
        "match_candidates",
        "matched_primary_candidate",
        "manufacturer_fit_matrix",
    }
)


# ── small ast helpers (source-based — no app imports) ────────────────────────────────────


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _class_defs(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}


def _class_field_names(cls: ast.ClassDef) -> set[str]:
    """Pydantic field names declared in a class body (annotated or assigned)."""
    names: set[str] = set()
    for stmt in cls.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
        elif isinstance(stmt, ast.Assign):
            for tgt in stmt.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
    return {n for n in names if not n.startswith("_") and n != "model_config"}


def _class_config_extra(cls: ast.ClassDef) -> str | None:
    """The `extra=` value on a class's `model_config = (Settings)ConfigDict(...)`."""
    for stmt in cls.body:
        targets = (
            stmt.targets
            if isinstance(stmt, ast.Assign)
            else [stmt.target]
            if isinstance(stmt, ast.AnnAssign)
            else []
        )
        if not any(isinstance(t, ast.Name) and t.id == "model_config" for t in targets):
            continue
        value = stmt.value
        if isinstance(value, ast.Call):
            for kw in value.keywords:
                if kw.arg == "extra" and isinstance(kw.value, ast.Constant):
                    return str(kw.value.value)
    return None


def _all_field_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for cls in _class_defs(tree).values():
        names |= _class_field_names(cls)
    return names


# ── trio import scan ─────────────────────────────────────────────────────────────────────


def _app_files() -> list[Path]:
    files: list[Path] = []
    for path in APP.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if "tests" in path.parts or path.name.startswith("test_"):
            continue
        files.append(path)
    return sorted(files)


def _trio_imports(path: Path) -> set[str]:
    """Trio module leaves imported by this file (via `import` or `from … import`)."""
    found: set[str] = set()
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.rsplit(".", 1)[-1] in TRIO:
                    found.add(alias.name.rsplit(".", 1)[-1])
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").rsplit(".", 1)[-1] in TRIO:
                found.add((node.module or "").rsplit(".", 1)[-1])
            for alias in node.names:
                if alias.name in TRIO:
                    found.add(alias.name)
    return found


# ── 1. Dormant trio has no live importer ───────────────────────────────────────────────


def test_dormant_matching_services_have_no_live_importers() -> None:
    violations: list[str] = []
    for path in _app_files():
        if path.stem in TRIO:
            continue  # the trio imports itself — the only sanctioned coupling
        imported = _trio_imports(path)
        if imported:
            violations.append(f"{path.relative_to(REPO_ROOT)}: imports {sorted(imported)}")
    assert not violations, (
        "Dormant manufacturer-matching service(s) imported from a live product module "
        "(AGENTS.md: matching/shortlist/winner selection stays DISABLED for the RWDR MVP). "
        "Gate behind SEALAI_ENABLE_MANUFACTURER_MATCHING and re-scope, or revert:\n  "
        + "\n  ".join(violations)
    )


# ── 2. Matching identity is stripped at the wire boundary ────────────────────────────────


def _workspace_schema() -> ast.Module:
    return _parse(APP / "api" / "v1" / "schemas" / "case_workspace.py")


def test_workspace_wire_contract_excludes_matching_identity() -> None:
    tree = _workspace_schema()
    leaked = FORBIDDEN_WIRE_FIELDS & _all_field_names(tree)
    assert not leaked, (
        "Manufacturer matching-identity field(s) declared on the user-facing wire contract "
        f"(schemas/case_workspace.py): {sorted(leaked)}. These belong to the internal "
        "MatchingState/RFQ-handover only (V1.8 §5.4 No-Go: no winner/recommendation to the "
        "end user). Keep them out of the serialized projection."
    )
    # The partner-matching read model must reject undeclared keys, so the internal
    # winner/recommendation cannot slip through serialization.
    partner = _class_defs(tree).get("PartnerMatchingSummary")
    assert partner is not None, "PartnerMatchingSummary must exist on the wire schema"
    assert _class_config_extra(partner) == "forbid"


def test_manufacturer_fit_matrix_never_emitted_on_the_wire() -> None:
    """The frontend ManufacturerFitPanel renders `manufacturer_fit_matrix` rows+scores; the
    backend must never declare that field, so the panel can only show its dormant fallback."""
    assert "manufacturer_fit_matrix" not in _all_field_names(_workspace_schema())


# ── 3. Activation flag is default-OFF (env-independent) ──────────────────────────────────


def test_manufacturer_matching_flag_default_off() -> None:
    settings = _class_defs(_parse(APP / "core" / "config.py")).get("Settings")
    assert settings is not None, "Settings class must exist"
    default: object = "MISSING"
    for stmt in settings.body:
        if (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id == "SEALAI_ENABLE_MANUFACTURER_MATCHING"
            and isinstance(stmt.value, ast.Constant)
        ):
            default = stmt.value.value
    assert default is False, (
        "SEALAI_ENABLE_MANUFACTURER_MATCHING must be declared on Settings and default False "
        "(the sanctioned, OFF-by-default activation gate for the RWDR MVP)."
    )


# ── 4. B4 — turn trace stores prompt HASHES only, never raw prompt text ──────────────────


def test_prompt_trace_carries_hash_only_no_fulltext() -> None:
    trace = _class_defs(_parse(APP / "agent" / "v92" / "contracts.py")).get("PromptTrace")
    assert trace is not None, "PromptTrace must exist"
    fields = _class_field_names(trace)
    assert "rendered_prompt_hash" in fields
    raw_text_fields = {
        "rendered_prompt",
        "prompt_text",
        "prompt_body",
        "prompt",
        "messages",
        "rendered_messages",
    }
    leaked = raw_text_fields & fields
    assert not leaked, f"PromptTrace must not store raw prompt text: {sorted(leaked)}"
    assert _class_config_extra(trace) == "forbid"


# ── Anti-false-pass: the detectors must trip on synthetic violations ─────────────────────


def test_detector_catches_synthetic_importer(tmp_path) -> None:
    synthetic = tmp_path / "synthetic_route.py"
    synthetic.write_text(
        "from app.services.manufacturer_fit_matrix_service import ManufacturerFitMatrixService\n"
        "from app.services import capability_service\n"
        "import app.services.problem_first_matching_service\n",
        encoding="utf-8",
    )
    assert _trio_imports(synthetic) == TRIO

    benign = tmp_path / "benign.py"
    benign.write_text("from app.services.rwdr_mvp_brief import build_brief\n", encoding="utf-8")
    assert _trio_imports(benign) == set()


def test_detector_catches_synthetic_wire_leak(tmp_path) -> None:
    synthetic = tmp_path / "synthetic_schema.py"
    synthetic.write_text(
        "from pydantic import BaseModel, ConfigDict\n"
        "class Leak(BaseModel):\n"
        "    winner_candidate_id: str | None = None\n"
        "    manufacturer_fit_matrix: dict | None = None\n"
        '    model_config = ConfigDict(extra="allow")\n',
        encoding="utf-8",
    )
    fields = _all_field_names(_parse(synthetic))
    assert {"winner_candidate_id", "manufacturer_fit_matrix"} <= fields
    leak_cls = _class_defs(_parse(synthetic))["Leak"]
    assert _class_config_extra(leak_cls) == "allow"
