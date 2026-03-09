from typing import List, Dict, Any, Tuple, Optional
import re
from app.agent.evidence.models import Claim, ClaimType
from app.agent.agent.state import SealingAIState
from app.agent.domain.parameters import PhysicalParameter
from app.agent.domain.limits import OperatingLimit
from app.agent.domain.material import MaterialValidator, MaterialPhysicalProfile
from copy import deepcopy

def evaluate_claim_conflicts(
    claims: List[Claim], 
    asserted_state: Dict[str, Any],
    relevant_fact_cards: List[Dict[str, Any]] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """
    Phase B2/H3/H6/H7: Prüft neue Claims gegen den aktuellen asserted state.
    Nutzt die FactCard Factory für dynamische Material-Validierung.
    """
    conflicts = []
    validated_params = {}
    relevant_fact_cards = relevant_fact_cards or []
    
    # 1. Aktuellen Kontext extrahieren
    current_medium = asserted_state.get("medium_profile", {}).get("name")
    
    # 2. Dynamische Material-Validatoren aus RAG-Kontext (via Factory H7)
    material_validators = {}
    for card in relevant_fact_cards:
        profile = MaterialPhysicalProfile.from_fact_card(card)
        if profile:
            material_validators[profile.material_id.lower()] = MaterialValidator(profile)

    for claim in claims:
        # Medium-Konflikt (legacy)
        if "medium" in claim.statement.lower() or "öl" in claim.statement.lower() or "wasser" in claim.statement.lower():
            new_medium = "öl" if "öl" in claim.statement.lower() else "wasser" if "wasser" in claim.statement.lower() else None
            if current_medium and new_medium and current_medium.lower() != new_medium.lower():
                conflicts.append({
                    "type": "PARAMETER_CONFLICT",
                    "severity": "CRITICAL",
                    "field": "medium",
                    "message": f"Konflikt: Assertiert ist '{current_medium}', Claim behauptet '{new_medium}'.",
                    "claim_statement": claim.statement
                })

        # Physikalische Parameter-Validierung (H3/H6/H7)
        if claim.claim_type == ClaimType.FACT_OBSERVED:
            # Temperatur-Parsing
            temp_match = re.search(r"(\d+)\s*(C|F|°C|°F)", claim.statement)
            if temp_match:
                val = float(temp_match.group(1))
                unit = temp_match.group(2).replace("°", "")
                
                try:
                    temp_param = PhysicalParameter(value=val, unit=unit)
                    has_conflict = False
                    
                    # Dynamische Prüfung gegen alle gefundenen Material-Validatoren
                    for mat_id, validator in material_validators.items():
                        # Prüfe ob das Material für diesen Kontext relevant ist
                        if (current_medium and mat_id in current_medium.lower()) or (mat_id in claim.statement.lower()):
                            if not validator.validate_temperature(temp_param):
                                conflicts.append({
                                    "type": "DOMAIN_LIMIT_VIOLATION",
                                    "severity": "CRITICAL",
                                    "field": "temperature",
                                    "message": f"{mat_id.upper()} Limit überschritten: {temp_param.to_base_unit()}°C > {validator.profile.temp_max}°C (Quelle: FactCard Factory).",
                                    "claim_statement": claim.statement
                                })
                                has_conflict = True
                    
                    if not has_conflict:
                        validated_params["temperature"] = temp_param.to_base_unit()
                        
                except Exception:
                    pass

            # Druck-Parsing
            pressure_match = re.search(r"(\d+)\s*(bar|psi)", claim.statement.lower())
            if pressure_match:
                val = float(pressure_match.group(1))
                unit = pressure_match.group(2)
                
                try:
                    pressure_param = PhysicalParameter(value=val, unit=unit)
                    validated_params["pressure"] = pressure_param.to_base_unit()
                except Exception:
                    pass
                
    return conflicts, validated_params

def process_cycle_update(
    old_state: SealingAIState, 
    intelligence_conflicts: List[Dict[str, Any]], 
    expected_revision: int,
    validated_params: Dict[str, float] = None
) -> SealingAIState:
    """
    Phase A8: Aktualisiert den SealingAIState und erhöht die Revision.
    Integriert neue Konflikte in den Governance-Layer.
    Aktualisiert den asserted Layer mit validierten Parametern.
    """
    new_state = deepcopy(old_state)
    
    # Validierung der Revision (Determinismus-Check)
    if old_state["cycle"]["state_revision"] != expected_revision:
        raise ValueError(f"Revision mismatch: expected {expected_revision}, got {old_state['cycle']['state_revision']}")
    
    # Konflikte hinzufügen
    new_state["governance"]["conflicts"].extend(intelligence_conflicts)
    
    # Validierte Parameter in den Asserted Layer schreiben
    if validated_params:
        if "operating_conditions" not in new_state["asserted"]:
            new_state["asserted"]["operating_conditions"] = {}
        new_state["asserted"]["operating_conditions"].update(validated_params)

    # Revision erhöhen
    new_state["cycle"]["state_revision"] += 1
    new_state["cycle"]["snapshot_parent_revision"] = expected_revision
    
    # Optional: Release Status anpassen bei kritischen Konflikten
    if any(c["severity"] == "CRITICAL" for c in intelligence_conflicts):
        new_state["governance"]["release_status"] = "inadmissible"
        
    return new_state
