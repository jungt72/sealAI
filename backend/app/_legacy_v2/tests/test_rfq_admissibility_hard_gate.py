from app._legacy_v2.utils.rfq_admissibility import (
    derive_release_status,
    normalize_rfq_admissibility_contract,
    rfq_contract_is_ready,
)


def test_normalize_rfq_admissibility_contract_with_blockers() -> None:
    """Test that existing blockers force the admissibility contract to inadmissible."""
    state = {
        "system": {
            "rfq_admissibility": {
                "status": "ready",
                "governed_ready": True,
                "reason": "all_good",
                "blockers": [],
            },
            "governance_metadata": {
                "unknowns_release_blocking": ["System level blocker"]
            },
            "answer_contract": {
                "governance_metadata": {
                    "unknowns_release_blocking": ["Contract level blocker"]
                }
            }
        },
        "reasoning": {}
    }

    normalized = normalize_rfq_admissibility_contract(state)
    
    assert normalized["status"] == "inadmissible"
    assert normalized["governed_ready"] is False
    assert normalized["reason"] == "blocking_unknowns"
    assert "System level blocker" in normalized["blockers"]
    assert "Contract level blocker" in normalized["blockers"]
    assert not rfq_contract_is_ready(normalized)


def test_rfq_contract_is_ready_with_blockers_directly() -> None:
    """Test that rfq_contract_is_ready fails if blockers list is not empty."""
    contract = {
        "status": "ready",
        "governed_ready": True,
        "blockers": ["Some blocker"],
    }
    assert not rfq_contract_is_ready(contract)


def test_normalize_rfq_admissibility_legacy_ready_with_blockers() -> None:
    """Test that reasoning.rfq_ready=True is overridden by blockers."""
    state = {
        "system": {
            "answer_contract": {
                "governance_metadata": {
                    "unknowns_release_blocking": ["Legacy blocker"]
                }
            }
        },
        "reasoning": {
            "rfq_ready": True
        }
    }
    
    normalized = normalize_rfq_admissibility_contract(state)

    assert normalized["status"] == "inadmissible"
    assert normalized["governed_ready"] is False
    assert normalized["reason"] == "blocking_unknowns"
    assert "Legacy blocker" in normalized["blockers"]
    assert not rfq_contract_is_ready(normalized)


# ── Batch C: release_status — alle 4 Werte ───────────────────────────────────

def test_release_status_inadmissible_when_blockers_present() -> None:
    """Blockers zwingen release_status auf inadmissible — keine anderen Signale relevant."""
    result = derive_release_status(
        blockers=["Medienvertraeglichkeit ungeklaert"],
        governed_ready=False,
        status="inadmissible",
        manufacturer_validation_items=[],
        requires_human_review=False,
        open_points=[],
    )
    assert result == "inadmissible"


def test_release_status_rfq_ready_when_governed_and_no_blockers() -> None:
    """rfq_ready nur wenn governed_ready=True, status==ready und keine Blocker."""
    result = derive_release_status(
        blockers=[],
        governed_ready=True,
        status="ready",
        manufacturer_validation_items=[],
        requires_human_review=False,
        open_points=[],
    )
    assert result == "rfq_ready"


def test_release_status_manufacturer_validation_required_from_unknowns() -> None:
    """manufacturer_validation_required aus governance.unknowns_manufacturer_validation — kein Raten."""
    result = derive_release_status(
        blockers=[],
        governed_ready=False,
        status="inadmissible",
        manufacturer_validation_items=["PTFE nur family_level — Compoundfreigabe fehlt"],
        requires_human_review=False,
        open_points=[],
    )
    assert result == "manufacturer_validation_required"


def test_release_status_precheck_only_from_requires_human_review() -> None:
    """precheck_only wenn requires_human_review=True und keine Blocker."""
    result = derive_release_status(
        blockers=[],
        governed_ready=False,
        status="inadmissible",
        manufacturer_validation_items=[],
        requires_human_review=True,
        open_points=[],
    )
    assert result == "precheck_only"


def test_release_status_precheck_only_from_open_points() -> None:
    """precheck_only wenn open_points nicht leer — expliziter, deterministischer Signal."""
    result = derive_release_status(
        blockers=[],
        governed_ready=False,
        status="inadmissible",
        manufacturer_validation_items=[],
        requires_human_review=False,
        open_points=["Temperaturbereich fuer aktuellen Betriebspunkt noch nicht bestaetigt"],
    )
    assert result == "precheck_only"


def test_blockers_override_rfq_ready_in_release_status() -> None:
    """Blockers dominieren — rfq_ready darf nicht gesetzt werden wenn Blocker vorhanden."""
    result = derive_release_status(
        blockers=["CRITICAL: gate failure"],
        governed_ready=True,
        status="ready",
        manufacturer_validation_items=[],
        requires_human_review=False,
        open_points=[],
    )
    assert result == "inadmissible"


def test_normalize_sets_release_status_manufacturer_validation_from_governance() -> None:
    """normalize_rfq_admissibility_contract leitet release_status aus governance_metadata ab."""
    state = {
        "system": {
            "rfq_admissibility": {
                "status": "inadmissible",
                "governed_ready": False,
                "reason": "incomplete",
                "blockers": [],
                "open_points": [],
            },
            "answer_contract": {
                "governance_metadata": {
                    "unknowns_manufacturer_validation": ["NBR compound-level unconfirmed"],
                    "unknowns_release_blocking": [],
                }
            }
        },
        "reasoning": {},
    }

    normalized = normalize_rfq_admissibility_contract(state)

    assert normalized["release_status"] == "manufacturer_validation_required"
    assert normalized["status"] == "inadmissible"  # status bleibt kompatibel


def test_normalize_rfq_admissibility_blocks_on_verification_conflict() -> None:
    """Test that BLOCKING_UNKNOWN conflicts in verification_report force inadmissible status."""
    state = {
        "system": {
            "rfq_admissibility": {
                "status": "ready",
                "governed_ready": True,
                "blockers": [],
            },
            "verification_report": {
                "conflicts": [
                    {
                        "conflict_type": "PARAMETER_CONFLICT",
                        "severity": "BLOCKING_UNKNOWN",
                        "summary": "Draft mentions pressure values but contract has no authoritative pressure.",
                        "resolution_status": "OPEN",
                    }
                ]
            }
        },
        "reasoning": {},
    }

    normalized = normalize_rfq_admissibility_contract(state)

    assert normalized["status"] == "inadmissible"
    assert normalized["governed_ready"] is False
    assert normalized["reason"] == "blocking_unknowns"
    assert any("no authoritative pressure" in b for b in normalized["blockers"])
    assert normalized["release_status"] == "inadmissible"


def test_normalize_rfq_admissibility_sets_mfr_validation_on_verification_conflict() -> None:
    """Test that RESOLUTION_REQUIRES_MANUFACTURER_SCOPE conflicts force manufacturer_validation_required status."""
    state = {
        "system": {
            "rfq_admissibility": {
                "status": "inadmissible",
                "governed_ready": False,
                "blockers": [],
            },
            "verification_report": {
                "conflicts": [
                    {
                        "conflict_type": "COMPOUND_SPECIFICITY_CONFLICT",
                        "severity": "RESOLUTION_REQUIRES_MANUFACTURER_SCOPE",
                        "summary": "Draft mentions specific grade but contract only carries family-level evidence.",
                        "resolution_status": "OPEN",
                    }
                ]
            }
        },
        "reasoning": {},
    }

    normalized = normalize_rfq_admissibility_contract(state)

    assert normalized["release_status"] == "manufacturer_validation_required"
    assert any("specific grade" in item for item in normalized["manufacturer_validation_items"])
