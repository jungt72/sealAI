"""
topology.py — Phase F-C.1/F-C.2, Governed Execution Graph

Assembles the governed StateGraph for the GOVERNED execution path.

Graph topology (Phase F-C.2 — with cycle control):

    turn_boundary → intake_observe → normalize → assert → medium_intelligence → evidence → compute → v92_engineering → challenge → governance
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
                                                            v92_dossier
                                                                  │
                                                              output_contract → governed_answer_composer → END

Zone assignments (Blaupause V1.1 §6.4):
    Zone 0  turn_boundary_node   — Semantic boundary → V9.2 route/stream/mutation contract
    Zone 1  intake_observe_node  — LLM extraction → ObservedState
    Zone 2  normalize_node       — Deterministic → NormalizedState
    Zone 3  assert_node          — Deterministic → AssertedState
    Zone 4a medium_intelligence_node — Deterministic capability → medium_intelligence
    Zone 4b evidence_node        — RAG retrieval → rag_evidence
    Zone 5  compute_node         — Domain calcs  → compute_results
    Zone 6a v92_engineering_node — Deterministic → V9.2 engineering ledger
    Zone 6b challenge_node       — Deterministic → ChallengeState
    Zone 7  governance_node      — Deterministic → GovernanceState
    Cycle   cycle_increment_node — Increments analysis_cycle (CONTINUE only)
    Zone 7  matching_node        — Deterministic matching → matching
    Zone 8  rfq_handover_node    — Deterministic RFQ handover → rfq
    Zone 9  dispatch_node        — Deterministic dispatch prep → dispatch
    Zone 10 norm_node            — Deterministic norm object → sealai_norm
    Zone 11 export_profile_node      — Deterministic export profile → export_profile
    Zone 12 manufacturer_mapping_node — Deterministic manufacturer mapping → manufacturer_mapping
    Zone 13 dispatch_contract_node    — Deterministic connector-ready contract → dispatch_contract
    Zone 14 v92_dossier_node          — Deterministic → V9.2 RFQ dossier
    Zone 15 output_contract_node      — Outward contract → output_public

Architecture invariants enforced here:
    - intake_observe_node is the ONLY node that may call an LLM for technical observation.
    - governed_answer_composer_node may call an LLM for text-only answer_markdown when feature-flagged.
    - All other nodes are deterministic and side-effect free.
    - RAG is only called with a structured query from AssertedState (Invariant 5).
    - Governance classification (Class A–D) is always derived before output.
    - Cycle limit is enforced by decide_cycle() — the graph never loops
      beyond max_cycles (Class B budget) or when Class A/C/D is reached.

Usage:
    from app.agent.graph.topology import build_governed_graph, get_governed_graph

    # Async runtime singleton (preferred for FastAPI production)
    graph = await get_governed_graph()
    result = await graph.ainvoke(state)

    # Or compile on demand (useful for testing)
    graph = build_governed_graph()
    result = await graph.ainvoke(state)
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from contextlib import suppress
from typing import Any

from langgraph.graph import END, StateGraph

from app.agent.graph import GraphState
from app.agent.graph.cycle_control import cycle_increment_node
from app.agent.graph.nodes.assert_node import assert_node
from app.agent.graph.nodes.challenge_node import challenge_node
from app.agent.graph.nodes.compute_node import compute_node
from app.agent.graph.nodes.dispatch_contract_node import dispatch_contract_node
from app.agent.graph.nodes.evidence_node import evidence_node
from app.agent.graph.nodes.export_profile_node import export_profile_node
from app.agent.graph.nodes.governance_node import governance_routing_node
from app.agent.graph.nodes.governed_answer_composer_node import (
    governed_answer_composer_node,
)
from app.agent.graph.nodes.intake_observe_node import intake_observe_node
from app.agent.graph.nodes.manufacturer_mapping_node import manufacturer_mapping_node
from app.agent.graph.nodes.medium_intelligence_node import medium_intelligence_node
from app.agent.graph.nodes.matching_node import matching_node
from app.agent.graph.nodes.normalize_node import normalize_node
from app.agent.graph.nodes.norm_node import norm_node
from app.agent.graph.nodes.output_contract_node import output_contract_node
from app.agent.graph.nodes.dispatch_node import dispatch_node
from app.agent.graph.nodes.rfq_handover_node import rfq_handover_node
from app.agent.graph.nodes.turn_boundary_node import turn_boundary_node
from app.agent.graph.nodes.v92_dossier_node import v92_dossier_node
from app.agent.graph.nodes.v92_engineering_node import v92_engineering_node

log = logging.getLogger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_FALSE_VALUES = {"0", "false", "no", "n", "off"}
_ASYNC_GRAPH_LOCK = asyncio.Lock()
_ASYNC_GOVERNED_GRAPH: Any | None = None
_ASYNC_CHECKPOINTER_CONTEXT: Any | None = None
_ASYNC_CHECKPOINTER: Any | None = None


def _env_bool(name: str) -> bool | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    return None


def _native_checkpointing_enabled() -> bool:
    explicit = (
        _env_bool("SEALAI_LANGGRAPH_CHECKPOINTING")
        if os.getenv("SEALAI_LANGGRAPH_CHECKPOINTING") is not None
        else _env_bool("SEALAI_ENABLE_LANGGRAPH_CHECKPOINTING")
    )
    if explicit is not None:
        return explicit
    app_env = (os.getenv("APP_ENV") or os.getenv("app_env") or "").strip().lower()
    return app_env in {"prod", "production", "staging"}


def _redis_checkpoint_url() -> str:
    return (
        os.getenv("LANGGRAPH_V2_REDIS_URL")
        or os.getenv("REDIS_URL")
        or os.getenv("redis_url")
        or ""
    ).strip()


def _build_default_checkpointer() -> Any | None:
    """Create a sync-safe fallback checkpointer for direct graph imports/tests.

    The FastAPI runtime uses ``get_governed_graph()`` below so native LangGraph
    ``astream()/ainvoke()`` calls run against an async-capable checkpointer.
    A sync RedisSaver would expose ``aget_tuple`` from the abstract base class
    and crash async streams with ``NotImplementedError``.
    """

    if not _native_checkpointing_enabled():
        return None
    redis_url = _redis_checkpoint_url()
    if redis_url:
        log.info("[topology] Redis checkpointing deferred to async governed graph runtime")
        return None
    try:
        from langgraph.checkpoint.memory import InMemorySaver  # type: ignore

        log.warning("[topology] LangGraph in-memory checkpointer enabled")
        return InMemorySaver()
    except Exception as exc:  # noqa: BLE001
        log.warning("[topology] LangGraph checkpointer disabled (%s: %s)", type(exc).__name__, exc)
        return None


async def _setup_checkpointer_async(checkpointer: Any) -> None:
    setup = getattr(checkpointer, "asetup", None) or getattr(checkpointer, "setup", None)
    if setup is None:
        return
    result = setup()
    if inspect.isawaitable(result):
        await result


async def _build_async_default_checkpointer() -> Any | None:
    """Create the production async checkpointer with safe local fallbacks."""

    global _ASYNC_CHECKPOINTER_CONTEXT, _ASYNC_CHECKPOINTER
    if not _native_checkpointing_enabled():
        return None

    redis_url = _redis_checkpoint_url()
    if redis_url:
        manager: Any | None = None
        try:
            try:
                from langgraph.checkpoint.redis.aio import AsyncRedisSaver  # type: ignore
            except Exception:  # noqa: BLE001
                from langgraph.checkpoint.redis import AsyncRedisSaver  # type: ignore

            manager = AsyncRedisSaver.from_conn_string(redis_url)
            checkpointer = (
                await manager.__aenter__() if hasattr(manager, "__aenter__") else manager
            )
            await _setup_checkpointer_async(checkpointer)
            if hasattr(manager, "__aexit__"):
                _ASYNC_CHECKPOINTER_CONTEXT = manager
            _ASYNC_CHECKPOINTER = checkpointer
            log.info("[topology] LangGraph async Redis checkpointer enabled")
            return checkpointer
        except Exception as exc:  # noqa: BLE001
            if manager is not None and hasattr(manager, "__aexit__"):
                with suppress(Exception):
                    await manager.__aexit__(None, None, None)
            _ASYNC_CHECKPOINTER_CONTEXT = None
            _ASYNC_CHECKPOINTER = None
            log.warning(
                "[topology] Async Redis checkpointer unavailable; falling back to in-memory checkpointer (%s: %s)",
                type(exc).__name__,
                exc,
            )

    try:
        from langgraph.checkpoint.memory import InMemorySaver  # type: ignore

        checkpointer = InMemorySaver()
        _ASYNC_CHECKPOINTER = checkpointer
        log.warning("[topology] LangGraph async runtime using in-memory checkpointer")
        return checkpointer
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "[topology] Async LangGraph checkpointer disabled (%s: %s)",
            type(exc).__name__,
            exc,
        )
        return None


async def get_governed_graph() -> Any:
    """Return the async-runtime governed graph singleton."""

    global _ASYNC_GOVERNED_GRAPH
    if _ASYNC_GOVERNED_GRAPH is not None:
        return _ASYNC_GOVERNED_GRAPH
    async with _ASYNC_GRAPH_LOCK:
        if _ASYNC_GOVERNED_GRAPH is None:
            _ASYNC_GOVERNED_GRAPH = build_governed_graph(
                checkpointer=await _build_async_default_checkpointer()
            )
        return _ASYNC_GOVERNED_GRAPH


async def close_governed_graph_resources() -> None:
    """Close async LangGraph resources during FastAPI shutdown."""

    global _ASYNC_GOVERNED_GRAPH, _ASYNC_CHECKPOINTER_CONTEXT, _ASYNC_CHECKPOINTER
    manager = _ASYNC_CHECKPOINTER_CONTEXT
    _ASYNC_GOVERNED_GRAPH = None
    _ASYNC_CHECKPOINTER_CONTEXT = None
    _ASYNC_CHECKPOINTER = None
    if manager is not None and hasattr(manager, "__aexit__"):
        with suppress(Exception):
            await manager.__aexit__(None, None, None)

# ---------------------------------------------------------------------------
# Node name constants
# ---------------------------------------------------------------------------

NODE_INTAKE_OBSERVE = "intake_observe"
NODE_TURN_BOUNDARY = "turn_boundary"
NODE_NORMALIZE = "normalize"
NODE_ASSERT = "assert"
NODE_MEDIUM_INTELLIGENCE = "medium_intelligence"
NODE_EVIDENCE = "evidence"
NODE_COMPUTE = "compute"
NODE_V92_ENGINEERING = "v92_engineering"
NODE_CHALLENGE = "challenge"
NODE_GOVERNANCE = "governance"
NODE_CYCLE_INCREMENT = "cycle_increment"
NODE_MATCHING = "matching"
NODE_RFQ_HANDOVER = "rfq_handover"
NODE_DISPATCH = "dispatch"
NODE_NORM = "norm"
NODE_EXPORT_PROFILE = "export_profile"
NODE_MANUFACTURER_MAPPING = "manufacturer_mapping"
NODE_DISPATCH_CONTRACT = "dispatch_contract"
NODE_V92_DOSSIER = "v92_dossier"
NODE_OUTPUT_CONTRACT = "output_contract"
NODE_GOVERNED_ANSWER_COMPOSER = "governed_answer_composer"


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def build_governed_graph(*, checkpointer: Any = None) -> StateGraph:
    """Build and compile the governed execution graph.

    Returns a compiled LangGraph StateGraph ready for ainvoke().
    Call this once at startup and reuse the returned object.

    Topology (Phase F-C.2):
        Linear path through boundary and analysis zones, then a conditional edge at
        governance_node routed by decide_cycle():
            CONTINUE  → cycle_increment_node → intake_observe_node (next turn)
            TERMINATE → matching → rfq_handover → dispatch → norm → export_profile → manufacturer_mapping → dispatch_contract → output_contract_node → governed_answer_composer_node → END
    """
    graph = StateGraph(GraphState)

    # ── Register nodes ────────────────────────────────────────────────────
    graph.add_node(NODE_TURN_BOUNDARY, turn_boundary_node)
    graph.add_node(NODE_INTAKE_OBSERVE, intake_observe_node)
    graph.add_node(NODE_NORMALIZE, normalize_node)
    graph.add_node(NODE_ASSERT, assert_node)
    graph.add_node(NODE_MEDIUM_INTELLIGENCE, medium_intelligence_node)
    graph.add_node(NODE_EVIDENCE, evidence_node)
    graph.add_node(NODE_COMPUTE, compute_node)
    graph.add_node(NODE_V92_ENGINEERING, v92_engineering_node)
    graph.add_node(NODE_CHALLENGE, challenge_node)
    graph.add_node(NODE_GOVERNANCE, governance_routing_node)
    graph.add_node(NODE_CYCLE_INCREMENT, cycle_increment_node)
    graph.add_node(NODE_MATCHING, matching_node)
    graph.add_node(NODE_RFQ_HANDOVER, rfq_handover_node)
    graph.add_node(NODE_DISPATCH, dispatch_node)
    graph.add_node(NODE_NORM, norm_node)
    graph.add_node(NODE_EXPORT_PROFILE, export_profile_node)
    graph.add_node(NODE_MANUFACTURER_MAPPING, manufacturer_mapping_node)
    graph.add_node(NODE_DISPATCH_CONTRACT, dispatch_contract_node)
    graph.add_node(NODE_V92_DOSSIER, v92_dossier_node)
    graph.add_node(NODE_OUTPUT_CONTRACT, output_contract_node)
    graph.add_node(NODE_GOVERNED_ANSWER_COMPOSER, governed_answer_composer_node)

    # ── Entry point ───────────────────────────────────────────────────────
    graph.set_entry_point(NODE_TURN_BOUNDARY)

    # ── Linear edges: turn_boundary → intake_observe → ... → governance ───
    graph.add_edge(NODE_TURN_BOUNDARY, NODE_INTAKE_OBSERVE)
    graph.add_edge(NODE_INTAKE_OBSERVE, NODE_NORMALIZE)
    graph.add_edge(NODE_NORMALIZE, NODE_ASSERT)
    graph.add_edge(NODE_ASSERT, NODE_MEDIUM_INTELLIGENCE)
    graph.add_edge(NODE_MEDIUM_INTELLIGENCE, NODE_EVIDENCE)
    graph.add_edge(NODE_EVIDENCE, NODE_COMPUTE)
    graph.add_edge(NODE_COMPUTE, NODE_V92_ENGINEERING)
    graph.add_edge(NODE_V92_ENGINEERING, NODE_CHALLENGE)
    graph.add_edge(NODE_CHALLENGE, NODE_GOVERNANCE)

    # ── Command-routed path: governance decides CONTINUE vs TERMINATE ─────
    graph.add_edge(NODE_CYCLE_INCREMENT, NODE_INTAKE_OBSERVE)

    # ── TERMINATE path: matching → rfq_handover → dispatch → norm → export_profile → manufacturer_mapping → dispatch_contract → output_contract → governed_answer_composer → END ─
    graph.add_edge(NODE_MATCHING, NODE_RFQ_HANDOVER)
    graph.add_edge(NODE_RFQ_HANDOVER, NODE_DISPATCH)
    graph.add_edge(NODE_DISPATCH, NODE_NORM)
    graph.add_edge(NODE_NORM, NODE_EXPORT_PROFILE)
    graph.add_edge(NODE_EXPORT_PROFILE, NODE_MANUFACTURER_MAPPING)
    graph.add_edge(NODE_MANUFACTURER_MAPPING, NODE_DISPATCH_CONTRACT)
    graph.add_edge(NODE_DISPATCH_CONTRACT, NODE_V92_DOSSIER)
    graph.add_edge(NODE_V92_DOSSIER, NODE_OUTPUT_CONTRACT)
    graph.add_edge(NODE_OUTPUT_CONTRACT, NODE_GOVERNED_ANSWER_COMPOSER)
    graph.add_edge(NODE_GOVERNED_ANSWER_COMPOSER, END)

    log.debug(
        "[topology] governed graph compiled with cycle control: "
        "CONTINUE→%s, TERMINATE→%s→%s→%s→%s→%s→%s→%s→%s→%s",
        NODE_CYCLE_INCREMENT,
        NODE_MATCHING,
        NODE_RFQ_HANDOVER,
        NODE_DISPATCH,
        NODE_EXPORT_PROFILE,
        NODE_MANUFACTURER_MAPPING,
        NODE_DISPATCH_CONTRACT,
        NODE_V92_DOSSIER,
        NODE_OUTPUT_CONTRACT,
        NODE_GOVERNED_ANSWER_COMPOSER,
    )

    return graph.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Pre-compiled singleton
# ---------------------------------------------------------------------------

GOVERNED_GRAPH = build_governed_graph(checkpointer=_build_default_checkpointer())
