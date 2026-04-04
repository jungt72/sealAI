"""
governance_node — Phase F-C.1, Zone 6

Deterministic governance class derivation.

Responsibility:
    Derive GovernanceState from AssertedState by running the deterministic
    reducer. No LLM, no I/O, no side effects.

Architecture invariants enforced here:
    - GovernanceState is ONLY produced by reduce_asserted_to_governance().
      No direct GovernanceState construction.
    - AssertedState is read-only in this node.
    - ObservedState, NormalizedState, and compute_results unchanged.

Reducer semantics (see state/reducers.py for full spec):
    A — all core fields at confirmed/estimated, no blocking unknowns,
        no conflict flags → rfq_admissible = True
    B — some core fields asserted, blocking unknowns exist, cycle < max
        → proceed with caveats, rfq_admissible = False
    C — blocking unknowns persist after max_cycles, OR unresolvable conflicts
        → auto-fallback, rfq_admissible = False
    D — none of the core required fields asserted at all
        → out of scope, rfq_admissible = False
"""
from __future__ import annotations

import logging

from app.agent.graph import GraphState
from app.agent.state.reducers import reduce_asserted_to_governance

log = logging.getLogger(__name__)


async def governance_node(state: GraphState) -> GraphState:
    """Zone 6 — Derive GovernanceState from AssertedState.

    Purely deterministic. No LLM, no I/O.
    Calls reduce_asserted_to_governance() and stores the result.
    """
    governance = reduce_asserted_to_governance(
        state.asserted,
        analysis_cycle=state.analysis_cycle,
        max_cycles=state.max_cycles,
    )

    log.debug(
        "[governance_node] class=%s rfq_admissible=%s blocking=%s conflicts=%s cycle=%d/%d",
        governance.gov_class,
        governance.rfq_admissible,
        state.asserted.blocking_unknowns,
        state.asserted.conflict_flags,
        state.analysis_cycle,
        state.max_cycles,
    )

    return state.model_copy(update={"governance": governance})
