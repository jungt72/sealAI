"""Static proof that MAT-RULES-01 remains inert and non-authoritative."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
BASE_RUNTIME_HASHES = {
    "backend/sealai_v2/config/product_maturity.json": (
        "59606ffc63256519f7c25bc3154459acf8bf5a5d7e90d1663afc17a725d901df"
    ),
    "backend/sealai_v2/pipeline/pipeline.py": (
        "3b596540440b27ac34bc1f9ff57b0086e2a599ea12a8ddda3c1572afa1143bcb"
    ),
    "backend/sealai_v2/pipeline/stages.py": (
        "cf042c0327fc7791fa22460a126783fb4c1d20383e169c6e4e7390d0a3872bde"
    ),
    "backend/sealai_v2/api/serializers.py": (
        "1795c1b7f0160bc4e99a174817fbfc3ee5a7c12f55791f34f06572d5fba6bb9d"
    ),
    "backend/sealai_v2/core/contracts.py": (
        "ed8af58c5407cd0d65730abfa390d56464e9a1f43f36715f9f6236913054b7b3"
    ),
    "backend/sealai_v2/core/material_constraints.py": (
        "cf8d9969c3730cd5eaa23c08e1dac81df1f3b20bb5eafd219dbc7b004e91de42"
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
    imports: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_public_runtime_frontend_matrix_and_deploy_are_byte_identical() -> None:
    for relative, expected in BASE_RUNTIME_HASHES.items():
        assert hashlib.sha256((REPO / relative).read_bytes()).hexdigest() == expected


def test_request_runtime_does_not_import_reviewed_rule_pack() -> None:
    forbidden = {
        "sealai_v2.core.material_reviewed_rules",
        "sealai_v2.db.material_reviewed_rules",
    }
    for relative in (
        "backend/sealai_v2/api/deps.py",
        "backend/sealai_v2/api/main.py",
        "backend/sealai_v2/api/serializers.py",
        "backend/sealai_v2/pipeline/pipeline.py",
        "backend/sealai_v2/pipeline/stages.py",
        "backend/sealai_v2/core/material_constraints.py",
        "backend/sealai_v2/material_shadow/capture.py",
        "backend/sealai_v2/orchestration/answer_cache.py",
    ):
        assert not (_imports(REPO / relative) & forbidden)


def test_reviewed_rule_capability_binding_is_repository_only() -> None:
    allowed = {
        REPO / "backend/sealai_v2/core/material_reviewed_rules.py",
        REPO / "backend/sealai_v2/db/material_reviewed_rules.py",
    }
    for path in (REPO / "backend/sealai_v2").rglob("*.py"):
        if path in allowed or "tests" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        assert "_bind_evidence_reviewed_material_rules" not in source, path
        assert "_validate_reviewed_material_rules" not in source, path


def test_coverage_manifest_contains_no_rules_claims_or_authority() -> None:
    path = REPO / "docs/ssot/material-rule-coverage-v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["authority"] == "NONE_EVIDENCE_GAPS_ONLY"
    assert payload["positive_statement_allowed"] is False
    assert payload["gaps"]
    assert all(item["status"] == "evidence_gap" for item in payload["gaps"])
    assert all(item["rule_refs"] == [] for item in payload["gaps"])
    assert all(item["review_snapshot_ids"] == [] for item in payload["gaps"])
    assert not any(
        key in item
        for item in payload["gaps"]
        for key in ("claim", "statement", "verdict", "temperature", "coefficient")
    )


def test_package_adds_no_model_migration_pointer_or_activation() -> None:
    for relative in (
        "backend/sealai_v2/core/material_reviewed_rules.py",
        "backend/sealai_v2/db/material_reviewed_rules.py",
    ):
        lowered = (REPO / relative).read_text(encoding="utf-8").lower()
        for token in (
            "active_pointer",
            "sampling_basis_points",
            "production_pointer",
            "deployment_cohort",
        ):
            assert token not in lowered
