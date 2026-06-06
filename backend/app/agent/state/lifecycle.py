"""Deterministic Case-Lifecycle status (V1.8 §6.3, pure read-only).

The lifecycle status reflects how far a case has progressed along
``inquiring → rfq_sent → quoted → solution_selected → installed → in_operation
→ incident → replaced``. Here it is **derived** from the accumulated case state
(the result of the case's events) — the most-advanced reached state wins. No LLM,
no I/O. Wired at the State-Gate commit seam so every committed turn carries a
live status; routing/dirty-rules become lifecycle-sensitive in later patches.
"""

from __future__ import annotations

from app.agent.state.models import CaseLifecycleStatus, GovernedSessionState


def derive_lifecycle_status(state: GovernedSessionState) -> CaseLifecycleStatus:
    """Most-advanced lifecycle state implied by the case state."""
    events = {r.event for r in (state.outcome_records or [])}
    if "replaced" in events:
        return "replaced"
    if "incident" in events:
        return "incident"

    solution_states = {s.state for s in (state.solution_profiles or [])}
    if "installed" in solution_states:
        return "in_operation" if "in_operation" in events else "installed"
    if "selected" in solution_states:
        return "solution_selected"
    if solution_states & {"offer", "candidate"}:
        return "quoted"

    if bool(getattr(state.action_readiness, "inquiry_sent", False)):
        return "rfq_sent"
    return "inquiring"
