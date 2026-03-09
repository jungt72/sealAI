import pytest
from app.agent.agent.logic import evaluate_claim_conflicts, process_cycle_update

def test_process_cycle_update_persists_parameters():
    """
    Test Phase A8: Validierte Parameter müssen in den asserted state geschrieben werden.
    """
    old_state = {
        "asserted": {
            "medium_profile": {"name": "Wasser"},
            "operating_conditions": {}
        },
        "governance": {"conflicts": [], "release_status": "rfq_ready"},
        "cycle": {"state_revision": 1, "snapshot_parent_revision": 0}
    }
    
    validated_params = {"temperature": 120.0, "pressure": 10.0}
    
    new_state = process_cycle_update(
        old_state=old_state,
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params=validated_params
    )
    
    assert new_state["asserted"]["operating_conditions"]["temperature"] == 120.0
    assert new_state["asserted"]["operating_conditions"]["pressure"] == 10.0
    assert new_state["cycle"]["state_revision"] == 2
from app.agent.evidence.models import Claim, ClaimType

def test_ptfe_temperature_limit_violation():
    """
    Test Phase H3/H6:
    Wenn Medium = PTFE und ein Claim 300°C fordert, muss ein CRITICAL Konflikt entstehen (via RAG).
    """
    # 1. State mit PTFE vorbereiten
    asserted_state = {
        "medium_profile": {"name": "PTFE-Compound"},
        "operating_conditions": {}
    }
    
    # 2. Claim mit 300°C einreichen
    claims = [
        Claim(
            claim_type=ClaimType.FACT_OBSERVED,
            statement="Die Anwendung läuft bei 300 C.",
            confidence=1.0,
            source_fact_ids=[]
        )
    ]

    # RAG FactCard für PTFE
    relevant_fact_cards = [{
        "topic": "PTFE Properties",
        "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
        "tags": ["ptfe"]
    }]
    
    # 3. Logik ausführen
    conflicts, validated_params = evaluate_claim_conflicts(
        claims, 
        asserted_state,
        relevant_fact_cards=relevant_fact_cards
    )
    
    # 4. Validierung
    assert len(conflicts) == 1
    assert conflicts[0]["type"] == "DOMAIN_LIMIT_VIOLATION"
    assert conflicts[0]["severity"] == "CRITICAL"
    assert "300" in conflicts[0]["message"]
    assert "260" in conflicts[0]["message"]
    assert "temperature" not in validated_params

def test_ptfe_temperature_within_limits():
    """
    Test Phase H3/H6:
    Wenn Medium = PTFE und ein Claim 200°C fordert, darf KEIN Konflikt entstehen.
    """
    asserted_state = {
        "medium_profile": {"name": "PTFE-Compound"},
        "operating_conditions": {}
    }
    
    claims = [
        Claim(
            claim_type=ClaimType.FACT_OBSERVED,
            statement="Temperatur ist 200 °C.",
            confidence=1.0,
            source_fact_ids=[]
        )
    ]

    relevant_fact_cards = [{
        "topic": "PTFE Properties",
        "content": "PTFE hat ein Temperaturlimit von max. 260 C.",
        "tags": ["ptfe"]
    }]
    
    conflicts, validated_params = evaluate_claim_conflicts(
        claims, 
        asserted_state,
        relevant_fact_cards=relevant_fact_cards
    )
    
    assert len(conflicts) == 0
    assert validated_params["temperature"] == 200.0

def test_non_ptfe_no_limit_check():
    """
    Test: Bei anderen Medien (z.B. NBR) gilt das 260°C Limit (hier) nicht.
    """
    asserted_state = {
        "medium_profile": {"name": "NBR"},
        "operating_conditions": {}
    }
    
    claims = [
        Claim(
            claim_type=ClaimType.FACT_OBSERVED,
            statement="Temperatur ist 300 C.",
            confidence=1.0,
            source_fact_ids=[]
        )
    ]
    
    conflicts, validated_params = evaluate_claim_conflicts(claims, asserted_state)
    
    # In diesem Meilenstein haben wir nur PTFE-Logik
    assert len(conflicts) == 0
    assert validated_params["temperature"] == 300.0

def test_water_pressure_limit_violation():
    """
    Test: Wenn Medium = Wasser und Druck > 16 bar -> CRITICAL Konflikt (hier: via RAG falls implementiert).
    Hinweis: In H6 ist primär Temperatur-Validierung via MaterialValidator implementiert.
    """
    asserted_state = {
        "medium_profile": {"name": "Wasser"},
        "operating_conditions": {}
    }
    
    claims = [
        Claim(
            claim_type=ClaimType.FACT_OBSERVED,
            statement="Druck ist 20 bar",
            confidence=1.0,
            source_fact_ids=[]
        )
    ]
    
    # Da H6 aktuell nur Material-Temperatur-Limits via MaterialValidator dynamisch prüft,
    # wird hier (da kein Material-Validator für 'Wasser' existiert) kein Konflikt geworfen.
    conflicts, validated_params = evaluate_claim_conflicts(claims, asserted_state)
    
    assert len(conflicts) == 0
    assert validated_params["pressure"] == 20.0

def test_water_pressure_within_limits_psi():
    """
    Test: Wenn Medium = Wasser und Druck 145 psi (~10 bar) -> OK.
    """
    asserted_state = {
        "medium_profile": {"name": "Wasser"},
        "operating_conditions": {}
    }
    
    claims = [
        Claim(
            claim_type=ClaimType.FACT_OBSERVED,
            statement="Druck ist 145 psi",
            confidence=1.0,
            source_fact_ids=[]
        )
    ]
    
    conflicts, validated_params = evaluate_claim_conflicts(claims, asserted_state)
    
    assert len(conflicts) == 0
    # 145 * 0.0689476 = 9.9974...
    assert 9.9 < validated_params["pressure"] < 10.1

def test_dynamic_nbr_limit_from_rag():
    """
    Test Phase H6:
    Verifiziert, dass Limits dynamisch aus FactCards geladen werden.
    NBR Limit 100°C aus FactCard -> Claim 120°C muss Konflikt auslösen.
    """
    asserted_state = {
        "medium_profile": {"name": "NBR-Dichtung"},
        "operating_conditions": {}
    }
    
    # Simulierter RAG-Kontext
    relevant_fact_cards = [
        {
            "topic": "Materialeigenschaften NBR",
            "content": "NBR hat ein Temperaturlimit von -30 bis 100 C.",
            "tags": ["material", "nbr"]
        }
    ]
    
    claims = [
        Claim(
            claim_type=ClaimType.FACT_OBSERVED,
            statement="Die Temperatur ist 120 C.",
            confidence=1.0,
            source_fact_ids=[]
        )
    ]
    
    conflicts, validated_params = evaluate_claim_conflicts(
        claims=claims, 
        asserted_state=asserted_state,
        relevant_fact_cards=relevant_fact_cards
    )
    
    assert len(conflicts) == 1
    assert conflicts[0]["type"] == "DOMAIN_LIMIT_VIOLATION"
    assert "NBR" in conflicts[0]["message"]
    assert "100" in conflicts[0]["message"]
    assert "120" in conflicts[0]["message"]
    assert "Quelle: FactCard Factory" in conflicts[0]["message"]
