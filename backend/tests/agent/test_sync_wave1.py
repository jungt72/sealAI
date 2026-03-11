import pytest
from app.agent.agent.sync import sync_working_profile_to_state

def test_sync_no_longer_writes_upstream():
    """
    Wave 1: Verifiziert, dass Änderungen im working_profile NICHT mehr
    in den asserted state (sealing_state) geschrieben werden.
    """
    state = {
        "working_profile": {
            "speed": 5000,
            "diameter": 30,
            "pressure": 10
        },
        "sealing_state": {
            "asserted": {
                "machine_profile": {}
            }
        }
    }
    
    updated_state = sync_working_profile_to_state(state)
    
    assert "speed" not in updated_state["sealing_state"]["asserted"]["machine_profile"]
    assert "diameter" not in updated_state["sealing_state"]["asserted"]["machine_profile"]
    assert "pressure" not in updated_state["sealing_state"]["asserted"]["machine_profile"]

def test_sync_still_mirrors_downstream():
    """
    Wave 1: Verifiziert, dass der asserted state (Wahrheit) weiterhin 
    in das working_profile (UI) gespiegelt wird.
    """
    state = {
        "working_profile": {},
        "sealing_state": {
            "asserted": {
                "machine_profile": {
                    "material": "PTFE"
                },
                "medium_profile": {
                    "name": "Wasser"
                },
                "operating_conditions": {
                    "temperature": 120,
                    "pressure": 15
                }
            }
        }
    }
    
    updated_state = sync_working_profile_to_state(state)
    
    assert updated_state["working_profile"]["material"] == "PTFE"
    assert updated_state["working_profile"]["medium"] == "Wasser"
    assert updated_state["working_profile"]["temperature"] == 120
    assert updated_state["working_profile"]["pressure"] == 15

def test_live_calc_tile_generation_persists():
    """
    Wave 1: Verifiziert, dass das LiveCalcTile weiterhin aus dem working_profile
    generiert wird, damit die UI interaktiv bleibt.
    """
    state = {
        "working_profile": {
            "v_m_s": 7.85,
            "pv_value": 78.5,
            "speed": 5000
        },
        "sealing_state": {
            "asserted": {}
        }
    }
    
    updated_state = sync_working_profile_to_state(state)
    
    tile = updated_state["working_profile"]["live_calc_tile"]
    assert tile["v_surface_m_s"] == 7.85
    assert tile["pv_value_mpa_m_s"] == 7.85  # 78.5 / 10
    assert tile["parameters"]["speed"] == 5000
