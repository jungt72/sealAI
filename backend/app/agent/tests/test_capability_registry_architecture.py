from __future__ import annotations

import ast
from pathlib import Path

from app.agent.capability_registry import (
    CapabilityId,
    CapabilityKind,
    CapabilityResult,
    CapabilitySafetyFlags,
)


CAPABILITY_REGISTRY_ROOT = Path(__file__).resolve().parents[1] / "capability_registry"

FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "app.agent.communication.v7_contracts",
    "app.agent.api.dispatch",
    "app.agent.api.routes",
    "app.agent.api.streaming",
    "app.agent.api.governed_runtime",
    "app.agent.graph.topology",
    "app.agent.graph.nodes",
    "app.services.rfq_preview_service",
    "app.api.v1.projections.case_workspace",
    "app.api.v1.endpoints",
    "frontend",
    "app.db",
    "app.database",
    "app.core.database",
    "app.repositories",
    "app.agent.state.persistence",
    "app.services.capability_service",
    "sqlalchemy",
)

FORBIDDEN_IMPORTED_NAMES: tuple[str, ...] = (
    "RuntimeAction",
    "RuntimeActionType",
    "RuntimeAnswerBuilder",
)


def test_capability_registry_modules_do_not_import_orchestration_boundaries() -> None:
    violations: list[str] = []
    for path in sorted(CAPABILITY_REGISTRY_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    _collect_forbidden_import_violations(
                        violations=violations,
                        path=path,
                        module=alias.name,
                        imported_name=alias.name.rsplit(".", 1)[-1],
                    )
            elif isinstance(node, ast.ImportFrom):
                module = "." * node.level + (node.module or "")
                for alias in node.names:
                    _collect_forbidden_import_violations(
                        violations=violations,
                        path=path,
                        module=module,
                        imported_name=alias.name,
                    )

    assert violations == []


def test_capability_result_safety_defaults_are_read_only_and_non_operational() -> None:
    assert CapabilitySafetyFlags().as_dict() == {
        "mutates_case_state": False,
        "creates_engineering_truth": False,
        "final_approval_claim_allowed": False,
        "dispatch_allowed": False,
        "external_contact_allowed": False,
        "export_allowed": False,
    }

    result = CapabilityResult(
        capability_id=CapabilityId.MEDIUM_INTELLIGENCE,
        capability_kind=CapabilityKind.DOMAIN_CONTEXT,
        input_summary="architecture_guard_default",
    )

    assert result.safety.as_dict() == {
        "mutates_case_state": False,
        "creates_engineering_truth": False,
        "final_approval_claim_allowed": False,
        "dispatch_allowed": False,
        "external_contact_allowed": False,
        "export_allowed": False,
    }


def _collect_forbidden_import_violations(
    *,
    violations: list[str],
    path: Path,
    module: str,
    imported_name: str,
) -> None:
    module = module.lstrip(".")
    if any(module == prefix or module.startswith(f"{prefix}.") for prefix in FORBIDDEN_IMPORT_PREFIXES):
        violations.append(f"{path.relative_to(CAPABILITY_REGISTRY_ROOT.parent)} imports {module}")
    if imported_name in FORBIDDEN_IMPORTED_NAMES:
        violations.append(
            f"{path.relative_to(CAPABILITY_REGISTRY_ROOT.parent)} imports forbidden symbol {imported_name}"
        )
