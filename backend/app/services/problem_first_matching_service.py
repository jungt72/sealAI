from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    requirement_type: str
    payload: Mapping[str, Any]
    strictness: str = "hard"


@dataclass(frozen=True, slots=True)
class CapabilityCoverage:
    met: tuple[str, ...]
    unmet: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ManufacturerCapability:
    manufacturer_id: str
    capability_type: str
    payload: Mapping[str, Any]
    technical_score: float = 70.0
    verification_multiplier: float = 1.0
    sponsored: bool = False


@dataclass(frozen=True, slots=True)
class ManufacturerMatch:
    manufacturer_id: str
    total_score: float
    technical_fit_score: float
    verification_multiplier: float
    capability_coverage: CapabilityCoverage
    accepts_quantity_range: bool
    estimated_lead_time_days: int | None = None
    sponsored: bool = False


class ProblemFirstMatchingService:
    """Case requirements filter manufacturer capabilities, never the reverse."""

    def derive_required_capabilities(self, case: Mapping[str, Any]) -> list[CapabilityRequirement]:
        requirements = []
        if case.get("engineering_path"):
            requirements.append(CapabilityRequirement("engineering_path", {"engineering_path": case["engineering_path"]}))
        if case.get("sealing_material_family"):
            requirements.append(CapabilityRequirement("material_expertise", {"sealing_material_family": case["sealing_material_family"]}))
        quantity = _quantity(case.get("quantity_requested"))
        if quantity is not None:
            requirements.append(CapabilityRequirement("lot_size_capability", {"quantity_requested": quantity}))
        if case.get("atex_required"):
            requirements.append(CapabilityRequirement("certification", {"atex_capable": True}))
        return requirements

    def match_manufacturers(self, case: Mapping[str, Any], capabilities: Sequence[ManufacturerCapability]) -> list[ManufacturerMatch]:
        requirements = self.derive_required_capabilities(case)
        by_mfr: dict[str, list[ManufacturerCapability]] = {}
        for capability in capabilities:
            by_mfr.setdefault(capability.manufacturer_id, []).append(capability)
        matches: list[ManufacturerMatch] = []
        for manufacturer_id, claims in by_mfr.items():
            coverage = _coverage(requirements, claims)
            if coverage.unmet:
                continue
            base = sum(claim.technical_score for claim in claims) / max(1, len(claims))
            multiplier = min(1.1, max(0.9, sum(claim.verification_multiplier for claim in claims) / max(1, len(claims))))
            quantity_ok = "lot_size_capability" in coverage.met or _quantity(case.get("quantity_requested")) is None
            matches.append(ManufacturerMatch(manufacturer_id, round(base * multiplier, 2), base, multiplier, coverage, quantity_ok, sponsored=False))
        return sorted(matches, key=lambda match: match.total_score, reverse=True)


def _coverage(requirements: Sequence[CapabilityRequirement], claims: Sequence[ManufacturerCapability]) -> CapabilityCoverage:
    met: list[str] = []
    unmet: list[str] = []
    for requirement in requirements:
        if any(_claim_satisfies(requirement, claim) for claim in claims):
            met.append(requirement.requirement_type)
        else:
            unmet.append(requirement.requirement_type)
    return CapabilityCoverage(tuple(met), tuple(unmet))


def _claim_satisfies(requirement: CapabilityRequirement, claim: ManufacturerCapability) -> bool:
    if requirement.requirement_type == "engineering_path":
        return claim.payload.get("engineering_path") == requirement.payload.get("engineering_path")
    if requirement.requirement_type == "material_expertise":
        return claim.payload.get("sealing_material_family") == requirement.payload.get("sealing_material_family")
    if requirement.requirement_type == "certification":
        return bool(claim.payload.get("atex_capable")) is True
    if requirement.requirement_type == "lot_size_capability":
        quantity = int(requirement.payload["quantity_requested"])
        minimum = int(claim.payload.get("minimum_order_pieces") or 1)
        maximum = claim.payload.get("maximum_order_pieces")
        if quantity <= 10 and claim.payload.get("accepts_single_pieces") is not True:
            return False
        return minimum <= quantity and (maximum is None or int(maximum) >= quantity)
    return claim.capability_type == requirement.requirement_type


def _quantity(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        raw = raw.get("pieces")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
