"""
Agent Graph — Phase 0A.3: Guidance / Qualification Split

Topology:

    START
      │
      ▼ route_by_policy (conditional edge)
      ├─── "fast_guidance_node"  ──────────────────────────────────────────► END
      │       (FAST_PATH: DIRECT_ANSWER | GUIDED_RECOMMENDATION)
      │
      └─── "reasoning_node"  ──► [tool_router]
               (STRUCTURED_PATH)       │
                                       ├─── "evidence_tool_node" ──► "reasoning_node"
                                       └─── "selection_node" ──► "final_response_node" ──► END

Rules:
- fast_guidance_node: lightweight, no tools, no sealing_state writes, no qualification
- reasoning_node: full structured path (UNCHANGED — Preserve P2)
- route_by_policy reads state["policy_path"] set by the router before graph invocation
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, List, Literal, Optional

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.agent.agent.logic import evaluate_claim_conflicts, extract_parameters, process_cycle_update
from app.agent.agent.prompts import (
    FAST_GUIDANCE_PROMPT_HASH,
    FAST_GUIDANCE_PROMPT_VERSION,
    REASONING_PROMPT_HASH,
    REASONING_PROMPT_VERSION,
    SYSTEM_PROMPT_TEMPLATE,
    build_fast_guidance_prompt,
)
from app.agent.agent.policy import INTERACTION_POLICY_VERSION
from app.agent.agent.boundaries import build_boundary_block
from app.agent.agent.commercial import build_handover_payload
from app.agent.agent.review import evaluate_review_trigger
from app.agent.agent.selection import build_final_reply, build_selection_state
from app.agent.agent.state import AgentState, SealingAIState
from app.agent.agent.tools import submit_claim, calculate_rwdr_specifications
from app.agent.evidence.models import Claim, ClaimType
from app.agent.agent.knowledge import load_fact_cards, retrieve_fact_cards

load_dotenv()

logger = logging.getLogger(__name__)

_GRAPH_MODEL_ID = "gpt-4o-mini"
_VISIBLE_REPLY_SYSTEM_PROMPT = "Du bist der sichtbare SealAI-Antwortlayer."
VISIBLE_REPLY_PROMPT_VERSION = "visible_reply_prompt_v1"
VISIBLE_REPLY_PROMPT_HASH = hashlib.sha256(_VISIBLE_REPLY_SYSTEM_PROMPT.encode()).hexdigest()[:12]
_NON_BINDING_ASSIST_INSTRUCTION = (
    "Du darfst nur explizit genannte Beobachtungen als nicht-bindende Rohclaims erfassen. "
    "Keine Release-Entscheidung, keine RFQ-Admissibility, keine Governance-Wertung, "
    "keine Compound- oder Materialfreigabe ableiten."
)

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover
    class ChatOpenAI:  # type: ignore[override]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def bind_tools(self, tools: list[Any]) -> "ChatOpenAI":
            return self

        async def ainvoke(self, messages: list[Any]) -> AIMessage:
            return AIMessage(content="stub")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

async def retrieve_rag_context(query: str, tenant_id: str | None) -> list[Any]:
    """Phase 0A.1: tenant_id is preserved and forwarded to the real Qdrant retrieval."""
    from app.agent.services.real_rag import retrieve_with_tenant
    return await retrieve_with_tenant(query, tenant_id)


def retrieve_fact_cards_fallback(query: str) -> list[Any]:
    kb_path = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base.json")
    cards = load_fact_cards(kb_path)
    return retrieve_fact_cards(query, cards)


def get_llm(config: Optional[RunnableConfig] = None) -> ChatOpenAI:
    return ChatOpenAI(model=_GRAPH_MODEL_ID, temperature=0)


def _last_human_query(state: AgentState) -> str:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""


async def _fetch_rag_cards(query: str, tenant_id: str | None) -> tuple[list[Any], str]:
    """Fetch RAG cards with fallback. Returns (cards_data, path_used)."""
    path_used = "real_rag"
    try:
        relevant_cards = await retrieve_rag_context(query, tenant_id)
    except Exception as exc:
        logger.error("[RAG] Real-RAG error, falling back: %s", exc, exc_info=True)
        relevant_cards = []
        path_used = "real_rag_error_fallback"

    if not relevant_cards and query:
        relevant_cards = retrieve_fact_cards_fallback(query)
        if path_used != "real_rag_error_fallback":
            path_used = "pseudo_rag_fallback"

    logger.info("[RAG] Path: %s, Hits: %d, Tenant: %s", path_used, len(relevant_cards), tenant_id)

    # Normalise to dict list (real_rag returns dicts; fallback returns FactCard objects)
    cards_data: list[Any] = []
    for c in relevant_cards:
        if isinstance(c, dict):
            cards_data.append(c)
        else:
            cards_data.append({
                "id": getattr(c, "id", None),
                "evidence_id": getattr(c, "evidence_id", None),
                "source_ref": getattr(c, "source_ref", None),
                "topic": getattr(c, "topic", ""),
                "content": getattr(c, "content", ""),
                "tags": getattr(c, "tags", []),
                "retrieval_rank": getattr(c, "retrieval_rank", 0),
                "retrieval_score": getattr(c, "retrieval_score", 0.0),
                "metadata": getattr(c, "metadata", {}),
                "normalized_evidence": getattr(c, "normalized_evidence", None),
            })

    cards_data = sorted(
        cards_data,
        key=lambda card: (
            str(card.get("evidence_id") or card.get("id") or ""),
            str(card.get("topic") or ""),
        ),
    )
    return cards_data, path_used


def _format_context(cards_data: list[Any]) -> str:
    ctx = "\n---\n".join(
        f"Topic: {c.get('topic', '')}\nContent: {c.get('content', '')}"
        for c in cards_data
    )
    return ctx or "Keine relevanten Informationen in der Wissensdatenbank gefunden."


# ---------------------------------------------------------------------------
# Entry router — Phase 0A.3
# ---------------------------------------------------------------------------

def route_by_policy(state: AgentState) -> Literal["fast_guidance_node", "reasoning_node"]:
    """
    Conditional entry edge: dispatches to fast or structured path based on
    state["policy_path"] injected by the API router before graph invocation.

    Defaults to "reasoning_node" (structured) when policy_path is absent or unknown.
    """
    policy_path = state.get("policy_path") or "structured"
    if policy_path == "fast":
        return "fast_guidance_node"
    return "reasoning_node"


# ---------------------------------------------------------------------------
# Fast-path node — DIRECT_ANSWER & GUIDED_RECOMMENDATION (Phase 0A.3)
# ---------------------------------------------------------------------------

async def fast_guidance_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """
    Lightweight guidance node for FAST_PATH interactions.

    Differences from reasoning_node (all intentional):
    - No submit_claim tool — LLM cannot mutate sealing_state
    - No extract_parameters — no heuristic working_profile updates
    - No sealing_state writes — governance layer stays untouched
    - Adapted system prompt based on result_form
    - Direct → END (no selection_node, no final_response_node)
    """
    query = _last_human_query(state)
    tenant_id = state.get("tenant_id")
    result_form = state.get("result_form") or "direct_answer"

    cards_data, _ = await _fetch_rag_cards(query, tenant_id)
    context_str = _format_context(cards_data)

    system_prompt = build_fast_guidance_prompt(context_str, result_form)
    system_msg = SystemMessage(content=system_prompt)

    llm = get_llm(config)
    # No tools bound — LLM answers in plain text only
    response = await llm.ainvoke([system_msg] + list(state.get("messages", [])))

    # Phase 0B.2: deterministically append boundary disclaimer (never LLM-generated)
    boundary = build_boundary_block("fast")
    bounded_content = f"{response.content.rstrip()}\n\n{boundary}"
    bounded_response = AIMessage(content=bounded_content)

    return {
        "messages": [bounded_response],
        "relevant_fact_cards": cards_data,
        "run_meta": {
            "model_id": _GRAPH_MODEL_ID,
            "prompt_version": FAST_GUIDANCE_PROMPT_VERSION,
            "prompt_hash": FAST_GUIDANCE_PROMPT_HASH,
            "policy_version": INTERACTION_POLICY_VERSION,
            "path": "fast",
        },
        # working_profile and sealing_state intentionally NOT modified
    }


# ---------------------------------------------------------------------------
# Structured-path nodes — UNCHANGED (Preserve P2)
# ---------------------------------------------------------------------------

async def reasoning_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """
    Reasoning Node (Phase D1 - RAG Injection).
    Full structured path: claim submission, sealing_state updates, governance.
    UNCHANGED from original — Preserve P2.
    """
    messages = state.get("messages", [])
    current_profile = state.get("working_profile", {})
    tenant_id = state.get("tenant_id")

    query = _last_human_query(state)

    cards_data, path_used = await _fetch_rag_cards(query, tenant_id)
    print(f"[RAG] Path: {path_used}, Hits: {len(cards_data)}, Tenant: {tenant_id}", flush=True)

    new_profile = extract_parameters(query, current_profile, cards_data) if query else current_profile

    context_str = _format_context(cards_data)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        context=context_str,
        working_profile=json.dumps(new_profile, indent=2),
    )
    system_prompt = f"{_NON_BINDING_ASSIST_INSTRUCTION}\n\n{system_prompt}"

    llm = get_llm(config)
    llm_with_tools = llm.bind_tools([submit_claim, calculate_rwdr_specifications])

    response = await llm_with_tools.ainvoke([SystemMessage(content=system_prompt)] + list(messages))

    return {
        "messages": [response],
        "relevant_fact_cards": cards_data,
        "working_profile": new_profile,
    }


def evidence_tool_node(state: AgentState) -> dict:
    """
    Evidence Tool Node (Phase C4/H5) — full dispatcher loop.

    Processes ALL tool_calls in last_message so the OpenAI message contract
    is never broken (every tool_call_id must have a matching ToolMessage).

    Dispatch table:
    - submit_claim                  → mutates sealing_state (existing logic, unchanged)
    - calculate_rwdr_specifications → deterministic calc via tool.invoke(), no state mutation
    - unknown tools                 → safe error ToolMessage (safety net)
    """
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", [])
    if not tool_calls:
        return {}

    # --- Partition tool calls by name ---
    new_claims: List[Claim] = []
    claim_to_tool_id: dict[str, str] = {}
    rwdr_calls: List[dict] = []
    unknown_calls: List[dict] = []

    for tc in tool_calls:
        if tc["name"] == "submit_claim":
            args = tc["args"]
            claim = Claim(
                claim_type=args["claim_type"],
                statement=args["statement"],
                confidence=args["confidence"],
                source_fact_ids=args.get("source_fact_ids", []),
            )
            new_claims.append(claim)
            claim_to_tool_id[claim.statement] = tc["id"]
        elif tc["name"] == "calculate_rwdr_specifications":
            rwdr_calls.append(tc)
        else:
            unknown_calls.append(tc)

    from app.agent.services.compound import validate_claim_against_matrix

    tool_outputs: List[ToolMessage] = []
    result: dict = {}
    working_profile = state.get("working_profile") or {}

    # Accumulate ALL domain conflicts across both dispatch paths so they are
    # written into governance.conflicts via process_cycle_update at the end.
    all_domain_conflicts: List[dict] = []

    # --- submit_claim path: mutate sealing_state (logic unchanged) ---
    if new_claims:
        old_sealing_state = state["sealing_state"]
        current_revision = old_sealing_state["cycle"]["state_revision"]

        intelligence_conflicts, validated_params = evaluate_claim_conflicts(
            claims=new_claims,
            asserted_state=old_sealing_state["asserted"],
            relevant_fact_cards=state.get("relevant_fact_cards", []),
            working_profile=working_profile,
        )
        all_domain_conflicts.extend(intelligence_conflicts)

        raw_claims = [
            {
                "statement": claim.statement,
                "claim_type": claim.claim_type,
                "confidence": claim.confidence,
                "source_fact_ids": claim.source_fact_ids,
                "source": "llm_submit_claim",
            }
            for claim in new_claims
        ]

        new_sealing_state = process_cycle_update(
            old_state=old_sealing_state,
            intelligence_conflicts=intelligence_conflicts,
            expected_revision=current_revision,
            validated_params=validated_params,
            raw_claims=raw_claims,
            relevant_fact_cards=state.get("relevant_fact_cards", []),
        )
        result["sealing_state"] = new_sealing_state

        conflicts_by_statement: dict[str, list] = {}
        for c in intelligence_conflicts:
            conflicts_by_statement.setdefault(c["claim_statement"], []).append(c)

        for claim in new_claims:
            tool_id = claim_to_tool_id[claim.statement]
            claim_conflicts = conflicts_by_statement.get(claim.statement, [])
            if claim_conflicts:
                error_msgs = []
                for c in claim_conflicts:
                    if c["type"] == "DOMAIN_LIMIT_VIOLATION":
                        error_msgs.append(f"DOMAIN_LIMIT_VIOLATION: {c['message']}")
                    else:
                        error_msgs.append(f"CONFLICT ({c['severity']}): {c['message']}")
                content = "Fehler bei der Claim-Verarbeitung:\n" + "\n".join(error_msgs)
            else:
                content = f"Claim erfolgreich verarbeitet: {claim.statement}"
            tool_outputs.append(ToolMessage(content=content, tool_call_id=tool_id))

    # --- calculate_rwdr_specifications path: deterministic calc ---
    # Phase 0B.1: after the RWDR tool runs, validate its output against the
    # compound matrix.  This catches domain violations even when the LLM
    # submits NO submit_claim calls (pure calc path).
    for tc in rwdr_calls:
        try:
            calc_result = calculate_rwdr_specifications.invoke(tc["args"])
        except Exception as exc:
            calc_result = json.dumps({"status": "error", "notes": [str(exc)]})

        # Parse v_surface and pv_value from calc result for compound validation
        try:
            calc_data = json.loads(calc_result) if isinstance(calc_result, str) else calc_result
        except Exception:
            calc_data = {}

        # Build a synthetic claim-like statement from the tool args so the
        # compound validator can extract rpm / diameter from it
        args = tc.get("args") or {}
        synthetic_stmt = (
            f"Welle {args.get('shaft_diameter_mm', '')}mm "
            f"{args.get('rpm', '')} rpm "
            f"{args.get('pressure_bar', '') or ''} bar"
        ).strip()

        # Merge working_profile with calculated values so compound validator
        # has the most accurate context
        enriched_wp = dict(working_profile)
        if calc_data.get("v_surface_m_s"):
            enriched_wp["v_m_s"] = calc_data["v_surface_m_s"]

        rwdr_conflicts = validate_claim_against_matrix(
            synthetic_stmt,
            candidate_materials=None,  # check absolute limits only
            working_profile=enriched_wp,
        )
        all_domain_conflicts.extend(rwdr_conflicts)

        tool_outputs.append(ToolMessage(
            content=str(calc_result),
            name=tc["name"],
            tool_call_id=tc["id"],
        ))

    # Write all accumulated domain conflicts into sealing_state governance
    # so the state_update event carries them to the frontend.
    if all_domain_conflicts and "sealing_state" not in result:
        old_sealing_state = state["sealing_state"]
        current_revision = old_sealing_state["cycle"]["state_revision"]
        new_sealing_state = process_cycle_update(
            old_state=old_sealing_state,
            intelligence_conflicts=all_domain_conflicts,
            expected_revision=current_revision,
            validated_params={},
            raw_claims=[],
            relevant_fact_cards=state.get("relevant_fact_cards", []),
        )
        result["sealing_state"] = new_sealing_state
    elif all_domain_conflicts and "sealing_state" in result:
        # Conflicts already written by submit_claim path; re-apply to include rwdr ones
        old_sealing_state = result["sealing_state"]
        current_revision = old_sealing_state["cycle"]["state_revision"]
        new_sealing_state = process_cycle_update(
            old_state=old_sealing_state,
            intelligence_conflicts=all_domain_conflicts,
            expected_revision=current_revision,
            validated_params={},
            raw_claims=[],
            relevant_fact_cards=state.get("relevant_fact_cards", []),
        )
        result["sealing_state"] = new_sealing_state

    # --- safety net: unknown tools must still get a ToolMessage ---
    for tc in unknown_calls:
        tool_outputs.append(ToolMessage(
            content=f"Tool '{tc['name']}' ist nicht verfügbar.",
            name=tc["name"],
            tool_call_id=tc["id"],
        ))

    result["messages"] = tool_outputs
    return result


def selection_node(state: AgentState) -> dict:
    """Builds selection state and evaluates deterministic HITL review trigger (Phase A3)."""
    sealing_state = state["sealing_state"]
    governance_state = sealing_state.get("governance", {})
    selection_state = build_selection_state(
        relevant_fact_cards=state.get("relevant_fact_cards", []),
        cycle_state=sealing_state.get("cycle", {}),
        governance_state=governance_state,
        asserted_state=sealing_state.get("asserted", {}),
    )
    new_sealing_state = dict(sealing_state)
    new_sealing_state["selection"] = selection_state

    # Phase A3: deterministic review trigger — never delegated to the LLM
    demo_data_in_scope: bool = bool(
        (sealing_state.get("result_contract") or {}).get("demo_data_in_scope", False)
    )
    new_sealing_state["review"] = evaluate_review_trigger(
        governance_state=governance_state,
        demo_data_in_scope=demo_data_in_scope,
    )

    return {"sealing_state": new_sealing_state}


async def final_response_node(state: AgentState) -> dict:
    """Structured-path final reply — boundary block, run_meta, handover, and audit (Phase 0B.2 / 0A.5 / A3 / A6 / 1B).

    Converted to async def so asyncio.create_task() inside AuditLogger.append()
    fires correctly from within the running event loop (Blueprint Section 15).
    """
    sealing_state = state["sealing_state"]
    selection_state = sealing_state.get("selection", {})
    governance_state = sealing_state.get("governance", {})
    review_state: dict = sealing_state.get("review") or {}
    known_unknowns: list[str] = list(governance_state.get("unknowns_release_blocking") or [])

    reply = build_final_reply(
        selection_state,
        known_unknowns=known_unknowns or None,
        review_required=bool(review_state.get("review_required", False)),
        review_reason=str(review_state.get("review_reason", "")),
    )

    # Phase A6: build commercial handover payload deterministically — no LLM involvement
    handover = build_handover_payload(sealing_state)
    new_sealing_state = dict(sealing_state)
    new_sealing_state["handover"] = handover

    # ── Phase 1B: Audit log — Blueprint Section 15 ───────────────────────────
    # Fire-and-forget via asyncio.create_task (AuditLogger.append internals).
    # Works here because we are in an async def — the event loop IS running.
    # final_response_node is ONLY reached on the structured (qualification) path.
    try:
        from app.services.audit.audit_logger import get_global_audit_logger

        audit_logger = get_global_audit_logger()
        if audit_logger is not None:
            session_id: str = (
                state.get("inquiry_id")
                or state.get("session_id")
                or sealing_state.get("cycle", {}).get("analysis_cycle_id")
                or "unknown"
            )
            tenant_id: str | None = (
                state.get("tenant_id")
                or sealing_state.get("cycle", {}).get("tenant_id")
            )
            critique_log = {
                "release_status": governance_state.get("release_status"),
                "rfq_admissibility": governance_state.get("rfq_admissibility"),
                "conflicts": governance_state.get("conflicts") or [],
                "unknowns_release_blocking": governance_state.get("unknowns_release_blocking") or [],
                "state_revision": sealing_state.get("cycle", {}).get("state_revision"),
                "node": "final_response_node",
            }
            audit_logger.append(
                session_id=session_id,
                tenant_id=tenant_id,
                state={
                    "working_profile": state.get("working_profile") or {},
                    "critique_log": critique_log,
                    "phase": "final_response_node:structured",
                },
            )
            logger.info(
                "[audit] scheduled: session=%s tenant=%s release=%s conflicts=%d",
                session_id,
                tenant_id,
                critique_log.get("release_status"),
                len(critique_log["conflicts"]),
            )
        else:
            logger.debug("[audit] global AuditLogger not initialised — skipping")
    except Exception as exc:
        logger.error("[audit] fire_audit failed (non-fatal): %s", exc)

    return {
        "messages": [AIMessage(content=reply)],
        "sealing_state": new_sealing_state,
    }


def router(state: AgentState) -> Literal["evidence_tool_node", "selection_node"]:
    """
    Internal structured-path router: tool-call vs no-tool-call.
    UNCHANGED — deterministic Blueprint Section 03.
    """
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "evidence_tool_node"
    return "selection_node"


# ---------------------------------------------------------------------------
# Graph topology
# ---------------------------------------------------------------------------

graph_builder = StateGraph(AgentState)

graph_builder.add_node("fast_guidance_node", fast_guidance_node)
graph_builder.add_node("reasoning_node", reasoning_node)
graph_builder.add_node("evidence_tool_node", evidence_tool_node)
graph_builder.add_node("selection_node", selection_node)
graph_builder.add_node("final_response_node", final_response_node)

# Entry switch (Phase 0A.3)
graph_builder.add_conditional_edges(
    START,
    route_by_policy,
    {
        "fast_guidance_node": "fast_guidance_node",
        "reasoning_node": "reasoning_node",
    },
)

# Fast path: direct to END
graph_builder.add_edge("fast_guidance_node", END)

# Structured path: full pipeline (UNCHANGED)
graph_builder.add_conditional_edges(
    "reasoning_node",
    router,
    {
        "evidence_tool_node": "evidence_tool_node",
        "selection_node": "selection_node",
    },
)
graph_builder.add_edge("evidence_tool_node", "reasoning_node")
graph_builder.add_edge("selection_node", "final_response_node")
graph_builder.add_edge("final_response_node", END)

app = graph_builder.compile()
