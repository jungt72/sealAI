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
