"""
cycle_control.py — Phase F-C.2

Deterministic cycle gate for the governed execution graph.

Two pure functions:
    decide_cycle(state) → CycleDecision
        Determines whether the graph continues for another analysis cycle
        (CONTINUE) or terminates and forwards to output_contract_node
        (TERMINATE). No LLM, no I/O, no side effects.

    increment_cycle(state) → GraphState
        Returns a new GraphState with analysis_cycle incremented by one.
        Never mutates the input state.

Cycle decision rules (Umbauplan F-C.2):
    Class A → TERMINATE   (rfq_admissible, nothing more to gather)
    Class B + cycle < max → CONTINUE  (blocking unknowns, budget remaining)
    Class B + cycle ≥ max → TERMINATE (budget exhausted → auto-promote to C)
    Class C → TERMINATE   (unresolvable conflict or cycle-limit reached)
    Class D → TERMINATE   (out of scope — no sealing-tech parameters)
    None    → TERMINATE   (governance not yet derived — fail-safe)

MAX_CYCLES:
    Read from env var SEALAI_MAX_CYCLES (int, default 3).
    Matches GovernedSessionState.max_cycles (the per-session limit stored
    in the state itself). decide_cycle reads state.max_cycles so that
    per-session overrides are respected even if the env default differs.

Topology integration (topology.py):
    The conditional edge after governance_node calls decide_cycle().
    On CONTINUE the graph routes to cycle_increment_node (which calls
    increment_cycle and re-enters intake_observe_node for the next turn).
    On TERMINATE the graph routes to output_contract_node.
"""
from __future__ import annotations

import logging
import os
from enum import Enum

from app.agent.graph import GraphState

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_MAX_CYCLES: int = int(os.environ.get("SEALAI_MAX_CYCLES", "3"))


# ---------------------------------------------------------------------------
# CycleDecision
# ---------------------------------------------------------------------------

class CycleDecision(str, Enum):
    """Routing decision produced by decide_cycle().

    str-valued so LangGraph can use it directly as a conditional edge key.
    """
    CONTINUE  = "continue"
    TERMINATE = "terminate"


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def decide_cycle(state: GraphState) -> CycleDecision:
    """Determine whether to run another analysis cycle or terminate.

    Pure function — no LLM, no I/O, no mutation of state.

    Args:
        state: Current GraphState after governance_node has run.

    Returns:
        CycleDecision.CONTINUE  — route back to intake_observe_node.
        CycleDecision.TERMINATE — route forward to output_contract_node.
    """
    gov_class   = state.governance.gov_class
    cycle       = state.analysis_cycle
    max_cycles  = state.max_cycles  # per-session limit (default 3)

    # Fail-safe: governance not yet derived
    if gov_class is None:
        log.debug("[cycle_control] gov_class=None → TERMINATE (fail-safe)")
        return CycleDecision.TERMINATE

    if gov_class == "A":
        # All core fields confirmed, rfq_admissible — nothing more to gather.
        log.debug("[cycle_control] Class A → TERMINATE")
        return CycleDecision.TERMINATE

    if gov_class == "B":
        if (
            getattr(state.governance, "preselection_blockers", None)
            or getattr(state.governance, "compliance_blockers", None)
            or getattr(state.governance, "type_sensitive_required", None)
        ):
            log.debug("[cycle_control] Class B with preselection blockers → TERMINATE")
            return CycleDecision.TERMINATE

        if cycle < max_cycles:
            log.debug(
                "[cycle_control] Class B cycle=%d/%d → CONTINUE",
                cycle, max_cycles,
            )
            return CycleDecision.CONTINUE
        else:
            log.debug(
                "[cycle_control] Class B cycle=%d/%d budget exhausted → TERMINATE",
                cycle, max_cycles,
            )
            return CycleDecision.TERMINATE

    if gov_class == "C":
        log.debug("[cycle_control] Class C → TERMINATE")
        return CycleDecision.TERMINATE

    # gov_class == "D" (out of scope) or any future unknown value
    log.debug("[cycle_control] Class %s → TERMINATE", gov_class)
    return CycleDecision.TERMINATE


def increment_cycle(state: GraphState) -> GraphState:
    """Return a new GraphState with analysis_cycle incremented by one.

    Pure function — never mutates the input state.
    The incremented turn_index is picked up by intake_observe_node so that
    extractions in the next cycle carry the correct source_turn.

    Args:
        state: Current GraphState (before re-entering intake_observe_node).

    Returns:
        New GraphState with analysis_cycle = state.analysis_cycle + 1.
    """
    new_cycle = state.analysis_cycle + 1
    log.debug(
        "[cycle_control] increment_cycle %d → %d",
        state.analysis_cycle, new_cycle,
    )
    return state.model_copy(update={"analysis_cycle": new_cycle})


# ---------------------------------------------------------------------------
# Thin node wrapper (used by topology.py)
# ---------------------------------------------------------------------------

async def cycle_increment_node(state: GraphState) -> GraphState:
    """Thin async node wrapper around increment_cycle().

    Inserted between governance_node and intake_observe_node on the
    CONTINUE branch. Keeps increment_cycle() a pure, testable function
    while satisfying LangGraph's async node contract.
    """
    return increment_cycle(state)
