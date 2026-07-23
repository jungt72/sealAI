"""Executable scope boundary for the local MAT-GOV-03B implementation."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import sys

from _model_schema_ast import load_material_schema, parse_material_schema_source


REPO = Path(__file__).resolve().parents[3]
MODELS = REPO / "backend/sealai_v2/db/models.py"
RAW_IDENTIFIER_COLUMNS = {
    "tenant_id",
    "session_id",
    "case_id",
    "decision_id",
    "correlation_id",
    "request_id",
}
CONTENT_COLUMNS = {
    "question",
    "answer",
    "prompt",
    "document",
    "exception",
    "werkstoff_tendenz",
}
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
            "tenant_ref_hmac",
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
        "daa66c5d268a8e04a1d14c11d23f5569c5208a52d0731d38b130edc1e9c3d370"
    ),
    "backend/sealai_v2/pipeline/stages.py": (
        "40b36ef33d0e7ad0ff1a2b8119b1420a7cfbe4c918b0a312f7e5520407e9be67"
    ),
    "backend/sealai_v2/api/serializers.py": (
        "df2550c2734e00964dc4549ce140df0885d294949e8b57184117d3c8c74c5fd6"
    ),
    "backend/sealai_v2/core/material_constraints.py": (
        "cf8d9969c3730cd5eaa23c08e1dac81df1f3b20bb5eafd219dbc7b004e91de42"
    ),
    "backend/sealai_v2/core/contracts.py": (
        "90ff3b4e1ea3d93a4d14b8099534108d34c6a67b6ca9492f6f1a88c3f9b1a3d5"
    ),
    "docker-compose.deploy.yml": (
        "e1ebec302d4b101684ca8c9f47f9c79606595ac2ebef5768cfdd31bd97ac4e67"
    ),
    ".env.example": (
        "acc32c4fd4717872f64ae4ad0501c570f348cf9f9daaf90a96163ef407f00da7"
    ),
    "frontend-v2/src/contracts.ts": (
        "7615d47b05b74363910e9879c2a0862d66b5c4fe8e1e98a82660f4b17816efbc"
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


def _assert_shadow_schema_privacy(schema: dict[str, frozenset[str]]) -> None:
    shadow_tables = {
        name: columns
        for name, columns in schema.items()
        if name.startswith("v2_material_shadow_")
    }
    for table_name, column_names in shadow_tables.items():
        assert column_names.isdisjoint(RAW_IDENTIFIER_COLUMNS), table_name
        assert column_names.isdisjoint(CONTENT_COLUMNS), table_name


def test_shadow_schema_never_persists_raw_identity_or_conversation_fields() -> None:
    _assert_shadow_schema_privacy(load_material_schema(MODELS))


def test_shadow_privacy_guard_rejects_aliased_physical_identifier_columns() -> None:
    for physical_name in sorted(RAW_IDENTIFIER_COLUMNS):
        source = f"""
class UnexpectedName(Base):
    __tablename__ = "v2_material_shadow_unexpected"
    safe_alias: Mapped[str] = mapped_column("{physical_name}", String(64))
"""
        schema = parse_material_schema_source(source)
        try:
            _assert_shadow_schema_privacy(schema)
        except AssertionError:
            continue
        raise AssertionError(
            f"aliased forbidden physical column was accepted: {physical_name}"
        )
