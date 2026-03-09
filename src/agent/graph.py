from typing import Literal, List, Optional, Any
from langgraph.graph import StateGraph, START, END
from src.agent.state import AgentState, SealingAIState
from src.evidence.models import Claim, ClaimType
from src.agent.logic import evaluate_claim_conflicts, process_cycle_update
from src.agent.tools import submit_claim
from src.agent.knowledge import load_fact_cards, retrieve_fact_cards, FactCard
from src.agent.prompts import SYSTEM_PROMPT_TEMPLATE
from langchain_core.messages import ToolMessage, AIMessage, SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig
from dotenv import load_dotenv
import os

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
    
    # 1. Knowledge Retrieval
    # Suche nach der letzten HumanMessage für die RAG-Suche
    query = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            query = msg.content
            break
            
    cards = get_fact_cards()
    relevant_cards = retrieve_fact_cards(query, cards) if query else []
    
    # 2. Context Formatting
    context_str = "\n---\n".join([f"Topic: {c.topic}\nContent: {c.content}" for c in relevant_cards])
    if not context_str:
        context_str = "Keine relevanten Informationen in der Wissensdatenbank gefunden."
        
    # 3. Prompt Construction
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context_str)
    system_msg = SystemMessage(content=system_prompt)
    
    # 4. LLM Call
    llm = get_llm(config)
    llm_with_tools = llm.bind_tools([submit_claim])
    
    # SystemMessage GANZ VORNE anfügen
    full_messages = [system_msg] + list(messages)
    
    response = llm_with_tools.invoke(full_messages)
    
    return {"messages": [response]}

def evidence_tool_node(state: AgentState) -> dict:
    """
    Evidence Tool Node (Phase C4).
    Abfangen, Sammeln und Injizieren von Claims in den fachlichen State.
    """
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", [])
    
    new_claims: List[Claim] = []
    tool_outputs: List[ToolMessage] = []
    
    for tc in tool_calls:
        if tc["name"] == "submit_claim":
            # Claim rekonstruieren
            args = tc["args"]
            claim = Claim(
                claim_type=args["claim_type"],
                statement=args["statement"],
                confidence=args["confidence"],
                source_fact_ids=args.get("source_fact_ids", [])
            )
            new_claims.append(claim)
            
            # ToolMessage für LangGraph Feedback-Schleife
            tool_outputs.append(ToolMessage(
                content=f"Claim verarbeitet: {claim.statement}",
                tool_call_id=tc["id"]
            ))

    if not new_claims:
        return {}

    # Aktuellen sealing_state extrahieren
    old_sealing_state = state["sealing_state"]
    current_revision = old_sealing_state["cycle"]["state_revision"]

    # 1. Konflikte prüfen (Phase B2)
    intelligence_conflicts = evaluate_claim_conflicts(
        claims=new_claims,
        asserted_state=old_sealing_state["asserted"]
    )

    # 2. State-Update durchführen (Phase A8)
    new_sealing_state = process_cycle_update(
        old_state=old_sealing_state,
        intelligence_conflicts=intelligence_conflicts,
        expected_revision=current_revision
    )

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
