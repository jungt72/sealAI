"""O-Ring screening geometry calculations.

Relocated out of the v92 core orchestrator (P1-4 PR4 / gap-audit C9): the
governed core no longer carries O-Ring engineering depth. O-Ring is NOT a
DomainPack (it is a shallow stub) — this is the existing real implementation
moved **verbatim**, kept behaviour-identical. The core injects its generic calc
primitives (the float reader, the string reader and the CalculationResult
builder) so this module owns only the O-Ring geometry and never imports back into
the orchestrator (no import cycle).
"""
from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, Callable

from app.agent.v92.models import CalculationResult
from app.mcp.calculations.oring_groove import lookup_nut

# Injected generic calc primitives (owned by the v92 orchestrator core).
FloatValue = Callable[..., "float | None"]
StringValue = Callable[..., str]
CalcResultBuilder = Callable[..., CalculationResult]


def oring_calculations(
    state: Any,
    *,
    snapshot_hash: str,
    float_value: FloatValue,
    string_value: StringValue,
    calc_result: CalcResultBuilder,
) -> list[CalculationResult]:
    cross_section = float_value(
        state,
        "oring_cross_section_mm",
        "cord_diameter_mm",
        "schnurdurchmesser_mm",
        "cross_section_mm",
    )
    groove_depth = float_value(state, "groove_depth_mm", "nuttiefe_mm")
    groove_width = float_value(state, "groove_width_mm", "nutbreite_mm")
    seal_id = float_value(state, "seal_inner_diameter_mm", "oring_inner_diameter_mm", "o_ring_inner_diameter_mm")
    shaft_diameter = float_value(state, "shaft_diameter_mm", "rod_diameter_mm", "bore_diameter_mm")
    radial_gap = float_value(state, "radial_gap_mm", "extrusion_gap_mm")
    pressure = float_value(state, "pressure_at_seal_bar", "pressure_delta_bar")
    results: list[CalculationResult] = []
    if cross_section is None:
        return results
    missing = []
    if pressure is None:
        missing.append("pressure_at_seal_bar")
        pressure = 0.0
    motion = string_value(state, "motion_type", "dynamic_type").lower()
    situation = "dynamisch" if any(marker in motion for marker in ("dynam", "rot", "hub", "rezip")) else "statisch"
    output = asdict(lookup_nut(cross_section, situation, pressure))
    status = "insufficient_data" if missing else "ok"
    notes = [
        "O-ring groove result is a screening calculation; tolerances and installation details still require review."
    ]
    if output.get("hinweis"):
        notes.append(str(output["hinweis"]))
    results.append(
        calc_result(
            calculation_id="oring.groove_screening",
            version="din3770_iso3601_2_metadata_v1",
            calculator="lookup_nut",
            status=status,
            snapshot_hash=snapshot_hash,
            outputs=output,
            units={
                "schnurdurchmesser_mm": "mm",
                "einbausituation": "text",
                "nuttiefe_mm": "mm",
                "nutbreite_mm": "mm",
                "vorpressung_pct": "%",
                "backup_ring_empfohlen": "bool",
                "empfohlene_shore": "text",
                "norm_ref": "text",
                "hinweis": "text",
            },
            missing_inputs=missing,
            dependencies=["oring_cross_section_mm", "pressure_at_seal_bar", "motion_type"],
            formula_refs=["din3770_iso3601_2_metadata_v1.lookup_nut"],
            validity_status="valid_for_screening" if not missing else "input_missing",
            engineering_signals=["o_ring_groove_metadata_screening"],
            notes=notes,
            limitations=["Metadata-backed groove screening; no ISO conformity claim without licensed rule review."],
        )
    )

    if groove_depth is not None and cross_section > 0:
        squeeze = ((cross_section - groove_depth) / cross_section) * 100.0
        status = "warning" if squeeze < 8.0 or squeeze > 30.0 else "ok"
        results.append(
            calc_result(
                calculation_id="oring.squeeze_pct",
                version="oring_geometry_screening_v1",
                calculator="deterministic_geometry",
                status=status,
                snapshot_hash=snapshot_hash,
                outputs={"squeeze_pct": round(squeeze, 2)},
                units={"squeeze_pct": "%"},
                dependencies=["oring_cross_section_mm", "groove_depth_mm"],
                formula_refs=["(cross_section_mm - groove_depth_mm) / cross_section_mm * 100"],
                engineering_signals=["o_ring_squeeze_screening"],
                limitations=["Screening range depends on seal type, elastomer hardness, tolerances and manufacturer data."],
            )
        )
    if groove_depth is not None and groove_width is not None and groove_depth > 0 and groove_width > 0:
        area_seal = math.pi / 4.0 * cross_section**2
        area_groove = groove_depth * groove_width
        gland_fill = area_seal / area_groove * 100.0
        status = "warning" if gland_fill > 85.0 else "ok"
        results.append(
            calc_result(
                calculation_id="oring.gland_fill_pct",
                version="oring_geometry_screening_v1",
                calculator="deterministic_geometry",
                status=status,
                snapshot_hash=snapshot_hash,
                outputs={"gland_fill_pct": round(gland_fill, 2)},
                units={"gland_fill_pct": "%"},
                dependencies=["oring_cross_section_mm", "groove_depth_mm", "groove_width_mm"],
                formula_refs=["(pi/4*cross_section_mm^2)/(groove_depth_mm*groove_width_mm)*100"],
                engineering_signals=["o_ring_gland_fill_screening"],
                limitations=["Thermal expansion and tolerance stack are not included unless supplied separately."],
            )
        )
    if seal_id is not None and shaft_diameter is not None and seal_id > 0:
        stretch = ((shaft_diameter - seal_id) / seal_id) * 100.0
        status = "warning" if stretch > 6.0 or stretch < -1.0 else "ok"
        results.append(
            calc_result(
                calculation_id="oring.stretch_pct",
                version="oring_geometry_screening_v1",
                calculator="deterministic_geometry",
                status=status,
                snapshot_hash=snapshot_hash,
                outputs={"stretch_pct": round(stretch, 2)},
                units={"stretch_pct": "%"},
                dependencies=["seal_inner_diameter_mm", "shaft_diameter_mm"],
                formula_refs=["(shaft_diameter_mm - seal_inner_diameter_mm) / seal_inner_diameter_mm * 100"],
                engineering_signals=["o_ring_stretch_screening"],
                limitations=["Only valid for the supplied installation geometry; confirm whether ID/shaft/bore convention fits the seal case."],
            )
        )
    if radial_gap is not None and pressure is not None:
        severity = "requires_expert_review" if pressure >= 100.0 and radial_gap > 0.2 else "valid_for_screening"
        results.append(
            calc_result(
                calculation_id="oring.extrusion_gap_screening",
                version="oring_extrusion_gap_screening_v1",
                calculator="deterministic_geometry",
                status="warning" if severity == "requires_expert_review" else "ok",
                snapshot_hash=snapshot_hash,
                outputs={
                    "radial_gap_mm": radial_gap,
                    "pressure_at_seal_bar": pressure,
                    "expert_review_required": severity == "requires_expert_review",
                },
                units={"radial_gap_mm": "mm", "pressure_at_seal_bar": "bar", "expert_review_required": "bool"},
                dependencies=["radial_gap_mm", "pressure_at_seal_bar"],
                formula_refs=["pressure_gap_screening_rule_v1"],
                validity_status=severity,
                engineering_signals=["o_ring_extrusion_gap_screening"],
                limitations=["Rule-of-thumb screening only; anti-extrusion ring, hardness and temperature require review."],
            )
        )
    return results
