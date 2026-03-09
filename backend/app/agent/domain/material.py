from typing import List, Optional, Dict, Any
import re
from pydantic import BaseModel, ConfigDict, Field
from app.agent.domain.parameters import PhysicalParameter
from app.agent.domain.limits import OperatingLimit

# Import existing model for compatibility if possible, or define a compatible one
try:
    from app.models.material_profile import MaterialPhysicalProfile as BaseMaterialPhysicalProfile
    
    class MaterialPhysicalProfile(BaseMaterialPhysicalProfile):
        @classmethod
        def from_fact_card(cls, card_dict: dict) -> Optional["MaterialPhysicalProfile"]:
            """
            Factory-Methode (Phase H7): Erzeugt ein Profil aus einer RAG FactCard.
            Extrahiert Materialnamen und Limits mittels RegEx.
            """
            content = card_dict.get("content", "")
            topic = card_dict.get("topic", "")
            
            # Suche nach Materialnamen (NBR, PTFE, FKM etc.)
            mat_match = re.search(r"\b(NBR|PTFE|FKM|EPDM|Silikon)\b", topic + " " + content, re.I)
            if not mat_match:
                return None
                
            mat_name = mat_match.group(1).upper()
            
            # Suche nach Temperatur-Limits: "X bis Y C" oder "max. Y C"
            temp_max_match = re.search(r"(?:bis|max\.|maximal)\s*(\d+)\s*C", content, re.I)
            temp_min_match = re.search(r"(-?\d+)\s*bis", content, re.I)
            
            if not temp_max_match:
                return None
                
            t_max = float(temp_max_match.group(1))
            t_min = float(temp_min_match.group(1)) if temp_min_match else -50.0 # Default
            
            return cls(
                material_id=mat_name,
                temp_min=t_min,
                temp_max=t_max,
                v_surface_max=0, # Fallback
                pv_limit_critical=3.0 # Fallback
            )

except ImportError:
    # Fallback/Mock for standalone domain logic if backend is not in path
    class MaterialPhysicalProfile(BaseModel):
        material_id: str
        temp_min: float
        temp_max: float
        v_surface_max: float
        pv_limit_critical: float
        model_config = ConfigDict(extra="ignore")

        @classmethod
        def from_fact_card(cls, card_dict: dict) -> Optional["MaterialPhysicalProfile"]:
            """
            Factory-Methode (Phase H7): Erzeugt ein Profil aus einer RAG FactCard.
            """
            content = card_dict.get("content", "")
            topic = card_dict.get("topic", "")
            
            mat_match = re.search(r"\b(NBR|PTFE|FKM|EPDM|Silikon)\b", topic + " " + content, re.I)
            if not mat_match:
                return None
                
            mat_name = mat_match.group(1).upper()
            temp_max_match = re.search(r"(?:bis|max\.|maximal)\s*(\d+)\s*C", content, re.I)
            temp_min_match = re.search(r"(-?\d+)\s*bis", content, re.I)
            
            if not temp_max_match:
                return None
                
            t_max = float(temp_max_match.group(1))
            t_min = float(temp_min_match.group(1)) if temp_min_match else -50.0
            
            return cls(
                material_id=mat_name,
                temp_min=t_min,
                temp_max=t_max,
                v_surface_max=0,
                pv_limit_critical=0
            )

class MaterialValidator:
    """
    Validiert ein Material gegen technische Einsatzbedingungen (Phase H3).
    Nutzt OperatingLimits zur deterministischen Prüfung.
    """
    def __init__(self, profile: MaterialPhysicalProfile):
        self.profile = profile
        
        # Erzeuge OperatingLimits aus dem Profil
        self.temp_limit = OperatingLimit(
            min_value=profile.temp_min,
            max_value=profile.temp_max,
            unit="C"
        )
        
        # Weitere Limits könnten hier initialisiert werden (PV, Speed etc.)

    def validate_temperature(self, temp: PhysicalParameter) -> bool:
        """Prüft, ob die Temperatur im zulässigen Bereich des Materials liegt."""
        return self.temp_limit.is_within_limits(temp)

    def get_validation_report(self, conditions: Dict[str, PhysicalParameter]) -> Dict[str, Any]:
        """
        Erzeugt einen detaillierten Validierungsbericht für mehrere Bedingungen.
        """
        report = {
            "material_id": self.profile.material_id,
            "is_valid": True,
            "checks": {}
        }
        
        if "temperature" in conditions:
            is_ok = self.validate_temperature(conditions["temperature"])
            report["checks"]["temperature"] = {
                "status": "OK" if is_ok else "CRITICAL",
                "value": conditions["temperature"].to_base_unit(),
                "limit_min": self.profile.temp_min,
                "limit_max": self.profile.temp_max,
                "unit": "C"
            }
            if not is_ok:
                report["is_valid"] = False
                
        return report
