"""
Tests für Number-Verification-Gate.
"""
import pytest

_SKIP_REASON = (
    "Legacy test targeting old calc engine number verification; replacement "
    "arrives in Sprint 4 Patch 4.6 and Sprint 4 Patch 4.7 per Implementation Plan. "
    "See audits/gate_0_to_1_2026-04-19.md §7.2."
)
pytest.skip(_SKIP_REASON, allow_module_level=True)

from app.langgraph_v2.nodes.p4_6_number_verification import (
    extract_numbers_with_units,
    node_p4_6_number_verification
)

@pytest.fixture
def anyio_backend():
    return 'asyncio'

def test_extract_numbers_basic():
    """Test basic number extraction."""
    text = "The max temperature is 260°C and pressure is 100 bar."
    numbers = extract_numbers_with_units(text)
    
    assert (260.0, "°c") in numbers  # Normalized to lowercase
    assert (100.0, "bar") in numbers

def test_extract_numbers_no_unit():
    """Test extraction without units."""
    text = "The value is 42 and another is 3.14"
    numbers = extract_numbers_with_units(text)
    
    assert (42.0, "") in numbers
    assert (3.14, "") in numbers

def test_extract_numbers_hrc():
    """Test HRC hardness values."""
    text = "Counterface must be 45 HRC minimum"
    numbers = extract_numbers_with_units(text)
    
    assert (45.0, "hrc") in numbers

@pytest.mark.anyio
async def test_verification_pass():
    """Test successful verification."""
    state = {
        "final_answer": "Max temperature is 260°C",
        "sources": [{"text": "PTFE max continuous temperature: 260°C"}],
        "factcard_matches": [],
        "recommendation_ready": True
    }
    
    result = await node_p4_6_number_verification(state)
    
    assert result["verification_passed"] is True
    assert result["last_node"] == "node_p4_6_number_verification"

@pytest.mark.anyio
async def test_verification_fail_hallucinated():
    """Test failed verification for hallucinated value."""
    state = {
        "final_answer": "Max temperature is 999°C",  # Hallucinated!
        "sources": [{"text": "PTFE max continuous temperature: 260°C"}],
        "factcard_matches": [],
        "recommendation_ready": True
    }
    
    result = await node_p4_6_number_verification(state)
    
    assert result["verification_passed"] is False
    assert "verification_error" in result
    assert len(result["verification_error"]["unverified_values"]) > 0

@pytest.mark.anyio
async def test_verification_factcard_source():
    """Test verification against FactCard."""
    state = {
        "final_answer": "Max temperature is 260°C",
        "sources": [],
        "factcard_matches": [
            {
                "id": "PTFE-F-001",
                "value": 260,
                "units": "°C",
                "property": "max_continuous_temp"
            }
        ],
        "recommendation_ready": True
    }
    
    result = await node_p4_6_number_verification(state)
    
    assert result["verification_passed"] is True

@pytest.mark.anyio
async def test_verification_tolerance():
    """Test rounding tolerance (±0.1%)."""
    state = {
        "final_answer": "Pressure is 100 bar",
        "sources": [{"text": "Operating pressure: 100.05 bar"}],  # Slight difference
        "factcard_matches": [],
        "recommendation_ready": True
    }
    
    result = await node_p4_6_number_verification(state)
    
    assert result["verification_passed"] is True  # Within tolerance

@pytest.mark.anyio
async def test_verification_skip_not_ready():
    """Test skip logic when recommendation_ready is False."""
    state = {
        "final_answer": "What is the pressure?",
        "sources": [],
        "factcard_matches": [],
        "recommendation_ready": False
    }
    
    result = await node_p4_6_number_verification(state)
    assert result["verification_passed"] is True

@pytest.mark.anyio
async def test_verification_skip_goal_smalltalk():
    """Test skip logic when goal is smalltalk."""
    state = {
        "final_answer": "I can help with seals.",
        "sources": [],
        "factcard_matches": [],
        "recommendation_ready": True,
        "intent": type('Intent', (), {'goal': 'smalltalk'})()
    }
    
    result = await node_p4_6_number_verification(state)
    assert result["verification_passed"] is True

@pytest.mark.anyio
async def test_verification_user_values():
    """Test verification against user-provided values in state."""
    state = {
        "final_answer": "The pressure you provided is 5 bar.",
        "sources": [],
        "factcard_matches": [],
        "recommendation_ready": True,
        "extracted_params": {"pressure_bar": 5.0}
    }
    
    result = await node_p4_6_number_verification(state)
    assert result["verification_passed"] is True

@pytest.mark.anyio
async def test_verification_list_marker_allowance():
    """Test that small integers (1-10) without units are allowed as fallback."""
    state = {
        "final_answer": "1. Do this. 2. Do that.",
        "sources": [],
        "factcard_matches": [],
        "recommendation_ready": True
    }
    
    result = await node_p4_6_number_verification(state)
    assert result["verification_passed"] is True
