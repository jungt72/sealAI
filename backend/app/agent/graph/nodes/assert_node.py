"""
assert_node — Phase F-C.1, Zone 3

Deterministic assertion derivation.

Responsibility:
    Derive AssertedState from NormalizedState and optional evidence claims.
    No LLM, no I/O, no side effects.

Architecture invariants enforced here:
    - AssertedState is ONLY produced by reduce_normalized_to_asserted().
      No direct AssertedState construction.
    - NormalizedState is read-only in this node.
    - ObservedState and GovernanceState remain unchanged.

Evidence handling (Phase F):
    In Phase F, full evidence retrieval lives in evidence_node (Zone 4).
    assert_node always receives evidence=None — the AssertedState is built
    from NormalizedState alone. Phase G evidence layer will supply real
    Claim objects via state.rag_evidence_claims.

Reducer semantics (see state/reducers.py for full spec):
    1. Parameters at 'confirmed' or 'estimated' → AssertedClaim.
    2. Parameters at 'inferred' → AssertedClaim (with caveat note).
    3. Parameters at 'requires_confirmation' → blocking_unknowns.
    4. Blocking ConflictRefs → conflict_flags.
    5. Core required fields absent entirely → blocking_unknowns.
"""
from __future__ import annotations

import logging

from app.agent.graph import GraphState
from app.agent.state.reducers import reduce_normalized_to_asserted

log = logging.getLogger(__name__)


async def assert_node(state: GraphState) -> GraphState:
    """Zone 3 — Derive AssertedState from NormalizedState.

    Purely deterministic. No LLM, no I/O.
    Calls reduce_normalized_to_asserted() and stores the result.

    Evidence is not passed in Phase F (evidence_node is Zone 4 and runs
    after assert_node in the cycle; real claims come in Phase G).
    """
    asserted = reduce_normalized_to_asserted(state.normalized, evidence=None)

    log.debug(
        "[assert_node] assertions=%s blocking=%s conflicts=%s",
        sorted(asserted.assertions.keys()),
        asserted.blocking_unknowns,
        asserted.conflict_flags,
    )

    return state.model_copy(update={"asserted": asserted})
