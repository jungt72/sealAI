import pytest
from app.services.knowledge.entity_resolver import normalize_entity

@pytest.mark.parametrize("input_val,expected", [
    ("Viton", "FKM"),
    ("viton", "FKM"),
    ("NBR", "NBR"),
    ("nitril", "NBR"),
    ("Kalrez", "FFKM"),
    ("Teflon", "PTFE"),
    ("Unknown", "Unknown"),
])
def test_normalize_entity_material(input_val, expected):
    assert normalize_entity("material", input_val) == expected

@pytest.mark.parametrize("input_val,expected", [
    # 0B.3b: entity_resolver returns technical service-layer IDs for medium
    ("Wasser", "wasser"),
    ("water", "wasser"),
    ("Öl", "hlp"),
    ("oil", "hlp"),
    ("Mineralöl", "hlp"),
    ("Hydrauliköl", "hlp"),
    ("HLP", "hlp"),
    ("Bio-Öl", "hees"),
    ("Panolin", "hees"),
    ("Ester", "hees"),
    ("HEES", "hees"),
])
def test_normalize_entity_medium(input_val, expected):
    assert normalize_entity("medium", input_val) == expected

def test_normalize_entity_unknown_type():
    assert normalize_entity("other", "Value") == "value"
