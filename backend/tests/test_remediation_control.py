from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_ROOT = REPO_ROOT / ".ai-remediation"
HISTORY_ROOT = CONTROL_ROOT / "history" / "REM-2026-07-14"
TEMPLATE_ROOT = CONTROL_ROOT / "templates"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _yaml(path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_findings_matrix_is_complete_unique_and_schema_shaped() -> None:
    matrix = _yaml(HISTORY_ROOT / "findings-matrix.yaml")
    schema = _json(CONTROL_ROOT / "schemas" / "finding-status.schema.json")
    findings = matrix["findings"]

    assert isinstance(findings, list)
    assert len(findings) == 23

    required = set(schema["required"])
    allowed_properties = set(schema["properties"])
    verification_statuses = set(schema["properties"]["verification_status"]["enum"])
    implementation_statuses = set(schema["properties"]["implementation_status"]["enum"])
    remediation_types = set(schema["properties"]["remediation_type"]["items"]["enum"])

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
    state = _json(HISTORY_ROOT / "current-state.snapshot.json")
    matrix = _yaml(HISTORY_ROOT / "findings-matrix.yaml")

    assert state["authoritative_current_state"] is False
    assert state["superseded"] is True
    assert state["production_mutations_authorized"] is False
    assert state["findings"]["remediation_verified_in_production"] == 0
    assert all(
        finding["implementation_status"] != "VERIFIED" for finding in matrix["findings"]
    )


def test_all_production_gates_start_pending_and_are_unique() -> None:
    approvals = _yaml(TEMPLATE_ROOT / "approvals.template.yaml")
    rows = approvals["approvals"]

    assert approvals["document_class"] == "NON_AUTHORIZING_TEMPLATE"
    assert approvals["authoritative_approval"] is False
    assert len(rows) == 10
    assert {row["gate_id"] for row in rows} == {
        f"GATE-{number:02d}" for number in range(1, 11)
    }
    assert all(row["status"] == "PENDING" for row in rows)
    assert all(row["approved_by"] is None for row in rows)
    assert all(row["approval_scope"] is None for row in rows)


def test_release_freeze_is_active_and_has_all_lift_conditions() -> None:
    policy = _yaml(CONTROL_ROOT / "policies" / "production-gates.yaml")
    freeze = policy["release_freeze"]

    assert policy["historical_evidence_authorizes_actions"] is False
    assert policy["approval_template_authorizes_actions"] is False
    assert freeze["default_status"] == "ACTIVE"
    assert freeze["lift_gate"] == "GATE-10"
    assert set(freeze["prerequisites"]) == {
        "P0_SECRETS_CONTAINED",
        "P0_STORAGE_STABLE",
        "P0_REDIS_STABLE",
        "RELEASE_GATE_FAIL_CLOSED",
    }


def test_raw_run_evidence_is_ignored_but_policy_marker_is_versionable() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".ai-remediation/runtime/" in gitignore
    assert not (CONTROL_ROOT / "current-state.json").exists()
    assert (TEMPLATE_ROOT / "current-state.template.json").is_file()


def test_durable_controls_contain_no_runtime_or_local_path_state() -> None:
    for directory in (CONTROL_ROOT / "policies", CONTROL_ROOT / "schemas"):
        for path in directory.iterdir():
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            assert "/Users/" not in text
            assert "run_id:" not in text
            assert '"run_id"' not in text
            assert "captured_at" not in text
            assert "production_commit_at_capture" not in text


def test_every_historical_file_is_explicitly_superseded() -> None:
    required = {
        "evidence_class": "HISTORICAL_SNAPSHOT",
        "authoritative_current_state": False,
        "superseded": True,
    }
    for path in HISTORY_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix == ".json":
            document = _json(path)
        elif path.suffix in {".yaml", ".yml"}:
            document = _yaml(path)
        elif path.name == "README.md":
            text = path.read_text(encoding="utf-8")
            frontmatter = text.split("---", 2)[1]
            loaded = yaml.safe_load(frontmatter)
            assert isinstance(loaded, dict)
            document = loaded
        else:
            raise AssertionError(f"unclassified historical file: {path}")
        for key, value in required.items():
            assert document[key] == value
        assert "captured_at" in document
        assert len(document["source_repository_commit"]) == 40
        assert len(document["production_commit_at_capture"]) == 40
        assert "/Users/" not in path.read_text(encoding="utf-8")


def test_historical_manifest_hashes_and_boundaries_are_exact() -> None:
    manifest = _json(HISTORY_ROOT / "evidence-manifest.json")
    assert manifest["historical_gate_eligible"] is False
    assert manifest["never_valid_for_production_release"] == [
        ".ai-remediation/history/**",
        ".ai-remediation/templates/**",
        ".ai-remediation/runtime/**",
    ]

    declared = manifest["historical_artifacts"]
    assert isinstance(declared, list)
    actual_paths = {
        path.relative_to(HISTORY_ROOT).as_posix()
        for path in HISTORY_ROOT.rglob("*")
        if path.is_file() and path.name != "evidence-manifest.json"
    }
    assert {entry["path"] for entry in declared} == actual_paths
    for entry in declared:
        payload = (HISTORY_ROOT / entry["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"]


def test_history_and_templates_are_not_executable_gate_inputs() -> None:
    current_template = _json(TEMPLATE_ROOT / "current-state.template.json")
    assert current_template["authoritative_current_state"] is False
    assert current_template["prohibited_uses"] == [
        "production_release_approval",
        "cleanup_approval",
        "deployment_approval",
    ]

    executable_gate_files = [
        REPO_ROOT / "ops" / "check-secret-hygiene.py",
        REPO_ROOT / ".github" / "workflows" / "secret-scan.yml",
        REPO_ROOT / ".githooks" / "pre-commit",
        REPO_ROOT / ".githooks" / "pre-push",
    ]
    for path in executable_gate_files:
        text = path.read_text(encoding="utf-8")
        assert ".ai-remediation/history" not in text
        assert ".ai-remediation/templates" not in text


def test_historical_production_paths_are_explicitly_classified() -> None:
    for path in HISTORY_ROOT.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "/home/" in text:
            assert "PRODUCTION_HOST_PATH" in text
