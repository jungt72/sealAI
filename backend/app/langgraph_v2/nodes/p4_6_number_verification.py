"""
NO-SOURCE-NO-NUMBER Verification Gate.

Verhindert halluzinierte numerische Werte in finalen Antworten.
"""
from app.langgraph_v2.state.sealai_state import SealAIState
import structlog
import re
from typing import Set, Tuple, List, Dict, Any

log = structlog.get_logger(__name__)

# Regex für Zahlen mit optionalen Einheiten
# Wir erlauben Einheiten bis 5 Zeichen, aber vermeiden common words
NUMBER_WITH_UNIT_PATTERN = re.compile(
    r'\b(\d+(?:\.\d+)?)(?:\s*([A-Za-z°µ]{1,5})\b)?',
    re.IGNORECASE
)

# Liste von Wörtern, die KEINE Einheiten sind (False Positives vermeiden)
NON_UNIT_WORDS = {
    "and", "und", "the", "der", "die", "das", "is", "ist", "for", "fuer", "für",
    "with", "mit", "as", "als", "at", "an", "on", "auf", "in", "by", "von"
}

async def node_p4_6_number_verification(state: SealAIState) -> dict:
    """
    Verifiziert alle numerischen Werte in final_answer gegen Sources.
    """
    # 1. Skip-Bedingungen (v4.4.1)
    recommendation_ready = state.get("recommendation_ready", False)
    intent = state.get("intent")
    goal = intent.goal if intent else state.get("goal")
    
    # Überspringe Verifikation, wenn Agent nur Rückfragen stellt oder im Smalltalk ist
    if not recommendation_ready or goal in ["smalltalk", "ask_missing"]:
        log.debug(
            "number_verification.skip_active", 
            recommendation_ready=recommendation_ready, 
            goal=goal
        )
        return {
            "verification_passed": True,
            "last_node": "node_p4_6_number_verification"
        }

    final_answer = state.get("final_answer", "")
    sources = state.get("sources", [])
    factcards = state.get("factcard_matches", [])
    
    # Skip wenn keine Antwort
    if not final_answer:
        log.debug("number_verification.skip_no_answer")
        return {
            "verification_passed": True,
            "last_node": "node_p4_6_number_verification"
        }
    
    # Extrahiere Zahlen aus Antwort
    answer_numbers = extract_numbers_with_units(final_answer)
    
    # Skip wenn keine Zahlen in Antwort
    if not answer_numbers:
        log.debug("number_verification.skip_no_numbers")
        return {
            "verification_passed": True,
            "last_node": "node_p4_6_number_verification"
        }
    
    # Extrahiere Zahlen aus Sources
    source_numbers: Set[Tuple[float, str]] = set()
    
    # A. Aus RAG Chunks
    for chunk in sources:
        chunk_text = chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
        source_numbers.update(extract_numbers_with_units(chunk_text))
    
    # B. Aus FactCards
    for fc in factcards:
        if isinstance(fc, dict):
            value = fc.get("value")
            units = fc.get("units", "")
            if isinstance(value, (int, float)):
                source_numbers.add((float(value), units.strip().lower()))
            # Auch aus raw text extrahieren
            fc_text = (fc.get("do_not_infer", "") or "") + " " + str(value)
            source_numbers.update(extract_numbers_with_units(fc_text))

    # C. Aus User-Eingaben (Working Profile / Extracted Params) - NEU v4.4.1
    source_numbers.update(extract_numbers_from_params(state))
    
    # Verifikation
    unverified = []
    
    for num, unit in answer_numbers:
        # Ignoriere kleine Integers ohne Einheit (oft Listen-Aufzählungen 1., 2., 3.)
        # wenn sie nicht verifiziert werden können.
        if unit == "" and num.is_integer() and 1 <= num <= 20:
            # Wir prüfen trotzdem, ob sie zufällig in den Quellen sind
            pass 
        
        found_match = False
        for source_num, source_unit in source_numbers:
            # Units müssen matchen (oder beide leer)
            if unit.lower() != source_unit.lower():
                continue
            
            # Exakte Übereinstimmung oder Toleranz für Rundung (±0.1%)
            if abs(num - source_num) < 0.001:
                found_match = True
                break
            
            if source_num > 0:
                rel_error = abs(num - source_num) / source_num
                if rel_error < 0.001:
                    found_match = True
                    break
        
        if not found_match:
            # Sonderregel: Kleine Integers ohne Einheit erlauben wir als Fallback
            # (Formatierung wie 1., 2. oder Mengenangaben "1 Stück")
            if unit == "" and num.is_integer() and 1 <= num <= 10:
                log.debug("number_verification.allow_small_integer_fallback", val=num)
                continue

            unverified.append({
                "value": num,
                "unit": unit,
                "formatted": f"{num} {unit}".strip()
            })
    
    # Entscheidung
    if unverified:
        log.error(
            "number_verification_failed",
            unverified_count=len(unverified),
            unverified_values=[v["formatted"] for v in unverified],
            answer_preview=final_answer[:200]
        )
        
        return {
            "verification_passed": False,
            "verification_error": {
                "type": "UNVERIFIED_NUMBERS",
                "message": (
                    f"Die Antwort enthält {len(unverified)} Werte, "
                    "die nicht in den Quellen verifiziert werden konnten."
                ),
                "unverified_values": unverified
            },
            "last_node": "node_p4_6_number_verification"
        }
    
    # Success
    log.info("number_verification_passed", count=len(answer_numbers))
    return {
        "verification_passed": True,
        "last_node": "node_p4_6_number_verification"
    }


def extract_numbers_from_params(state: SealAIState) -> Set[Tuple[float, str]]:
    """Extrahiert numerische Werte aus dem State (User-Eingaben)."""
    nums = set()
    
    # 1. working_profile
    wp = state.get("working_profile")
    if wp:
        data = wp.as_dict() if hasattr(wp, "as_dict") else (wp if isinstance(wp, dict) else {})
        for k, v in data.items():
            if isinstance(v, (int, float)):
                unit = ""
                k_lower = k.lower()
                if "pressure" in k_lower: unit = "bar"
                elif "temp" in k_lower: unit = "°c"
                elif "dn" in k_lower: unit = "dn"
                elif "pn" in k_lower: unit = "pn"
                
                nums.add((float(v), unit))
                nums.add((float(v), "")) # Auch ohne Einheit erlauben
    
    # 2. extracted_params
    ep = state.get("extracted_params") or {}
    for k, v in ep.items():
        if isinstance(v, (int, float)):
            unit = ""
            k_lower = k.lower()
            if "pressure" in k_lower: unit = "bar"
            elif "temp" in k_lower: unit = "°c"
            nums.add((float(v), unit))
            nums.add((float(v), ""))

    # 3. parameters (TechnicalParameters)
    tp = state.get("parameters")
    if tp:
        data = tp.as_dict() if hasattr(tp, "as_dict") else (tp if isinstance(tp, dict) else {})
        for k, v in data.items():
            if isinstance(v, (int, float)):
                nums.add((float(v), ""))
                
    return nums


def extract_numbers_with_units(text: str) -> Set[Tuple[float, str]]:
    """
    Extrahiert (Zahl, Einheit)-Paare aus Text.
    
    Beispiele:
        "10.5 bar" → (10.5, "bar")
        "200°C" → (200.0, "°C")
        "2.4 mm" → (2.4, "mm")
        "50" → (50.0, "")
        "45 HRC" → (45.0, "HRC")
    
    Returns:
        Set of (value, unit) tuples
    """
    numbers = set()
    
    for match in NUMBER_WITH_UNIT_PATTERN.finditer(text):
        num_str = match.group(1)
        unit = match.group(2) or ""
        
        try:
            num = float(num_str)
            # Normalisiere unit (lowercase, strip)
            unit_clean = unit.strip().lower() if unit else ""
            
            # Verhindere common words als units
            if unit_clean in NON_UNIT_WORDS:
                unit_clean = ""
                
            numbers.add((num, unit_clean))
        except ValueError:
            continue
    
    return numbers
