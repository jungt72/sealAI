"""Static proof that MAT-EVID-01C is isolated, immutable and non-authoritative."""

from __future__ import annotations

import ast
from pathlib import Path

from _model_schema_ast import load_material_schema


REPO = Path(__file__).resolve().parents[3]
MODELS = REPO / "backend/sealai_v2/db/models.py"
EXPECTED = {
    "v2_material_evidence_review_dossiers": frozenset(
        {
            "review_id",
            "tenant_id",
            "evidence_snapshot_id",
            "creator_subject",
            "creator_identity_kind",
            "created_at",
        }
    ),
    "v2_material_evidence_review_snapshots": frozenset(
        {
            "review_snapshot_id",
            "review_id",
            "evidence_snapshot_id",
            "evidence_content_sha256",
            "evidence_manifest_schema_version",
            "evidence_contract_version",
            "review_schema_version",
            "canonicalization_version",
            "mat_evid_review_contract_version",
            "content_sha256",
            "canonical_payload_json",
            "canonical_bytes",
            "runtime_authority",
            "positive_statement_allowed",
            "created_by_subject",
            "created_at",
        }
    ),
    "v2_material_evidence_review_validation_events": frozenset(
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
    "v2_material_evidence_review_lifecycle_events": frozenset(
        {
            "event_id",
            "review_snapshot_id",
            "sequence_no",
            "event_type",
            "review_state",
            "approval_state",
            "actor_tenant_id",
            "actor_subject",
            "actor_role",
            "actor_identity_kind",
            "previous_event_sha256",
            "event_sha256",
            "created_at",
        }
    ),
    "v2_material_evidence_review_audit_events": frozenset(
        {
            "event_id",
            "review_snapshot_id",
            "event_type",
            "actor_tenant_id",
            "actor_subject",
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


def test_01c_schema_is_exact_and_has_no_deployment_or_pointer() -> None:
    schema = load_material_schema(MODELS)
    assert {name: schema[name] for name in EXPECTED} == EXPECTED
    assert {
        name for name in schema if name.startswith("v2_material_evidence_review_")
    } == set(EXPECTED)
    assert not any(
        token in name
        for name in EXPECTED
        for token in ("pointer", "deployment", "cohort", "active")
    )


def test_primary_runtime_does_not_import_01c_review_contract() -> None:
    for relative in (
        "backend/sealai_v2/api/deps.py",
        "backend/sealai_v2/api/main.py",
        "backend/sealai_v2/api/serializers.py",
        "backend/sealai_v2/pipeline/pipeline.py",
        "backend/sealai_v2/pipeline/stages.py",
        "backend/sealai_v2/core/material_constraints.py",
        "backend/sealai_v2/knowledge/matrix.py",
        "backend/sealai_v2/orchestration/answer_cache.py",
    ):
        imports = _imports(REPO / relative)
        assert not any("material_evidence_review" in name for name in imports)


def test_01c_migration_is_additive_empty_and_contains_no_runtime_operations() -> None:
    path = (
        REPO
        / "backend/sealai_v2/db/migrations/versions/20260718_0016_mat_evid_01c_review.py"
    )
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"bulk_insert", "execute_many"}
    lowered = source.lower()
    for token in (
        "active_pointer",
        "deployment_state",
        "seed_data",
        "runtime_binding_created",
    ):
        assert token not in lowered


def test_01c_has_no_api_or_frontend_surface() -> None:
    api = REPO / "backend/sealai_v2/api"
    frontend = REPO / "frontend-v2/src"
    for root in (api, frontend):
        for path in root.rglob("*"):
            if path.is_file():
                assert "material_evidence_review" not in path.read_text(
                    encoding="utf-8", errors="ignore"
                )
