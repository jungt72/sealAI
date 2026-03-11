import json
import os
from typing import Dict, AsyncGenerator
from fastapi import APIRouter, HTTPException, FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from app.agent.api.models import ChatRequest, ChatResponse
from app.agent.agent.graph import app
from app.agent.agent.state import AgentState
from app.agent.agent.sync import sync_working_profile_to_state
from app.agent.cli import create_initial_state
from langchain_core.messages import HumanMessage, AIMessage

router = APIRouter()

# Globaler In-Memory Session Store (Phase F2)
SESSION_STORE: Dict[str, AgentState] = {}

def execute_agent(state: AgentState) -> AgentState:
    """Kapselt den Aufruf des LangGraph-Agenten."""
    state = app.invoke(state)
    return sync_working_profile_to_state(state)

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
            "sealing_state": initial_sealing_state,
            "working_profile": {}
        }
    
    current_state = SESSION_STORE[session_id]
    current_state["messages"].append(HumanMessage(content=request.message))
    
    final_state = current_state 
    
    try:
        # 2. Über LangGraph Events iterieren (Version v2)
        async for event in app.astream_events(current_state, version="v2"):
            kind = event["event"]
            
            # Token-Streaming vom Chat-Modell
            if kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk and chunk.content:
                    yield f"data: {json.dumps({'chunk': chunk.content})}\n\n"
            
            # Finalen State am Ende der Kette abgreifen
            elif kind == "on_chain_end" and event["name"] == "LangGraph":
                final_state = event["data"].get("output")

        # 3. Session-Store aktualisieren
        if final_state:
            # Wave 1: Sync aufrufen
            final_state = sync_working_profile_to_state(final_state)
            SESSION_STORE[session_id] = final_state
            
            # 4. Finalen technischen State senden
            yield f"data: {json.dumps({
                'state': final_state['sealing_state'],
                'working_profile': final_state.get('working_profile', {})
            })}\n\n"
        
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """REST-Endpunkt für Chat-Anfragen (Phase F2)."""
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
    """Streaming-Endpunkt für Echtzeit-Antworten (Phase F3)."""
    return StreamingResponse(
        event_generator(request),
        media_type="text/event-stream"
    )

# FastAPI App Instanz für Phase G1
app_api = FastAPI(title="SealAI LangGraph PoC API")
app_api.include_router(router)

# Statische Dateien ausliefern
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app_api.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    print(f"WARNUNG: Statisches Verzeichnis nicht gefunden: {static_dir}")
