"""Incident intake — Soll-Ist diagnosis → structured Outcome-Event (V1.8 §5.3/AC14).

When a leakage is reported at an installed part, the diagnosis is a **Soll-Ist
comparison**, not a cold start: the deterministic Operating-Window (requirement
profile vs the chosen SolutionProfile's limits) already points at where the
application left the datasheet envelope. This module turns the worst
requirement-vs-limit mismatch into a structured ``OutcomeRecord``.

Pure code, no LLM. The ``suspected_cause`` is a **hypothesis** derived from the
Soll-Ist mismatch — never a verdict or a definitive root cause (Safety-Formel:
Ferndiagnose ist Hypothese mit Prüfschritt, keine Gewissheit). Confidence
reflects how clear the Soll-Ist signal is, not certainty of causation.

The RWDR pattern/cause maps below move to ``DomainPack.outcome_taxonomy()`` at
pack #2 (Rule of Three).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from app.agent.state.models import GovernedSessionState, OutcomeRecord
from app.agent.state.operating_window import (
    OperatingWindowRow,
    _select_solution,
    project_operating_window,
)

# RWDR incident taxonomy (§3.4 outcome_taxonomy), keyed by the failing limit
# field (NOT a seal type). → DomainPack.outcome_taxonomy() at pack #2.
_RWDR_INCIDENT_PATTERNS: dict[str, str] = {
    "temp_max_continuous_c": "lip_hardening_thermal",
    "temp_min_continuous_c": "cold_embrittlement",
    "v_max_m_s": "running_groove_wear",
    "p_max_bar": "lip_extrusion_pressure",
    "dry_run_capable": "dry_running_track",
}

_RWDR_SUSPECTED_CAUSES: dict[str, str] = {
    "temp_max_continuous_c": "operating_temperature_above_continuous_limit",
    "temp_min_continuous_c": "operating_temperature_below_minimum_limit",
    "v_max_m_s": "surface_speed_above_limit",
    "p_max_bar": "pressure_above_lip_limit",
    "dry_run_capable": "dry_running_not_supported",
}


def _worst_row(rows: Sequence[OperatingWindowRow]) -> OperatingWindowRow | None:
    """The most diagnostic Soll-Ist row: a critical mismatch outweighs a clarify.

    limit_unknown rows are *missing data*, not a cause, so they never win.
    """
    critical = [r for r in rows if r.flag == "critical"]
    if critical:
        return critical[0]
    clarify = [
        r for r in rows if r.flag == "clarify" and r.requirement_value is not None
    ]
    return clarify[0] if clarify else None


def build_incident_outcome(
    state: GovernedSessionState,
    *,
    case_id: str = "",
    tenant_id: str = "",
    position_id: str = "pos_1",
    installed_at: str | None = None,
    runtime_hours_estimate: int | None = None,
    evidence_refs: Sequence[str] | None = None,
    compute_results: Sequence[Mapping[str, Any]] | None = None,
) -> OutcomeRecord:
    """Build a structured incident ``OutcomeRecord`` from the Soll-Ist comparison.

    The chosen SolutionProfile and the worst requirement-vs-limit mismatch drive
    ``solution_ref``, ``outcome_pattern`` and the **hypothesis** ``suspected_cause``.
    With no solution / no mismatch, the record is still emitted (event=incident)
    but carries no pattern/cause and ``low`` confidence — never a fabricated cause.
    """
    window = project_operating_window(state, compute_results=compute_results)
    solution = _select_solution(state.solution_profiles)
    worst = _worst_row(window.rows)

    if worst is not None:
        outcome_pattern = _RWDR_INCIDENT_PATTERNS.get(worst.field)
        suspected_cause = _RWDR_SUSPECTED_CAUSES.get(
            worst.field, f"{worst.field}_mismatch"
        )
        confidence = "high" if worst.flag == "critical" else "medium"
    else:
        outcome_pattern = None
        suspected_cause = None
        confidence = "low"

    return OutcomeRecord(
        case_id=case_id,
        tenant_id=tenant_id,
        position_id=position_id,
        solution_ref=solution.solution_id if solution else None,
        event="incident",
        installed_at=installed_at,
        runtime_hours_estimate=runtime_hours_estimate,
        outcome_pattern=outcome_pattern,
        suspected_cause=suspected_cause,
        evidence_refs=list(evidence_refs or []),
        confidence=confidence,
    )
