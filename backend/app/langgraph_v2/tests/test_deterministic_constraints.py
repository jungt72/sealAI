import pytest
from app.langgraph_v2.nodes.reasoning_core_node import _build_system_prompt
from app.langgraph_v2.nodes.conversational_rag import _build_engineering_physics_report
from app.langgraph_v2.state import SealAIState, LiveCalcTile
from app.services.rag.state import WorkingProfile

def test_reasoning_core_prompt_with_chem_warning():
    state = SealAIState()
    state.live_calc_tile = LiveCalcTile(
        chem_warning=True,
        chem_message="NBR is incompatible with HEES oil at high temperatures."
    )
    profile = WorkingProfile(medium="HEES", temperature_max_c=80)
    state.working_profile = profile
    
    prompt = _build_system_prompt(
        state=state,
        profile=profile,
        unresolved_gaps=[],
        warning_notes=[],
        calc_ranges="status=warning"
    )
    
    assert "DETERMINISTIC SYSTEM STATE (INVIOLABLE RULES)" in prompt
    assert "CRITICAL WARNING: NBR is incompatible with HEES oil at high temperatures." in prompt
    assert "CONFLICT RESOLUTION (RAG vs. CALCULATION)" in prompt
    assert "Zwingende Einsatzbedingungen: Temperatur: 80.0 °C, Medium: HEES" in prompt

def test_conversational_rag_report_with_pv_warning():
    tile_dict = {
        "status": "warning",
        "pv_value_mpa_m_s": 2.5,
        "pv_warning": True,
        "chem_warning": True,
        "chem_message": "Material A is unsuitable for this chemical."
    }
    
    report, has_risk = _build_engineering_physics_report(tile_dict)
    
    assert has_risk is True
    assert "DETERMINISTIC SYSTEM STATE (INVIOLABLE RULES)" in report
    assert "CRITICAL WARNING: Material A is unsuitable for this chemical." in report
    assert "Aktueller PV-Wert: 2.5 MPa*m/s" in report
    assert "CONFLICT RESOLUTION (RAG vs. CALCULATION)" in report

def test_reasoning_core_prompt_no_tile():
    state = SealAIState()
    profile = WorkingProfile()
    
    prompt = _build_system_prompt(
        state=state,
        profile=profile,
        unresolved_gaps=[],
        warning_notes=[],
        calc_ranges="none"
    )
    
    assert "DETERMINISTIC SYSTEM STATE (INVIOLABLE RULES)" in prompt
    assert "The following parameters and warnings are the result of deterministic physical calculations" in prompt
