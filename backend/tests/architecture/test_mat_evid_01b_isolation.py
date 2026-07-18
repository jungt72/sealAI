"""Static proof that MAT-EVID-01B stays pointerless, in shadow, and default-off."""

from __future__ import annotations

import ast
from pathlib import Path

from _model_schema_ast import load_material_schema


REPO = Path(__file__).resolve().parents[3]
MODELS = REPO / "backend/sealai_v2/db/models.py"
EXPECTED = {
    "v2_material_evidence_runtime_bindings": frozenset(
        {
            "binding_id",
            "binding_schema_version",
            "binding_contract_version",
            "binding_state",
            "ruleset_snapshot_id",
            "ruleset_content_sha256",
            "evidence_snapshot_id",
            "evidence_content_sha256",
            "evidence_manifest_schema_version",
            "evidence_canonicalization_version",
            "evidence_contract_version",
            "domain_pack_id",
            "domain_pack_version",
            "evaluator_version",
            "kernel_version",
            "authority",
            "positive_statement_allowed",
            "created_at",
        }
    ),
    "v2_material_evidence_runtime_pins": frozenset(
        {
            "pin_id",
            "pin_schema_version",
            "binding_id",
            "binding_state",
            "ruleset_snapshot_id",
            "ruleset_content_sha256",
            "evidence_snapshot_id",
            "evidence_content_sha256",
            "authority",
            "positive_statement_allowed",
            "created_at",
        }
    ),
    "v2_material_evidence_runtime_evaluations": frozenset(
        {
            "evaluation_id",
            "pin_id",
            "binding_state",
            "ruleset_snapshot_id",
            "ruleset_content_sha256",
            "evidence_snapshot_id",
            "evidence_content_sha256",
            "result_sha256",
            "stable_error_code",
            "authority",
            "positive_statement_allowed",
            "created_at",
        }
    ),
    "v2_material_evidence_runtime_evaluation_refs": frozenset(
        {"ref_id", "evaluation_id", "rule_ref", "claim_ref", "source_ref"}
    ),
    "v2_material_evidence_runtime_audit_events": frozenset(
        {
            "event_id",
            "binding_id",
            "pin_id",
            "evaluation_id",
            "event_type",
            "actor_subject",
            "event_payload_json",
            "event_sha256",
            "created_at",
        }
    ),
}
EXPECTED_V2 = {f"{name}_v2": columns for name, columns in EXPECTED.items()}
EVIDENCE_TABLES = frozenset(
    {
        "v2_material_evidence_manifests",
        "v2_material_evidence_snapshots",
        "v2_material_evidence_audit_events",
        "v2_material_evidence_validation_events",
        *EXPECTED,
        "v2_material_evidence_manifests_v2",
        "v2_material_evidence_snapshots_v2",
        "v2_material_evidence_audit_events_v2",
        "v2_material_evidence_validation_events_v2",
        *EXPECTED_V2,
    }
)


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_runtime_evidence_schema_is_exact_and_has_no_activation_lifecycle() -> None:
    schema = load_material_schema(MODELS)
    assert {name: schema[name] for name in EXPECTED} == EXPECTED
    assert {name: schema[name] for name in EXPECTED_V2} == EXPECTED_V2
    assert {
        name
        for name in schema
        if name.startswith("v2_material_evidence_")
        and not name.startswith("v2_material_evidence_review_")
    } == EVIDENCE_TABLES
    forbidden = ("active_pointer", "approval", "deployment", "cohort", "reviewed")
    assert not any(token in name for name in EXPECTED for token in forbidden)


def test_primary_request_runtime_does_not_import_01b() -> None:
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
        assert not any("material_evidence_binding" in name for name in imports)


def test_flags_are_explicit_false_and_sampling_remains_zero() -> None:
    settings = (REPO / "backend/sealai_v2/config/settings.py").read_text(
        encoding="utf-8"
    )
    assert "material_evidence_runtime_binding_enabled: bool = False" in settings
    assert "material_ruleset_shadow_sampling_basis_points: int = 0" in settings
    for relative in (".env.example", ".env.prod.example"):
        text = (REPO / relative).read_text(encoding="utf-8")
        assert "MATERIAL_EVIDENCE_RUNTIME_BINDING_ENABLED=false" in text
    compose = (REPO / "docker-compose.deploy.yml").read_text(encoding="utf-8")
    assert "MATERIAL_EVIDENCE_RUNTIME_BINDING_ENABLED:-false" in compose


def test_01b_migration_is_additive_empty_and_pointerless() -> None:
    path = (
        REPO
        / "backend/sealai_v2/db/migrations/versions/20260718_0015_mat_evid_01b_runtime.py"
    )
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"bulk_insert", "execute_many"}
    lowered = source.lower()
    for token in ("active_pointer", "review_state", "approval_state", "seed_data"):
        assert token not in lowered
