from __future__ import annotations

from typing import Iterable

from .base import NormCheckContext, NormCheckResult, NormModule
from .din_3760_iso_6194 import Din3760Iso6194Module
from .eu_food_contact import EuFoodContactModule
from .fda_food_contact import FdaFoodContactModule


class NormModuleRegistry:
    """In-memory registry for deterministic norm modules."""

    def __init__(self, modules: Iterable[NormModule] | None = None) -> None:
        self._modules: dict[str, NormModule] = {}
        for module in modules or ():
            self.register(module)

    def register(self, module: NormModule) -> None:
        if not module.module_id:
            raise ValueError("norm module_id must not be empty")
        if module.module_id in self._modules:
            raise ValueError(f"norm module already registered: {module.module_id}")
        self._modules[module.module_id] = module

    def get(self, module_id: str) -> NormModule | None:
        return self._modules.get(module_id)

    def list_modules(self) -> list[NormModule]:
        return [self._modules[key] for key in sorted(self._modules)]

    def applicable_modules(self, context: NormCheckContext) -> list[NormModule]:
        return [module for module in self.list_modules() if module.applies_to(context)]

    def run_checks(self, context: NormCheckContext) -> list[NormCheckResult]:
        return [module.check(context) for module in self.applicable_modules(context)]


def build_default_registry() -> NormModuleRegistry:
    return NormModuleRegistry(
        [
            Din3760Iso6194Module(),
            EuFoodContactModule(),
            FdaFoodContactModule(),
        ]
    )
