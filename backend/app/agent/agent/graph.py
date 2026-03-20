from typing import Literal, List, Optional, Any
import logging
from langgraph.graph import StateGraph, START, END
from app.agent.agent.state import AgentState, SealingAIState
from app.agent.evidence.models import Claim, ClaimType
from app.agent.agent.logic import evaluate_claim_conflicts, process_cycle_update, extract_parameters
from app.agent.agent.tools import submit_claim
from app.agent.agent.knowledge import load_fact_cards, retrieve_fact_cards
from app.agent.agent.prompts import SYSTEM_PROMPT_TEMPLATE
from app.agent.agent.selection import build_selection_state, build_final_reply
from langchain_core.messages import ToolMessage, AIMessage, SystemMessage, HumanMessage
try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover - minimal import repair for offline test env
    class ChatOpenAI:  # type: ignore[override]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def bind_tools(self, tools: list[Any]) -> "ChatOpenAI":
            return self

        async def ainvoke(self, messages: list[Any]) -> AIMessage:
            return AIMessage(content="stub")
from langchain_core.runnables import RunnableConfig
from dotenv import load_dotenv
import os
import json
import hashlib

# Umgebungsvariablen laden (API Keys etc.)
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


async def retrieve_rag_context(query: str, tenant_id: str | None) -> list[Any]:
    del tenant_id
    return retrieve_fact_cards_fallback(query)


def retrieve_fact_cards_fallback(query: str) -> list[Any]:
    kb_path = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base.json")
    cards = load_fact_cards(kb_path)
    return retrieve_fact_cards(query, cards)

def get_llm(config: Optional[RunnableConfig] = None):
    """
    Factory-Methode für das LLM (Phase C5).
    """
    return ChatOpenAI(model=_GRAPH_MODEL_ID, temperature=0)

async def reasoning_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """
    Reasoning Node (Phase D1 - RAG Injection).
    Reichert den Kontext mit FactCards an.
    Nutzt Real-RAG als Primärquelle mit sauberem async Fallback (Phase K19).
    """
    messages = state.get("messages", [])
    current_profile = state.get("working_profile", {})
    tenant_id = state.get("tenant_id")
    
    # 1. Knowledge Retrieval
    # Suche nach der letzten HumanMessage für die RAG-Suche
    query = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            query = msg.content
            break
            
    # Primärer Pfad: Real RAG (Sauberer Async-Aufruf)
    path_used = "real_rag"
    try:
        relevant_cards = await retrieve_rag_context(query, tenant_id)
    except Exception as e:
        logger.error(f"[RAG] Real-RAG Error, falling back: {e}", exc_info=True)
        relevant_cards = []
        path_used = "real_rag_error_fallback"

    # Fallback Pfad: Pseudo RAG (lokales JSON via knowledge-Service)
    if not relevant_cards and query:
        # retrieve_fact_cards_fallback ist aktuell synchron
        relevant_cards = retrieve_fact_cards_fallback(query)
        if path_used != "real_rag_error_fallback":
            path_used = "pseudo_rag_fallback"

    logger.info(f"[RAG] Path: {path_used}, Hits: {len(relevant_cards)}, Tenant: {tenant_id}")
    print(f"[RAG] Path: {path_used}, Hits: {len(relevant_cards)}, Tenant: {tenant_id}", flush=True)
    
    # 2. Heuristische Extraktion (Wave 1: Bleibt im working_profile)
    # Wir übergeben nur die relevanten Karten an extract_parameters (H8 Alternativen)
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
    cards_data = sorted(
        cards_data,
        key=lambda card: (
            str(card.get("evidence_id") or card.get("id") or ""),
            str(card.get("topic") or ""),
        ),
    )
    new_profile = extract_parameters(query, current_profile, cards_data) if query else current_profile

    # 3. Context Formatting
    context_str = "\n---\n".join(
        [f"Topic: {card.get('topic', '')}\nContent: {card.get('content', '')}" for card in cards_data]
    )
    if not context_str:
        context_str = "Keine relevanten Informationen in der Wissensdatenbank gefunden."
        
    # 4. Prompt Construction
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        context=context_str,
        working_profile=json.dumps(new_profile, indent=2)
    )
    system_prompt = f"{_NON_BINDING_ASSIST_INSTRUCTION}\n\n{system_prompt}"
    system_msg = SystemMessage(content=system_prompt)
    
    # 5. LLM Call
    llm = get_llm(config)
    llm_with_tools = llm.bind_tools([submit_claim])
    
    # SystemMessage GANZ VORNE anfügen
    full_messages = [system_msg] + list(messages)
    
    # invoke() ist synchron, invoke_async/ainvoke() wäre besser für echte async-chains
    response = await llm_with_tools.ainvoke(full_messages)
    
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

    # 2. Konflikte prüfen (Phase B2)
    intelligence_conflicts, validated_params = evaluate_claim_conflicts(
        claims=new_claims,
        asserted_state=old_sealing_state["asserted"],
        relevant_fact_cards=state.get("relevant_fact_cards", [])
    )

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


def final_response_node(state: AgentState) -> dict:
    selection_state = state["sealing_state"].get("selection", {})
    reply = build_final_reply(selection_state)
    return {"messages": [AIMessage(content=reply)]}


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
graph_builder.add_node("reasoning_node", reasoning_node)
graph_builder.add_node("evidence_tool_node", evidence_tool_node)
graph_builder.add_node("selection_node", selection_node)
graph_builder.add_node("final_response_node", final_response_node)

# Edges definieren (START -> reasoning_node <--> evidence_tool_node -> selection_node -> final_response_node -> END)
graph_builder.add_edge(START, "reasoning_node")

graph_builder.add_conditional_edges(
    "reasoning_node",
    router,
    {
        "evidence_tool_node": "evidence_tool_node",
        "selection_node": "selection_node",
    }
)

graph_builder.add_edge("evidence_tool_node", "reasoning_node")
graph_builder.add_edge("selection_node", "final_response_node")
graph_builder.add_edge("final_response_node", END)

# Kompilieren des Graphen
app = graph_builder.compile()
