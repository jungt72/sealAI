"""P5 Procurement Engine Node for SEALAI v4.4.0 (Sprint 8).

Pure Python — no LLM (R1 enforced). Implements 4-stage partner matching
and generates an RFQ-PDF via Jinja2 StrictUndefined (R2 enforced).

Matching stages:
  Stage 1 (MUST): is_paying_partner == True
  Stage 2 (MUST): seal_family in partner.supported_bauformen
  Stage 3 (SHOULD): medium in partner.supported_media AND
                    pressure_max_bar <= partner.pressure_max_bar
  Stage 4 (NICE):  sort by delivery_days ASC (fastest first)

Fallback: if Stage 1 or Stage 2 yields 0 candidates, fallback=True and a
neutral PDF (no partner branding) is rendered.

Watermark: if state.is_critical_application == True, the RFQ-PDF includes
a hardcoded critical-application warning block.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

import structlog
from jinja2 import UndefinedError
from pydantic import BaseModel, ConfigDict, Field

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.jinja import render_template

logger = structlog.get_logger("rag.nodes.p5_procurement")

_RFQ_TEMPLATE_NAME = "rfq_template.j2"


# ---------------------------------------------------------------------------
# Partner data model
# ---------------------------------------------------------------------------


class PartnerRecord(BaseModel):
    """A registered partner in the procurement network."""

    partner_id: str
    name: str
    is_paying_partner: bool
    supported_bauformen: List[str]  # e.g. ["Spiraldichtung", "Kammprofil", "Flachdichtung"]
    supported_media: List[str]      # e.g. ["steam", "gas", "liquid", "H2", "O2"]
    pressure_max_bar: float         # Maximum pressure the partner can handle
    locations: List[str]            # ISO country codes, e.g. ["DE", "AT"]
    delivery_days: int              # Typical delivery time in calendar days

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Static partner registry (hardcoded for demo/test — no DB dependency)
# ---------------------------------------------------------------------------

_PARTNER_REGISTRY: List[PartnerRecord] = [
    PartnerRecord(
        partner_id="P001",
        name="Müller Dichtungstechnik GmbH",
        is_paying_partner=True,
        supported_bauformen=["Spiraldichtung", "Kammprofil", "Flachdichtung"],
        supported_media=["steam", "gas", "liquid", "water"],
        pressure_max_bar=200.0,
        locations=["DE"],
        delivery_days=7,
    ),
    PartnerRecord(
        partner_id="P002",
        name="Alpine Seals AG",
        is_paying_partner=True,
        supported_bauformen=["Spiraldichtung", "O-Ring"],
        supported_media=["H2", "O2", "gas", "liquid"],
        pressure_max_bar=500.0,
        locations=["AT", "CH"],
        delivery_days=10,
    ),
    PartnerRecord(
        partner_id="P003",
        name="NonPaying Partner KG",
        is_paying_partner=False,
        supported_bauformen=["Spiraldichtung"],
        supported_media=["steam"],
        pressure_max_bar=100.0,
        locations=["DE"],
        delivery_days=5,
    ),
    PartnerRecord(
        partner_id="P004",
        name="TechSeal BV",
        is_paying_partner=True,
        supported_bauformen=["PTFE-Dichtung", "Flachdichtung"],
        supported_media=["liquid", "steam"],
        pressure_max_bar=150.0,
        locations=["DE", "NL"],
        delivery_days=14,
    ),
    PartnerRecord(
        partner_id="P005",
        name="FastSeal GmbH",
        is_paying_partner=True,
        supported_bauformen=["Spiraldichtung", "Kammprofil", "Flachdichtung", "O-Ring", "PTFE-Dichtung"],
        supported_media=["steam", "gas", "liquid", "water", "H2", "O2"],
        pressure_max_bar=300.0,
        locations=["DE"],
        delivery_days=3,
    ),
]


# ---------------------------------------------------------------------------
# Procurement result model
# ---------------------------------------------------------------------------


class ProcurementResult(BaseModel):
    """Output of the 4-stage partner matching process."""

    matched_partners: List[PartnerRecord] = Field(default_factory=list)
    fallback: bool = False
    stages_completed: int = 0  # 0 = no MUST stages passed; 1 = stage1 only; 2 = stage1+2; 3 = +SHOULD
    fallback_reason: str = ""
    warning: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 4-Stage matching logic
# ---------------------------------------------------------------------------


def _match_stage1_paying(candidates: List[PartnerRecord]) -> List[PartnerRecord]:
    """Stage 1 (MUST): only paying partners."""
    return [p for p in candidates if p.is_paying_partner]


def _match_stage2_bauform(
    candidates: List[PartnerRecord],
    seal_family: Optional[str],
) -> List[PartnerRecord]:
    """Stage 2 (MUST): partner must support the requested Bauform (case-insensitive)."""
    if not seal_family:
        return []
    needle = seal_family.strip().lower()
    return [
        p for p in candidates
        if any(b.strip().lower() == needle for b in p.supported_bauformen)
    ]


def _match_stage3_medium_druck(
    candidates: List[PartnerRecord],
    medium: Optional[str],
    pressure_max_bar: Optional[float],
) -> List[PartnerRecord]:
    """Stage 3 (SHOULD): prefer partners that handle the medium and pressure.

    Non-blocking: if no candidate passes this filter, all Stage-2 survivors
    are returned with a warning (so Stage 4 still has something to sort).
    """
    if not candidates:
        return candidates

    filtered: List[PartnerRecord] = []
    for p in candidates:
        medium_ok = (
            medium is None
            or any(m.strip().lower() == medium.strip().lower() for m in p.supported_media)
        )
        pressure_ok = pressure_max_bar is None or pressure_max_bar <= p.pressure_max_bar
        if medium_ok and pressure_ok:
            filtered.append(p)

    return filtered if filtered else candidates  # keep all if SHOULD yields nothing


def _match_stage4_geo(candidates: List[PartnerRecord]) -> List[PartnerRecord]:
    """Stage 4 (NICE): sort by delivery_days ascending (fastest first)."""
    return sorted(candidates, key=lambda p: p.delivery_days)


def run_procurement_matching(
    seal_family: Optional[str],
    medium: Optional[str],
    pressure_max_bar: Optional[float],
    *,
    registry: Optional[List[PartnerRecord]] = None,
) -> ProcurementResult:
    """Execute all 4 stages and return a ProcurementResult."""
    candidates: List[PartnerRecord] = list(_PARTNER_REGISTRY if registry is None else registry)

    # Stage 1: MUST — paying partner
    stage1 = _match_stage1_paying(candidates)
    if not stage1:
        return ProcurementResult(
            matched_partners=[],
            fallback=True,
            stages_completed=0,
            fallback_reason="Keine zahlenden Partner im Netzwerk",
        )

    # Stage 2: MUST — Bauform
    stage2 = _match_stage2_bauform(stage1, seal_family)
    if not stage2:
        return ProcurementResult(
            matched_partners=[],
            fallback=True,
            stages_completed=1,
            fallback_reason=f"Kein Partner unterstützt Bauform '{seal_family or 'unbekannt'}'",
        )

    # Stage 3: SHOULD — Medium/Druck
    stage3 = _match_stage3_medium_druck(stage2, medium, pressure_max_bar)
    warning: Optional[str] = None
    stages_reached = 2
    if stage3 != stage2:
        # SHOULD filter was effective
        stages_reached = 3
    else:
        # SHOULD returned all Stage-2 survivors (either all passed or none — check which)
        strict_filtered = [
            p for p in stage2
            if (
                (medium is None or any(m.strip().lower() == (medium or "").strip().lower() for m in p.supported_media))
                and (pressure_max_bar is None or pressure_max_bar <= p.pressure_max_bar)
            )
        ]
        if strict_filtered:
            stages_reached = 3
        else:
            warning = (
                f"Kein Partner mit Medien/Druckfreigabe für '{medium or '?'}' / "
                f"{pressure_max_bar or '?'} bar — alle Stage-2-Partner aufgeführt"
            )

    # Stage 4: NICE — sort by delivery_days
    final = _match_stage4_geo(stage3)

    return ProcurementResult(
        matched_partners=final,
        fallback=False,
        stages_completed=stages_reached,
        fallback_reason="",
        warning=warning,
    )


# ---------------------------------------------------------------------------
# RFQ PDF rendering
# ---------------------------------------------------------------------------


def _build_rfq_template_context(
    result: ProcurementResult,
    state: SealAIState,
) -> Dict[str, Any]:
    """Build Jinja2 context dict for rfq_template.j2."""
    wp = state.working_profile
    calc = state.calculation_result or {}

    # WorkingProfile fields
    medium = (wp.medium if wp else None) or "nicht angegeben"
    pressure_max_bar = (wp.pressure_max_bar if wp else None) or calc.get("pressure_max_bar") or "n/a"
    temperature_max_c = (wp.temperature_max_c if wp else None) or calc.get("temperature_max_c") or "n/a"
    flange_standard = (wp.flange_standard if wp else None) or "n/a"
    flange_dn = (wp.flange_dn if wp else None) or "n/a"
    flange_pn = wp.flange_pn if wp else None
    flange_class = wp.flange_class if wp else None
    bolt_count = (wp.bolt_count if wp else None) or "n/a"
    bolt_size = (wp.bolt_size if wp else None) or "n/a"
    cyclic_load = (wp.cyclic_load if wp else False)
    emission_class = (wp.emission_class if wp else None) or ""
    industry_sector = (wp.industry_sector if wp else None) or ""

    # flange_pn_or_class for display
    if flange_pn:
        flange_pn_or_class = f"PN {flange_pn}"
    elif flange_class:
        flange_pn_or_class = f"Class {flange_class}"
    else:
        flange_pn_or_class = "n/a"

    # CalcOutput fields
    gasket_inner_d_mm = calc.get("gasket_inner_d_mm", "n/a")
    gasket_outer_d_mm = calc.get("gasket_outer_d_mm", "n/a")
    required_gasket_stress_mpa = calc.get("required_gasket_stress_mpa", "n/a")
    available_bolt_load_kn = calc.get("available_bolt_load_kn")
    safety_factor = calc.get("safety_factor", "n/a")
    temperature_margin_c = calc.get("temperature_margin_c", "n/a")
    pressure_margin_bar = calc.get("pressure_margin_bar", "n/a")

    # Matched partners as plain dicts (for template iteration)
    matched_partners_dicts = [p.model_dump() for p in result.matched_partners]

    return {
        # Watermark flag
        "is_critical_application": state.is_critical_application,
        # WorkingProfile
        "medium": medium,
        "pressure_max_bar": pressure_max_bar,
        "temperature_max_c": temperature_max_c,
        "flange_standard": flange_standard,
        "flange_dn": flange_dn,
        "flange_pn_or_class": flange_pn_or_class,
        "bolt_count": bolt_count,
        "bolt_size": bolt_size,
        "cyclic_load": cyclic_load,
        "emission_class": emission_class,
        "industry_sector": industry_sector,
        # CalcOutput
        "gasket_inner_d_mm": gasket_inner_d_mm,
        "gasket_outer_d_mm": gasket_outer_d_mm,
        "required_gasket_stress_mpa": required_gasket_stress_mpa,
        "available_bolt_load_kn": available_bolt_load_kn,
        "safety_factor": safety_factor,
        "temperature_margin_c": temperature_margin_c,
        "pressure_margin_bar": pressure_margin_bar,
        # P4.5 Quality Gate
        "critique_log": list(state.critique_log or []),
        # Procurement result
        "matched_partners": matched_partners_dicts,
        "fallback": result.fallback,
        "fallback_reason": result.fallback_reason or "",
        "procurement_warning": result.warning or "",
        # Metadata
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "tenant_id": state.tenant_id or "n/a",
    }


def _render_rfq_pdf(result: ProcurementResult, state: SealAIState) -> str:
    """Render the RFQ document via Jinja2 StrictUndefined (R2 enforced)."""
    ctx = _build_rfq_template_context(result, state)
    return render_template(_RFQ_TEMPLATE_NAME, ctx)


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------


def node_p5_procurement(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """P5 Procurement Engine — 4-stage partner matching + RFQ-PDF generation.

    Reads seal_family, working_profile, calculation_result, critique_log,
    is_critical_application from state.  Returns procurement_result and
    rfq_pdf_text.

    Skips silently (returns minimal state update) if no working_profile and
    no calculation_result is present (e.g. rfq_trigger on cold-start).
    """
    wp = state.working_profile
    calc = state.calculation_result

    logger.info(
        "p5_procurement_start",
        has_working_profile=bool(wp),
        has_calculation_result=bool(calc),
        is_critical=state.is_critical_application,
        run_id=state.run_id,
        thread_id=state.thread_id,
        tenant_id=state.tenant_id,
    )

    # Derive inputs for matching
    seal_family: Optional[str] = state.seal_family
    medium: Optional[str] = wp.medium if wp else None
    pressure_max_bar: Optional[float] = wp.pressure_max_bar if wp else None

    # Run 4-stage matching
    result = run_procurement_matching(
        seal_family=seal_family,
        medium=medium,
        pressure_max_bar=pressure_max_bar,
    )

    logger.info(
        "p5_procurement_matching_done",
        fallback=result.fallback,
        stages_completed=result.stages_completed,
        matched_count=len(result.matched_partners),
        fallback_reason=result.fallback_reason,
        run_id=state.run_id,
    )

    # Render RFQ PDF via Jinja2 StrictUndefined
    rfq_pdf_text: Optional[str] = None
    render_error: Optional[str] = None

    try:
        rfq_pdf_text = _render_rfq_pdf(result, state)
    except UndefinedError as exc:
        render_error = f"P5: Jinja2 template error: {exc}"
        logger.error(
            "p5_rfq_render_undefined",
            error=str(exc),
            template=_RFQ_TEMPLATE_NAME,
            run_id=state.run_id,
        )
    except FileNotFoundError:
        render_error = f"P5: template '{_RFQ_TEMPLATE_NAME}' not found"
        logger.error(
            "p5_rfq_template_not_found",
            template=_RFQ_TEMPLATE_NAME,
            run_id=state.run_id,
        )

    update: Dict[str, Any] = {
        "procurement_result": result.model_dump(),
        "phase": PHASE.PROCUREMENT,
        "last_node": "node_p5_procurement",
    }
    if rfq_pdf_text is not None:
        update["rfq_pdf_text"] = rfq_pdf_text
    if render_error:
        update["error"] = render_error

    return update


__all__ = [
    "PartnerRecord",
    "ProcurementResult",
    "node_p5_procurement",
    "run_procurement_matching",
]
