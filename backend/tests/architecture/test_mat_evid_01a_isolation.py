"""Executable proof that MAT-EVID-01A is additive and runtime-inert."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from _model_schema_ast import load_material_schema


REPO = Path(__file__).resolve().parents[3]
MODELS = REPO / "backend/sealai_v2/db/models.py"
EXPECTED_SCHEMA = {
    "v2_material_evidence_manifests": frozenset(
        {
            "manifest_id",
            "ruleset_snapshot_id",
            "domain_pack_id",
            "created_by_subject",
            "created_at",
        }
    ),
    "v2_material_evidence_snapshots": frozenset(
        {
            "snapshot_id",
            "manifest_id",
            "evidence_manifest_schema_version",
            "canonicalization_version",
            "mat_evid_contract_version",
            "content_sha256",
            "canonical_payload_json",
            "canonical_bytes",
            "created_by_subject",
            "created_at",
        }
    ),
    "v2_material_evidence_validation_events": frozenset(
        {
            "event_id",
            "snapshot_id",
            "validator_contract_version",
            "validation_state",
            "error_code",
            "validation_sha256",
            "created_at",
        }
    ),
    "v2_material_evidence_audit_events": frozenset(
        {
            "event_id",
            "snapshot_id",
            "event_type",
            "actor_subject",
            "event_payload_json",
            "event_sha256",
            "created_at",
        }
    ),
}
EXPECTED_SCHEMA_V2 = {
    "v2_material_evidence_manifests_v2": frozenset(
        {
            "manifest_id",
            "target_type",
            "target_ref",
            "ruleset_snapshot_id",
            "media_ref",
            "domain_pack_id",
            "created_by_subject",
            "created_at",
        }
    ),
    "v2_material_evidence_snapshots_v2": EXPECTED_SCHEMA[
        "v2_material_evidence_snapshots"
    ],
    "v2_material_evidence_validation_events_v2": EXPECTED_SCHEMA[
        "v2_material_evidence_validation_events"
    ],
    "v2_material_evidence_audit_events_v2": EXPECTED_SCHEMA[
        "v2_material_evidence_audit_events"
    ],
}
MAT_GOV_03A_TABLES = frozenset(
    {
        "v2_material_rulesets",
        "v2_material_ruleset_snapshots",
        "v2_material_snapshot_validation_events",
        "v2_material_snapshot_audit_events",
    }
)
UNCHANGED_03A = {
    "backend/sealai_v2/core/material_rulesets.py": (
        "0522d613ab3c7e3c2ea2c87bfc586ad1382b75aa986a9393c5739ea1ce73b00f"
    ),
    "backend/sealai_v2/db/migrations/versions/20260717_0011_mat_gov_03a_snapshots.py": (
        "7c1855d36c4c4ae61f479901a9819e97fc05a885dc560cf810b5293ccb45b18a"
    ),
}
UNCHANGED_PUBLIC = {
    "backend/sealai_v2/config/product_maturity.json": (
        "59606ffc63256519f7c25bc3154459acf8bf5a5d7e90d1663afc17a725d901df"
    ),
    "backend/sealai_v2/knowledge/matrix_seed.json": (
        "ab6a32cf9ef9deac402619cc1d0eaf67d30b39fa2c0c1d45fc2eb5782da4ed82"
    ),
    "backend/sealai_v2/pipeline/pipeline.py": (
        "ff0dd7f62813aa018bb028f52b18470d2725834f70572907d393664bc583b106"
    ),
    "backend/sealai_v2/pipeline/stages.py": (
        "40b36ef33d0e7ad0ff1a2b8119b1420a7cfbe4c918b0a312f7e5520407e9be67"
    ),
    "backend/sealai_v2/api/serializers.py": (
        "df2550c2734e00964dc4549ce140df0885d294949e8b57184117d3c8c74c5fd6"
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


def test_evidence_schema_is_exact_and_contains_no_lifecycle_or_runtime_tables() -> None:
    schema = load_material_schema(MODELS)
    actual = {name: schema[name] for name in EXPECTED_SCHEMA}
    assert actual == EXPECTED_SCHEMA
    assert {name: schema[name] for name in EXPECTED_SCHEMA_V2} == EXPECTED_SCHEMA_V2
    forbidden = (
        "review",
        "approval",
        "deployment",
        "pointer",
        "active",
        "cohort",
        "lease",
        "runtime",
    )
    assert not any(token in table for table in actual for token in forbidden)
    non_shadow = {
        table for table in schema if not table.startswith("v2_material_shadow_")
    }
    assert MAT_GOV_03A_TABLES | set(EXPECTED_SCHEMA) | set(EXPECTED_SCHEMA_V2) <= (
        non_shadow
    )


def test_mat_gov_03a_schema_v1_files_are_byte_identical_to_accepted_baseline() -> None:
    for relative, expected in UNCHANGED_03A.items():
        assert hashlib.sha256((REPO / relative).read_bytes()).hexdigest() == expected


def test_public_runtime_flags_matrix_and_frontend_are_unchanged() -> None:
    for relative, expected in UNCHANGED_PUBLIC.items():
        actual = hashlib.sha256((REPO / relative).read_bytes()).hexdigest()
        assert actual == expected, relative


def test_request_runtime_does_not_import_evidence_foundation() -> None:
    runtime_files = (
        "backend/sealai_v2/api/deps.py",
        "backend/sealai_v2/api/main.py",
        "backend/sealai_v2/api/serializers.py",
        "backend/sealai_v2/pipeline/pipeline.py",
        "backend/sealai_v2/pipeline/stages.py",
        "backend/sealai_v2/core/material_constraints.py",
        "backend/sealai_v2/knowledge/matrix.py",
        "backend/sealai_v2/orchestration/answer_cache.py",
    )
    for relative in runtime_files:
        imports = _imports(REPO / relative)
        assert "sealai_v2.core.material_evidence" not in imports
        assert "sealai_v2.core.material_evidence_v2" not in imports
        assert "sealai_v2.db.material_evidence" not in imports
        assert "sealai_v2.db.material_evidence_v2" not in imports
        assert "sealai_v2.core.material_evidence_binding" not in imports
        assert "sealai_v2.db.material_evidence_binding" not in imports
        assert "sealai_v2.material_evidence_binding" not in imports


def test_evidence_migration_contains_no_data_or_lifecycle_operations() -> None:
    migration = (
        REPO / "backend/sealai_v2/db/migrations/versions/20260718_0014_mat_evid_01a.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(migration)
    forbidden_calls = {"bulk_insert", "execute_many"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_calls
    lowered = migration.lower()
    for token in ("active_pointer", "review_state", "approval_state", "seed_data"):
        assert token not in lowered
