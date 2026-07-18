"""Static proof that the AI review track is closed, inert and non-human."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from _model_schema_ast import load_material_schema


REPO = Path(__file__).resolve().parents[3]
MODELS = REPO / "backend/sealai_v2/db/models.py"
MIGRATION = REPO / (
    "backend/sealai_v2/db/migrations/versions/" "20260718_0019_mat_evid_ai_review.py"
)
RUNNER = REPO / "backend/sealai_v2/material_evidence_ai_review/runner.py"
EXECUTABLE_TRUST = REPO / (
    "backend/sealai_v2/material_evidence_ai_review/" "claude-executable-trust-v1.json"
)
EXPECTED = {
    "v2_material_evidence_ai_review_batches": frozenset(
        {
            "batch_id",
            "tenant_id",
            "environment",
            "domain_pack_id",
            "ruleset_snapshot_id",
            "evidence_snapshot_id",
            "creator_identity_kind",
            "creator_provider",
            "creator_model",
            "creator_version",
            "creator_run_id",
            "created_at",
        }
    ),
    "v2_material_evidence_ai_review_snapshots": frozenset(
        {
            "review_snapshot_id",
            "batch_id",
            "ruleset_snapshot_id",
            "ruleset_content_sha256",
            "evidence_snapshot_id",
            "evidence_content_sha256",
            "ai_review_schema_version",
            "canonicalization_version",
            "ai_review_contract_version",
            "content_sha256",
            "canonical_payload_json",
            "canonical_bytes",
            "authority",
            "positive_statement_allowed",
            "creator_input_sha256",
            "creator_output_sha256",
            "created_at",
        }
    ),
    "v2_material_evidence_ai_challenges": frozenset(
        {
            "challenge_id",
            "review_snapshot_id",
            "challenger_identity_kind",
            "challenger_provider",
            "challenger_model",
            "challenger_version",
            "challenger_run_id",
            "challenger_prompt_version",
            "challenger_prompt_sha256",
            "audit_input_sha256",
            "audit_input_file_sha256",
            "canonical_audit_input_json",
            "audit_output_sha256",
            "cli_result_file_sha256",
            "canonical_cli_receipt_json",
            "claude_executable_sha256",
            "canonical_executable_attestation_json",
            "claude_executable_attestation_sha256",
            "report_sha256",
            "process_returncode",
            "session_id_sha256",
            "runner_receipt_sha256",
            "tools_enabled",
            "mcp_enabled",
            "hooks_enabled",
            "session_persistence_enabled",
            "web_search_requests",
            "web_fetch_requests",
            "canonical_report_json",
            "created_at",
        }
    ),
    "v2_material_evidence_ai_adjudications": frozenset(
        {
            "adjudication_id",
            "review_snapshot_id",
            "challenge_id",
            "adjudicator_identity_kind",
            "adjudicator_provider",
            "adjudicator_model",
            "adjudicator_version",
            "adjudicator_run_id",
            "input_sha256",
            "output_sha256",
            "outcome",
            "replacement_ruleset_snapshot_id",
            "replacement_evidence_snapshot_id",
            "canonical_adjudication_json",
            "created_at",
        }
    ),
    "v2_material_evidence_ai_validation_events": frozenset(
        {
            "event_id",
            "review_snapshot_id",
            "validator_contract_version",
            "validation_state",
            "error_code",
            "validation_sha256",
            "created_at",
        }
    ),
    "v2_material_evidence_ai_lifecycle_events": frozenset(
        {
            "event_id",
            "review_snapshot_id",
            "sequence_no",
            "event_type",
            "state",
            "actor_identity_kind",
            "actor_provider",
            "actor_run_id",
            "artifact_ref",
            "previous_event_sha256",
            "event_sha256",
            "created_at",
        }
    ),
    "v2_material_evidence_ai_audit_events": frozenset(
        {
            "event_id",
            "review_snapshot_id",
            "event_type",
            "actor_identity_kind",
            "actor_provider",
            "actor_run_id",
            "event_payload_json",
            "event_sha256",
            "created_at",
        }
    ),
}


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_ai_review_schema_is_exact_and_has_no_human_subject_columns() -> None:
    schema = load_material_schema(MODELS)
    assert {name: schema[name] for name in EXPECTED} == EXPECTED
    assert {
        name for name in schema if name.startswith("v2_material_evidence_ai_")
    } == set(EXPECTED)
    columns = {column for values in EXPECTED.values() for column in values}
    assert (
        not {
            "creator_subject",
            "reviewer_subject",
            "approver_subject",
            "approval_state",
            "review_state",
        }
        & columns
    )


def test_ai_review_migration_is_additive_empty_and_inert() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"bulk_insert", "execute_many"}
    lowered = source.lower()
    for token in (
        "active_pointer",
        "sampling_basis_points",
        "public_payload",
        "seed_data",
        "backfill",
        "verified_human",
        "application_validated",
    ):
        assert token not in lowered


def test_runtime_api_settings_and_frontend_do_not_import_ai_review() -> None:
    for relative in (
        "backend/sealai_v2/api/deps.py",
        "backend/sealai_v2/api/main.py",
        "backend/sealai_v2/api/serializers.py",
        "backend/sealai_v2/config/settings.py",
        "backend/sealai_v2/pipeline/pipeline.py",
        "backend/sealai_v2/pipeline/stages.py",
        "backend/sealai_v2/core/material_constraints.py",
        "backend/sealai_v2/knowledge/matrix.py",
        "backend/sealai_v2/orchestration/answer_cache.py",
    ):
        assert not any(
            "material_evidence_ai_review" in name for name in _imports(REPO / relative)
        )
    for root in (REPO / "backend/sealai_v2/api", REPO / "frontend-v2/src"):
        for path in root.rglob("*"):
            if path.is_file():
                source = path.read_text(encoding="utf-8", errors="ignore")
                assert "AI_CROSS_REVIEW_NON_AUTHORITATIVE" not in source
                assert "ai_cross_reviewed_non_authoritative" not in source


def test_human_review_contracts_do_not_import_ai_review() -> None:
    for relative in (
        "backend/sealai_v2/core/material_evidence_review.py",
        "backend/sealai_v2/core/material_evidence_review_v2.py",
        "backend/sealai_v2/db/material_evidence_review.py",
        "backend/sealai_v2/db/material_evidence_review_v2.py",
    ):
        assert not any(
            "material_evidence_ai_review" in name for name in _imports(REPO / relative)
        )


def test_claude_executable_is_owner_pinned_and_never_resolved_from_path() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "shutil.which" not in source
    assert 'allowed = {\n        "HOME",\n        "LANG"' in source
    manifest = json.loads(EXECUTABLE_TRUST.read_text(encoding="utf-8"))
    assert set(manifest) == {"contract_version", "installations", "schema_version"}
    assert manifest["contract_version"] == ("MAT-EVID-AI-CLAUDE-EXECUTABLE-TRUST.v1")
    assert manifest["schema_version"] == 1
    assert len(manifest["installations"]) == 1
    installation = manifest["installations"][0]
    assert set(installation) == {
        "entrypoint",
        "executable_sha256",
        "machine",
        "platform",
        "resolved_path",
        "version",
    }
    assert Path(installation["entrypoint"]).is_absolute()
    assert Path(installation["resolved_path"]).is_absolute()
    assert len(installation["executable_sha256"]) == 64
    manifest_sha256 = hashlib.sha256(EXECUTABLE_TRUST.read_bytes()).hexdigest()
    assert f'"{manifest_sha256}"' in source
