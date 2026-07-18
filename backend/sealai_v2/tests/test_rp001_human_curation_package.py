from __future__ import annotations

import json
from pathlib import Path

from sealai_v2.core.material_rule_coverage import (
    coverage_content_sha256,
    parse_coverage_report,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_DIR = (
    REPO_ROOT
    / "docs"
    / "ops"
    / "material-evidence-curation"
    / "RP-001_ELASTOMER_MEDIA_EXCLUSIONS_V1"
)
COVERAGE_PATH = REPO_ROOT / "docs" / "ssot" / "material-rule-coverage-v1.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_package_is_explicitly_non_authoritative_and_non_importable() -> None:
    manifest = _json(PACKAGE_DIR / "package-manifest.json")

    assert manifest["package_id"] == "RP-001_ELASTOMER_MEDIA_EXCLUSIONS_V1"
    assert manifest["package_state"] == "human_curation_only"
    assert manifest["authority"] == "NONE_WORKSHEET_ONLY"
    assert manifest["import_eligible"] is False
    assert manifest["positive_statement_allowed"] is False
    assert manifest["ratified_owner_decisions"] == [
        {
            "decision_id": "RP001-OD-01",
            "state": "ratified_import_blocked_pending_v2",
            "decision": "no_material_placeholder_typed_evidence_scope_v2",
            "required_scope": (
                "media_identity without materials and with exactly one media_ref"
            ),
        }
    ]
    assert manifest["open_owner_decisions"] == []
    assert {
        "claim",
        "material_fact",
        "canonical_media_classification",
        "material_rule",
        "factual_approval",
        "active_pointer",
        "public_statement",
        "deployment",
    } == set(manifest["forbidden_outputs"])


def test_candidate_register_is_an_exact_gap_projection_without_pairing() -> None:
    coverage = parse_coverage_report(COVERAGE_PATH.read_bytes())
    register = _json(PACKAGE_DIR / "candidate-register.json")
    candidates = (
        register["material_axis_candidates"] + register["service_media_axis_candidates"]
    )

    expected = {
        gap.subject_id: (gap.kind.value, gap.label, gap.status.value)
        for gap in coverage.gaps
    }
    actual = {
        item["subject_id"]: (
            "material_family"
            if item["subject_id"].startswith("material:")
            else "service_group",
            item["label"],
            item["coverage_status"],
        )
        for item in candidates
    }

    assert len(candidates) == 53
    assert len(register["material_axis_candidates"]) == 20
    assert len(register["service_media_axis_candidates"]) == 33
    assert actual == expected
    assert all(item["triage_state"] == "unassessed" for item in candidates)
    assert register["proposed_rule_pairs"] == []
    assert register["automatic_pairing_allowed"] is False
    assert register["automatic_matrix_import_allowed"] is False
    assert register["positive_statement_allowed"] is False
    assert register["source_coverage_sha256"] == coverage_content_sha256(coverage)


def test_package_contains_no_claim_rule_or_simulated_subject_record() -> None:
    manifest = _json(PACKAGE_DIR / "package-manifest.json")
    register = _json(PACKAGE_DIR / "candidate-register.json")
    serialized = json.dumps(
        {"manifest": manifest, "register": register},
        ensure_ascii=False,
        sort_keys=True,
    )

    assert "claim_text" not in serialized
    assert "rule_ref" not in serialized
    assert "review_snapshot_id" not in serialized
    assert "creator_subject" not in serialized
    assert "reviewer_subject" not in serialized
    assert "approver_subject" not in serialized


def test_manifest_lists_every_human_work_artifact() -> None:
    manifest = _json(PACKAGE_DIR / "package-manifest.json")
    actual = {
        path.name
        for path in PACKAGE_DIR.iterdir()
        if path.name != "package-manifest.json"
    }

    assert set(manifest["artifacts"]) == actual
    assert {
        "creator-worklist.md",
        "reviewer-worklist.md",
        "owner-approver-worklist.md",
    } <= actual


def test_role_worklists_keep_verified_humans_separate() -> None:
    creator = (PACKAGE_DIR / "creator-worklist.md").read_text(encoding="utf-8")
    reviewer = (PACKAGE_DIR / "reviewer-worklist.md").read_text(encoding="utf-8")
    approver = (PACKAGE_DIR / "owner-approver-worklist.md").read_text(encoding="utf-8")

    assert "material_evidence:create" in creator
    assert "material_evidence:review" in reviewer
    assert "material_evidence:approve" in approver
    assert "different authenticated subject" in reviewer
    assert "third authenticated subject" in approver
    assert "positive compatibility statement" in creator
    assert "No shared account, service principal, agent, model" in approver
