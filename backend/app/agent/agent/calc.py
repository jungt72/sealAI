import math
import logging
from typing import Dict, Any

logger = logging.getLogger("app.agent.calc")

def calc_kinematics(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Layer 1: Kinematik (Geschwindigkeiten, Beschleunigung)"""
    d = profile.get("diameter")  # in mm
    n = profile.get("speed")     # in U/min
    
    if d is not None and n is not None:
        try:
            # v = (d * pi * n) / 60000 [m/s]
            v_m_s = (float(d) * math.pi * float(n)) / 60000.0
            profile["v_m_s"] = round(v_m_s, 3)
        except (ValueError, TypeError) as e:
            logger.debug(f"Fehler in calc_kinematics: {e}")
            
    return profile

def calc_tribology(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Layer 2: Tribologie (Lastprofile, PV-Werte, Reibleistung)"""
    p = profile.get("pressure")  # in bar
    v_m_s = profile.get("v_m_s") # in m/s (kommt aus Layer 1)
    
    if p is not None and v_m_s is not None:
        try:
            pv_value = float(p) * float(v_m_s)
            profile["pv_value"] = round(pv_value, 3)
        except (ValueError, TypeError) as e:
            logger.debug(f"Fehler in calc_tribology: {e}")
            
    return profile

def calc_thermodynamics(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Layer 3: Thermodynamik (Reibungswärme, thermische Ausdehnung)"""
    # Platzhalter für zukünftige delta_T Berechnungen
    return profile

def calc_mechanics(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Layer 4: Mechanik (Spaltextrusion, Verpressung, Nut-Füllgrad)"""
    # Platzhalter für zukünftige Extrusionsberechnungen basierend auf Druck & Temp
    return profile

def calculate_physics(profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Zentraler Orchestrator der Physik-Engine.
    Führt alle Berechnungs-Layer in der korrekten, abhängigen Reihenfolge aus.
    """
    profile = calc_kinematics(profile)
    profile = calc_tribology(profile)
    profile = calc_thermodynamics(profile)
    profile = calc_mechanics(profile)
    
    return profile
