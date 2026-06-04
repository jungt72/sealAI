from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.agent.capability_registry.contracts import (
    CapabilityDescriptor,
    CapabilityId,
    CapabilityInput,
    CapabilityModule,
    CapabilityResult,
)
from app.agent.capability_registry.medium_intelligence import (
    MediumIntelligenceCapability,
)


class CapabilityNotFoundError(KeyError):
    pass


@dataclass(slots=True)
class CapabilityRegistry:
    modules: Sequence[CapabilityModule] = field(default_factory=tuple)
    _modules_by_id: dict[str, CapabilityModule] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        modules_by_id: dict[str, CapabilityModule] = {}
        for module in self.modules:
            capability_id = module.descriptor.capability_id.value
            if capability_id in modules_by_id:
                raise ValueError(f"duplicate capability_id registered: {capability_id}")
            modules_by_id[capability_id] = module
        self._modules_by_id = modules_by_id

    def list_capabilities(self) -> tuple[CapabilityDescriptor, ...]:
        return tuple(module.descriptor for module in self._modules_by_id.values())

    def get(self, capability_id: CapabilityId | str) -> CapabilityModule:
        key = _capability_id_value(capability_id)
        try:
            return self._modules_by_id[key]
        except KeyError as exc:
            raise CapabilityNotFoundError(key) from exc

    def invoke(
        self,
        capability_id: CapabilityId | str,
        payload: Mapping[str, Any] | CapabilityInput | None = None,
    ) -> CapabilityResult:
        module = self.get(capability_id)
        capability_input = _capability_input(capability_id, payload)
        return module.run(capability_input)


def build_default_capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry(modules=(MediumIntelligenceCapability(),))


def _capability_input(
    capability_id: CapabilityId | str,
    payload: Mapping[str, Any] | CapabilityInput | None,
) -> CapabilityInput:
    if isinstance(payload, CapabilityInput):
        return payload
    return CapabilityInput(
        capability_id=capability_id,
        payload=dict(payload or {}),
    )


def _capability_id_value(capability_id: CapabilityId | str) -> str:
    return str(getattr(capability_id, "value", capability_id))
