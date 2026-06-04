from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.services.capability_service import ManufacturerCapabilityProfile


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

    def capabilities_from_profiles(
        self,
        profiles: Sequence[ManufacturerCapabilityProfile],
    ) -> list[ManufacturerCapability]:
        capabilities: list[ManufacturerCapability] = []
        for profile in profiles:
            score, multiplier = _profile_scores(profile)
            for seal_type in profile.supported_seal_types:
                capabilities.append(
                    ManufacturerCapability(
                        profile.manufacturer_id,
                        "engineering_path",
                        {"engineering_path": seal_type},
                        technical_score=score,
                        verification_multiplier=multiplier,
                    )
                )
            for material in profile.supported_material_families:
                capabilities.append(
                    ManufacturerCapability(
                        profile.manufacturer_id,
                        "material_expertise",
                        {"sealing_material_family": material},
                        technical_score=score,
                        verification_multiplier=multiplier,
                    )
                )
            capabilities.append(
                ManufacturerCapability(
                    profile.manufacturer_id,
                    "certification",
                    {"atex_capable": profile.atex_capable is True},
                    technical_score=score,
                    verification_multiplier=multiplier,
                )
            )
            capabilities.append(
                ManufacturerCapability(
                    profile.manufacturer_id,
                    "lot_size_capability",
                    {
                        "minimum_order_pieces": (
                            1 if profile.small_quantity_capable else 11
                        ),
                        "maximum_order_pieces": None,
                        "accepts_single_pieces": profile.small_quantity_capable is True,
                    },
                    technical_score=score,
                    verification_multiplier=multiplier,
                )
            )
        return capabilities

    def match_manufacturer_profiles(
        self,
        case: Mapping[str, Any],
        profiles: Sequence[ManufacturerCapabilityProfile],
    ) -> list[ManufacturerMatch]:
        return self.match_manufacturers(case, self.capabilities_from_profiles(profiles))

    def derive_required_capabilities(
        self, case: Mapping[str, Any]
    ) -> list[CapabilityRequirement]:
        requirements = []
        if case.get("engineering_path"):
            requirements.append(
                CapabilityRequirement(
                    "engineering_path", {"engineering_path": case["engineering_path"]}
                )
            )
        if case.get("sealing_material_family"):
            requirements.append(
                CapabilityRequirement(
                    "material_expertise",
                    {"sealing_material_family": case["sealing_material_family"]},
                )
            )
        quantity = _quantity(case.get("quantity_requested"))
        if quantity is not None:
            requirements.append(
                CapabilityRequirement(
                    "lot_size_capability", {"quantity_requested": quantity}
                )
            )
        if case.get("atex_required"):
            requirements.append(
                CapabilityRequirement("certification", {"atex_capable": True})
            )
        return requirements

    def match_manufacturers(
        self, case: Mapping[str, Any], capabilities: Sequence[ManufacturerCapability]
    ) -> list[ManufacturerMatch]:
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
            multiplier = min(
                1.1,
                max(
                    0.9,
                    sum(claim.verification_multiplier for claim in claims)
                    / max(1, len(claims)),
                ),
            )
            quantity_ok = (
                "lot_size_capability" in coverage.met
                or _quantity(case.get("quantity_requested")) is None
            )
            sponsored = any(claim.sponsored for claim in claims)
            matches.append(
                ManufacturerMatch(
                    manufacturer_id,
                    round(base * multiplier, 2),
                    base,
                    multiplier,
                    coverage,
                    quantity_ok,
                    sponsored=sponsored,
                )
            )
        return sorted(matches, key=lambda match: match.total_score, reverse=True)


def _coverage(
    requirements: Sequence[CapabilityRequirement],
    claims: Sequence[ManufacturerCapability],
) -> CapabilityCoverage:
    met: list[str] = []
    unmet: list[str] = []
    for requirement in requirements:
        if any(_claim_satisfies(requirement, claim) for claim in claims):
            met.append(requirement.requirement_type)
        else:
            unmet.append(requirement.requirement_type)
    return CapabilityCoverage(tuple(met), tuple(unmet))


def _claim_satisfies(
    requirement: CapabilityRequirement, claim: ManufacturerCapability
) -> bool:
    if requirement.requirement_type == "engineering_path":
        return claim.payload.get("engineering_path") == requirement.payload.get(
            "engineering_path"
        )
    if requirement.requirement_type == "material_expertise":
        return claim.payload.get("sealing_material_family") == requirement.payload.get(
            "sealing_material_family"
        )
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


def _profile_scores(profile: ManufacturerCapabilityProfile) -> tuple[float, float]:
    gap_penalty = min(30.0, len(profile.open_profile_gaps) * 4.0)
    score = max(50.0, 92.0 - gap_penalty)
    multiplier_by_evidence = {
        "verified": 1.1,
        "documented": 1.03,
        "self_declared": 0.97,
        "weak": 0.9,
        "unknown": 0.9,
    }
    return score, multiplier_by_evidence.get(profile.evidence_level, 0.9)
