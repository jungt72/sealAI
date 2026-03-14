from typing import Literal, List, Optional, Any, Dict
import asyncio
import logging
from langgraph.graph import StateGraph, START, END
from app.agent.agent.state import AgentState, SealingAIState
from app.agent.evidence.models import Claim, ClaimType
from app.agent.agent.logic import evaluate_claim_conflicts, process_cycle_update, extract_parameters
from app.agent.hardening.guard import (
    claim_whitelist_check,
    snapshot_deterministic_layers,
    assert_deterministic_unchanged,
)
from app.agent.agent.tools import submit_claim
from app.agent.agent.knowledge import retrieve_rag_context, retrieve_fact_cards_fallback
from app.agent.agent.prompts import SYSTEM_PROMPT_TEMPLATE
from app.agent.agent.rwdr_orchestration import is_rwdr_flow_active, run_rwdr_orchestration
from app.agent.agent.selection import build_selection_state, build_final_reply, build_visible_reply_fallback
from app.agent.case_state import build_conversation_guidance_contract, build_visible_case_narrative
from langchain_core.messages import ToolMessage, AIMessage, SystemMessage, HumanMessage, message_chunk_to_message
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig
from dotenv import load_dotenv
import os
import json

# Umgebungsvariablen laden (API Keys etc.)
load_dotenv()

logger = logging.getLogger(__name__)
_NON_BINDING_ASSIST_INSTRUCTION = (
    "Du darfst nur explizit genannte Beobachtungen als nicht-bindende Rohclaims erfassen. "
    "Keine Release-Entscheidung, keine RFQ-Admissibility, keine Governance-Wertung, "
    "keine Compound- oder Materialfreigabe ableiten."
)
_VISIBLE_REPLY_SYSTEM_PROMPT = (
    "Du formulierst nur die sichtbare Chat-Antwort fuer SealAI. "
    "Die fachliche Priorisierung ist bereits deterministisch entschieden und darf von dir nicht neu erfunden werden. "
    "Nutze die uebergebene Guidance Contract Struktur strikt als Grenze: keine zusaetzlichen Fragen, "
    "maximal die angegebenen 0-3 requested_fields, keine neuen fehlenden Daten erfinden. "
    "Formuliere natuerlich, knapp und kontextsensitiv auf Deutsch. "
    "Wenn ask_mode 'recompute_first' ist, erklaere zuerst den Recompute-Schritt und stelle keine neue Rueckfrage. "
    "Wenn ask_mode 'qualification_ready' oder 'no_question_needed' ist, stelle keine Rueckfrage. "
    "Die Governed Summary ist technisch bindend; du darfst sie sprachlich natuerlich machen, aber nicht fachlich veraendern."
)

def get_llm(config: Optional[RunnableConfig] = None):
    """
    Factory-Methode für das LLM (Phase C5).
    """
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)


def get_fact_cards(query: str, tenant_id: Optional[str] = None):
    """Backward-compatible retrieval hook for agent tests and local graph wiring."""
    del tenant_id
    return retrieve_fact_cards_fallback(query)


def _extract_query(messages: List[Any]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return ""


def _normalize_cards(relevant_cards: List[Any]) -> List[dict]:
    cards_data = [
        {
            "id": c.id,
            "evidence_id": c.evidence_id,
            "source_ref": c.source_ref,
            "topic": c.topic,
            "content": c.content,
            "tags": c.tags,
            "retrieval_rank": c.retrieval_rank,
            "retrieval_score": c.retrieval_score,
            "metadata": c.metadata,
            "normalized_evidence": getattr(c, "normalized_evidence", None),
        }
        for c in relevant_cards
    ]
    return sorted(
        cards_data,
        key=lambda card: (
            str(card.get("evidence_id") or card.get("id") or ""),
            str(card.get("topic") or ""),
        ),
    )


def _build_reasoning_prompt(cards_data: List[dict], new_profile: dict) -> SystemMessage:
    context_str = "\n---\n".join(
        [f"Topic: {card.get('topic', '')}\nContent: {card.get('content', '')}" for card in cards_data]
    )
    if not context_str:
        context_str = "Keine relevanten Informationen in der Wissensdatenbank gefunden."

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        context=context_str,
        working_profile=json.dumps(new_profile, indent=2)
    )
    system_prompt = f"{_NON_BINDING_ASSIST_INSTRUCTION}\n\n{system_prompt}"
    return SystemMessage(content=system_prompt)


def _build_visible_reply_messages(
    *,
    latest_user_message: str,
    governed_summary: str,
    visible_case_narrative: Dict[str, Any],
    guidance_contract: Dict[str, Any],
) -> List[Any]:
    return [
        SystemMessage(content=_VISIBLE_REPLY_SYSTEM_PROMPT),
        HumanMessage(
            content=(
                "Letzte Nutzeranfrage:\n"
                f"{latest_user_message or '(leer)'}\n\n"
                "Governed Summary:\n"
                f"{governed_summary}\n\n"
                "Visible Case Narrative Contract:\n"
                f"{json.dumps(visible_case_narrative, ensure_ascii=False, indent=2)}\n\n"
                "Deterministic Guidance Contract:\n"
                f"{json.dumps(guidance_contract, ensure_ascii=False, indent=2)}\n\n"
                "Schreibe daraus genau eine sichtbare Assistant-Antwort."
            )
        ),
    ]


async def _collect_streamed_ai_message(runnable: Any, messages: List[Any]) -> AIMessage:
    aggregated_chunk = None
    async for chunk in runnable.astream(messages):
        aggregated_chunk = chunk if aggregated_chunk is None else aggregated_chunk + chunk

    if aggregated_chunk is None:
        response = await runnable.ainvoke(messages)
        if isinstance(response, AIMessage):
            return response
        return AIMessage(content=str(getattr(response, "content", "") or response))

    message = message_chunk_to_message(aggregated_chunk)
    if isinstance(message, AIMessage):
        return message
    return AIMessage(content=str(getattr(message, "content", "") or message))


def _collect_streamed_ai_message_sync(
    runnable: Any,
    messages: List[Any],
    config: Optional[RunnableConfig] = None,
) -> AIMessage:
    aggregated_chunk = None
    for chunk in runnable.stream(messages, config=config):
        aggregated_chunk = chunk if aggregated_chunk is None else aggregated_chunk + chunk

    if aggregated_chunk is None:
        response = runnable.invoke(messages, config=config)
        if isinstance(response, AIMessage):
            return response
        return AIMessage(content=str(getattr(response, "content", "") or response))

    message = message_chunk_to_message(aggregated_chunk)
    if isinstance(message, AIMessage):
        return message
    return AIMessage(content=str(getattr(message, "content", "") or message))


def _build_reply_qualification_context(state: AgentState) -> Dict[str, Any]:
    sealing_state = state.get("sealing_state") or {}
    governance = sealing_state.get("governance") or {}
    rwdr_output = ((sealing_state.get("rwdr") or {}).get("output")) or {}
    cycle = sealing_state.get("cycle") or {}
    working_profile = state.get("working_profile") or {}
    blockers = [str(item) for item in governance.get("unknowns_release_blocking", []) if item]
    blockers.extend(str(item) for item in governance.get("gate_failures", []) if item)
    if rwdr_output.get("hard_stop"):
        blockers.append(str(rwdr_output.get("hard_stop")))
    invalidation_state = build_conversation_guidance_contract(
        {
            "sealing_state": sealing_state,
            "working_profile": working_profile,
            "relevant_fact_cards": state.get("relevant_fact_cards", []),
        }
    )
    requires_recompute = invalidation_state.get("ask_mode") == "recompute_first"
    obsolescence_state = "active" if bool(cycle.get("contract_obsolete")) else "clear"
    return {
        "rwdr_type_class": rwdr_output.get("type_class"),
        "hard_stop": rwdr_output.get("hard_stop"),
        "review_flags": list(rwdr_output.get("review_flags", [])),
        "blockers": list(dict.fromkeys(blockers)),
        "scope_of_validity": list(governance.get("scope_of_validity", [])),
        "assumptions_active": list(governance.get("assumptions_active", [])),
        "obsolescence_state": obsolescence_state,
        "recompute_requirement": "required" if requires_recompute else "not_required",
    }


async def _retrieve_relevant_cards_async(query: str, tenant_id: Optional[str]) -> List[Any]:
    path_used = "real_rag"
    try:
        relevant_cards = await retrieve_rag_context(query, tenant_id)
    except Exception as e:
        logger.error(f"[RAG] Real-RAG Error, falling back: {e}", exc_info=True)
        relevant_cards = []
        path_used = "real_rag_error_fallback"

    if not relevant_cards and query:
        relevant_cards = get_fact_cards(query, tenant_id)
        if path_used != "real_rag_error_fallback":
            path_used = "pseudo_rag_fallback"

    logger.info(f"[RAG] Path: {path_used}, Hits: {len(relevant_cards)}, Tenant: {tenant_id}")
    print(f"[RAG] Path: {path_used}, Hits: {len(relevant_cards)}, Tenant: {tenant_id}", flush=True)
    return relevant_cards


def _retrieve_relevant_cards_sync(query: str, tenant_id: Optional[str]) -> List[Any]:
    return asyncio.run(_retrieve_relevant_cards_async(query, tenant_id))

async def reasoning_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """
    Reasoning Node (Phase D1 - RAG Injection).
    Reichert den Kontext mit FactCards an.
    Nutzt Real-RAG als Primärquelle mit sauberem async Fallback (Phase K19).
    """
    messages = list(state.get("messages", []))
    current_profile = dict(state.get("working_profile") or {})
    tenant_id = state.get("tenant_id")
    query = _extract_query(messages)
    relevant_cards = await _retrieve_relevant_cards_async(query, tenant_id)
    cards_data = _normalize_cards(relevant_cards)
    _sealing_state_r = state.get("sealing_state") or {}
    _det_hash_r = snapshot_deterministic_layers(_sealing_state_r)
    new_profile = extract_parameters(query, current_profile, cards_data) if query else current_profile
    assert_deterministic_unchanged(_det_hash_r, _sealing_state_r, node_name="reasoning_node")
    system_msg = _build_reasoning_prompt(cards_data, new_profile)
    llm = get_llm(config)
    llm_with_tools = llm.bind_tools([submit_claim])
    full_messages = [system_msg] + list(messages)
    response = await _collect_streamed_ai_message(llm_with_tools, full_messages)
    return {
        "messages": [response],
        "relevant_fact_cards": cards_data,
        "working_profile": new_profile
    }


def reasoning_node_sync(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    messages = list(state.get("messages", []))
    current_profile = dict(state.get("working_profile") or {})
    tenant_id = state.get("tenant_id")
    query = _extract_query(messages)
    relevant_cards = _retrieve_relevant_cards_sync(query, tenant_id)
    cards_data = _normalize_cards(relevant_cards)
    _sealing_state_rs = state.get("sealing_state") or {}
    _det_hash_rs = snapshot_deterministic_layers(_sealing_state_rs)
    new_profile = extract_parameters(query, current_profile, cards_data) if query else current_profile
    assert_deterministic_unchanged(_det_hash_rs, _sealing_state_rs, node_name="reasoning_node_sync")
    system_msg = _build_reasoning_prompt(cards_data, new_profile)
    llm = get_llm(config)
    llm_with_tools = llm.bind_tools([submit_claim])
    full_messages = [system_msg] + list(messages)
    response = _collect_streamed_ai_message_sync(llm_with_tools, full_messages, config=config)
    return {
        "messages": [response],
        "relevant_fact_cards": cards_data,
        "working_profile": new_profile
    }

def evidence_tool_node(state: AgentState) -> dict:
    """
    Evidence Tool Node (Phase C4/H5).
    Abfangen, Sammeln und Injizieren von Claims in den fachlichen State.
    Liefert Feedback über Konflikte an das LLM zurück.
    """
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", [])
    
    # 1. Claims und Mapping sammeln
    new_claims: List[Claim] = []
    claim_to_tool_id = {}
    
    for tc in tool_calls:
        if tc["name"] == "submit_claim":
            args = tc["args"]
            claim = Claim(
                claim_type=args["claim_type"],
                statement=args["statement"],
                confidence=args["confidence"],
                source_fact_ids=args.get("source_fact_ids", [])
            )
            new_claims.append(claim)
            claim_to_tool_id[claim.statement] = tc["id"]

    if not new_claims:
        return {}

    # Aktuellen sealing_state extrahieren
    old_sealing_state = state["sealing_state"]
    current_revision = old_sealing_state["cycle"]["state_revision"]
    _det_hash_evidence = snapshot_deterministic_layers(old_sealing_state)

    # 2. Konflikte prüfen (Phase B2)
    intelligence_conflicts, validated_params = evaluate_claim_conflicts(
        claims=new_claims,
        asserted_state=old_sealing_state["asserted"],
        relevant_fact_cards=state.get("relevant_fact_cards", [])
    )
    validated_params = claim_whitelist_check(validated_params)
    # Guard: evaluate_claim_conflicts must never mutate the deterministic layers.
    # Assert on old_sealing_state (before the reducer runs) so the check is sound.
    assert_deterministic_unchanged(_det_hash_evidence, old_sealing_state, node_name="evidence_tool_node")

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

    # 3. State-Update ausschließlich über den Engineering-Firewall-Reducer.
    new_sealing_state = process_cycle_update(
        old_state=old_sealing_state,
        intelligence_conflicts=intelligence_conflicts,
        expected_revision=current_revision,
        validated_params=validated_params,
        raw_claims=raw_claims,
        relevant_fact_cards=state.get("relevant_fact_cards", []),
    )

    # 4. Tool-Feedback (Firewall Feedback Loop H5)
    tool_outputs: List[ToolMessage] = []
    
    # Gruppiere Konflikte nach Statement
    conflicts_by_statement = {}
    for c in intelligence_conflicts:
        stmt = c["claim_statement"]
        if stmt not in conflicts_by_statement:
            conflicts_by_statement[stmt] = []
        conflicts_by_statement[stmt].append(c)

    for claim in new_claims:
        tool_id = claim_to_tool_id[claim.statement]
        
        # Prüfen, ob für diesen Claim Konflikte vorliegen
        claim_conflicts = conflicts_by_statement.get(claim.statement, [])
        
        if claim_conflicts:
            # Detaillierte Fehlermeldung für das LLM
            error_msgs = []
            for c in claim_conflicts:
                if c["type"] == "DOMAIN_LIMIT_VIOLATION":
                    error_msgs.append(f"DOMAIN_LIMIT_VIOLATION: {c['message']}")
                else:
                    error_msgs.append(f"CONFLICT ({c['severity']}): {c['message']}")
            
            content = "Fehler bei der Claim-Verarbeitung:\n" + "\n".join(error_msgs)
        else:
            content = f"Claim erfolgreich verarbeitet: {claim.statement}"

        tool_outputs.append(ToolMessage(
            content=content,
            tool_call_id=tool_id
        ))

    # Rückgabe an den Graphen
    return {
        "messages": tool_outputs,
        "sealing_state": new_sealing_state
    }

def selection_node(state: AgentState) -> dict:
    sealing_state = state["sealing_state"]
    selection_state = build_selection_state(
        relevant_fact_cards=state.get("relevant_fact_cards", []),
        cycle_state=sealing_state.get("cycle", {}),
        governance_state=sealing_state.get("governance", {}),
        asserted_state=sealing_state.get("asserted", {}),
    )
    new_sealing_state = dict(sealing_state)
    new_sealing_state["selection"] = selection_state
    return {"sealing_state": new_sealing_state}


def final_response_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    selection_state = state["sealing_state"].get("selection", {})
    guidance_contract = build_conversation_guidance_contract(state)
    visible_case_narrative = build_visible_case_narrative(state=state)
    governed_summary = str(visible_case_narrative.get("governed_summary") or build_final_reply(
        selection_state,
        qualification_context=_build_reply_qualification_context(state),
    ))
    latest_user_message = _extract_query(list(state.get("messages", [])))
    prompt_messages = _build_visible_reply_messages(
        latest_user_message=latest_user_message,
        governed_summary=governed_summary,
        visible_case_narrative=visible_case_narrative,
        guidance_contract=guidance_contract,
    )

    try:
        llm = get_llm(config)
        response = _collect_streamed_ai_message_sync(llm, prompt_messages, config=config)
        reply = (response.content if isinstance(response, AIMessage) else str(getattr(response, "content", "") or response)).strip()
        if not reply:
            reply = build_visible_reply_fallback(selection_state, guidance_contract)
    except Exception:
        logger.exception("Visible final reply rendering failed; falling back to deterministic reply.")
        reply = build_visible_reply_fallback(selection_state, guidance_contract)

    return {"messages": [AIMessage(content=reply)]}


def rwdr_orchestration_node(state: AgentState) -> dict:
    """Graph entry for the active RWDR flow.

    The graph may route messages into the RWDR path, but it must not duplicate
    core or decision logic. RWDR engineering stays in the dedicated modules.
    """
    latest_user_message = None
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            latest_user_message = message.content
            break
    new_sealing_state, reply = run_rwdr_orchestration(
        state["sealing_state"],
        latest_user_message=latest_user_message,
    )
    return {"sealing_state": new_sealing_state, "messages": [reply]}


def entry_router(state: AgentState) -> Literal["rwdr_orchestration_node", "reasoning_node"]:
    if is_rwdr_flow_active(state):
        return "rwdr_orchestration_node"
    return "reasoning_node"


def router(state: AgentState) -> Literal["evidence_tool_node", "selection_node"]:
    """
    Conditional Edge zur Prüfung auf Tool-Calls.
    Ermöglicht deterministisches Routing (Blueprint Section 03).
    """
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    
    # Prüfe auf Tool-Calls im letzten Message-Objekt
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "evidence_tool_node"
    
    return "selection_node"

# Aufbau der Graphen-Topologie
graph_builder = StateGraph(AgentState)

# Nodes hinzufügen
graph_builder.add_node("rwdr_orchestration_node", rwdr_orchestration_node)
graph_builder.add_node("reasoning_node", reasoning_node_sync)
graph_builder.add_node("evidence_tool_node", evidence_tool_node)
graph_builder.add_node("selection_node", selection_node)
graph_builder.add_node("final_response_node", final_response_node)

# Edges definieren (START -> rwdr|reasoning -> ...)
graph_builder.add_conditional_edges(
    START,
    entry_router,
    {
        "rwdr_orchestration_node": "rwdr_orchestration_node",
        "reasoning_node": "reasoning_node",
    }
)

graph_builder.add_conditional_edges(
    "reasoning_node",
    router,
    {
        "evidence_tool_node": "evidence_tool_node",
        "selection_node": "selection_node",
    }
)

graph_builder.add_edge("rwdr_orchestration_node", END)
graph_builder.add_edge("evidence_tool_node", "reasoning_node")
graph_builder.add_edge("selection_node", "final_response_node")
graph_builder.add_edge("final_response_node", END)

# Kompilieren des Graphen
app = graph_builder.compile()
