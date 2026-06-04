from __future__ import annotations

import inspect

import pytest

from app.services.norm_modules import (
    Din3760Iso6194Module,
    EscalationPolicy,
    NormCheckResult,
    NormCheckStatus,
    NormModule,
    NormModuleRegistry,
    build_default_registry,
)


class FakeNormModule(NormModule):
    module_id = "norm_fake_extension"
    version = "0.1.0"

    def applies_to(self, context):
        return context.get("engineering_path") == "fake_path"

    def required_fields(self):
        return ["engineering_path", "fake_required"]

    def check(self, context):
        if not self.applies_to(context):
            return NormCheckResult(
                module_id=self.module_id,
                version=self.version,
                status=NormCheckStatus.NOT_APPLICABLE,
                applies=False,
                escalation=EscalationPolicy.OUT_OF_SCOPE,
            )
        if not context.get("fake_required"):
            return NormCheckResult(
                module_id=self.module_id,
                version=self.version,
                status=NormCheckStatus.INSUFFICIENT_DATA,
                applies=True,
                missing_required_fields=("fake_required",),
                escalation=EscalationPolicy.BLOCK_UNTIL_MISSING_FIELDS,
            )
        return NormCheckResult(
            module_id=self.module_id,
            version=self.version,
            status=NormCheckStatus.PASS,
            applies=True,
            escalation=EscalationPolicy.NO_ESCALATION,
        )

    def escalation_policy(self):
        return EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW


def test_norm_module_base_contract_is_abstract() -> None:
    assert inspect.isabstract(NormModule)
    with pytest.raises(TypeError):
        NormModule()  # type: ignore[abstract]


def test_fake_module_implements_required_contract() -> None:
    module = FakeNormModule()
    assert module.module_id == "norm_fake_extension"
    assert module.version == "0.1.0"
    assert module.required_fields() == ["engineering_path", "fake_required"]
    assert module.escalation_policy() is EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW


def test_registry_registers_and_gets_fake_module() -> None:
    registry = NormModuleRegistry()
    module = FakeNormModule()
    registry.register(module)
    assert registry.get("norm_fake_extension") is module


def test_registry_rejects_duplicate_module_id() -> None:
    registry = NormModuleRegistry([FakeNormModule()])
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeNormModule())


def test_registry_rejects_empty_module_id() -> None:
    class EmptyIdModule(FakeNormModule):
        module_id = ""

    registry = NormModuleRegistry()
    with pytest.raises(ValueError, match="module_id"):
        registry.register(EmptyIdModule())


def test_registry_lists_modules_sorted_by_id() -> None:
    registry = NormModuleRegistry([FakeNormModule(), Din3760Iso6194Module()])
    assert [module.module_id for module in registry.list_modules()] == [
        "norm_din_3760_iso_6194",
        "norm_fake_extension",
    ]


def test_registry_finds_applicable_fake_module() -> None:
    registry = NormModuleRegistry([FakeNormModule(), Din3760Iso6194Module()])
    applicable = registry.applicable_modules({"engineering_path": "fake_path"})
    assert [module.module_id for module in applicable] == ["norm_fake_extension"]


def test_registry_runs_only_applicable_modules() -> None:
    registry = NormModuleRegistry([FakeNormModule(), Din3760Iso6194Module()])
    results = registry.run_checks({"engineering_path": "fake_path", "fake_required": True})
    assert len(results) == 1
    assert results[0].module_id == "norm_fake_extension"
    assert results[0].status is NormCheckStatus.PASS


def test_registry_fake_module_reports_missing_fields() -> None:
    registry = NormModuleRegistry([FakeNormModule()])
    result = registry.run_checks({"engineering_path": "fake_path"})[0]
    assert result.status is NormCheckStatus.INSUFFICIENT_DATA
    assert result.missing_required_fields == ("fake_required",)
    assert result.escalation is EscalationPolicy.BLOCK_UNTIL_MISSING_FIELDS


def test_default_registry_contains_din_iso_module() -> None:
    registry = build_default_registry()
    assert registry.get("norm_din_3760_iso_6194") is not None


def test_norm_check_result_blocking_property() -> None:
    blocking = NormCheckResult(
        module_id="x",
        version="1",
        status=NormCheckStatus.FAIL,
        applies=True,
    )
    review = NormCheckResult(
        module_id="x",
        version="1",
        status=NormCheckStatus.REVIEW_REQUIRED,
        applies=True,
    )
    assert blocking.has_blocking_issue is True
    assert review.has_blocking_issue is False


def test_norm_modules_do_not_import_forbidden_runtime_layers() -> None:
    import app.services.norm_modules.base as base
    import app.services.norm_modules.din_3760_iso_6194 as din_iso
    import app.services.norm_modules.registry as registry

    sources = "\n".join(
        inspect.getsource(module) for module in (base, din_iso, registry)
    )
    assert "app.agent" not in sources
    assert "langgraph" not in sources.lower()
    assert "fastapi" not in sources.lower()
