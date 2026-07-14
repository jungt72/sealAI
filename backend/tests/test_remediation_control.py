from __future__ import annotations

import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / ".ai-remediation"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _yaml(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_findings_matrix_is_complete_unique_and_schema_shaped() -> None:
    matrix = _yaml(CONTROL_ROOT / "findings-matrix.yaml")
    schema = _json(CONTROL_ROOT / "schemas" / "finding-status.schema.json")
    findings = matrix["findings"]

    assert isinstance(findings, list)
    assert len(findings) == 23

    required = set(schema["required"])
    allowed_properties = set(schema["properties"])
    verification_statuses = set(
        schema["properties"]["verification_status"]["enum"]
    )
    implementation_statuses = set(
        schema["properties"]["implementation_status"]["enum"]
    )
    remediation_types = set(
        schema["properties"]["remediation_type"]["items"]["enum"]
    )

    finding_ids: list[str] = []
    for finding in findings:
        assert isinstance(finding, dict)
        assert set(finding) == allowed_properties
        assert required <= set(finding)
        assert finding["verification_status"] in verification_statuses
        assert finding["implementation_status"] in implementation_statuses
        assert set(finding["remediation_type"]) <= remediation_types
        finding_ids.append(finding["finding_id"])

    assert len(finding_ids) == len(set(finding_ids))
    assert set(finding_ids) == {
        "SEC-001",
        "SEC-002",
        "OPS-001",
        "OPS-002",
        "REL-001",
        "REL-002",
        "NET-001",
        "AUTH-001",
        "AUTH-002",
        "RAG-001",
        "DATA-001",
        "APP-001",
        "AUTH-003",
        "GOV-001",
        "DR-001",
        "OBS-001",
        "REL-003",
        "LOG-001",
        "CONT-001",
        "NET-002",
        "AUTH-004",
        "API-001",
        "TLS-001",
    }


def test_local_changes_do_not_claim_production_verification() -> None:
    state = _json(CONTROL_ROOT / "current-state.json")
    matrix = _yaml(CONTROL_ROOT / "findings-matrix.yaml")

    assert state["production_mutations_authorized"] is False
    assert state["findings"]["remediation_verified_in_production"] == 0
    assert all(
        finding["implementation_status"] != "VERIFIED"
        for finding in matrix["findings"]
    )


def test_all_production_gates_start_pending_and_are_unique() -> None:
    approvals = _yaml(CONTROL_ROOT / "approvals.yaml")
    rows = approvals["approvals"]

    assert len(rows) == 10
    assert {row["gate_id"] for row in rows} == {
        f"GATE-{number:02d}" for number in range(1, 11)
    }
    assert all(row["status"] == "PENDING" for row in rows)
    assert all(row["approved_by"] is None for row in rows)
    assert all(row["approval_scope"] is None for row in rows)


def test_release_freeze_is_active_and_has_all_lift_conditions() -> None:
    state = _json(CONTROL_ROOT / "current-state.json")
    freeze = state["release_freeze"]

    assert freeze["status"] == "ACTIVE"
    assert freeze["lift_gate"] == "GATE-10"
    assert set(freeze["required_conditions"]) == {
        "P0_SECRETS_CONTAINED",
        "P0_STORAGE_STABLE",
        "P0_REDIS_STABLE",
        "RELEASE_GATE_FAIL_CLOSED",
    }
    assert freeze["satisfied_conditions"] == []


def test_raw_run_evidence_is_ignored_but_policy_marker_is_versionable() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".ai-remediation/runs/*/evidence/*" in gitignore
    assert "!.ai-remediation/runs/*/evidence/README.md" in gitignore
