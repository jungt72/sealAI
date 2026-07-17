"""Executable scope boundary for the local MAT-GOV-03B implementation."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import sys

from _model_schema_ast import load_material_schema


REPO = Path(__file__).resolve().parents[3]
MODELS = REPO / "backend/sealai_v2/db/models.py"
EXPECTED_03B_SCHEMA = {
    "v2_material_shadow_bindings": frozenset(
        {
            "binding_id",
            "binding_schema_version",
            "snapshot_id",
            "content_sha256",
            "environment",
            "purpose",
            "scope_kind",
            "tenant_ref_hmac",
            "hmac_key_id",
            "domain_pack_id",
            "domain_pack_version",
            "evaluator_version",
            "kernel_version",
            "runtime_profile_sha256",
            "build_git_sha",
            "build_tree_hash",
            "valid_from",
            "valid_until",
            "creator_subject",
            "reason",
            "sampling_policy_version",
            "sampling_basis_points",
            "created_at",
        }
    ),
    "v2_material_shadow_binding_events": frozenset(
        {
            "event_id",
            "event_schema_version",
            "binding_id",
            "event_type",
            "actor_subject",
            "reason",
            "effective_at",
            "created_at",
            "event_sha256",
        }
    ),
    "v2_material_shadow_pins": frozenset(
        {
            "pin_id",
            "pin_schema_version",
            "binding_id",
            "snapshot_id",
            "content_sha256",
            "environment",
            "purpose",
            "scope_kind",
            "tenant_ref_hmac",
            "hmac_key_id",
            "domain_pack_id",
            "domain_pack_version",
            "evaluator_version",
            "kernel_version",
            "runtime_profile_sha256",
            "build_git_sha",
            "build_tree_hash",
            "sampling_policy_version",
            "sampled",
            "authority",
            "positive_statement_allowed",
            "acquired_at",
            "binding_valid_until",
        }
    ),
    "v2_material_shadow_session_versions": frozenset(
        {
            "session_version_id",
            "session_ref_hmac",
            "hmac_key_id",
            "version_no",
            "pin_id",
            "created_at",
        }
    ),
    "v2_material_shadow_session_upgrade_events": frozenset(
        {
            "event_id",
            "from_session_version_id",
            "to_session_version_id",
            "actor_subject",
            "reason",
            "created_at",
        }
    ),
    "v2_material_shadow_outbox": frozenset(
        {
            "job_id",
            "pin_id",
            "session_version_id",
            "sequence_no",
            "hmac_key_id",
            "correlation_hmac",
            "case_ref_hmac",
            "decision_ref_hmac",
            "material_id",
            "medium_id",
            "material_state",
            "medium_state",
            "medium_cardinality",
            "relation_state",
            "domain_pack_id",
            "domain_pack_version",
            "input_fingerprint",
            "idempotency_key",
            "status",
            "attempts",
            "stable_error_code",
            "created_at",
            "claimed_at",
            "lease_owner",
            "lease_expires_at",
            "next_attempt_at",
            "completed_at",
        }
    ),
    "v2_material_shadow_evaluations": frozenset(
        {
            "evaluation_id",
            "job_id",
            "pin_id",
            "hmac_key_id",
            "evaluation_state",
            "verdict",
            "decisive_ref",
            "result_sha256",
            "stable_error_code",
            "cache_hit",
            "authority",
            "positive_statement_allowed",
            "created_at",
            "expires_at",
        }
    ),
    "v2_material_shadow_evaluation_matches": frozenset(
        {"match_id", "evaluation_id", "rule_ref", "verdict", "source_ref"}
    ),
    "v2_material_shadow_evaluation_refs": frozenset(
        {
            "ref_id",
            "evaluation_id",
            "ref_kind",
            "ref_hmac",
            "hmac_key_id",
            "authority",
        }
    ),
}
UNCHANGED_PUBLIC_SURFACES = {
    "backend/sealai_v2/knowledge/matrix_seed.json": (
        "ab6a32cf9ef9deac402619cc1d0eaf67d30b39fa2c0c1d45fc2eb5782da4ed82"
    ),
    "backend/sealai_v2/pipeline/pipeline.py": (
        "5842a3f7cd658036e867fafc4af74a0fedb2dfdab9b715708f5fd18d15ee7973"
    ),
    "backend/sealai_v2/pipeline/stages.py": (
        "cf042c0327fc7791fa22460a126783fb4c1d20383e169c6e4e7390d0a3872bde"
    ),
    "backend/sealai_v2/api/serializers.py": (
        "1795c1b7f0160bc4e99a174817fbfc3ee5a7c12f55791f34f06572d5fba6bb9d"
    ),
    "backend/sealai_v2/core/material_constraints.py": (
        "cf8d9969c3730cd5eaa23c08e1dac81df1f3b20bb5eafd219dbc7b004e91de42"
    ),
    "backend/sealai_v2/core/contracts.py": (
        "ed8af58c5407cd0d65730abfa390d56464e9a1f43f36715f9f6236913054b7b3"
    ),
    "docker-compose.deploy.yml": (
        "322c08a81b97becffa8af53e63f645ff2ac1b8426b3867ce20443007c284a988"
    ),
    ".env.example": (
        "746c1c14050f996a37087999d4c1ba39068cb879cdb870f4745cea0962d3d6c1"
    ),
    "frontend-v2/src/contracts.ts": (
        "1f0b3d92dba2b30d0207dca2bdfb05b63efea3f33960e67e74705482bce38963"
    ),
    "frontend-v2/src/components/Answer.tsx": (
        "3d6f6ad1b9050032233b2525b20ec5476090d02e9821d38d8429cc15ef07c415"
    ),
}


def _imports(path: Path) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_visible_material_prompt_matrix_products_and_frontend_are_unchanged() -> None:
    for relative, expected in UNCHANGED_PUBLIC_SURFACES.items():
        actual = hashlib.sha256((REPO / relative).read_bytes()).hexdigest()
        assert actual == expected, relative


def test_shadow_flags_are_closed_default_off_and_have_no_snapshot_setting() -> None:
    sys.path.insert(0, str(REPO / "backend"))
    from sealai_v2.config.settings import Settings

    settings = Settings()
    assert settings.material_ruleset_shadow_enabled is False
    assert settings.material_ruleset_shadow_persistence_enabled is False
    assert settings.material_ruleset_shadow_sampling_enabled is False
    assert settings.material_ruleset_shadow_sampling_basis_points == 0
    assert not any(
        name.startswith("material_ruleset_shadow") and "snapshot" in name
        for name in Settings.model_fields
    )


def test_shadow_capture_is_lazy_and_does_not_enter_pipeline_or_serializers() -> None:
    runtime_files = (
        "backend/sealai_v2/pipeline/pipeline.py",
        "backend/sealai_v2/pipeline/stages.py",
        "backend/sealai_v2/api/serializers.py",
        "backend/sealai_v2/api/deps.py",
    )
    for relative in runtime_files:
        imports = _imports(REPO / relative)
        assert not any(name.startswith("sealai_v2.material_shadow") for name in imports)


def test_03b_schema_contains_no_activation_or_admin_aggregate() -> None:
    schema = load_material_schema(MODELS)
    tables = {
        name: columns
        for name, columns in schema.items()
        if name.startswith("v2_material_shadow_")
    }
    assert tables == EXPECTED_03B_SCHEMA
    forbidden = (
        "active_pointer",
        "approval",
        "review",
        "deployment",
        "cohort",
        "stage_ack",
    )
    assert not any(token in table for table in tables for token in forbidden)


def test_shadow_schema_never_persists_raw_identity_or_conversation_fields() -> None:
    raw_identifier_columns = {
        "tenant_id",
        "session_id",
        "case_id",
        "decision_id",
        "correlation_id",
        "request_id",
    }
    content_columns = {
        "question",
        "answer",
        "prompt",
        "document",
        "exception",
        "werkstoff_tendenz",
    }
    shadow_tables = {
        name: columns
        for name, columns in load_material_schema(MODELS).items()
        if name.startswith("v2_material_shadow_")
    }
    for table_name, column_names in shadow_tables.items():
        assert column_names.isdisjoint(raw_identifier_columns), table_name
        assert column_names.isdisjoint(content_columns), table_name
