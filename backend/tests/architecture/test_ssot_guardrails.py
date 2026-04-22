from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_APP = REPO_ROOT / "backend" / "app"
SSOT_REGISTRY = REPO_ROOT / "docs" / "architecture" / "SSOT_REGISTRY.md"
DEPRECATED_MAP = REPO_ROOT / "docs" / "architecture" / "DEPRECATED_MAP.md"

BANNED_PRODUCT_IMPORT_PREFIXES = ("app.langgraph_v2",)

NON_CANONICAL_TREES = (
    "archive/",
    "_trash/",
    "_local_keep/",
    "backups/",
    "langgraph_backup/",
)

CANONICAL_PATHS = (
    "backend/app/agent/api/router.py",
    "backend/app/agent/api/routes/chat.py",
    "backend/app/agent/api/streaming.py",
    "backend/app/agent/api/governed_runtime.py",
    "backend/app/agent/api/dispatch.py",
    "backend/app/agent/state/models.py",
    "backend/app/agent/state/reducers.py",
    "backend/app/agent/state/persistence.py",
    "backend/app/agent/api/loaders.py",
    "backend/app/api/v1/projections/case_workspace.py",
    "backend/app/api/v1/projections/workspace_routing.py",
    "backend/app/api/v1/projections/ptfe_rwdr_enrichment.py",
    "backend/app/api/v1/schemas/case_workspace.py",
    "backend/app/agent/api/routes/workspace.py",
    "backend/app/api/v1/endpoints/state.py",
    "backend/app/services/calculation_engine.py",
    "backend/app/services/application_pattern_service.py",
    "backend/app/services/medium_intelligence_service.py",
    "backend/app/services/advisory_engine.py",
    "backend/app/services/problem_first_matching_service.py",
    "backend/app/services/capability_service.py",
    "backend/app/services/terminology_service.py",
    "frontend/src/lib/contracts/workspace.ts",
    "frontend/src/lib/mapping/workspace.ts",
)


def _python_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and ".pytest_cache" not in path.parts
    )


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_ssot_registry_and_deprecated_map_exist() -> None:
    assert (
        SSOT_REGISTRY.exists()
    ), "SSoT registry must exist before architecture changes."
    assert (
        DEPRECATED_MAP.exists()
    ), "Deprecated map must exist before architecture cleanup."


def test_canonical_registry_paths_exist() -> None:
    missing = [path for path in CANONICAL_PATHS if not (REPO_ROOT / path).exists()]
    assert not missing, (
        "SSoT registry references missing canonical files: " + ", ".join(missing)
    )


def test_product_code_does_not_import_removed_langgraph_v2() -> None:
    offenders: list[str] = []
    for path in _python_files(BACKEND_APP):
        for module in _imports(path):
            if module.startswith(BANNED_PRODUCT_IMPORT_PREFIXES):
                offenders.append(f"{path.relative_to(REPO_ROOT)} imports {module}")
    assert not offenders, (
        "Removed LangGraph v2 imports found in product code:\n" + "\n".join(offenders)
    )


def test_non_canonical_trees_are_documented_as_patch_hazards() -> None:
    registry = SSOT_REGISTRY.read_text(encoding="utf-8")
    deprecated = DEPRECATED_MAP.read_text(encoding="utf-8")
    docs = registry + "\n" + deprecated
    missing = [prefix for prefix in NON_CANONICAL_TREES if prefix not in docs]
    assert not missing, "Non-canonical trees must be documented: " + ", ".join(missing)


def test_agent_router_has_single_canonical_mount() -> None:
    main_py = (REPO_ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    v1_api_py = (REPO_ROOT / "backend" / "app" / "api" / "v1" / "api.py").read_text(
        encoding="utf-8"
    )

    assert "from app.agent.api.router import router as agent_router" in main_py
    assert re.search(
        r"include_router\(agent_router,\s*prefix=[\"']/api/agent[\"']", main_py
    )
    assert "api_router.include_router(agent_router" not in v1_api_py


def test_v1_state_facade_mutations_fail_closed() -> None:
    state_py = (
        REPO_ROOT / "backend" / "app" / "api" / "v1" / "endpoints" / "state.py"
    ).read_text(encoding="utf-8")
    for route_name in (
        "update_state",
        "confirm_rfq_package",
        "select_partner",
        "initiate_rfq_handover",
    ):
        assert f"def {route_name}" in state_py
    assert state_py.count("status_code=501") >= 4
    assert (
        "State mutation is only supported on the canonical /api/agent runtime path"
        in state_py
    )


def test_architecture_docs_mark_legacy_tests_as_non_canonical() -> None:
    deprecated = DEPRECATED_MAP.read_text(encoding="utf-8")
    assert "backend/tests/contract/*" in deprecated
    assert "app.langgraph_v2" in deprecated
    registry = SSOT_REGISTRY.read_text(encoding="utf-8")
    assert "backend/app/agent/state/models.py" in registry
    assert "backend/app/api/v1/projections/case_workspace.py" in registry
