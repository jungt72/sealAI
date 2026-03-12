import pytest
from pydantic import ValidationError
from app.agent.api.models import ChatRequest, ChatResponse
from app.agent.domain.rwdr import RWDRSelectorInputDTO, RWDRSelectorInputPatchDTO, RWDRSelectorOutputDTO

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


def test_chat_request_accepts_rwdr_input_contract():
    req = ChatRequest(
        message="Bitte RWDR vorselektieren",
        rwdr_input=RWDRSelectorInputDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=35.0,
            max_speed_rpm=2800.0,
            pressure_profile="light_pressure_upto_0_5_bar",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
            confidence={"pressure_profile": "known"},
        ),
    )

    assert req.rwdr_input is not None
    assert req.rwdr_input.shaft_diameter_mm == 35.0


def test_chat_request_accepts_rwdr_input_patch_contract():
    req = ChatRequest(
        message="RWDR weiterfuehren",
        rwdr_input_patch=RWDRSelectorInputPatchDTO(
            max_speed_rpm=2800.0,
            pressure_profile="light_pressure_upto_0_5_bar",
            confidence={"pressure_profile": "known"},
        ),
    )

    assert req.rwdr_input_patch is not None
    assert req.rwdr_input_patch.max_speed_rpm == 2800.0


def test_chat_response_accepts_rwdr_output_contract():
    res = ChatResponse(
        reply="RWDR-Struktur erfasst",
        session_id="session-123",
        sealing_state={"cycle": {"state_revision": 1}},
        rwdr_output=RWDRSelectorOutputDTO(
            type_class="rwdr_with_dust_lip",
            modifiers=["installation_sleeve_required"],
            warnings=[],
            review_flags=["review_due_to_geometry"],
            hard_stop=None,
            reasoning=["API contract exposes typed RWDR output."],
        ),
    )

    assert res.rwdr_output is not None
    assert res.rwdr_output.review_flags == ["review_due_to_geometry"]
