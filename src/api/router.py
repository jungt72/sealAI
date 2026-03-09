import json
from typing import Dict, AsyncGenerator
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from src.api.models import ChatRequest, ChatResponse
from src.agent.graph import app
from src.agent.state import AgentState
from src.main import create_initial_state
from langchain_core.messages import HumanMessage, AIMessage

router = APIRouter()

# Globaler In-Memory Session Store (Phase F2)
SESSION_STORE: Dict[str, AgentState] = {}

def execute_agent(state: AgentState) -> AgentState:
    """Kapselt den Aufruf des LangGraph-Agenten."""
    return app.invoke(state)

async def event_generator(request: ChatRequest) -> AsyncGenerator[str, None]:
    """
    Asynchroner Generator für SSE-Streaming (Phase F3).
    Extrahiert Chunks aus dem LLM-Stream und sendet sie an das Frontend.
    """
    session_id = request.session_id
    
    # 1. Session laden oder initialisieren
    if session_id not in SESSION_STORE:
        initial_sealing_state = create_initial_state()
        initial_sealing_state["cycle"]["analysis_cycle_id"] = f"session_{session_id}_1"
        SESSION_STORE[session_id] = {
            "messages": [],
            "sealing_state": initial_sealing_state
        }
    
    current_state = SESSION_STORE[session_id]
    current_state["messages"].append(HumanMessage(content=request.message))
    
    full_reply = ""
    final_state = current_state # Fallback
    
    try:
        # 2. Über LangGraph Events iterieren (Version v2)
        async for event in app.astream_events(current_state, version="v2"):
            kind = event["event"]
            
            # Token-Streaming vom Chat-Modell
            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and chunk.content:
                    full_reply += chunk.content
                    yield f"data: {json.dumps({'chunk': chunk.content})}\n\n"
            
            # Finalen State am Ende der Kette abgreifen
            elif kind == "on_chain_end" and event["name"] == "LangGraph":
                final_state = event["data"].get("output")

        # 3. Session-Store aktualisieren
        if final_state:
            SESSION_STORE[session_id] = final_state
            # 4. Finalen technischen State senden
            yield f"data: {json.dumps({'state': final_state['sealing_state']})}\n\n"
        
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    # (Bestehender Code unverändert, zur Kürze hier weggelassen oder beibehalten)
    # ... (Code von F2)
    session_id = request.session_id
    if session_id not in SESSION_STORE:
        initial_sealing_state = create_initial_state()
        initial_sealing_state["cycle"]["analysis_cycle_id"] = f"session_{session_id}_1"
        SESSION_STORE[session_id] = {"messages": [], "sealing_state": initial_sealing_state}
    current_state = SESSION_STORE[session_id]
    current_state["messages"].append(HumanMessage(content=request.message))
    try:
        updated_state = execute_agent(current_state)
        SESSION_STORE[session_id] = updated_state
        last_msg = [m for m in updated_state["messages"] if isinstance(m, AIMessage)][-1]
        return ChatResponse(reply=last_msg.content, session_id=session_id, sealing_state=updated_state["sealing_state"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """
    Streaming-Endpunkt für Echtzeit-Antworten (Phase F3).
    Gibt eine StreamingResponse mit text/event-stream zurück.
    """
    return StreamingResponse(
        event_generator(request),
        media_type="text/event-stream"
    )
