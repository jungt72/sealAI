from typing import Literal, List, Optional, Any
from langgraph.graph import StateGraph, START, END
from src.agent.state import AgentState, SealingAIState
from src.evidence.models import Claim, ClaimType
from src.agent.logic import evaluate_claim_conflicts, process_cycle_update
from src.agent.tools import submit_claim
from langchain_core.messages import ToolMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableConfig

def get_llm(config: Optional[RunnableConfig] = None):
    """
    Factory-Methode für das LLM (Phase C5).
    Ermöglicht einfache Erweiterbarkeit und Mocking in Tests.
    """
    # Standardmodell für Reasoning
    return ChatOpenAI(model="gpt-4o-mini", temperature=0)

def reasoning_node(state: AgentState, config: Optional[RunnableConfig] = None) -> dict:
    """
    Reasoning Node (Phase C5).
    Nutzt ein LLM mit gebundenen Tools, um die technische Strategie festzulegen.
    """
    llm = get_llm(config)
    
    # Binde das submit_claim Tool zwingend an das Modell (Strict Tooling)
    llm_with_tools = llm.bind_tools([submit_claim])
    
    # Aufruf des LLM mit dem bisherigen Nachrichtenverlauf
    response = llm_with_tools.invoke(state["messages"])
    
    # Rückgabe der AIMessage an LangGraph
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
