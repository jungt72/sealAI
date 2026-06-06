"""Deterministic Operating-Window check (V1.8 §5.6 — Betriebsfenster).

100 % code, **no LLM** ("calculated" is only credible as a deterministic
result). Compares the case requirement profile (Anforderung) against a
SolutionProfile's limit fields, field by field, and produces a margin + flag per
field. Missing limits never vanish silently — they become a ``limit_unknown``
row with a suggested manufacturer question. Flags are screening signals, never a
release ("ok" = within the datasheet limit, NOT "geeignet"/freigegeben — the
manufacturer/engineer evaluates).

The comparison *mechanics* here are type-agnostic; the *spec* (which requirement
field maps to which solution limit, and in which direction) is injected. The
RWDR spec lives at the bottom of this module today (one pack — Rule of Three);
it moves to the DomainPack when pack #2 lands.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, Field

from app.agent.state.models import GovernedSessionState, SolutionProfile

OperatingWindowFlag = Literal["ok", "clarify", "critical", "limit_unknown"]
ComparisonDirection = Literal["req_le_limit", "req_ge_limit", "capability_required"]

#: Requirement statuses confident enough to read "ok" rather than "clarify"
#: (a deterministic ``calculated`` value is as trustworthy as a ``confirmed`` one).
_CONFIDENT_STATUSES = frozenset({"confirmed", "calculated"})


class LimitComparison(BaseModel):
    """One requirement↔limit field pairing (pack data)."""

    limit_field: str
    requirement_field: str
    label: str = ""
    direction: ComparisonDirection = "req_le_limit"
    unit: str = ""


class OperatingWindowRow(BaseModel):
    field: str
    label: str = ""
    unit: str = ""
    requirement_value: Any = None
    requirement_status: str = "unknown"
    limit_value: Any = None
    limit_source_doc: Optional[str] = None
    limit_source_page: Optional[int] = None
    margin: Optional[float] = None
    flag: OperatingWindowFlag = "limit_unknown"
    suggested_manufacturer_question: Optional[str] = None
    note: str = ""


class OperatingWindow(BaseModel):
    rows: list[OperatingWindowRow] = Field(default_factory=list)
    has_critical: bool = False
    has_clarify: bool = False
    has_unknown_limit: bool = False


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _solution_limits(solution: SolutionProfile | None) -> dict[str, Any]:
    """field -> (value, source_doc, source_page) for the solution's fields."""
    limits: dict[str, Any] = {}
    if solution is None:
        return limits
    for f in solution.fields:
        limits[f.field] = f
    return limits


def compute_operating_window(
    requirement_values: Mapping[str, Any],
    requirement_statuses: Mapping[str, str],
    solution: SolutionProfile | None,
    comparisons: Sequence[LimitComparison],
    *,
    margin_clarify_ratio: float = 0.1,
) -> OperatingWindow:
    """Build the deterministic Operating-Window projection.

    ``margin_clarify_ratio``: a non-negative margin smaller than this fraction of
    the limit is flagged ``clarify`` (tight) rather than ``ok``.
    """
    limit_fields = _solution_limits(solution)
    rows: list[OperatingWindowRow] = []

    for comp in comparisons:
        label = comp.label or comp.limit_field
        sol_field = limit_fields.get(comp.limit_field)
        req_value = requirement_values.get(comp.requirement_field)
        req_status = str(requirement_statuses.get(comp.requirement_field, "unknown"))
        row = OperatingWindowRow(
            field=comp.limit_field,
            label=label,
            unit=comp.unit,
            requirement_value=req_value,
            requirement_status=req_status,
            limit_value=getattr(sol_field, "value", None),
            limit_source_doc=getattr(sol_field, "source_doc", None),
            limit_source_page=getattr(sol_field, "source_page", None),
        )

        if sol_field is None or sol_field.value is None:
            row.flag = "limit_unknown"
            row.note = "Limit unbekannt"
            row.suggested_manufacturer_question = (
                f"Bitte {label} laut Datenblatt/Herstellerangabe bestätigen."
            )
            rows.append(row)
            continue

        if req_value is None:
            row.flag = "clarify"
            row.note = "Anforderung offen"
            rows.append(row)
            continue

        if comp.direction == "capability_required":
            if bool(req_value) and not bool(sol_field.value):
                row.flag = "critical"
                row.suggested_manufacturer_question = (
                    f"{label}: laut Datenblatt nicht gegeben, aber gefordert — "
                    "bitte mit Hersteller klären."
                )
            elif req_status not in _CONFIDENT_STATUSES:
                row.flag = "clarify"
            else:
                row.flag = "ok"
            rows.append(row)
            continue

        rf, lf = _to_float(req_value), _to_float(sol_field.value)
        if rf is None or lf is None:
            row.flag = "clarify"
            row.note = "nicht numerisch vergleichbar"
            rows.append(row)
            continue

        margin = (lf - rf) if comp.direction == "req_le_limit" else (rf - lf)
        row.margin = margin
        if margin < 0:
            row.flag = "critical"
            row.suggested_manufacturer_question = (
                f"{label}: Anforderung über dem Limit laut Datenblatt — "
                "bitte mit Hersteller klären."
            )
        elif (
            margin < abs(lf) * margin_clarify_ratio
            or req_status not in _CONFIDENT_STATUSES
        ):
            row.flag = "clarify"
        else:
            row.flag = "ok"
        rows.append(row)

    return OperatingWindow(
        rows=rows,
        has_critical=any(r.flag == "critical" for r in rows),
        has_clarify=any(r.flag == "clarify" for r in rows),
        has_unknown_limit=any(r.flag == "limit_unknown" for r in rows),
    )


# --- RWDR pack data (Rule of Three: moves to the DomainPack at pack #2) --------
# Requirement field names are the case-side keys; the wiring patch (L2) maps the
# governed asserted state onto these. Limit fields match RwdrPack solution limits.
RWDR_OPERATING_WINDOW_COMPARISONS: tuple[LimitComparison, ...] = (
    LimitComparison(
        limit_field="temp_max_continuous_c",
        requirement_field="temperature_c",
        label="Dauertemperatur",
        direction="req_le_limit",
        unit="°C",
    ),
    LimitComparison(
        limit_field="temp_min_continuous_c",
        requirement_field="temperature_min_c",
        label="Min. Dauertemperatur",
        direction="req_ge_limit",
        unit="°C",
    ),
    LimitComparison(
        limit_field="v_max_m_s",
        requirement_field="v_surface_m_s",
        label="Umfangsgeschwindigkeit",
        direction="req_le_limit",
        unit="m/s",
    ),
    LimitComparison(
        limit_field="p_max_bar",
        requirement_field="pressure_bar",
        label="Druck an der Dichtkante",
        direction="req_le_limit",
        unit="bar",
    ),
    LimitComparison(
        limit_field="dry_run_capable",
        requirement_field="dry_running_required",
        label="Trockenlauf",
        direction="capability_required",
    ),
)


# --- Projection from the governed case state (V1.8 §5.6, pure read-only) -------
# Maps each comparison's abstract requirement_field onto the governed
# asserted-state keys (the field names actually stored differ by aspect, e.g. the
# operating temperature lives under temperature_max_c / temperature_c). First hit
# wins; v_surface is injected separately from the deterministic compute result.
_REQUIREMENT_ALIASES: dict[str, tuple[str, ...]] = {
    "temperature_c": ("temperature_max_c", "temperature_c"),
    "temperature_min_c": ("temperature_min_c",),
    "pressure_bar": (
        "pressure_at_seal_bar",
        "pressure_bar",
        "pressure_differential_bar",
    ),
    "dry_running_required": ("dry_running_required", "dry_running"),
}

#: SolutionProfile state precedence for "the solution in operation/chosen".
_SOLUTION_STATE_PRECEDENCE = ("installed", "selected", "offer", "candidate")


def _select_solution(profiles: Sequence[SolutionProfile]) -> SolutionProfile | None:
    """The most-committed solution profile (installed > selected > … > first)."""
    for state in _SOLUTION_STATE_PRECEDENCE:
        for profile in profiles:
            if profile.state == state:
                return profile
    return profiles[0] if profiles else None


def project_operating_window(
    state: GovernedSessionState,
    *,
    compute_results: Sequence[Mapping[str, Any]] | None = None,
) -> OperatingWindow:
    """Deterministic Operating-Window projection for a governed case.

    Reads the confirmed requirement profile (``asserted.assertions``) and the
    deterministic circumference-speed result, picks the chosen SolutionProfile,
    and compares them via the RWDR spec. Pure read-only — no LLM, no mutation.
    ``compute_results`` defaults to ``state.compute_results`` when the caller
    passes a GraphState (the persisted GovernedSessionState has none).
    """
    assertions = state.asserted.assertions or {}
    req_values: dict[str, Any] = {}
    req_status: dict[str, str] = {}

    for comp in RWDR_OPERATING_WINDOW_COMPARISONS:
        rf = comp.requirement_field
        for key in _REQUIREMENT_ALIASES.get(rf, (rf,)):
            claim = assertions.get(key)
            value = getattr(claim, "asserted_value", None)
            if claim is not None and value is not None:
                req_values[rf] = value
                req_status[rf] = str(getattr(claim, "status", "unknown"))
                break

    results = compute_results
    if results is None:
        results = getattr(state, "compute_results", None) or []
    # Pick the computed circumference speed by the value it carries, not by a
    # seal-type label — keeps this core projection free of per-type branching.
    for result in results:
        if isinstance(result, Mapping) and result.get("v_surface_m_s") is not None:
            req_values["v_surface_m_s"] = result["v_surface_m_s"]
            req_status["v_surface_m_s"] = "calculated"
            break

    return compute_operating_window(
        req_values,
        req_status,
        _select_solution(state.solution_profiles),
        RWDR_OPERATING_WINDOW_COMPARISONS,
    )
