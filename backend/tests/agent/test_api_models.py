import pytest
from pydantic import ValidationError
from app.agent.api.models import ChatRequest, ChatResponse

def test_chat_request_valid():
    """
    Test: Gültige ChatRequest-Instanziierung.
    """
    req = ChatRequest(message="Hallo", session_id="session-1")
    assert req.message == "Hallo"
    assert req.session_id == "session-1"

def test_chat_request_default_session():
    """
    Test: ChatRequest nutzt Standardwert für session_id.
    """
    req = ChatRequest(message="Hallo")
    assert req.session_id == "default"

def test_chat_request_empty_message():
    """
    Test: ChatRequest lehnt leere Nachrichten ab (min_length=1).
    """
    with pytest.raises(ValidationError):
        ChatRequest(message="")

def test_chat_request_extra_fields():
    """
    Test: ChatRequest lehnt unbekannte Felder ab (extra="forbid").
    """
    with pytest.raises(ValidationError):
        ChatRequest(message="Hallo", unknown_field="Ups")

def test_chat_response_valid():
    """
    Test: Gültige ChatResponse-Instanziierung.
    """
    res = ChatResponse(
        reply="Hallo zurück",
        session_id="session-123",
        sealing_state={"cycle": {"state_revision": 1}}
    )
    assert res.reply == "Hallo zurück"
    assert res.session_id == "session-123"
    assert res.sealing_state["cycle"]["state_revision"] == 1

def test_chat_response_extra_fields():
    """
    Test: ChatResponse lehnt unbekannte Felder ab (extra="forbid").
    """
    with pytest.raises(ValidationError):
        ChatResponse(
            reply="Antwort",
            session_id="id",
            sealing_state={},
            extra="unzulässig"
        )
