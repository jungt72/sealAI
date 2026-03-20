from app.agent.agent.logic import process_cycle_update
from app.agent.cli import create_initial_state


def test_process_cycle_update_marks_trade_name_medium_as_confirmation_required():
    new_state = process_cycle_update(
        old_state=create_initial_state(),
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params={},
        raw_claims=[{"statement": "Medium ist Panolin.", "claim_type": "fact_observed", "certainty": "explicit_value", "source": "llm_submit_claim"}],
    )
    medium_identity = new_state["normalized"]["identity_records"]["medium"]
    assert medium_identity["identity_class"] == "identity_unresolved"
    assert medium_identity["mapping_reason"] == "trade_name_requires_confirmation:panolin"
    assert "medium_confirmation_required" in new_state["governance"]["unknowns_release_blocking"]


def test_process_cycle_update_material_synonym_becomes_probable_and_asserted():
    new_state = process_cycle_update(
        old_state=create_initial_state(),
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params={},
        raw_claims=[{"statement": "Material ist Nitril.", "claim_type": "fact_observed", "certainty": "explicit_value", "source": "llm_submit_claim"}],
    )
    material_identity = new_state["normalized"]["identity_records"]["material_family"]
    assert material_identity["identity_class"] == "identity_probable"
    assert new_state["asserted"]["machine_profile"]["material"] == "NBR"
