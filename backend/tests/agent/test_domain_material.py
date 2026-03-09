import pytest
from app.agent.domain.material import MaterialValidator, MaterialPhysicalProfile
from app.agent.domain.parameters import PhysicalParameter

@pytest.fixture
def fkm_profile():
    return MaterialPhysicalProfile(
        material_id="FKM_80",
        temp_min=-20.0,
        temp_max=200.0,
        v_surface_max=2.5,
        pv_limit_critical=3.0
    )

def test_material_temperature_validation(fkm_profile):
    """Test: Temperaturvalidierung für FKM."""
    validator = MaterialValidator(fkm_profile)
    
    # 150°C ist OK
    assert validator.validate_temperature(PhysicalParameter(value=150.0, unit="C")) is True
    
    # 250°C ist zu heiß
    assert validator.validate_temperature(PhysicalParameter(value=250.0, unit="C")) is False
    
    # -30°C ist zu kalt
    assert validator.validate_temperature(PhysicalParameter(value=-30.0, unit="C")) is False

def test_material_validation_report(fkm_profile):
    """Test: Erzeugung eines Berichts."""
    validator = MaterialValidator(fkm_profile)
    
    conditions = {
        "temperature": PhysicalParameter(value=400.0, unit="F") # 400°F ≈ 204.4°C (Zu heiß)
    }
    
    report = validator.get_validation_report(conditions)
    
    assert report["material_id"] == "FKM_80"
    assert report["is_valid"] is False
    assert report["checks"]["temperature"]["status"] == "CRITICAL"
    assert report["checks"]["temperature"]["value"] > 200.0

def test_material_profile_factory_from_fact_card():
    """
    Test Phase H7: FactCard Factory.
    Prüft, ob Profile korrekt aus FactCards extrahiert werden.
    """
    fact_card = {
        "topic": "PTFE-Compound G25",
        "content": "Gefülltes PTFE (G25) hat ein Temperaturlimit von max. 260 C.",
        "tags": ["ptfe", "material"]
    }
    
    profile = MaterialPhysicalProfile.from_fact_card(fact_card)
    
    assert profile is not None
    assert profile.material_id == "PTFE"
    assert profile.temp_max == 260.0
    assert profile.temp_min == -50.0 # Default fallback
    
    # Test NBR mit Range
    nbr_card = {
        "topic": "NBR 70 Shore",
        "content": "Standard NBR hat ein Limit von -30 bis 100 C.",
        "tags": ["nbr"]
    }
    
    nbr_profile = MaterialPhysicalProfile.from_fact_card(nbr_card)
    assert nbr_profile.material_id == "NBR"
    assert nbr_profile.temp_min == -30.0
    assert nbr_profile.temp_max == 100.0

def test_factory_returns_none_for_invalid_card():
    """Test: Factory gibt None zurück, wenn keine Daten gefunden werden."""
    invalid_card = {"topic": "Unbekannt", "content": "Keine technischen Daten."}
    assert MaterialPhysicalProfile.from_fact_card(invalid_card) is None
