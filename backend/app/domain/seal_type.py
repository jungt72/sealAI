"""Stable v0.8.3 SealFamily / SealType normalization primitives.

This module is deterministic and side-effect free. It produces read-only
projection facts for S-SEAL-001; it does not persist seal type authority and
does not confirm engineering truth.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class SealFamily(str, Enum):
    static_elastomer = "static_elastomer"
    flat_gasket = "flat_gasket"
    rotary_shaft = "rotary_shaft"
    mechanical_face = "mechanical_face"
    hydraulic = "hydraulic"
    pneumatic = "pneumatic"
    packing = "packing"
    metal_seal = "metal_seal"
    custom_profile = "custom_profile"
    unknown = "unknown"


class SealType(str, Enum):
    o_ring = "o_ring"
    x_ring = "x_ring"
    backup_ring = "backup_ring"
    flat_gasket = "flat_gasket"
    flange_gasket = "flange_gasket"
    profile_gasket = "profile_gasket"
    bonded_seal = "bonded_seal"
    clamp_gasket = "clamp_gasket"
    radial_shaft_seal = "radial_shaft_seal"
    cassette_seal = "cassette_seal"
    v_ring = "v_ring"
    rotary_lip_seal = "rotary_lip_seal"
    rotary_swivel_seal = "rotary_swivel_seal"
    mechanical_seal = "mechanical_seal"
    hydraulic_rod_seal = "hydraulic_rod_seal"
    hydraulic_piston_seal = "hydraulic_piston_seal"
    hydraulic_wiper = "hydraulic_wiper"
    hydraulic_guide_ring = "hydraulic_guide_ring"
    hydraulic_buffer_seal = "hydraulic_buffer_seal"
    pneumatic_rod_seal = "pneumatic_rod_seal"
    pneumatic_piston_seal = "pneumatic_piston_seal"
    u_cup = "u_cup"
    chevron_packing = "chevron_packing"
    gland_packing = "gland_packing"
    valve_stem_seal = "valve_stem_seal"
    expansion_joint_seal = "expansion_joint_seal"
    spring_energized_seal = "spring_energized_seal"
    metal_seal = "metal_seal"
    custom_profile = "custom_profile"
    molded_seal = "molded_seal"
    fabric_reinforced_seal = "fabric_reinforced_seal"
    unknown_seal = "unknown_seal"


@dataclass(frozen=True, slots=True)
class SealTypeNormalizationResult:
    """Code-level projection facts for S-SEAL-001."""

    seal_family: SealFamily
    seal_type: SealType
    confidence: float
    matched_alias: str | None = None
    source: str = "seal_type_normalizer"
    notes: tuple[str, ...] = ()
    ambiguous: bool = False
    candidate_types: tuple[SealType, ...] = ()

    @property
    def confidence_band(self) -> str:
        if self.confidence >= 0.85:
            return "high"
        if self.confidence >= 0.55:
            return "medium"
        return "low"

    @property
    def event_names(self) -> tuple[str, ...]:
        if self.seal_type is SealType.unknown_seal:
            return ("SealTypeRemainsUnknown",)
        return (
            "SealTypeCandidateDetected",
            "SealTypeNormalized",
            "SealApplicationProfileUpdated",
        )


@dataclass(frozen=True, slots=True)
class _AliasRule:
    pattern: re.Pattern[str]
    seal_type: SealType
    matched_alias: str
    confidence: float = 0.9


def normalize_seal_type(
    text: str | None,
    *,
    context: Mapping[str, Any] | None = None,
) -> SealTypeNormalizationResult:
    """Normalize a seal-system alias into a conservative SealType projection."""

    text_norm = _normalize_text(text)
    context_norm = _normalize_context(context)
    combined = " ".join(item for item in (text_norm, context_norm) if item)
    weak_hint = _weak_engineering_path_hint(context)

    explicit_result = _match_explicit_text(text_norm)
    if explicit_result is not None:
        return _with_weak_hint_note(explicit_result, weak_hint)

    contextual_result = _match_context_sensitive_text(text_norm, context_norm)
    if contextual_result is not None:
        return _with_weak_hint_note(contextual_result, weak_hint)

    context_result = _match_explicit_text(combined)
    if context_result is not None:
        return _with_note(
            _with_weak_hint_note(context_result, weak_hint),
            "seal type inferred from projection context, not user-confirmed",
        )

    if weak_hint is not None:
        return SealTypeNormalizationResult(
            seal_family=seal_family_for_type(weak_hint),
            seal_type=weak_hint,
            confidence=0.45,
            matched_alias=None,
            source="weak_engineering_path_hint",
            notes=("weak legacy engineering_path hint only",),
            ambiguous=True,
            candidate_types=(weak_hint,),
        )

    return SealTypeNormalizationResult(
        seal_family=SealFamily.unknown,
        seal_type=SealType.unknown_seal,
        confidence=0.1,
        source="seal_type_normalizer",
        notes=("no reliable seal type alias detected",),
    )


def seal_family_for_type(seal_type: SealType | str) -> SealFamily:
    coerced = _coerce_seal_type(seal_type)
    return _SEAL_TYPE_TO_FAMILY.get(coerced, SealFamily.unknown)


def type_specific_missing_hints_for_type(seal_type: SealType | str) -> tuple[str, ...]:
    coerced = _coerce_seal_type(seal_type)
    return _TYPE_SPECIFIC_MISSING_HINTS.get(coerced, ())


def _match_explicit_text(text: str) -> SealTypeNormalizationResult | None:
    if not text:
        return None

    for rule in _EXPLICIT_ALIAS_RULES:
        if rule.pattern.search(text):
            return SealTypeNormalizationResult(
                seal_family=seal_family_for_type(rule.seal_type),
                seal_type=rule.seal_type,
                confidence=rule.confidence,
                matched_alias=rule.matched_alias,
                candidate_types=(rule.seal_type,),
            )
    return None


def _match_context_sensitive_text(
    text: str, context_text: str
) -> SealTypeNormalizationResult | None:
    if not text:
        return None

    if _matches(text, r"\b(hydraulikdichtung|hydraulic\s+seal)\b"):
        return _family_ambiguous(
            SealFamily.hydraulic,
            "hydraulic seal",
            (
                SealType.hydraulic_rod_seal,
                SealType.hydraulic_piston_seal,
                SealType.hydraulic_wiper,
                SealType.hydraulic_guide_ring,
            ),
        )
    if _matches(text, r"\b(pneumatikdichtung|pneumatic\s+seal)\b"):
        return _family_ambiguous(
            SealFamily.pneumatic,
            "pneumatic seal",
            (SealType.pneumatic_rod_seal, SealType.pneumatic_piston_seal),
        )
    if _matches(text, r"\b(stangendichtung|rod\s+seal)\b"):
        if _has_pneumatic_context(context_text):
            return _confident(SealType.pneumatic_rod_seal, "rod seal")
        if _has_hydraulic_context(context_text):
            return _confident(SealType.hydraulic_rod_seal, "rod seal")
        return _unknown_ambiguous(
            "rod seal",
            (SealType.hydraulic_rod_seal, SealType.pneumatic_rod_seal),
        )
    if _matches(text, r"\b(kolbendichtung|piston\s+seal)\b"):
        if _has_pneumatic_context(context_text):
            return _confident(SealType.pneumatic_piston_seal, "piston seal")
        if _has_hydraulic_context(context_text):
            return _confident(SealType.hydraulic_piston_seal, "piston seal")
        return _unknown_ambiguous(
            "piston seal",
            (SealType.hydraulic_piston_seal, SealType.pneumatic_piston_seal),
        )
    return None


def _confident(seal_type: SealType, matched_alias: str) -> SealTypeNormalizationResult:
    return SealTypeNormalizationResult(
        seal_family=seal_family_for_type(seal_type),
        seal_type=seal_type,
        confidence=0.9,
        matched_alias=matched_alias,
        candidate_types=(seal_type,),
    )


def _family_ambiguous(
    seal_family: SealFamily,
    matched_alias: str,
    candidate_types: tuple[SealType, ...],
) -> SealTypeNormalizationResult:
    return SealTypeNormalizationResult(
        seal_family=seal_family,
        seal_type=SealType.unknown_seal,
        confidence=0.5,
        matched_alias=matched_alias,
        notes=("family detected, exact seal type still open",),
        ambiguous=True,
        candidate_types=candidate_types,
    )


def _unknown_ambiguous(
    matched_alias: str,
    candidate_types: tuple[SealType, ...],
) -> SealTypeNormalizationResult:
    return SealTypeNormalizationResult(
        seal_family=SealFamily.unknown,
        seal_type=SealType.unknown_seal,
        confidence=0.45,
        matched_alias=matched_alias,
        notes=("alias requires hydraulic or pneumatic context",),
        ambiguous=True,
        candidate_types=candidate_types,
    )


def _with_weak_hint_note(
    result: SealTypeNormalizationResult,
    weak_hint: SealType | None,
) -> SealTypeNormalizationResult:
    if weak_hint is None or weak_hint is result.seal_type:
        return result
    candidates = tuple(dict.fromkeys((*result.candidate_types, weak_hint)))
    return SealTypeNormalizationResult(
        seal_family=result.seal_family,
        seal_type=result.seal_type,
        confidence=result.confidence,
        matched_alias=result.matched_alias,
        source=result.source,
        notes=(
            *result.notes,
            f"explicit alias preferred over weak engineering_path hint: {weak_hint.value}",
        ),
        ambiguous=True,
        candidate_types=candidates,
    )


def _with_note(
    result: SealTypeNormalizationResult,
    note: str,
) -> SealTypeNormalizationResult:
    return SealTypeNormalizationResult(
        seal_family=result.seal_family,
        seal_type=result.seal_type,
        confidence=min(result.confidence, 0.75),
        matched_alias=result.matched_alias,
        source=result.source,
        notes=(*result.notes, note),
        ambiguous=result.ambiguous,
        candidate_types=result.candidate_types,
    )


def _weak_engineering_path_hint(context: Mapping[str, Any] | None) -> SealType | None:
    if not isinstance(context, Mapping):
        return None
    raw = (
        context.get("engineering_path")
        or _mapping_value(context.get("routing"), "engineering_path")
        or _mapping_value(context.get("routing"), "path")
    )
    value = _normalize_text(raw)
    if value == "rwdr":
        return SealType.radial_shaft_seal
    if value == "ms_pump":
        return SealType.mechanical_seal
    return None


def _mapping_value(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, Mapping) else None


def _normalize_context(context: Mapping[str, Any] | None) -> str:
    if not isinstance(context, Mapping):
        return ""
    return _normalize_text(" ".join(_iter_context_values(context)))


def _iter_context_values(value: Any) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key) in {"engineering_path", "path"}:
                continue
            yield from _iter_context_values(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_context_values(item)
        return
    yield str(value)


def _normalize_text(value: Any) -> str:
    text = str(value or "").replace("®", "").casefold()
    text = re.sub(r"[_/]+", " ", text)
    return " ".join(text.split())


def _matches(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE | re.UNICODE) is not None


def _has_hydraulic_context(text: str) -> bool:
    return _matches(text, r"\b(hydraul|hydraulic|hydraulik|zylinder|cylinder)\w*\b")


def _has_pneumatic_context(text: str) -> bool:
    return _matches(text, r"\b(pneumat|pneumatic|pneumatik)\w*\b")


def _coerce_seal_type(value: SealType | str) -> SealType:
    if isinstance(value, SealType):
        return value
    try:
        return SealType(str(value))
    except ValueError:
        return SealType.unknown_seal


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE | re.UNICODE)


_EXPLICIT_ALIAS_RULES: tuple[_AliasRule, ...] = (
    _AliasRule(
        _compile(r"\b(radialwellendichtring|wellendichtring|rwdr|wdr|simmerring)\b"),
        SealType.radial_shaft_seal,
        "radial shaft seal",
    ),
    _AliasRule(
        _compile(r"\b(oil\s+seal|rotary\s+lip\s+seal|shaft\s+seal)\b"),
        SealType.radial_shaft_seal,
        "radial shaft seal",
    ),
    _AliasRule(
        _compile(r"\b(flanschdichtung|flange\s+gasket)\b"),
        SealType.flange_gasket,
        "flange gasket",
    ),
    _AliasRule(
        _compile(r"\b(flachdichtung|flat\s+gasket|cut\s+gasket|gasket)\b"),
        SealType.flat_gasket,
        "flat gasket",
    ),
    _AliasRule(_compile(r"\b(abstreifer|wiper\s+seal)\b"), SealType.hydraulic_wiper, "wiper seal"),
    _AliasRule(_compile(r"\b(f[uü]hrungsring|guide\s+ring)\b"), SealType.hydraulic_guide_ring, "guide ring"),
    _AliasRule(_compile(r"\b(pneumatic\s+rod\s+seal)\b"), SealType.pneumatic_rod_seal, "pneumatic rod seal"),
    _AliasRule(_compile(r"\b(pneumatic\s+piston\s+seal)\b"), SealType.pneumatic_piston_seal, "pneumatic piston seal"),
    _AliasRule(_compile(r"\b(o-?\s*ring|oring)\b"), SealType.o_ring, "o-ring"),
    _AliasRule(_compile(r"\b(x-?\s*ring|quad\s+ring)\b"), SealType.x_ring, "x-ring"),
    _AliasRule(
        _compile(r"\b(gleitringdichtung|mechanical\s+seal|face\s+seal)\b"),
        SealType.mechanical_seal,
        "mechanical seal",
    ),
    _AliasRule(
        _compile(r"\b(stopfbuchspackung|gland\s+packing|compression\s+packing)\b"),
        SealType.gland_packing,
        "gland packing",
    ),
    _AliasRule(_compile(r"\bpackung\b"), SealType.gland_packing, "packing", 0.75),
    _AliasRule(
        _compile(r"\b(kundenspezifisches\s+profil|sonderprofil|custom\s+profile)\b"),
        SealType.custom_profile,
        "custom profile",
    ),
    _AliasRule(_compile(r"\b(formteildichtung|molded\s+seal)\b"), SealType.molded_seal, "molded seal"),
)


_SEAL_TYPE_TO_FAMILY: dict[SealType, SealFamily] = {
    SealType.o_ring: SealFamily.static_elastomer,
    SealType.x_ring: SealFamily.static_elastomer,
    SealType.backup_ring: SealFamily.static_elastomer,
    SealType.flat_gasket: SealFamily.flat_gasket,
    SealType.flange_gasket: SealFamily.flat_gasket,
    SealType.profile_gasket: SealFamily.flat_gasket,
    SealType.bonded_seal: SealFamily.static_elastomer,
    SealType.clamp_gasket: SealFamily.flat_gasket,
    SealType.radial_shaft_seal: SealFamily.rotary_shaft,
    SealType.cassette_seal: SealFamily.rotary_shaft,
    SealType.v_ring: SealFamily.rotary_shaft,
    SealType.rotary_lip_seal: SealFamily.rotary_shaft,
    SealType.rotary_swivel_seal: SealFamily.rotary_shaft,
    SealType.mechanical_seal: SealFamily.mechanical_face,
    SealType.hydraulic_rod_seal: SealFamily.hydraulic,
    SealType.hydraulic_piston_seal: SealFamily.hydraulic,
    SealType.hydraulic_wiper: SealFamily.hydraulic,
    SealType.hydraulic_guide_ring: SealFamily.hydraulic,
    SealType.hydraulic_buffer_seal: SealFamily.hydraulic,
    SealType.pneumatic_rod_seal: SealFamily.pneumatic,
    SealType.pneumatic_piston_seal: SealFamily.pneumatic,
    SealType.u_cup: SealFamily.hydraulic,
    SealType.chevron_packing: SealFamily.packing,
    SealType.gland_packing: SealFamily.packing,
    SealType.valve_stem_seal: SealFamily.packing,
    SealType.expansion_joint_seal: SealFamily.custom_profile,
    SealType.spring_energized_seal: SealFamily.custom_profile,
    SealType.metal_seal: SealFamily.metal_seal,
    SealType.custom_profile: SealFamily.custom_profile,
    SealType.molded_seal: SealFamily.custom_profile,
    SealType.fabric_reinforced_seal: SealFamily.custom_profile,
    SealType.unknown_seal: SealFamily.unknown,
}


_TYPE_SPECIFIC_MISSING_HINTS: dict[SealType, tuple[str, ...]] = {
    SealType.radial_shaft_seal: (
        "shaft_diameter",
        "housing_bore",
        "width",
        "speed_rpm",
        "medium",
        "temperature",
        "pressure_or_pressure_difference",
        "shaft_surface",
        "installation_direction",
    ),
    SealType.flat_gasket: (
        "flange_standard",
        "flange_size_or_dimensions",
        "inner_outer_diameter",
        "hole_pattern",
        "pressure",
        "temperature",
        "medium",
        "gasket_material",
        "thickness",
        "bolt_load_or_torque",
        "surface_roughness",
        "certification_requirement",
    ),
    SealType.flange_gasket: (
        "flange_standard",
        "flange_size_or_dimensions",
        "inner_outer_diameter",
        "hole_pattern",
        "pressure",
        "temperature",
        "medium",
        "gasket_material",
        "thickness",
        "bolt_load_or_torque",
        "surface_roughness",
        "certification_requirement",
    ),
    SealType.hydraulic_rod_seal: (
        "rod_or_piston_diameter",
        "groove_dimensions",
        "pressure",
        "pressure_peaks",
        "hydraulic_fluid",
        "temperature",
        "speed_or_stroke",
        "single_or_double_acting",
        "contamination",
        "wiper_or_guide_required",
        "water_content",
    ),
    SealType.hydraulic_piston_seal: (
        "rod_or_piston_diameter",
        "groove_dimensions",
        "pressure",
        "pressure_peaks",
        "hydraulic_fluid",
        "temperature",
        "speed_or_stroke",
        "single_or_double_acting",
        "contamination",
        "wiper_or_guide_required",
        "water_content",
    ),
    SealType.hydraulic_wiper: (
        "rod_or_piston_diameter",
        "groove_dimensions",
        "stroke",
        "contamination",
        "water_content",
        "temperature",
        "hydraulic_fluid",
    ),
    SealType.hydraulic_guide_ring: (
        "rod_or_piston_diameter",
        "groove_dimensions",
        "load_direction",
        "stroke",
        "hydraulic_fluid",
        "temperature",
        "contamination",
    ),
    SealType.hydraulic_buffer_seal: (
        "rod_or_piston_diameter",
        "groove_dimensions",
        "pressure",
        "pressure_peaks",
        "hydraulic_fluid",
        "temperature",
        "speed_or_stroke",
    ),
    SealType.mechanical_seal: (
        "pump_or_aggregate_type",
        "shaft_diameter",
        "medium",
        "pressure",
        "temperature",
        "speed",
        "viscosity",
        "solids_or_gas_content",
        "single_or_double_seal",
        "flush_or_barrier_fluid",
        "atex_or_leakage_requirement",
    ),
    SealType.o_ring: (
        "inner_diameter",
        "cross_section",
        "groove_dimensions",
        "material",
        "hardness",
        "medium",
        "temperature",
        "pressure",
        "static_or_dynamic",
        "squeeze_or_stretch",
        "backup_ring_required",
        "certification_requirement",
    ),
    SealType.x_ring: (
        "inner_diameter",
        "cross_section",
        "groove_dimensions",
        "material",
        "hardness",
        "medium",
        "temperature",
        "pressure",
        "static_or_dynamic",
        "squeeze_or_stretch",
        "certification_requirement",
    ),
    SealType.backup_ring: (
        "inner_diameter",
        "cross_section",
        "groove_dimensions",
        "material",
        "pressure",
        "temperature",
        "medium",
    ),
    SealType.pneumatic_rod_seal: (
        "rod_or_piston_diameter",
        "groove_dimensions",
        "pressure",
        "temperature",
        "speed_or_stroke",
        "air_quality",
        "lubrication",
        "friction_requirement",
    ),
    SealType.pneumatic_piston_seal: (
        "rod_or_piston_diameter",
        "groove_dimensions",
        "pressure",
        "temperature",
        "speed_or_stroke",
        "air_quality",
        "lubrication",
        "friction_requirement",
    ),
    SealType.gland_packing: (
        "shaft_or_stem_diameter",
        "stuffing_box_dimensions",
        "medium",
        "temperature",
        "pressure",
        "speed",
        "lubrication_or_flush",
    ),
}


assert set(_SEAL_TYPE_TO_FAMILY) == set(SealType)
