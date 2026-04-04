"""
topology.py — Phase F-C.1/F-C.2, Governed Execution Graph

Assembles the governed StateGraph for the GOVERNED execution path.

Graph topology (Phase F-C.2 — with cycle control):

    intake_observe → normalize → assert → evidence → compute → governance
                                                                    │
                                            ┌───────────────────────┤ decide_cycle()
                                            │                       │
                                     CONTINUE                  TERMINATE
                                            │                       │
                                    cycle_increment             matching
                                            │
                                    (back to intake_observe)        │
                                                            rfq_handover
                                                                  │
                                                               dispatch
                                                                  │
                                                                  norm
                                                                  │
                                                            export_profile
                                                                  │
                                                         manufacturer_mapping
                                                                  │
                                                            dispatch_contract
                                                                  │
                                                              output_contract → END

Zone assignments (Blaupause V1.1 §6.4):
    Zone 1  intake_observe_node  — LLM extraction → ObservedState
    Zone 2  normalize_node       — Deterministic → NormalizedState
    Zone 3  assert_node          — Deterministic → AssertedState
    Zone 4  evidence_node        — RAG retrieval → rag_evidence
    Zone 5  compute_node         — Domain calcs  → compute_results
    Zone 6  governance_node      — Deterministic → GovernanceState
    Cycle   cycle_increment_node — Increments analysis_cycle (CONTINUE only)
    Zone 7  matching_node        — Deterministic matching → matching
    Zone 8  rfq_handover_node    — Deterministic RFQ handover → rfq
    Zone 9  dispatch_node        — Deterministic dispatch prep → dispatch
    Zone 10 norm_node            — Deterministic norm object → sealai_norm
    Zone 11 export_profile_node      — Deterministic export profile → export_profile
    Zone 12 manufacturer_mapping_node — Deterministic manufacturer mapping → manufacturer_mapping
    Zone 13 dispatch_contract_node    — Deterministic connector-ready contract → dispatch_contract
    Zone 14 output_contract_node      — Outward contract → output_public

Architecture invariants enforced here:
    - intake_observe_node is the ONLY node that may call an LLM (Invariant 4).
    - All other nodes are deterministic and side-effect free.
    - RAG is only called with a structured query from AssertedState (Invariant 5).
    - Governance classification (Class A–D) is always derived before output.
    - Cycle limit is enforced by decide_cycle() — the graph never loops
      beyond max_cycles (Class B budget) or when Class A/C/D is reached.

Usage:
    from app.agent.graph.topology import build_governed_graph, GOVERNED_GRAPH

    # Pre-compiled singleton (preferred for production)
    result = await GOVERNED_GRAPH.ainvoke(state)

    # Or compile on demand (useful for testing)
    graph = build_governed_graph()
    result = await graph.ainvoke(state)
"""
from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from app.agent.graph import GraphState
from app.agent.graph.cycle_control import (
    CycleDecision,
    cycle_increment_node,
    decide_cycle,
)
from app.agent.graph.nodes.assert_node import assert_node
from app.agent.graph.nodes.compute_node import compute_node
from app.agent.graph.nodes.dispatch_contract_node import dispatch_contract_node
from app.agent.graph.nodes.evidence_node import evidence_node
from app.agent.graph.nodes.export_profile_node import export_profile_node
from app.agent.graph.nodes.governance_node import governance_node
from app.agent.graph.nodes.intake_observe_node import intake_observe_node
from app.agent.graph.nodes.manufacturer_mapping_node import manufacturer_mapping_node
from app.agent.graph.nodes.matching_node import matching_node
from app.agent.graph.nodes.normalize_node import normalize_node
from app.agent.graph.nodes.norm_node import norm_node
from app.agent.graph.nodes.output_contract_node import output_contract_node
from app.agent.graph.nodes.dispatch_node import dispatch_node
from app.agent.graph.nodes.rfq_handover_node import rfq_handover_node

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Node name constants
# ---------------------------------------------------------------------------

NODE_INTAKE_OBSERVE  = "intake_observe"
NODE_NORMALIZE       = "normalize"
NODE_ASSERT          = "assert"
NODE_EVIDENCE        = "evidence"
NODE_COMPUTE         = "compute"
NODE_GOVERNANCE      = "governance"
NODE_CYCLE_INCREMENT = "cycle_increment"
NODE_MATCHING        = "matching"
NODE_RFQ_HANDOVER    = "rfq_handover"
NODE_DISPATCH        = "dispatch"
NODE_NORM            = "norm"
NODE_EXPORT_PROFILE  = "export_profile"
NODE_MANUFACTURER_MAPPING = "manufacturer_mapping"
NODE_DISPATCH_CONTRACT = "dispatch_contract"
NODE_OUTPUT_CONTRACT = "output_contract"


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------

def build_governed_graph() -> StateGraph:
    """Build and compile the governed execution graph.

    Returns a compiled LangGraph StateGraph ready for ainvoke().
    Call this once at startup and reuse the returned object.

    Topology (Phase F-C.2):
        Linear path through 6 analysis zones, then a conditional edge at
        governance_node routed by decide_cycle():
            CONTINUE  → cycle_increment_node → intake_observe_node (next turn)
            TERMINATE → matching → rfq_handover → dispatch → norm → export_profile → manufacturer_mapping → dispatch_contract → output_contract_node → END
    """
    graph = StateGraph(GraphState)

    # ── Register nodes ────────────────────────────────────────────────────
    graph.add_node(NODE_INTAKE_OBSERVE,  intake_observe_node)
    graph.add_node(NODE_NORMALIZE,       normalize_node)
    graph.add_node(NODE_ASSERT,          assert_node)
    graph.add_node(NODE_EVIDENCE,        evidence_node)
    graph.add_node(NODE_COMPUTE,         compute_node)
    graph.add_node(NODE_GOVERNANCE,      governance_node)
    graph.add_node(NODE_CYCLE_INCREMENT, cycle_increment_node)
    graph.add_node(NODE_MATCHING,        matching_node)
    graph.add_node(NODE_RFQ_HANDOVER,    rfq_handover_node)
    graph.add_node(NODE_DISPATCH,        dispatch_node)
    graph.add_node(NODE_NORM,            norm_node)
    graph.add_node(NODE_EXPORT_PROFILE,  export_profile_node)
    graph.add_node(NODE_MANUFACTURER_MAPPING, manufacturer_mapping_node)
    graph.add_node(NODE_DISPATCH_CONTRACT, dispatch_contract_node)
    graph.add_node(NODE_OUTPUT_CONTRACT, output_contract_node)

    # ── Entry point ───────────────────────────────────────────────────────
    graph.set_entry_point(NODE_INTAKE_OBSERVE)

    # ── Linear edges: intake_observe → ... → governance ──────────────────
    graph.add_edge(NODE_INTAKE_OBSERVE, NODE_NORMALIZE)
    graph.add_edge(NODE_NORMALIZE,      NODE_ASSERT)
    graph.add_edge(NODE_ASSERT,         NODE_EVIDENCE)
    graph.add_edge(NODE_EVIDENCE,       NODE_COMPUTE)
    graph.add_edge(NODE_COMPUTE,        NODE_GOVERNANCE)

    # ── Conditional edge: governance → cycle gate ─────────────────────────
    graph.add_conditional_edges(
        NODE_GOVERNANCE,
        decide_cycle,
        {
            CycleDecision.CONTINUE:  NODE_CYCLE_INCREMENT,
            CycleDecision.TERMINATE: NODE_MATCHING,
        },
    )

    # ── CONTINUE path: cycle_increment loops back to intake_observe ───────
    graph.add_edge(NODE_CYCLE_INCREMENT, NODE_INTAKE_OBSERVE)

    # ── TERMINATE path: matching → rfq_handover → dispatch → norm → export_profile → manufacturer_mapping → dispatch_contract → output_contract → END ─
    graph.add_edge(NODE_MATCHING, NODE_RFQ_HANDOVER)
    graph.add_edge(NODE_RFQ_HANDOVER, NODE_DISPATCH)
    graph.add_edge(NODE_DISPATCH, NODE_NORM)
    graph.add_edge(NODE_NORM, NODE_EXPORT_PROFILE)
    graph.add_edge(NODE_EXPORT_PROFILE, NODE_MANUFACTURER_MAPPING)
    graph.add_edge(NODE_MANUFACTURER_MAPPING, NODE_DISPATCH_CONTRACT)
    graph.add_edge(NODE_DISPATCH_CONTRACT, NODE_OUTPUT_CONTRACT)
    graph.add_edge(NODE_OUTPUT_CONTRACT, END)

    log.debug(
        "[topology] governed graph compiled with cycle control: "
        "CONTINUE→%s, TERMINATE→%s→%s→%s→%s→%s→%s→%s",
        NODE_CYCLE_INCREMENT,
        NODE_MATCHING,
        NODE_RFQ_HANDOVER,
        NODE_DISPATCH,
        NODE_EXPORT_PROFILE,
        NODE_MANUFACTURER_MAPPING,
        NODE_DISPATCH_CONTRACT,
        NODE_OUTPUT_CONTRACT,
    )

    return graph.compile()


# ---------------------------------------------------------------------------
# Pre-compiled singleton
# ---------------------------------------------------------------------------

GOVERNED_GRAPH = build_governed_graph()
