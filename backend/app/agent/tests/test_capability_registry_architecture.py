from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Mapping

import pytest

from app.agent.capability_registry import (
    CapabilityDescriptor,
    CapabilityId,
    CapabilityKind,
    CapabilityRegistry,
    CapabilityResult,
    CapabilitySafetyFlags,
    build_default_capability_registry,
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

EXPECTED_DEFAULT_CAPABILITY_IDS: tuple[str, ...] = ("medium_intelligence",)
CAPABILITY_SAMPLE_INPUTS: dict[str, dict[str, Any]] = {
    "medium_intelligence": {"medium": "HLP46"},
}

FORBIDDEN_OUTPUT_TERMS: tuple[str, ...] = (
    "freigegeben",
    "final approved",
    "approved solution",
    "certified recommendation",
    "garantiert geeignet",
    "garantiert beständig",
    "garantiert bestaendig",
    "zertifiziert",
    "beste Lösung",
    "beste Loesung",
)

DYNAMIC_DISCOVERY_IMPORT_PREFIXES: tuple[str, ...] = (
    "glob",
    "importlib",
    "pkgutil",
)

DYNAMIC_DISCOVERY_CALL_NAMES: tuple[str, ...] = (
    "glob",
    "rglob",
    "iter_modules",
    "walk_packages",
    "import_module",
    "listdir",
    "scandir",
    "walk",
)

ENVIRONMENT_REGISTRATION_CALL_NAMES: tuple[str, ...] = (
    "getenv",
    "get",
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


def test_default_capability_registry_matches_static_allowlist() -> None:
    first_registry = build_default_capability_registry()
    second_registry = build_default_capability_registry()

    first_ids = _capability_ids(first_registry)
    second_ids = _capability_ids(second_registry)

    assert first_ids == EXPECTED_DEFAULT_CAPABILITY_IDS
    assert second_ids == EXPECTED_DEFAULT_CAPABILITY_IDS
    assert first_ids == tuple(sorted(first_ids))


def test_capability_registry_rejects_duplicate_capability_ids() -> None:
    original_registry = build_default_capability_registry()
    original_module = original_registry.get(CapabilityId.MEDIUM_INTELLIGENCE)

    with pytest.raises(
        ValueError, match="duplicate capability_id registered: medium_intelligence"
    ):
        CapabilityRegistry(
            modules=(
                original_module,
                _DuplicateMediumCapability(),
            )
        )

    after_failed_registration = build_default_capability_registry()
    assert _capability_ids(after_failed_registration) == EXPECTED_DEFAULT_CAPABILITY_IDS
    assert type(
        after_failed_registration.get(CapabilityId.MEDIUM_INTELLIGENCE)
    ) is type(original_module)


def test_capability_registry_uses_no_dynamic_discovery_or_env_registration() -> None:
    violations: list[str] = []
    for path in sorted(CAPABILITY_REGISTRY_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _module_matches(alias.name, DYNAMIC_DISCOVERY_IMPORT_PREFIXES):
                        violations.append(
                            f"{path.relative_to(CAPABILITY_REGISTRY_ROOT.parent)} imports dynamic discovery module {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").lstrip(".")
                if _module_matches(module, DYNAMIC_DISCOVERY_IMPORT_PREFIXES):
                    violations.append(
                        f"{path.relative_to(CAPABILITY_REGISTRY_ROOT.parent)} imports dynamic discovery module {module}"
                    )
            elif isinstance(node, ast.Call):
                call_name = _call_name(node.func)
                if call_name in DYNAMIC_DISCOVERY_CALL_NAMES:
                    violations.append(
                        f"{path.relative_to(CAPABILITY_REGISTRY_ROOT.parent)} calls dynamic discovery function {call_name}"
                    )
                if call_name in ENVIRONMENT_REGISTRATION_CALL_NAMES and _is_os_env_call(
                    node.func
                ):
                    violations.append(
                        f"{path.relative_to(CAPABILITY_REGISTRY_ROOT.parent)} uses environment-driven registration call {call_name}"
                    )

    assert violations == []


def test_every_registered_capability_returns_default_deny_capability_result() -> None:
    registry = build_default_capability_registry()
    capability_ids = _capability_ids(registry)

    assert set(CAPABILITY_SAMPLE_INPUTS) == set(EXPECTED_DEFAULT_CAPABILITY_IDS)

    for capability_id in capability_ids:
        result = registry.invoke(capability_id, CAPABILITY_SAMPLE_INPUTS[capability_id])

        assert isinstance(result, CapabilityResult)
        assert result.safety.as_dict() == {
            "mutates_case_state": False,
            "creates_engineering_truth": False,
            "final_approval_claim_allowed": False,
            "dispatch_allowed": False,
            "external_contact_allowed": False,
            "export_allowed": False,
        }

        payload = result.as_dict()
        assert "answer_markdown" not in payload
        assert "reply" not in payload
        assert "proposed_case_delta" not in payload

        user_visible_candidate_context = {
            "candidate_facts": payload["candidate_facts"],
            "context_notes": payload["context_notes"],
            "risk_notes": payload["risk_notes"],
            "missing_field_hints": payload["missing_field_hints"],
            "rfq_relevance_notes": payload["rfq_relevance_notes"],
        }
        flattened = _flatten_text(user_visible_candidate_context).casefold()
        for term in FORBIDDEN_OUTPUT_TERMS:
            assert term.casefold() not in flattened


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
    if any(
        module == prefix or module.startswith(f"{prefix}.")
        for prefix in FORBIDDEN_IMPORT_PREFIXES
    ):
        violations.append(
            f"{path.relative_to(CAPABILITY_REGISTRY_ROOT.parent)} imports {module}"
        )
    if imported_name in FORBIDDEN_IMPORTED_NAMES:
        violations.append(
            f"{path.relative_to(CAPABILITY_REGISTRY_ROOT.parent)} imports forbidden symbol {imported_name}"
        )


def _capability_ids(registry: object) -> tuple[str, ...]:
    return tuple(
        sorted(
            descriptor.capability_id.value
            for descriptor in registry.list_capabilities()  # type: ignore[attr-defined]
        )
    )


def _module_matches(module: str, prefixes: tuple[str, ...]) -> bool:
    return any(
        module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes
    )


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _is_os_env_call(func: ast.expr) -> bool:
    if not isinstance(func, ast.Attribute):
        return False
    if func.attr == "getenv":
        return isinstance(func.value, ast.Name) and func.value.id == "os"
    if func.attr != "get":
        return False
    value = func.value
    return (
        isinstance(value, ast.Attribute)
        and value.attr == "environ"
        and isinstance(value.value, ast.Name)
        and value.value.id == "os"
    )


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return " ".join(
            f"{_flatten_text(key)} {_flatten_text(item)}" for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_text(item) for item in value)
    if value is None:
        return ""
    return str(value)


class _DuplicateMediumCapability:
    @property
    def descriptor(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            capability_id=CapabilityId.MEDIUM_INTELLIGENCE,
            kind=CapabilityKind.DOMAIN_CONTEXT,
            name="Duplicate Medium",
            version="duplicate_test_v1",
            description="Test-only duplicate capability.",
        )

    def run(self, capability_input: object) -> CapabilityResult:
        return CapabilityResult(
            capability_id=CapabilityId.MEDIUM_INTELLIGENCE,
            capability_kind=CapabilityKind.DOMAIN_CONTEXT,
            input_summary="duplicate_test",
        )
