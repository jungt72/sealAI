from typing import Any, Dict, List
import structlog

logger = structlog.get_logger("langgraph_v2.nodes.critic")

def technical_critic_node(state: Any) -> Dict[str, Any]:
    logger.info("technical_critic_start")
    issues = []
    
    def get_v(obj, key, default=None):
        if obj is None: return default
        try:
            if key in obj: return obj[key]
        except: pass
        try:
            return obj.get(key, default)
        except: pass
        try:
            return getattr(obj, key)
        except: pass
        return default

    params = get_v(state, 'parameters', {})
    recommendation = get_v(state, 'material_choice', {})
    working_memory = get_v(state, 'working_memory', {})
    
    # --- EXTRAKTION DER STRUKTURIERTEN RAG-EVIDENZ ---
    evidence = get_v(working_memory, 'technical_evidence', [])
    
    temp = float(get_v(params, 'temperature', 0) or 0)
    pressure = float(get_v(params, 'pressure', 0) or 0)
    material = str(get_v(recommendation, 'material', '') or '').upper()
    
    # --- VALIDIERUNG GEGEN HARTE RAG-FAKTEN ---
    for fact in evidence:
        category = fact.get('category')
        val = float(fact.get('value', 0) or 0)
        raw_text = fact.get('raw', '')
        
        # Beispiel: RAG-Dokument nennt ein spezifisches Temperatur-Limit
        if category == 'temperature' and material in fact.get('context', '').upper():
            if temp > val:
                issues.append(f"RAG-KONFLIKT: Dokument nennt Limit {val}°C für {material}, aber Anwendung hat {temp}°C. (Quelle: '{raw_text}')")
        
        # Beispiel: RAG-Dokument nennt ein spezifisches Druck-Limit
        if category == 'pressure' and material in fact.get('context', '').upper():
            if pressure > val:
                issues.append(f"RAG-KONFLIKT: Laut Datenblatt ist {material} nur bis {val} bar geeignet. (Anfrage: {pressure} bar)")

    # --- ALLGEMEINES REGELWERK (FALLBACK) ---
    if not issues:
        t_limits = {"NBR": 100, "FKM": 200, "EPDM": 150, "PTFE": 260}
        limit = t_limits.get(material, 100)
        if temp > limit:
            issues.append(f"TECHNISCHES LIMIT: {material} überschreitet Standard-Limit von {limit}°C.")

    is_valid = len(issues) == 0
    return {
        "critic_feedback": {
            "is_valid": is_valid,
            "issues": issues,
            "status": "approved" if is_valid else "rejected",
            "score": max(0, 100 - len(issues) * 20),
            "evidence_used": len(evidence)
        },
        "last_node": "technical_critic_node"
    }

def critic_router(state: Any) -> str:
    def get_v(obj, key, default=None):
        if obj is None: return default
        try:
            if key in obj: return obj[key]
        except: pass
        try: return obj.get(key, default)
        except: pass
        try: return getattr(obj, key)
        except: pass
        return default
    feedback = get_v(state, 'critic_feedback', {})
    status = get_v(feedback, 'status', 'approved')
    return "refine" if status == "rejected" else "approve"
