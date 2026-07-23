"""Static proof that MED-NORM-01 is closed, empty and runtime-inert."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from _model_schema_ast import load_material_schema


REPO = Path(__file__).resolve().parents[3]
MODELS = REPO / "backend/sealai_v2/db/models.py"
EXPECTED = {
    "v2_medium_catalogs": frozenset(
        {
            "catalog_id",
            "tenant_id",
            "domain_pack_id",
            "created_by_subject",
            "created_at",
        }
    ),
    "v2_medium_catalog_snapshots": frozenset(
        {
            "snapshot_id",
            "catalog_id",
            "media_catalog_schema_version",
            "canonicalization_version",
            "med_norm_contract_version",
            "content_sha256",
            "canonical_payload_json",
            "canonical_bytes",
            "runtime_authority",
            "positive_statement_allowed",
            "created_by_subject",
            "created_at",
        }
    ),
    "v2_medium_catalog_validation_events": frozenset(
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
    "v2_medium_catalog_audit_events": frozenset(
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
UNCHANGED_RUNTIME = {
    "backend/sealai_v2/config/product_maturity.json": (
        "59606ffc63256519f7c25bc3154459acf8bf5a5d7e90d1663afc17a725d901df"
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
    "backend/sealai_v2/core/contracts.py": (
        "90ff3b4e1ea3d93a4d14b8099534108d34c6a67b6ca9492f6f1a88c3f9b1a3d5"
    ),
    "backend/sealai_v2/core/material_constraints.py": (
        "cf8d9969c3730cd5eaa23c08e1dac81df1f3b20bb5eafd219dbc7b004e91de42"
    ),
    "backend/sealai_v2/core/medium_extract.py": (
        "1d0dc81327a1c4bc4db650a30493779a608ccf27ee944c6b52f055c53de8680a"
    ),
    "backend/sealai_v2/knowledge/matrix_seed.json": (
        "ab6a32cf9ef9deac402619cc1d0eaf67d30b39fa2c0c1d45fc2eb5782da4ed82"
    ),
    "frontend-v2/src/contracts.ts": (
        "7615d47b05b74363910e9879c2a0862d66b5c4fe8e1e98a82660f4b17816efbc"
    ),
    "frontend-v2/src/components/Answer.tsx": (
        "3d6f6ad1b9050032233b2525b20ec5476090d02e9821d38d8429cc15ef07c415"
    ),
    "docker-compose.deploy.yml": (
        "e1ebec302d4b101684ca8c9f47f9c79606595ac2ebef5768cfdd31bd97ac4e67"
    ),
    ".env.example": (
        "acc32c4fd4717872f64ae4ad0501c570f348cf9f9daaf90a96163ef407f00da7"
    ),
}


def _imports(path: Path) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_medium_catalog_schema_is_exact_and_has_no_pointer_or_activation() -> None:
    schema = load_material_schema(MODELS)
    assert {name: schema[name] for name in EXPECTED} == EXPECTED
    assert {name for name in schema if name.startswith("v2_medium_catalog")} == set(
        EXPECTED
    )
    assert not any(
        token in name
        for name in EXPECTED
        for token in ("active", "pointer", "deployment", "sampling", "approval")
    )


def test_public_runtime_matrix_extractor_frontend_and_deploy_are_unchanged() -> None:
    for relative, expected in UNCHANGED_RUNTIME.items():
        assert hashlib.sha256((REPO / relative).read_bytes()).hexdigest() == expected


def test_request_runtime_does_not_import_medium_catalog() -> None:
    for relative in (
        "backend/sealai_v2/api/deps.py",
        "backend/sealai_v2/api/main.py",
        "backend/sealai_v2/api/serializers.py",
        "backend/sealai_v2/pipeline/pipeline.py",
        "backend/sealai_v2/pipeline/stages.py",
        "backend/sealai_v2/core/material_constraints.py",
        "backend/sealai_v2/core/medium_extract.py",
        "backend/sealai_v2/material_shadow/capture.py",
        "backend/sealai_v2/orchestration/answer_cache.py",
    ):
        imports = _imports(REPO / relative)
        assert "sealai_v2.core.medium_catalog" not in imports
        assert "sealai_v2.db.medium_catalog" not in imports


def test_evidence_verified_catalog_capability_is_repository_only() -> None:
    allowed = {
        REPO / "backend/sealai_v2/core/medium_catalog.py",
        REPO / "backend/sealai_v2/db/medium_catalog.py",
    }
    for path in (REPO / "backend/sealai_v2").rglob("*.py"):
        if path in allowed or "tests" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        assert "_bind_evidence_verified_medium_catalog" not in source, path


def test_migration_is_additive_empty_and_has_no_runtime_state() -> None:
    path = (
        REPO
        / "backend/sealai_v2/db/migrations/versions/20260718_0017_med_norm_01_catalog.py"
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
        "sampling_basis_points",
        "seed_data",
    ):
        assert token not in lowered


def test_catalog_module_contains_no_embedded_media_entries() -> None:
    source = (REPO / "backend/sealai_v2/core/medium_catalog.py").read_text(
        encoding="utf-8"
    )
    assert "_MEDIUM_SYNONYMS" not in source
    assert "mineral_oil" not in source.lower()
    assert "brake" not in source.lower()
    assert "refrigerant" not in source.lower()
