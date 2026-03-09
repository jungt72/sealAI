from typing import List, Dict, Any
from src.evidence.models import Claim
from src.agent.state import SealingAIState
from copy import deepcopy

def evaluate_claim_conflicts(claims: List[Claim], asserted_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Phase B2: Prüft neue Claims gegen den aktuellen asserted state.
    Erkennt fachliche Widersprüche (z.B. Medium-Konflikte).
    """
    conflicts = []
    
    # Beispiel-Logik für den Test: Medium-Konflikt erkennen
    current_medium = asserted_state.get("medium_profile", {}).get("name")
    
    for claim in claims:
        # Wenn der Claim ein Medium betrifft und es bereits eines gibt
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
                
    return conflicts

def process_cycle_update(
    old_state: SealingAIState, 
    intelligence_conflicts: List[Dict[str, Any]], 
    expected_revision: int
) -> SealingAIState:
    """
    Phase A8: Aktualisiert den SealingAIState und erhöht die Revision.
    Integriert neue Konflikte in den Governance-Layer.
    """
    new_state = deepcopy(old_state)
    
    # Validierung der Revision (Determinismus-Check)
    if old_state["cycle"]["state_revision"] != expected_revision:
        raise ValueError(f"Revision mismatch: expected {expected_revision}, got {old_state['cycle']['state_revision']}")
    
    # Konflikte hinzufügen
    new_state["governance"]["conflicts"].extend(intelligence_conflicts)
    
    # Revision erhöhen
    new_state["cycle"]["state_revision"] += 1
    new_state["cycle"]["snapshot_parent_revision"] = expected_revision
    
    # Optional: Release Status anpassen bei kritischen Konflikten
    if any(c["severity"] == "CRITICAL" for c in intelligence_conflicts):
        new_state["governance"]["release_status"] = "inadmissible"
        
    return new_state
