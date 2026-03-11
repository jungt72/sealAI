from typing import Literal, List, Optional, Any
from langgraph.graph import StateGraph, START, END
from app.agent.agent.state import AgentState, SealingAIState
from app.agent.evidence.models import Claim, ClaimType
from app.agent.agent.logic import evaluate_claim_conflicts, process_cycle_update, extract_parameters
from app.agent.agent.tools import submit_claim
from app.agent.agent.knowledge import load_fact_cards, retrieve_fact_cards, FactCard
from app.agent.agent.prompts import SYSTEM_PROMPT_TEMPLATE
from langchain_core.messages import ToolMessage, AIMessage, SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig
from dotenv import load_dotenv
import os
import json

# Umgebungsvariablen laden (API Keys etc.)
load_dotenv()

# Pfad zur Knowledge Base
_KB_PATH = "upload/PTFE/SEALAI_KB_PTFE_factcards_gates_v1_3.json"
_CARDS_CACHE: Optional[List[FactCard]] = None

def get_fact_cards() -> List[FactCard]:
    """Lazy Loader für die Knowledge Base."""
    global _CARDS_CACHE
    if _CARDS_CACHE is None:
        # Versuche den Pfad relativ zur Root zu finden
        root_path = os.getcwd()
        path = os.path.join(root_path, _KB_PATH)
        _CARDS_CACHE = load_fact_cards(path)
    return _CARDS_CACHE

def get_llm(config: Optional[RunnableConfig] = None):
    """
    Factory-Methode für das LLM (Phase C5).
    """
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)

def reasoning_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """
    Reasoning Node (Phase D1 - RAG Injection).
    Reichert den Kontext mit FactCards aus der Knowledge Base an.
    """
    messages = state.get("messages", [])
    current_profile = state.get("working_profile", {})
    
    # 1. Knowledge Retrieval
    # Suche nach der letzten HumanMessage für die RAG-Suche
    query = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            query = msg.content
            break
            
    cards = get_fact_cards()
    relevant_cards = retrieve_fact_cards(query, cards) if query else []
    
    # 2. Heuristische Extraktion (Wave 1: Bleibt im working_profile)
    all_cards_data = [{"topic": c.topic, "content": c.content, "tags": c.tags} for c in cards]
    new_profile = extract_parameters(query, current_profile, all_cards_data) if query else current_profile

    # 3. Context Formatting
    context_str = "\n---\n".join([f"Topic: {c.topic}\nContent: {c.content}" for c in relevant_cards])
    if not context_str:
        context_str = "Keine relevanten Informationen in der Wissensdatenbank gefunden."
        
    # 4. Prompt Construction
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        context=context_str,
        working_profile=json.dumps(new_profile, indent=2)
    )
    system_msg = SystemMessage(content=system_prompt)
    
    # 5. LLM Call
    llm = get_llm(config)
    llm_with_tools = llm.bind_tools([submit_claim])
    
    # SystemMessage GANZ VORNE anfügen
    full_messages = [system_msg] + list(messages)
    
    response = llm_with_tools.invoke(full_messages)
    
    # FactCards für Tool-Node persistieren (Phase H6)
    cards_data = [{"topic": c.topic, "content": c.content, "tags": c.tags} for c in relevant_cards]
    
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

    # 3. State-Update durchführen (Phase A8)
    new_sealing_state = process_cycle_update(
        old_state=old_sealing_state,
        intelligence_conflicts=intelligence_conflicts,
        expected_revision=current_revision,
        validated_params=validated_params
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

def router(state: AgentState) -> Literal["evidence_tool_node", END]:
    """
    Conditional Edge zur Prüfung auf Tool-Calls.
    Ermöglicht deterministisches Routing (Blueprint Section 03).
    """
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    
    # Prüfe auf Tool-Calls im letzten Message-Objekt
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "evidence_tool_node"
    
    return END

# Aufbau der Graphen-Topologie
graph_builder = StateGraph(AgentState)

# Nodes hinzufügen
graph_builder.add_node("reasoning_node", reasoning_node)
graph_builder.add_node("evidence_tool_node", evidence_tool_node)

# Edges definieren (START -> reasoning_node <--> evidence_tool_node -> END)
graph_builder.add_edge(START, "reasoning_node")

graph_builder.add_conditional_edges(
    "reasoning_node",
    router,
    {
        "evidence_tool_node": "evidence_tool_node",
        END: END
    }
)

graph_builder.add_edge("evidence_tool_node", "reasoning_node")

# Kompilieren des Graphen
app = graph_builder.compile()
