import pytest
import asyncio
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.agent.api.router import router, SESSION_STORE, chat_endpoint, event_generator
from app.agent.api.models import ChatRequest
from app.agent.domain.rwdr import RWDRSelectorOutputDTO
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

    with patch("app.agent.api.router.execute_agent", return_value=mock_updated_state):
        response = asyncio.run(
            chat_endpoint(ChatRequest(message="Hallo Agent", session_id="test_session"))
        )

        # 3. Validierung
        data = response.model_dump()
        
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
    
    with patch("app.agent.api.router.execute_agent", return_value=mock_state_1):
        asyncio.run(chat_endpoint(ChatRequest(message="Erste Nachricht", session_id=session_id)))
    
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
    
    with patch("app.agent.api.router.execute_agent", return_value=mock_state_2):
        response = asyncio.run(chat_endpoint(ChatRequest(message="Zweite Nachricht", session_id=session_id)))
    
    assert response.reply == "Fortgesetzt."
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

    with patch("app.agent.api.router.app.astream_events", side_effect=mock_astream_events):
        chunks = []
        async def _collect():
            async for chunk in event_generator(ChatRequest(message="Starte Stream", session_id=session_id)):
                chunks.append(chunk)

        asyncio.run(_collect())
        content = "".join(chunks)

        assert "Stream" in content
        assert "ing" in content
        assert "state" in content
        assert "10" in content
        assert "[DONE]" in content


def test_api_chat_stream_endpoint_projects_rwdr_payload():
    session_id = "stream_rwdr_test"

    async def mock_astream_events(state, version):
        del version
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {
                "messages": state["messages"] + [AIMessage(content="RWDR streaming")],
                "working_profile": {},
                "sealing_state": {
                    "cycle": {"state_revision": 11},
                    "rwdr": {
                        "flow": {
                            "active": True,
                            "stage": "stage_2",
                            "missing_fields": ["available_width_mm"],
                            "next_field": "available_width_mm",
                            "ready_for_decision": False,
                            "decision_executed": False,
                        },
                        "output": RWDRSelectorOutputDTO(
                            type_class="engineering_review_required",
                            modifiers=[],
                            warnings=[],
                            review_flags=["review_water_with_pressure"],
                            hard_stop=None,
                            reasoning=["Projected in SSE payload."],
                        ),
                    },
                },
            }}
        }

    with patch("app.agent.api.router.app.astream_events", side_effect=mock_astream_events):
        chunks = []

        async def _collect():
            async for chunk in event_generator(ChatRequest(message="RWDR Stream", session_id=session_id)):
                chunks.append(chunk)

        asyncio.run(_collect())
        content = "".join(chunks)

        assert "\"rwdr\"" in content
        assert "\"stage_2\"" in content
        assert "\"rwdr_output\"" in content
        assert "\"engineering_review_required\"" in content


def test_api_chat_endpoint_transports_structured_rwdr_output():
    mock_updated_state = {
        "messages": [
            HumanMessage(content="RWDR"),
            AIMessage(content="RWDR preselection ready.")
        ],
        "sealing_state": {
            "cycle": {"state_revision": 2, "analysis_cycle_id": "session_rwdr_1"},
            "governance": {"release_status": "inadmissible"},
            "rwdr": {
                "output": RWDRSelectorOutputDTO(
                    type_class="standard_rwdr",
                    modifiers=[],
                    warnings=[],
                    review_flags=[],
                    hard_stop=None,
                    reasoning=["Deterministic RWDR output attached to chat response."],
                )
            },
        },
    }

    with patch("app.agent.api.router.execute_agent", return_value=mock_updated_state):
        response = asyncio.run(
            chat_endpoint(ChatRequest(message="RWDR", session_id="rwdr_session"))
        )

    assert response.rwdr_output is not None
    assert response.rwdr_output.type_class == "standard_rwdr"
