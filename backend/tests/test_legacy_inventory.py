"""Deterministic tests for the non-mutating legacy inventory classifier."""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import sys

import pytest


REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "backend" / "tests" / "fixtures" / "legacy_inventory_synthetic.json"


def _module():
    name = "legacy_inventory_test"
    spec = importlib.util.spec_from_file_location(
        name, REPO / "ops" / "legacy_inventory.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_covers_every_asset_type_and_every_permitted_classification():
    module = _module()
    report = module.classify_inventory(
        _fixture(), REPO, generated_at="2026-07-15T00:00:00Z"
    )
    by_id = {item["id"]: item for item in report["objects"]}

    assert set(report["coverage"]) == set(module.ASSET_TYPES)
    assert by_id["service:api"]["classification"] == "ACTIVE"
    assert by_id["image:legacy-backend"]["classification"] == "LEGACY_BUT_IN_USE"
    assert by_id["backup:rollback-v1"]["classification"] == "REQUIRED_FOR_ROLLBACK"
    assert by_id["prompt_family:unused-v0"]["classification"] == "ORPHANED"
    assert by_id["frontend:v1"]["classification"] == "SAFE_TO_ARCHIVE"
    assert (
        by_id["feature_flag:dead-chat"]["classification"]
        == "SAFE_TO_DELETE_AFTER_APPROVAL"
    )
    assert by_id["qdrant_collection:unknown-old"]["classification"] == "UNKNOWN"
    assert set(item["classification"] for item in report["objects"]) == set(
        module.CLASSIFICATIONS
    )


def test_delete_classification_never_authorizes_or_performs_cleanup():
    module = _module()
    report = module.classify_inventory(
        _fixture(), REPO, generated_at="2026-07-15T00:00:00Z"
    )
    item = next(
        value for value in report["objects"] if value["id"] == "feature_flag:dead-chat"
    )
    assert item["classification"] == "SAFE_TO_DELETE_AFTER_APPROVAL"
    assert item["gate"]["approval_ready"] is False
    assert item["gate"]["cleanup_ready"] is False
    assert item["mutation_authorized"] is False
    assert item["action_taken"] is False
    assert report["production_query_performed"] is False
    assert report["mutation_performed"] is False


def test_dependency_edges_and_output_are_deterministic():
    module = _module()
    first = module.classify_inventory(
        _fixture(), REPO, generated_at="2026-07-15T00:00:00Z"
    )
    second = module.classify_inventory(
        _fixture(), REPO, generated_at="2026-07-15T00:00:00Z"
    )
    assert module._canonical_json(first) == module._canonical_json(second)
    assert {(edge["from"], edge["to"]) for edge in first["dependencies"]} == {
        ("service:api", "image:legacy-backend"),
        ("network_workload:metrics", "configuration:legacy-metrics"),
    }


def test_missing_dependency_duplicate_id_and_age_only_evidence_fail_closed():
    module = _module()
    missing = _fixture()
    missing["objects"][0]["dependencies"] = ["service:not-present"]
    with pytest.raises(module.InventoryError, match="missing dependency"):
        module.classify_inventory(missing, REPO)

    duplicate = _fixture()
    duplicate["objects"][1]["id"] = duplicate["objects"][0]["id"]
    with pytest.raises(module.InventoryError, match="not unique"):
        module.classify_inventory(duplicate, REPO)

    age_only = _fixture()
    age_only["objects"][0]["age_days"] = 9999
    with pytest.raises(module.InventoryError, match="schema validation"):
        module.classify_inventory(age_only, REPO)


def test_incomplete_or_unknown_evidence_cannot_become_cleanup_safe():
    module = _module()
    value = _fixture()
    target = next(item for item in value["objects"] if item["id"] == "frontend:v1")
    target["evidence_state"] = "INCOMPLETE"
    report = module.classify_inventory(value, REPO, generated_at="2026-07-15T00:00:00Z")
    classified = next(item for item in report["objects"] if item["id"] == "frontend:v1")
    assert classified["classification"] == "UNKNOWN"
    assert classified["mutation_authorized"] is False


def test_secret_canary_and_symlink_input_are_rejected(tmp_path):
    module = _module()
    canary = ("sk-" + "proj-" + "Z" * 24).encode("ascii")
    with pytest.raises(module.InventoryError, match="secret canary"):
        module._assert_no_secret(canary, label="synthetic input")

    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(module.InventoryError, match="symlink"):
        module._read_regular(link, limit=1024, label="inventory input")

    repo = tmp_path / "repo"
    repo.mkdir()
    outside_dir = tmp_path / "outside-dir"
    outside_dir.mkdir()
    (outside_dir / "input.json").write_text("{}", encoding="utf-8")
    (repo / "linked-dir").symlink_to(outside_dir, target_is_directory=True)
    with pytest.raises(module.InventoryError, match="symlink|unavailable"):
        module._read_regular(
            repo / "linked-dir" / "input.json",
            limit=1024,
            label="parent swap probe",
        )
    with pytest.raises(module.InventoryError, match="symlink|unavailable"):
        module._atomic_write(repo / "linked-dir" / "report.json", b"{}\n")
    assert not (outside_dir / "report.json").exists()


def test_report_semantics_are_recomputed_and_tampering_fails_closed():
    module = _module()
    report = module.classify_inventory(
        _fixture(), REPO, generated_at="2026-07-15T00:00:00Z"
    )

    bad_summary = json.loads(json.dumps(report))
    bad_summary["summary"]["ACTIVE"] += 1
    with pytest.raises(module.InventoryError, match="summary"):
        module.validate_report(bad_summary, REPO)

    bad_reverse_edge = json.loads(json.dumps(report))
    target = next(
        item
        for item in bad_reverse_edge["objects"]
        if item["id"] == "image:legacy-backend"
    )
    target["dependents"] = []
    with pytest.raises(module.InventoryError, match="reverse dependencies"):
        module.validate_report(bad_reverse_edge, REPO)

    bad_gate = json.loads(json.dumps(report))
    target = next(item for item in bad_gate["objects"] if item["id"] == "frontend:v1")
    target["gate"]["cleanup_ready"] = False
    with pytest.raises(module.InventoryError, match="gate booleans"):
        module.validate_report(bad_gate, REPO)

    bad_reason = json.loads(json.dumps(report))
    bad_reason["objects"][0]["reason"] = "A different classification rationale."
    with pytest.raises(module.InventoryError, match="reason"):
        module.validate_report(bad_reason, REPO)

    bad_coverage = json.loads(json.dumps(report))
    next(item for item in bad_coverage["objects"] if item["asset_type"] == "port")[
        "asset_type"
    ] = "service"
    with pytest.raises(module.InventoryError, match="declared coverage"):
        module.validate_report(bad_coverage, REPO)


def test_classifier_has_no_infrastructure_query_or_mutation_runtime():
    source = (REPO / "ops" / "legacy_inventory.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert imported.isdisjoint(
        {"subprocess", "socket", "requests", "docker", "paramiko"}
    )
    assert "delete" not in {
        node.name.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    assert "archive" not in {
        node.name.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }


def test_required_coverage_cannot_be_silently_omitted():
    module = _module()
    value = _fixture()
    value["objects"] = [
        item for item in value["objects"] if item["asset_type"] != "port"
    ]
    with pytest.raises(module.InventoryError, match="schema validation|cover"):
        module.classify_inventory(value, REPO)
