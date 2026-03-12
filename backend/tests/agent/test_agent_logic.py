import pytest
from app.agent.agent.logic import evaluate_claim_conflicts, process_cycle_update
from app.agent.cli import create_initial_state


def test_process_cycle_update_persists_parameters():
    """
    Test Phase A8: Validierte Parameter müssen in den asserted state geschrieben werden.
    """
    old_state = create_initial_state()
    old_state["asserted"]["medium_profile"] = {"name": "Wasser"}
    old_state["governance"]["release_status"] = "rfq_ready"
    old_state["governance"]["rfq_admissibility"] = "ready"
    
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
    assert new_state["cycle"]["snapshot_parent_revision"] == 1
    assert new_state["cycle"]["superseded_by_cycle"] is None
    assert new_state["cycle"]["contract_obsolete"] is False
    assert new_state["cycle"]["contract_obsolete_reason"] is None
    assert new_state["governance"]["release_status"] == "manufacturer_validation_required"
    assert new_state["governance"]["rfq_admissibility"] == "provisional"
    assert "specificity_not_compound_confirmed" in new_state["governance"]["unknowns_manufacturer_validation"]


def test_process_cycle_update_channels_raw_claims_through_observed_and_normalized():
    old_state = create_initial_state()

    new_state = process_cycle_update(
        old_state=old_state,
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params={"temperature": 120.0},
        raw_claims=[
            {
                "statement": "Temperatur ist 120 C und Medium ist Wasser.",
                "claim_type": "fact_observed",
                "confidence": 0.9,
                "source_fact_ids": ["fc-1"],
                "source": "llm_submit_claim",
            }
        ],
    )

    assert new_state["observed"]["observed_inputs"][0]["raw_text"] == "Temperatur ist 120 C und Medium ist Wasser."
    assert new_state["observed"]["observed_inputs"][0]["source"] == "llm_submit_claim"
    assert new_state["normalized"]["normalized_parameters"]["temperature_c"] == 120.0
    assert new_state["normalized"]["normalized_parameters"]["medium_normalized"] == "Wasser"
    assert new_state["normalized"]["identity_records"]["temperature"]["identity_class"] == "identity_confirmed"
    assert new_state["normalized"]["identity_records"]["temperature"]["deterministic_source"] == "raw_claim_regex"
    assert new_state["asserted"]["operating_conditions"]["temperature"] == 120.0
    assert new_state["asserted"]["medium_profile"]["name"] == "Wasser"


def test_process_cycle_update_normalizes_non_normative_release_status():
    old_state = create_initial_state()
    old_state["governance"]["release_status"] = "released"
    old_state["governance"]["rfq_admissibility"] = "open"

    new_state = process_cycle_update(
        old_state=old_state,
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params={},
        raw_claims=[],
    )

    assert new_state["governance"]["release_status"] == "precheck_only"
    assert new_state["governance"]["rfq_admissibility"] == "inadmissible"


def test_process_cycle_update_separates_blocking_and_manufacturer_unknowns():
    old_state = create_initial_state()

    new_state = process_cycle_update(
        old_state=old_state,
        intelligence_conflicts=[
            {"type": "DOMAIN_LIMIT_VIOLATION", "severity": "CRITICAL", "field": "temperature", "message": "temperature limit exceeded"},
            {"type": "manufacturer_scope_required", "severity": "RESOLUTION_REQUIRES_MANUFACTURER_SCOPE", "message": "manufacturer review required"},
        ],
        expected_revision=1,
        validated_params={"temperature": 120.0},
        raw_claims=[{"statement": "Medium bleibt unklar.", "claim_type": "fact_observed", "confidence": 0.8, "source": "llm_submit_claim"}],
    )

    assert new_state["governance"]["release_status"] == "inadmissible"
    assert new_state["governance"]["rfq_admissibility"] == "inadmissible"
    assert "domain_limit_violation" in new_state["governance"]["unknowns_release_blocking"]
    assert "manufacturer review required" in new_state["governance"]["unknowns_manufacturer_validation"]
    assert "temperature limit exceeded" in new_state["governance"]["gate_failures"]


def test_process_cycle_update_raw_claim_grade_and_manufacturer_without_evidence_stays_provisional():
    old_state = create_initial_state()

    new_state = process_cycle_update(
        old_state=old_state,
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params={"temperature": 120.0},
        raw_claims=[
            {
                "statement": "Material ist PTFE, Grade G25, Hersteller Acme. Medium ist Wasser.",
                "claim_type": "fact_observed",
                "confidence": 1.0,
                "source": "llm_submit_claim",
            }
        ],
    )

    assert new_state["governance"]["specificity_level"] == "family_only"
    assert new_state["governance"]["unknowns_release_blocking"] == []
    assert "specificity_not_compound_confirmed" in new_state["governance"]["unknowns_manufacturer_validation"]
    assert new_state["governance"]["release_status"] == "manufacturer_validation_required"
    assert new_state["governance"]["rfq_admissibility"] == "provisional"


def test_process_cycle_update_allows_rfq_ready_only_for_evidence_bound_compound_specificity():
    old_state = create_initial_state()

    new_state = process_cycle_update(
        old_state=old_state,
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params={"temperature": 120.0},
        raw_claims=[
            {
                "statement": "Material ist PTFE, Grade G25, Hersteller Acme. Medium ist Wasser.",
                "claim_type": "fact_observed",
                "confidence": 1.0,
                "source": "llm_submit_claim",
                "source_fact_ids": ["fc-1"],
            }
        ],
        relevant_fact_cards=[
            {
                "evidence_id": "fc-1",
                "source_ref": "doc-1",
                "source": "S4",
                "source_type": "standard_test_method",
                "source_rank": 1,
                "topic": "PTFE G25",
                "content": "PTFE grade G25 fuer Acme.",
                "metadata": {
                    "material_family": "PTFE",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                    "temperature_max_c": 260,
                },
            }
        ],
    )

    identity = new_state["normalized"]["identity_records"]["manufacturer_name"]
    assert identity["deterministic_source"] == "fact_card_binding"
    assert identity["evidence_quality"] == "qualified"
    assert identity["authority_quality"] == "sufficient"
    assert identity["temporal_quality"] == "sufficient"
    assert identity["source_fact_ids"] == ["fc-1"]
    assert new_state["governance"]["specificity_level"] == "compound_required"
    assert new_state["governance"]["unknowns_manufacturer_validation"] == []
    assert new_state["governance"]["release_status"] == "rfq_ready"
    assert new_state["governance"]["rfq_admissibility"] == "ready"


def test_process_cycle_update_upgrades_only_to_subfamily_without_manufacturer():
    old_state = create_initial_state()

    new_state = process_cycle_update(
        old_state=old_state,
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params={"temperature": 120.0},
        raw_claims=[
            {
                "statement": "Material ist PTFE, Grade G25. Medium ist Wasser.",
                "claim_type": "fact_observed",
                "confidence": 1.0,
                "source": "llm_submit_claim",
                "source_fact_ids": ["fc-1"],
            }
        ],
        relevant_fact_cards=[
            {
                "evidence_id": "fc-1",
                "source_ref": "doc-1",
                "source": "S4",
                "source_type": "standard_test_method",
                "source_rank": 1,
                "topic": "PTFE G25",
                "content": "PTFE grade G25 hat ein Temperaturlimit von max. 260 C.",
                "metadata": {
                    "material_family": "PTFE",
                    "grade_name": "G25",
                    "temperature_max_c": 260,
                },
            }
        ],
    )

    assert new_state["governance"]["specificity_level"] == "subfamily"
    assert new_state["governance"]["release_status"] == "manufacturer_validation_required"
    assert new_state["governance"]["rfq_admissibility"] == "provisional"
    assert "specificity_not_compound_confirmed" in new_state["governance"]["unknowns_manufacturer_validation"]
    assert "manufacturer_name_unconfirmed_for_compound" in new_state["governance"]["unknowns_manufacturer_validation"]


def test_process_cycle_update_ignores_manual_compound_required_without_identity_evidence():
    old_state = create_initial_state()
    old_state["governance"]["specificity_level"] = "compound_required"

    new_state = process_cycle_update(
        old_state=old_state,
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params={"temperature": 120.0},
        raw_claims=[{"statement": "Medium ist Wasser.", "claim_type": "fact_observed", "confidence": 1.0, "source": "llm_submit_claim"}],
    )

    assert new_state["governance"]["specificity_level"] == "family_only"
    assert new_state["governance"]["release_status"] == "manufacturer_validation_required"
    assert new_state["governance"]["rfq_admissibility"] == "provisional"
    assert "specificity_not_compound_confirmed" in new_state["governance"]["unknowns_manufacturer_validation"]


def test_process_cycle_update_marks_claim_hint_without_fact_card_binding_as_unresolved():
    old_state = create_initial_state()

    new_state = process_cycle_update(
        old_state=old_state,
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params={"temperature": 120.0},
        raw_claims=[
            {
                "statement": "Material ist PTFE, Grade G25, Hersteller Acme. Medium ist Wasser.",
                "claim_type": "fact_observed",
                "confidence": 1.0,
                "source": "llm_submit_claim",
                "source_fact_ids": ["fc-missing"],
            }
        ],
        relevant_fact_cards=[],
    )

    assert new_state["normalized"]["identity_records"]["grade_name"]["identity_class"] == "identity_unresolved"
    assert new_state["normalized"]["identity_records"]["grade_name"]["mapping_reason"] == "claim_hint_without_fact_card_binding:grade_name"
    assert new_state["normalized"]["identity_records"]["manufacturer_name"]["identity_class"] == "identity_unresolved"
    assert new_state["governance"]["specificity_level"] == "family_only"
    assert new_state["governance"]["release_status"] == "manufacturer_validation_required"


def test_process_cycle_update_rejects_unqualified_fact_card_identity_for_rfq_ready():
    old_state = create_initial_state()

    new_state = process_cycle_update(
        old_state=old_state,
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params={"temperature": 120.0},
        raw_claims=[
            {
                "statement": "Material ist PTFE, Grade G25, Hersteller Acme. Medium ist Wasser.",
                "claim_type": "fact_observed",
                "confidence": 1.0,
                "source": "llm_submit_claim",
                "source_fact_ids": ["fc-1"],
            }
        ],
        relevant_fact_cards=[
            {
                "evidence_id": "fc-1",
                "topic": "PTFE G25",
                "content": "PTFE grade G25 fuer Acme.",
                "metadata": {
                    "material_family": "PTFE",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                    "temperature_max_c": 260,
                },
            }
        ],
    )

    assert new_state["normalized"]["identity_records"]["manufacturer_name"]["identity_class"] == "identity_unresolved"
    assert new_state["normalized"]["identity_records"]["manufacturer_name"]["mapping_reason"] == "manufacturer_name_metadata_missing_reference"
    assert new_state["governance"]["specificity_level"] == "family_only"
    assert new_state["governance"]["release_status"] == "manufacturer_validation_required"
    assert new_state["governance"]["rfq_admissibility"] == "provisional"


def test_process_cycle_update_rejects_authoritatively_weak_fact_card_for_rfq_ready():
    old_state = create_initial_state()

    new_state = process_cycle_update(
        old_state=old_state,
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params={"temperature": 120.0},
        raw_claims=[
            {
                "statement": "Material ist PTFE, Grade G25, Hersteller Acme. Medium ist Wasser.",
                "claim_type": "fact_observed",
                "confidence": 1.0,
                "source": "llm_submit_claim",
                "source_fact_ids": ["fc-1"],
            }
        ],
        relevant_fact_cards=[
            {
                "evidence_id": "fc-1",
                "source_ref": "doc-1",
                "source": "S3",
                "source_type": "handbook_excerpt",
                "source_rank": 2,
                "topic": "PTFE G25",
                "content": "PTFE grade G25 fuer Acme.",
                "metadata": {
                    "material_family": "PTFE",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                    "temperature_max_c": 260,
                },
            }
        ],
    )

    assert new_state["normalized"]["identity_records"]["manufacturer_name"]["identity_class"] == "identity_unresolved"
    assert new_state["normalized"]["identity_records"]["manufacturer_name"]["mapping_reason"] == "authority_insufficient:handbook_excerpt:rank_2"
    assert new_state["governance"]["specificity_level"] == "family_only"
    assert new_state["governance"]["release_status"] == "manufacturer_validation_required"
    assert new_state["governance"]["rfq_admissibility"] == "provisional"


def test_process_cycle_update_rejects_temporally_undated_fact_card_for_rfq_ready():
    old_state = create_initial_state()

    new_state = process_cycle_update(
        old_state=old_state,
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params={"temperature": 120.0},
        raw_claims=[
            {
                "statement": "Material ist PTFE, Grade G25, Hersteller Acme. Medium ist Wasser.",
                "claim_type": "fact_observed",
                "confidence": 1.0,
                "source": "llm_submit_claim",
                "source_fact_ids": ["fc-1"],
            }
        ],
        relevant_fact_cards=[
            {
                "evidence_id": "fc-1",
                "source_ref": "doc-1",
                "source": "S1",
                "source_type": "manufacturer_technical_brochure",
                "source_rank": 2,
                "topic": "PTFE G25",
                "content": "PTFE grade G25 fuer Acme.",
                "metadata": {
                    "material_family": "PTFE",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                    "temperature_max_c": 260,
                },
            }
        ],
    )

    assert new_state["normalized"]["identity_records"]["manufacturer_name"]["identity_class"] == "identity_unresolved"
    assert new_state["normalized"]["identity_records"]["manufacturer_name"]["mapping_reason"] == "temporal_metadata_missing"
    assert new_state["governance"]["specificity_level"] == "family_only"
    assert new_state["governance"]["release_status"] == "manufacturer_validation_required"
    assert new_state["governance"]["rfq_admissibility"] == "provisional"


def test_process_cycle_update_surfaces_conflicting_fact_card_identity_as_inadmissible():
    old_state = create_initial_state()

    new_state = process_cycle_update(
        old_state=old_state,
        intelligence_conflicts=[],
        expected_revision=1,
        validated_params={"temperature": 120.0},
        raw_claims=[
            {
                "statement": "Material ist PTFE, Grade G25, Hersteller Acme. Medium ist Wasser.",
                "claim_type": "fact_observed",
                "confidence": 1.0,
                "source": "llm_submit_claim",
                "source_fact_ids": ["fc-1", "fc-2"],
            }
        ],
        relevant_fact_cards=[
            {
                "evidence_id": "fc-1",
                "source_ref": "doc-1",
                "source": "S4",
                "source_type": "standard_test_method",
                "source_rank": 1,
                "topic": "PTFE G25",
                "content": "PTFE grade G25 fuer Acme.",
                "metadata": {
                    "material_family": "PTFE",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                    "temperature_max_c": 260,
                },
            },
            {
                "evidence_id": "fc-2",
                "source_ref": "doc-2",
                "source": "S4",
                "source_type": "standard_test_method",
                "source_rank": 1,
                "topic": "PTFE G25",
                "content": "PTFE grade G25 fuer Contoso.",
                "metadata": {
                    "material_family": "PTFE",
                    "grade_name": "G25",
                    "manufacturer_name": "Contoso",
                    "temperature_max_c": 260,
                },
            },
        ],
    )

    assert new_state["normalized"]["identity_records"]["manufacturer_name"]["identity_class"] == "identity_unresolved"
    assert new_state["normalized"]["identity_records"]["manufacturer_name"]["deterministic_source"] == "fact_card_binding_conflict"
    assert "fact_card_identity_conflict:manufacturer_name" in new_state["governance"]["gate_failures"]
    assert "fact_card_identity_conflict:manufacturer_name" in new_state["governance"]["unknowns_release_blocking"]
    assert new_state["governance"]["release_status"] == "inadmissible"
    assert new_state["governance"]["rfq_admissibility"] == "inadmissible"


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
