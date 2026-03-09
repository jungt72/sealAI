import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.router import router, SESSION_STORE
from langchain_core.messages import AIMessage, HumanMessage

# Temporäre App für den Router-Test
app = FastAPI()
app.include_router(router)

client = TestClient(app)

@pytest.fixture(autouse=True)
def clear_sessions():
    """Löscht den Session Store vor jedem Test."""
    SESSION_STORE.clear()

def test_api_chat_endpoint_success():
    """
    Test Phase F2:
    Verifiziert den POST /chat Endpunkt mit einem gemockten Agenten.
    """
    # 1. Mock für den Agenten-Lauf vorbereiten
    # Wir mocken die execute_agent Funktion, um keine echten API-Aufrufe zu machen.
    mock_updated_state = {
        "messages": [
            HumanMessage(content="Hallo Agent"),
            AIMessage(content="Hallo! Wie kann ich helfen?")
        ],
        "sealing_state": {
            "cycle": {"state_revision": 1, "analysis_cycle_id": "session_test_1"},
            "governance": {"release_status": "inadmissible"}
        }
    }

    with patch("src.api.router.execute_agent", return_value=mock_updated_state):
        # 2. Anfrage senden
        response = client.post(
            "/chat",
            json={"message": "Hallo Agent", "session_id": "test_session"}
        )

        # 3. Validierung
        assert response.status_code == 200
        data = response.json()
        
        assert data["reply"] == "Hallo! Wie kann ich helfen?"
        assert data["session_id"] == "test_session"
        assert "sealing_state" in data
        assert data["sealing_state"]["cycle"]["state_revision"] == 1

def test_api_session_persistence():
    """
    Test Phase F2:
    Verifiziert, dass der Session-Store Nachrichten akkumuliert.
    """
    session_id = "persistence_test"
    
    # Erste Anfrage
    mock_state_1 = {
        "messages": [HumanMessage(content="Erste Nachricht"), AIMessage(content="Verstanden.")],
        "sealing_state": {"cycle": {"state_revision": 1}}
    }
    
    with patch("src.api.router.execute_agent", return_value=mock_state_1):
        client.post("/chat", json={"message": "Erste Nachricht", "session_id": session_id})
    
    # Prüfen, ob Session existiert
    assert session_id in SESSION_STORE
    assert len(SESSION_STORE[session_id]["messages"]) == 2
    
    # Zweite Anfrage
    mock_state_2 = {
        "messages": [
            HumanMessage(content="Erste Nachricht"), 
            AIMessage(content="Verstanden."),
            HumanMessage(content="Zweite Nachricht"),
            AIMessage(content="Fortgesetzt.")
        ],
        "sealing_state": {"cycle": {"state_revision": 2}}
    }
    
    with patch("src.api.router.execute_agent", return_value=mock_state_2):
        response = client.post("/chat", json={"message": "Zweite Nachricht", "session_id": session_id})
    
    assert response.status_code == 200
    assert response.json()["reply"] == "Fortgesetzt."
    assert len(SESSION_STORE[session_id]["messages"]) == 4

def test_api_chat_empty_message():
    """
    Test Phase F2:
    Leere Nachrichten werden bereits auf Pydantic-Ebene (F1) abgelehnt.
    """
    response = client.post("/chat", json={"message": ""})
    assert response.status_code == 422 # Unprocessable Entity (FastAPI Validation)

def test_api_chat_stream_endpoint():
    """
    Test Phase F3:
    Verifiziert den Streaming-Endpunkt /chat/stream.
    """
    session_id = "stream_test"
    
    # Asynchroner Mock für astream_events
    async def mock_astream_events(state, version):
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": AIMessage(content="Stream")}
        }
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": AIMessage(content="ing")}
        }
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {
                "messages": state["messages"] + [AIMessage(content="Streaming")],
                "sealing_state": {"cycle": {"state_revision": 10}}
            }}
        }

    with patch("src.api.router.app.astream_events", side_effect=mock_astream_events):
        with client.stream(
            "POST", 
            "/chat/stream", 
            json={"message": "Starte Stream", "session_id": session_id}
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
            
            # Den Stream konsumieren und Inhalte prüfen
            content = "".join([line for line in response.iter_lines()])
            
            assert "Stream" in content
            assert "ing" in content
            assert "state" in content
            assert "10" in content
            assert "[DONE]" in content
