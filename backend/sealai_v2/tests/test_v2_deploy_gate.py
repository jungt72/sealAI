from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


_MODULE_PATH = Path(__file__).resolve().parents[3] / "ops" / "v2_deploy_gate.py"
_SPEC = importlib.util.spec_from_file_location("v2_deploy_gate", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)


TOPICS = ["A", "B"]
L1 = "openai/gpt-test"
PROFILE = "profile-target"
TREE = "tree-target"


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _manifest(*, tree: str, profile: str, label: str) -> dict:
    return {
        "run_label": label,
        "tree_hash": tree,
        "runtime_profile_hash": profile,
        "roles": {"l1": {"provider": "openai", "model": "gpt-test"}},
    }


def _fixture(tmp_path: Path) -> Path:
    runs = tmp_path / "runs"
    baseline_path = runs / "baseline" / "results.json"
    baseline = {
        "manifest": {
            **_manifest(tree="tree-base", profile="profile-base", label="baseline"),
            "n_cases": 25,
            "auxiliary_suites_included": True,
        },
        "multiturn": {
            "summary": {
                "memory_schranken_quota": 1.0,
                "parametric_schranken_quota": 1.0,
            }
        },
        "injection": {"exfiltration": {"schranken_quota": 1.0}},
        "parametric": {"schranken_quota": 1.0},
    }
    _write(baseline_path, baseline)
    baseline_sha = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    _write(
        tmp_path / "remediation" / "m15_failed_topics_v1.json",
        {
            "schema_version": 1,
            "failed_topics": TOPICS,
            "baseline": {
                "run_label": "baseline",
                "tree_hash": "tree-base",
                "runtime_profile_hash": "profile-base",
                "results_sha256": baseline_sha,
            },
            "policy": {
                "paid_replay": "failed_topics_only",
                "full_replay_claimed": False,
                "required_target_adjudication": True,
            },
        },
    )
    _write(
        runs / "target" / "results.json",
        {
            "manifest": {
                **_manifest(tree=TREE, profile=PROFILE, label="target"),
                "evaluation_scope": "targeted_cases",
                "requested_case_ids": TOPICS,
                "evaluated_case_ids": TOPICS,
                "errors": [],
            },
            "parametric": {"schranken_quota": 1.0},
            "adjudication": {
                "columns": {
                    "flags_on": {
                        "column": "flags_on",
                        "n_gate_cases": 2,
                        "n_gates_pending": 0,
                        "n_units_human_relevant": 2,
                        "n_units_pending": 0,
                        "schranken_quota_final": 1.0,
                    }
                }
            },
        },
    )
    return runs


def test_targeted_remediation_is_bound_to_baseline_scope_and_target_runtime(tmp_path):
    runs = _fixture(tmp_path)

    match = gate.find_gated_remediation(runs, TREE, L1, PROFILE)

    assert match is not None
    assert match["evidence_type"] == "targeted_remediation"
    assert match["baseline_run_label"] == "baseline"
    assert match["remediated_case_ids"] == TOPICS
    assert match["full_replay_claimed"] is False


def test_targeted_remediation_refuses_incomplete_case_scope(tmp_path):
    runs = _fixture(tmp_path)
    target = runs / "target" / "results.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["manifest"]["evaluated_case_ids"] = ["A"]
    _write(target, data)

    assert gate.find_gated_remediation(runs, TREE, L1, PROFILE) is None


def test_targeted_remediation_refuses_pending_human_adjudication(tmp_path):
    runs = _fixture(tmp_path)
    target = runs / "target" / "results.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["adjudication"]["columns"]["flags_on"]["n_units_pending"] = 1
    _write(target, data)

    assert gate.find_gated_remediation(runs, TREE, L1, PROFILE) is None


def test_targeted_remediation_refuses_modified_baseline(tmp_path):
    runs = _fixture(tmp_path)
    baseline = runs / "baseline" / "results.json"
    baseline.write_text(baseline.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    assert gate.find_gated_remediation(runs, TREE, L1, PROFILE) is None


CHAIN_ROOT_TOPICS = ["A", "B", "C"]
CHAIN_FAILED_TOPICS = ["B", "C"]
CHAIN_CARRIED_CELLS = ["A/flags_on"]
CHAIN_TARGET_CELLS = ["B/flags_off", "B/flags_on", "C/auxiliary"]


def _record(cell: str, *, gate_relevant: bool = True) -> dict:
    case_id, column = cell.rsplit("/", 1)
    return {
        "case_id": case_id,
        "column": column,
        "error": None,
        "judge_error": None,
        "judge": {"parse_ok": True},
        "score": {"gate_relevant": gate_relevant},
    }


def _final_case(cell: str, *, gate_relevant: bool = True) -> dict:
    case_id, column = cell.rsplit("/", 1)
    return {
        "case_id": case_id,
        "column": column,
        "human_pending": False,
        "axis1_final": "pass",
        "gate_pending": False,
        "final_gate_clean": True if gate_relevant else None,
    }


def _chain_fixture(tmp_path: Path) -> Path:
    runs = tmp_path / "runs"
    remediation = tmp_path / "remediation"
    baseline_path = runs / "baseline" / "results.json"
    baseline = {
        "manifest": {
            **_manifest(tree="tree-base", profile="profile-base", label="baseline"),
            "n_cases": 25,
            "auxiliary_suites_included": True,
        },
        "multiturn": {
            "summary": {
                "memory_schranken_quota": 1.0,
                "parametric_schranken_quota": 1.0,
            }
        },
        "injection": {"exfiltration": {"schranken_quota": 1.0}},
        "parametric": {"schranken_quota": 1.0},
    }
    _write(baseline_path, baseline)
    baseline_sha = hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    _write(
        remediation / "m15_failed_topics_v1.json",
        {
            "schema_version": 1,
            "failed_topics": CHAIN_ROOT_TOPICS,
            "baseline": {
                "run_label": "baseline",
                "tree_hash": "tree-base",
                "runtime_profile_hash": "profile-base",
                "results_sha256": baseline_sha,
            },
            "policy": {
                "paid_replay": "failed_topics_only",
                "full_replay_claimed": False,
                "required_target_adjudication": True,
            },
        },
    )

    parent_cells = CHAIN_CARRIED_CELLS + CHAIN_TARGET_CELLS
    parent = {
        "manifest": {
            **_manifest(tree="tree-parent", profile="profile-parent", label="parent"),
            "evaluation_scope": "targeted_cases",
            "requested_case_ids": CHAIN_ROOT_TOPICS,
            "evaluated_case_ids": CHAIN_ROOT_TOPICS,
            "errors": [],
        },
        "records": [_record(cell) for cell in parent_cells],
        "parametric": {"schranken_quota": 1.0},
        "adjudication": {
            "final_cases": [_final_case(cell) for cell in parent_cells],
        },
    }
    _write(runs / "parent" / "results.json", parent)

    target = {
        "manifest": {
            **_manifest(tree=TREE, profile=PROFILE, label="chain-target"),
            "evaluation_scope": "targeted_cases",
            "requested_case_ids": CHAIN_FAILED_TOPICS,
            "evaluated_case_ids": CHAIN_FAILED_TOPICS,
            "errors": [],
        },
        "records": [_record(cell) for cell in CHAIN_TARGET_CELLS],
        "parametric": {"schranken_quota": 1.0},
        "adjudication": {
            "final_cases": [_final_case(cell) for cell in CHAIN_TARGET_CELLS],
            "columns": {
                "flags_off": {
                    "column": "flags_off",
                    "n_gate_cases": 1,
                    "n_gates_pending": 0,
                    "n_units_human_relevant": 1,
                    "n_units_pending": 0,
                    "schranken_quota_final": 1.0,
                },
                "flags_on": {
                    "column": "flags_on",
                    "n_gate_cases": 1,
                    "n_gates_pending": 0,
                    "n_units_human_relevant": 1,
                    "n_units_pending": 0,
                    "schranken_quota_final": 1.0,
                },
                "auxiliary": {
                    "column": "auxiliary",
                    "n_gate_cases": 1,
                    "n_gates_pending": 0,
                    "n_units_human_relevant": 1,
                    "n_units_pending": 0,
                    "schranken_quota_final": 1.0,
                },
            },
        },
    }
    _write(runs / "chain-target" / "results.json", target)

    _write(
        remediation / "m15_failed_topics_v2.json",
        {
            "schema_version": 2,
            "root_scope": "m15_failed_topics_v1.json",
            "parent_run": {
                "run_label": "parent",
                "tree_hash": "tree-parent",
                "runtime_profile_hash": "profile-parent",
                "evaluation_payload_sha256": gate._evaluation_payload_sha256(parent),
            },
            "carried_cells": CHAIN_CARRIED_CELLS,
            "failed_topics": CHAIN_FAILED_TOPICS,
            "target_cells": CHAIN_TARGET_CELLS,
            "target": {
                "tree_hash": TREE,
                "runtime_profile_hash": PROFILE,
            },
            "policy": {
                "paid_replay": "remaining_failed_topics_only",
                "carry_forward_requires_human_adjudication": True,
                "target_requires_human_adjudication": True,
                "full_replay_claimed": False,
            },
        },
    )
    return runs


def test_chained_remediation_reruns_only_remaining_failed_topics(tmp_path):
    runs = _chain_fixture(tmp_path)

    match = gate.find_gated_chained_remediation(runs, TREE, L1, PROFILE)

    assert match is not None
    assert match["evidence_type"] == "targeted_remediation_chain"
    assert match["carried_cells"] == CHAIN_CARRIED_CELLS
    assert match["remediated_case_ids"] == CHAIN_FAILED_TOPICS
    assert match["full_replay_claimed"] is False


def test_chained_remediation_refuses_pending_carried_cell(tmp_path):
    runs = _chain_fixture(tmp_path)
    parent_path = runs / "parent" / "results.json"
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    parent["adjudication"]["final_cases"][0]["human_pending"] = True
    _write(parent_path, parent)

    assert gate.find_gated_chained_remediation(runs, TREE, L1, PROFILE) is None


def test_chained_remediation_refuses_mutated_parent_payload(tmp_path):
    runs = _chain_fixture(tmp_path)
    parent_path = runs / "parent" / "results.json"
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    parent["records"][0]["answer"] = "mutated after scope approval"
    _write(parent_path, parent)

    assert gate.find_gated_chained_remediation(runs, TREE, L1, PROFILE) is None


def test_chained_remediation_refuses_extra_target_cell(tmp_path):
    runs = _chain_fixture(tmp_path)
    target_path = runs / "chain-target" / "results.json"
    target = json.loads(target_path.read_text(encoding="utf-8"))
    target["records"].append(_record("EXTRA/flags_on"))
    _write(target_path, target)

    assert gate.find_gated_chained_remediation(runs, TREE, L1, PROFILE) is None


def test_chained_remediation_refuses_target_tree_mismatch(tmp_path):
    runs = _chain_fixture(tmp_path)

    assert (
        gate.find_gated_chained_remediation(runs, "different-tree", L1, PROFILE) is None
    )
