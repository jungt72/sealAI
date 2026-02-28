"""P5 Procurement Engine with capability-based partner matching.

Pure Python — no LLM (R1 enforced). Implements deterministic partner matching
and generates an RFQ-PDF via Jinja2 StrictUndefined (R2 enforced).
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
    capabilities: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Static partner registry (hardcoded for demo/test — no DB dependency)
# ---------------------------------------------------------------------------

_PARTNER_REGISTRY: List[PartnerRecord] = [
    PartnerRecord(
        partner_id="p1",
        name="Partner A",
        is_paying_partner=True,
        supported_bauformen=["PTFE-Dichtung", "O-Ring", "Spiraldichtung"],
        supported_media=["steam", "gas", "liquid", "water", "food", "pharma"],
        pressure_max_bar=180.0,
        locations=["DE"],
        delivery_days=6,
        capabilities=["FDA", "STANDARD_PTFE"],
    ),
    PartnerRecord(
        partner_id="p2",
        name="Partner B",
        is_paying_partner=True,
        supported_bauformen=["Spiraldichtung", "O-Ring", "PTFE-Dichtung"],
        supported_media=["H2", "O2", "gas", "liquid", "steam", "cryo"],
        pressure_max_bar=500.0,
        locations=["DE", "AT", "CH"],
        delivery_days=10,
        capabilities=["HIGH_PRESSURE_MACHINING", "CRYO", "API_682", "SPRING_ENERGIZED"],
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
        capabilities=["STANDARD_PTFE"],
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
        capabilities=["STANDARD_PTFE", "HIGH_PRESSURE_MACHINING"],
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
    capabilities_needed: List[str] = Field(default_factory=list)
    critical_capabilities: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# 4-Stage matching logic
# ---------------------------------------------------------------------------


def _normalize_capability(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    text = text.replace("-", "_").replace(" ", "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text


def _unique_capabilities(values: List[Any]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for value in values:
        cap = _normalize_capability(value)
        if not cap or cap in seen:
            continue
        seen.add(cap)
        out.append(cap)
    return out


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dumped
    return {}


def _live_calc_tile_dict(state: SealAIState) -> Dict[str, Any]:
    return _as_dict(getattr(state, "live_calc_tile", {}) or {})


def _derive_capability_requirements(state: SealAIState) -> Dict[str, Any]:
    existing = dict(getattr(state, "capability_requirements", {}) or {})
    existing_needed = existing.get("capabilities_needed")
    existing_critical = existing.get("critical_capabilities")

    if isinstance(existing_needed, list) and existing_needed:
        capabilities_needed = _unique_capabilities(existing_needed)
        critical_capabilities = (
            _unique_capabilities(existing_critical)
            if isinstance(existing_critical, list) and existing_critical
            else list(capabilities_needed)
        )
        return {
            **existing,
            "capabilities_needed": capabilities_needed,
            "critical_capabilities": critical_capabilities,
            "source": existing.get("source") or "state",
        }

    tile = _live_calc_tile_dict(state)
    wp = getattr(state, "working_profile", None)
    medium_value = (
        (getattr(wp, "medium", None) if wp is not None else None)
        or getattr(getattr(state, "parameters", None), "medium", None)
        or getattr(state, "medium", None)
        or ""
    )
    medium = str(medium_value).strip().lower()

    capabilities_needed: List[str] = []
    food_markers = ("teig", "food", "pharma", "lebensmittel", "hygien")
    if any(marker in medium for marker in food_markers):
        capabilities_needed.append("FDA")
    if bool(tile.get("shrinkage_risk")):
        capabilities_needed.extend(["CRYO", "SPRING_ENERGIZED"])
    if bool(tile.get("requires_backup_ring")):
        capabilities_needed.append("HIGH_PRESSURE_MACHINING")

    capabilities_needed = _unique_capabilities(capabilities_needed)
    critical_capabilities = list(capabilities_needed)
    return {
        **existing,
        "capabilities_needed": capabilities_needed,
        "critical_capabilities": critical_capabilities,
        "source": "derived",
    }


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


def _match_stage2b_capabilities(
    candidates: List[PartnerRecord],
    *,
    critical_capabilities: List[str],
) -> List[PartnerRecord]:
    """Stage 2b (MUST): partner must satisfy all critical capabilities."""
    if not candidates:
        return []
    if not critical_capabilities:
        return list(candidates)
    critical = set(_unique_capabilities(critical_capabilities))
    matched: List[PartnerRecord] = []
    for partner in candidates:
        partner_caps = set(_unique_capabilities(list(partner.capabilities or [])))
        if critical.issubset(partner_caps):
            matched.append(partner)
    return matched


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


def _capability_match_score(partner: PartnerRecord, capabilities_needed: List[str]) -> int:
    if not capabilities_needed:
        return 0
    target = set(_unique_capabilities(capabilities_needed))
    if not target:
        return 0
    partner_caps = set(_unique_capabilities(list(partner.capabilities or [])))
    return len(target.intersection(partner_caps))


def run_procurement_matching(
    seal_family: Optional[str],
    medium: Optional[str],
    pressure_max_bar: Optional[float],
    *,
    capabilities_needed: Optional[List[str]] = None,
    critical_capabilities: Optional[List[str]] = None,
    registry: Optional[List[PartnerRecord]] = None,
) -> ProcurementResult:
    """Execute capability-based matching and return a ProcurementResult."""
    candidates: List[PartnerRecord] = list(_PARTNER_REGISTRY if registry is None else registry)
    capabilities_needed_n = _unique_capabilities(list(capabilities_needed or []))
    critical_capabilities_n = _unique_capabilities(
        list(critical_capabilities or capabilities_needed_n)
    )

    # Stage 1: MUST — paying partner
    stage1 = _match_stage1_paying(candidates)
    if not stage1:
        return ProcurementResult(
            matched_partners=[],
            fallback=True,
            stages_completed=0,
            fallback_reason="Keine zahlenden Partner im Netzwerk",
            capabilities_needed=capabilities_needed_n,
            critical_capabilities=critical_capabilities_n,
        )

    # Stage 2: MUST — Bauform
    stage2 = _match_stage2_bauform(stage1, seal_family)
    if not stage2:
        return ProcurementResult(
            matched_partners=[],
            fallback=True,
            stages_completed=1,
            fallback_reason=f"Kein Partner unterstützt Bauform '{seal_family or 'unbekannt'}'",
            capabilities_needed=capabilities_needed_n,
            critical_capabilities=critical_capabilities_n,
        )

    # Stage 2b: MUST — critical capabilities
    stage2b = _match_stage2b_capabilities(
        stage2,
        critical_capabilities=critical_capabilities_n,
    )
    if not stage2b:
        return ProcurementResult(
            matched_partners=[],
            fallback=True,
            stages_completed=2,
            fallback_reason=(
                "Kein Partner erfüllt die kritischen Fähigkeiten: "
                + ", ".join(critical_capabilities_n or ["n/a"])
            ),
            capabilities_needed=capabilities_needed_n,
            critical_capabilities=critical_capabilities_n,
        )

    # Stage 3: SHOULD — medium/pressure
    stage3 = _match_stage3_medium_druck(stage2b, medium, pressure_max_bar)
    warning: Optional[str] = None
    stages_reached = 3
    if stage3 != stage2b:
        # SHOULD filter was effective
        stages_reached = 4
    else:
        # SHOULD returned all Stage-2b survivors (either all passed or none — check which)
        strict_filtered = [
            p for p in stage2b
            if (
                (medium is None or any(m.strip().lower() == (medium or "").strip().lower() for m in p.supported_media))
                and (pressure_max_bar is None or pressure_max_bar <= p.pressure_max_bar)
            )
        ]
        if strict_filtered:
            stages_reached = 4
        else:
            warning = (
                f"Kein Partner mit Medien/Druckfreigabe für '{medium or '?'}' / "
                f"{pressure_max_bar or '?'} bar — alle capability-konformen Partner aufgeführt"
            )

    # Stage 4: NICE — prefer capability coverage, then fastest delivery
    ranked = sorted(
        stage3,
        key=lambda p: (-_capability_match_score(p, capabilities_needed_n), p.delivery_days),
    )
    final = _match_stage4_geo(ranked)

    return ProcurementResult(
        matched_partners=final,
        fallback=False,
        stages_completed=stages_reached,
        fallback_reason="",
        warning=warning,
        capabilities_needed=capabilities_needed_n,
        critical_capabilities=critical_capabilities_n,
    )


# ---------------------------------------------------------------------------
# RFQ PDF rendering
# ---------------------------------------------------------------------------


def _build_rfq_template_context(
    result: ProcurementResult,
    state: SealAIState,
    *,
    capability_requirements: Optional[Dict[str, Any]] = None,
    rfq_payload: Optional[Dict[str, Any]] = None,
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
    capability_blob = dict(capability_requirements or {})

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
        "capability_requirements": capability_blob,
        "capabilities_needed": list(result.capabilities_needed or []),
        "critical_capabilities": list(result.critical_capabilities or []),
        "rfq_payload": dict(rfq_payload or {}),
        # Metadata
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "tenant_id": state.tenant_id or "n/a",
    }


def _render_rfq_pdf(
    result: ProcurementResult,
    state: SealAIState,
    *,
    capability_requirements: Optional[Dict[str, Any]] = None,
    rfq_payload: Optional[Dict[str, Any]] = None,
) -> str:
    """Render the RFQ document via Jinja2 StrictUndefined (R2 enforced)."""
    ctx = _build_rfq_template_context(
        result,
        state,
        capability_requirements=capability_requirements,
        rfq_payload=rfq_payload,
    )
    return render_template(_RFQ_TEMPLATE_NAME, ctx)


def _validated_parameters_dict(state: SealAIState) -> Dict[str, Any]:
    wp = getattr(state, "working_profile", None)
    if wp is not None:
        wp_dict = _as_dict(wp)
        if wp_dict:
            return wp_dict
    params = getattr(state, "parameters", None)
    if params is not None:
        as_dict = getattr(params, "as_dict", None)
        if callable(as_dict):
            return dict(as_dict() or {})
    return {}


def _build_sealai_poc_rationale(
    state: SealAIState,
    tile: Dict[str, Any],
    capability_requirements: Dict[str, Any],
) -> str:
    if bool(tile.get("hrc_warning")):
        return "Option B chosen due to hrc_warning: shaft hardness below recommended PTFE threshold."
    if bool(tile.get("requires_backup_ring")):
        return "Option with backup-ring capability chosen due to extrusion risk under high pressure."
    if bool(tile.get("shrinkage_risk")):
        return "Cryogenic path chosen due to shrinkage_risk; spring-energized capability required."
    critical_caps = list((capability_requirements or {}).get("critical_capabilities") or [])
    if critical_caps:
        return f"Partner path chosen to satisfy critical capabilities: {', '.join(critical_caps)}."
    return "Standard capability path chosen with available validated parameters and physics checks."


def _build_rfq_payload(
    state: SealAIState,
    result: ProcurementResult,
    capability_requirements: Dict[str, Any],
) -> Dict[str, Any]:
    tile = _live_calc_tile_dict(state)
    partners = [partner.model_dump() for partner in result.matched_partners]
    return {
        "validated_parameters": _validated_parameters_dict(state),
        "kinematics_and_physics": tile,
        "sealai_poc_rationale": _build_sealai_poc_rationale(state, tile, capability_requirements),
        "matched_partners": partners,
        "capability_requirements": dict(capability_requirements or {}),
    }


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
    capability_requirements = _derive_capability_requirements(state)
    capabilities_needed = list(capability_requirements.get("capabilities_needed") or [])
    critical_capabilities = list(capability_requirements.get("critical_capabilities") or [])

    logger.info(
        "p5_procurement_start",
        has_working_profile=bool(wp),
        has_calculation_result=bool(calc),
        is_critical=state.is_critical_application,
        run_id=state.run_id,
        thread_id=state.thread_id,
        tenant_id=state.tenant_id,
        capabilities_needed=capabilities_needed,
        critical_capabilities=critical_capabilities,
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
        capabilities_needed=capabilities_needed,
        critical_capabilities=critical_capabilities,
    )
    rfq_payload = _build_rfq_payload(state, result, capability_requirements)

    logger.info(
        "p5_procurement_matching_done",
        fallback=result.fallback,
        stages_completed=result.stages_completed,
        matched_count=len(result.matched_partners),
        fallback_reason=result.fallback_reason,
        capabilities_needed=result.capabilities_needed,
        critical_capabilities=result.critical_capabilities,
        run_id=state.run_id,
    )

    # Render RFQ PDF via Jinja2 StrictUndefined
    rfq_pdf_text: Optional[str] = None
    render_error: Optional[str] = None

    try:
        rfq_pdf_text = _render_rfq_pdf(
            result,
            state,
            capability_requirements=capability_requirements,
            rfq_payload=rfq_payload,
        )
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
        "capability_requirements": capability_requirements,
        "rfq_payload": rfq_payload,
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
