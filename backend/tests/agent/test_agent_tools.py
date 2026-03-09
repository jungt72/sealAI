import pytest
from app.agent.agent.tools import submit_claim
from app.agent.evidence.models import ClaimType
from pydantic import ValidationError

def test_submit_claim_valid_args():
    """
    Test: Tool-Aufruf mit validen Argumenten muss erfolgreich sein.
    """
    result = submit_claim.invoke({
        "claim_type": ClaimType.FACT_OBSERVED,
        "statement": "Medium ist Wasser bei 10 bar",
        "confidence": 0.95,
        "source_fact_ids": ["raw_input_1"]
    })
    
    assert "Claim empfangen" in result
    assert "fact_observed" in result
    assert "Wasser bei 10 bar" in result

def test_submit_claim_pydantic_validation():
    """
    Test: Tool muss bei invaliden Argumenten (Pydantic) einen Fehler werfen.
    """
    # Ungültige Konfidenz (> 1.0)
    with pytest.raises(ValidationError):
        submit_claim.invoke({
            "claim_type": ClaimType.FACT_OBSERVED,
            "statement": "Test Statement",
            "confidence": 1.5,
            "source_fact_ids": []
        })

    # Zu kurzes Statement
    with pytest.raises(ValidationError):
        submit_claim.invoke({
            "claim_type": ClaimType.FACT_OBSERVED,
            "statement": "abc",  # min_length=5
            "confidence": 0.8,
            "source_fact_ids": []
        })

def test_submit_claim_args_schema():
    """
    Test: Das args_schema des Tools muss die Felder des Claim-Modells widerspiegeln.
    """
    schema = submit_claim.args_schema.model_json_schema()
    
    properties = schema["properties"]
    assert "claim_type" in properties
    assert "statement" in properties
    assert "confidence" in properties
    assert "source_fact_ids" in properties
    
    # Check enum values for claim_type
    # Depending on how langchain wraps it, it might be a reference or a literal list
    # But usually it carries the enum information
    assert "enum" in properties["claim_type"] or "$ref" in properties["claim_type"]
