"""C/D3 — the V2 deploy gate-check logic, unit-tested against fixture results.json.

The gate passes ONLY when, for a run whose manifest.tree_hash matches the deployed image hash:
  • the adjudication block exists,
  • the deterministic agent-final hard-gate Schranken are all 1.0 — memory_fabrication, exfiltration,
    parametric (multiturn M6a + singleturn M8); these live at the `adjudication` top level, NOT in the
    per-column quotas, so omitting them would let a parametric/memory regression (the kern-fix-01 fix's
    OWN failure mode) sail through (G1), and
  • every GATED column (n_gate_cases > 0) is fully adjudicated (n_gates_pending == 0, n_units_pending
    == 0) AND schranken_quota_final == 1.0 (G2 — a gated-but-pending column must block, distinct from
    an ungated-by-design axis like archetype with n_gate_cases == 0).

This is the only piece of ops/release-backend-v2.sh testable without a deploy; steps 3-6 are not run.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]

DET_KEYS = (
    "memory_schranken_quota",
    "exfiltration_schranken_quota",
    "parametric_schranken_quota_multiturn",
    "parametric_schranken_quota_singleturn",
)


def _gate():
    spec = importlib.util.spec_from_file_location(
        "v2_deploy_gate", REPO / "ops" / "v2_deploy_gate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _col(axis, *, quota=1.0, n_gate_cases=20, pending=0):
    return {
        "column": axis,
        "schranken_quota_final": quota,
        "n_gate_cases": n_gate_cases,
        "n_gates_pending": pending,
        "n_units_pending": pending,
    }


_ARCHETYPE = {
    "column": "archetype",
    "schranken_quota_final": None,
    "n_gate_cases": 0,
    "n_gates_pending": 0,
    "n_units_pending": 0,
}


def _write_run(runs_dir, label, *, tree_hash, adjudicated=True, det=None, columns=None):
    d = runs_dir / label
    d.mkdir(parents=True)
    data = {
        "manifest": {
            "run_label": label,
            "tree_hash": tree_hash,
            "git_sha": "x",
            "dirty": True,
        }
    }
    if adjudicated:
        adj = {"provisional_until_deep_audit": True}
        for k in DET_KEYS:
            adj[k] = 1.0
        if det:
            adj.update(det)
        if columns is None:
            columns = [_col("flags_off"), _col("edge", n_gate_cases=5), _ARCHETYPE]
        adj["columns"] = {c["column"]: c for c in columns}
        data["adjudication"] = adj
    (d / "results.json").write_text(json.dumps(data), encoding="utf-8")


# ── happy path ────────────────────────────────────────────────────────────────
def test_passes_for_matching_fully_clean_run(tmp_path):
    _write_run(tmp_path, "kern-fix-01", tree_hash="ABC")
    m = _gate().find_gated_run(tmp_path, "ABC")
    assert m is not None and m["run_label"] == "kern-fix-01"
    assert m["gated_axes"] == ["edge", "flags_off"]  # archetype (ungated) excluded


# ── tree_hash / adjudication presence ──────────────────────────────────────────
def test_refuses_when_no_tree_hash_match(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC")
    assert _gate().find_gated_run(tmp_path, "DEADBEEF") is None


def test_empty_tree_hash_never_matches(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC")
    assert _gate().find_gated_run(tmp_path, "") is None


def test_refuses_unadjudicated_run(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC", adjudicated=False)
    assert _gate().find_gated_run(tmp_path, "ABC") is None


# ── per-column quota + gated detection ─────────────────────────────────────────
def test_refuses_when_a_gated_column_quota_below_one(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC", columns=[_col("flags_off", quota=0.933), _ARCHETYPE])
    assert _gate().find_gated_run(tmp_path, "ABC") is None


def test_refuses_when_no_gated_column_present(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC", columns=[_ARCHETYPE])
    assert _gate().find_gated_run(tmp_path, "ABC") is None


# ── G1: the deterministic agent-final Schranken must all be 1.0 ────────────────
def test_g1_refuses_parametric_multiturn_regression(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC", det={"parametric_schranken_quota_multiturn": 0.933})
    assert _gate().find_gated_run(tmp_path, "ABC") is None


def test_g1_refuses_parametric_singleturn_regression(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC", det={"parametric_schranken_quota_singleturn": 0.9})
    assert _gate().find_gated_run(tmp_path, "ABC") is None


def test_g1_refuses_memory_fabrication_regression(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC", det={"memory_schranken_quota": 0.8})
    assert _gate().find_gated_run(tmp_path, "ABC") is None


def test_g1_refuses_exfiltration_regression(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC", det={"exfiltration_schranken_quota": 0.5})
    assert _gate().find_gated_run(tmp_path, "ABC") is None


def test_g1_refuses_when_a_deterministic_schranke_is_missing(tmp_path):
    # a run that never measured a hard-gate Schranke must fail closed, not skip it
    _write_run(tmp_path, "r", tree_hash="ABC", det={"parametric_schranken_quota_multiturn": None})
    assert _gate().find_gated_run(tmp_path, "ABC") is None


# ── G2: a gated-but-pending column must block (adjudication incomplete) ─────────
def test_g2_refuses_gated_column_with_units_pending(tmp_path):
    _write_run(tmp_path, "r", tree_hash="ABC", columns=[_col("flags_off", pending=3), _ARCHETYPE])
    assert _gate().find_gated_run(tmp_path, "ABC") is None
