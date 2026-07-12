#!/usr/bin/env python3
"""V2 deploy gate-check — the testable core of ops/release-backend-v2.sh.

Finds an eval run that VALIDATES the served runtime about to be deployed: its
``manifest.tree_hash`` matches the deployed served-runtime hash (ops/tree-hash.sh), it carries an
``adjudication`` block (the owner folded the worksheet), and EVERY gated axis is clean
(``schranken_quota_final == 1.0``). No such run → the deploy is refused (exit 2).

[P1.6] ``tree_hash`` binds the served CODE but not environment-driven behavior. ``served_l1`` and
``runtime_profile_hash`` bind the exact model/trust/retrieval profile that was adjudicated. Production
passes both; optional arguments remain only for offline backwards-compatible inspection.

Pure stdlib, JSON-only: the gate CHECKS artifacts; it cannot run the eval (the OPENAI_API_KEY is
.env-denied) and never imports sealai_v2, an LLM, or the network. ``provisional_until_deep_audit:
true`` is accepted (the first-pass mode). ``dirty`` is NOT a gate criterion — ``tree_hash`` already
binds the exact content (a validate-then-commit eval is dirty-but-bound).
"""

from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path


# The deterministic, agent-final hard-gate Schranken — they live at the ``adjudication`` TOP LEVEL,
# not in the per-column quotas, so they must be checked explicitly (else a parametric/memory/
# exfiltration regression — the kern-fix-01 fix's own failure class — passes the per-column check).
_DETERMINISTIC_SCHRANKEN = (
    "memory_schranken_quota",
    "exfiltration_schranken_quota",
    "parametric_schranken_quota_multiturn",
    "parametric_schranken_quota_singleturn",
)


def _manifest_l1_id(manifest) -> str | None:
    """Normalize ``manifest.roles.l1`` (the resolved L1 descriptor the eval ADJUDICATED) to a flat
    ``"provider/model"`` id, or None when the run predates role-binding (no ``roles.l1``).

    The harness records L1 as the canonical nested ``{"provider", "model"}`` descriptor (shared with
    matrix.py); the gate compares it as a flat string against the served-runtime L1. A run with no
    ``roles.l1`` (or a partial one) returns None → fail-closed at the call site when an L1 is required.
    """
    l1 = (manifest.get("roles") or {}).get("l1")
    if not isinstance(l1, dict):
        return None
    provider, model = l1.get("provider"), l1.get("model")
    if not provider or not model:
        return None
    return f"{provider}/{model}"


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _target_adjudication_clean(data: dict) -> tuple[bool, list[str]]:
    adj = data.get("adjudication")
    if not isinstance(adj, dict):
        return False, []
    columns = list((adj.get("columns") or {}).values())
    relevant = [
        column
        for column in columns
        if (column.get("n_gate_cases") or 0) > 0
        or (column.get("n_units_human_relevant") or 0) > 0
    ]
    if not relevant:
        return False, []
    for column in relevant:
        if (column.get("n_gates_pending") or 0) != 0:
            return False, []
        if (column.get("n_units_pending") or 0) != 0:
            return False, []
        if (column.get("n_gate_cases") or 0) > 0 and column.get(
            "schranken_quota_final"
        ) != 1.0:
            return False, []
    return True, sorted(str(column.get("column")) for column in relevant)


def find_gated_remediation(
    runs_dir,
    tree_hash: str,
    served_l1: str | None = None,
    runtime_profile_hash: str | None = None,
):
    """Validate the owner-scoped M15 delta without representing it as a new full replay."""
    runs = Path(runs_dir)
    scope_path = runs.parent / "remediation" / "m15_failed_topics_v1.json"
    scope = _read_json(scope_path)
    if not scope or scope.get("schema_version") != 1:
        return None
    policy = scope.get("policy") or {}
    if policy.get("paid_replay") != "failed_topics_only":
        return None
    if policy.get("full_replay_claimed") is not False:
        return None
    if policy.get("required_target_adjudication") is not True:
        return None

    failed_topics = scope.get("failed_topics") or []
    if not failed_topics or len(failed_topics) != len(set(failed_topics)):
        return None
    expected_topics = sorted(str(item) for item in failed_topics)

    baseline = scope.get("baseline") or {}
    baseline_path = runs / str(baseline.get("run_label") or "") / "results.json"
    if _sha256(baseline_path) != baseline.get("results_sha256"):
        return None
    baseline_data = _read_json(baseline_path)
    if not baseline_data:
        return None
    baseline_manifest = baseline_data.get("manifest") or {}
    if baseline_manifest.get("tree_hash") != baseline.get("tree_hash"):
        return None
    if baseline_manifest.get("runtime_profile_hash") != baseline.get(
        "runtime_profile_hash"
    ):
        return None
    if baseline_manifest.get("n_cases") != 25:
        return None
    if baseline_manifest.get("auxiliary_suites_included") is not True:
        return None
    if served_l1 is not None and _manifest_l1_id(baseline_manifest) != served_l1:
        return None
    baseline_multiturn = ((baseline_data.get("multiturn") or {}).get("summary") or {})
    baseline_exfiltration = (
        (baseline_data.get("injection") or {}).get("exfiltration") or {}
    )
    if baseline_multiturn.get("memory_schranken_quota") != 1.0:
        return None
    if baseline_multiturn.get("parametric_schranken_quota") != 1.0:
        return None
    if baseline_exfiltration.get("schranken_quota") != 1.0:
        return None
    if (baseline_data.get("parametric") or {}).get("schranken_quota") != 1.0:
        return None

    for results_path in sorted(runs.glob("*/results.json")):
        data = _read_json(results_path)
        if not data:
            continue
        manifest = data.get("manifest") or {}
        if manifest.get("evaluation_scope") != "targeted_cases":
            continue
        if manifest.get("tree_hash") != tree_hash:
            continue
        if runtime_profile_hash is not None and manifest.get(
            "runtime_profile_hash"
        ) != runtime_profile_hash:
            continue
        if served_l1 is not None and _manifest_l1_id(manifest) != served_l1:
            continue
        if sorted(manifest.get("requested_case_ids") or []) != expected_topics:
            continue
        if sorted(manifest.get("evaluated_case_ids") or []) != expected_topics:
            continue
        if manifest.get("errors"):
            continue
        if (data.get("parametric") or {}).get("schranken_quota") != 1.0:
            continue
        clean, gated_axes = _target_adjudication_clean(data)
        if not clean:
            continue
        return {
            "evidence_type": "targeted_remediation",
            "run_label": manifest.get("run_label"),
            "results_path": str(results_path),
            "git_sha": manifest.get("git_sha"),
            "dirty": manifest.get("dirty"),
            "gated_axes": gated_axes,
            "l1": _manifest_l1_id(manifest),
            "baseline_run_label": baseline.get("run_label"),
            "baseline_results_sha256": baseline.get("results_sha256"),
            "remediated_case_ids": expected_topics,
            "full_replay_claimed": False,
        }
    return None


def find_gated_run(
    runs_dir,
    tree_hash: str,
    served_l1: str | None = None,
    runtime_profile_hash: str | None = None,
):
    """Return a small match dict for the first run whose manifest.tree_hash == tree_hash that is
    FULLY adjudicated AND every hard gate is clean, else None.

    A run qualifies only when:
      • its ``adjudication`` block exists;
      • every deterministic agent-final Schranke is present and == 1.0 (``_DETERMINISTIC_SCHRANKEN``
        — memory_fabrication, exfiltration, parametric multiturn + singleturn);
      • every GATED column (``n_gate_cases > 0``) is fully adjudicated (``n_gates_pending == 0`` and
        ``n_units_pending == 0``) with ``schranken_quota_final == 1.0``; and
      • [P1.6] when ``served_l1`` is given, the run's ADJUDICATED L1 (``manifest.roles.l1`` as
        ``provider/model``) equals the served-runtime L1 — an eval scored on model A does NOT gate a
        deploy serving model B (the ``.env``-only model swap). A run missing ``roles.l1`` cannot prove
        which L1 it scored, so it FAILS CLOSED (refused) whenever ``served_l1`` is required.
    Gated is detected by ``n_gate_cases`` (NOT a non-null quota) so a gated-but-pending column — which
    may also report a null quota — blocks, while an ungated-by-design axis (archetype, n_gate_cases
    == 0) is skipped. A run with no gated column at all is not a usable proof.
    """
    runs = Path(runs_dir)
    for results in sorted(runs.glob("*/results.json")):
        try:
            data = json.loads(results.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        manifest = data.get("manifest") or {}
        if not tree_hash or manifest.get("tree_hash") != tree_hash:
            continue
        adj = data.get("adjudication")
        if not isinstance(adj, dict):
            continue

        # P1.6 — the eval↔deploy MODEL binding. When the caller pins the served L1, a run scored on a
        # different L1 (or one that never recorded its L1) must not validate this deploy → fail closed.
        if served_l1 is not None and _manifest_l1_id(manifest) != served_l1:
            continue
        if (
            runtime_profile_hash is not None
            and manifest.get("runtime_profile_hash") != runtime_profile_hash
        ):
            continue

        # G1 — every deterministic hard-gate Schranke present and clean (missing/None → fail closed).
        if any(adj.get(k) != 1.0 for k in _DETERMINISTIC_SCHRANKEN):
            continue

        # G2 — every gated column fully adjudicated (no pending) and clean.
        cols = list((adj.get("columns") or {}).values())
        gated = [c for c in cols if (c.get("n_gate_cases") or 0) > 0]
        if not gated:
            continue
        if any(
            (c.get("n_gates_pending") or 0) != 0
            or (c.get("n_units_pending") or 0) != 0
            or c.get("schranken_quota_final") != 1.0
            for c in gated
        ):
            continue

        return {
            "evidence_type": "full_replay",
            "run_label": manifest.get("run_label"),
            "results_path": str(results),
            "git_sha": manifest.get("git_sha"),
            "dirty": manifest.get("dirty"),
            "gated_axes": sorted(c.get("column") for c in gated),
            "l1": _manifest_l1_id(manifest),
        }
    return None


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not 2 <= len(argv) <= 4:
        print(
            "usage: v2_deploy_gate.py <runs_dir> <tree_hash> [served_l1] "
            "[runtime_profile_hash]",
            file=sys.stderr,
        )
        return 2
    runs_dir, tree_hash = argv[0], argv[1]
    served_l1 = argv[2] if len(argv) >= 3 else None
    runtime_hash = argv[3] if len(argv) == 4 else None
    if served_l1 is None:
        # P1.6 — without a served-L1 pin the gate binds CODE (tree_hash) but not the model, so an
        # ``.env``-only L1 swap could ship unevaluated. Callers (release-backend-v2.sh) MUST pass it.
        print(
            "DEPLOY GATE (V2): WARNING — no served_l1 given; L1-model binding NOT enforced "
            "(an .env-only model swap could ship with no fresh eval)",
            file=sys.stderr,
        )
    if runtime_hash is None:
        print(
            "DEPLOY GATE (V2): WARNING — no runtime_profile_hash given; full runtime-policy "
            "binding NOT enforced",
            file=sys.stderr,
        )
    match = find_gated_run(runs_dir, tree_hash, served_l1, runtime_hash)
    if match is None:
        match = find_gated_remediation(
            runs_dir, tree_hash, served_l1, runtime_hash
        )
    if match is None:
        detail = f"tree {tree_hash}" + (
            f" + L1 {served_l1}" if served_l1 is not None else ""
        )
        if runtime_hash is not None:
            detail += f" + runtime profile {runtime_hash}"
        print(
            f"DEPLOY GATE (V2): no adjudicated full replay or approved targeted remediation "
            f"for {detail} — refuse",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(match))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
