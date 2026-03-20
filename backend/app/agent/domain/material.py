from typing import List, Optional, Dict, Any, Tuple
import re
import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from app.agent.domain.parameters import PhysicalParameter
from app.agent.domain.limits import OperatingLimit


_MATERIAL_PATTERN = re.compile(r"\b(NBR|PTFE|FKM|EPDM|SILIKON)\b", re.I)
_GRADE_PATTERN = re.compile(r"\b(?:grade|compound|typ|type)\s*[:\-]?\s*([a-z0-9._-]+)\b", re.I)
_FILLER_PATTERN = re.compile(r"\b(filled|glass[- ]filled|carbon[- ]filled|bronze[- ]filled)\b", re.I)
_YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")
_KB_SOURCE_PATH = Path(__file__).resolve().parents[2] / "data" / "kb" / "SEALAI_KB_PTFE_factcards_gates_v1_3.json"
_SOURCE_CATALOG_CACHE: Optional[Dict[str, Dict[str, Any]]] = None


def _read_metadata_str(metadata: Dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _read_metadata_float(metadata: Dict[str, Any], *keys: str) -> Optional[float]:
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            continue
    return None


def _load_source_catalog() -> Dict[str, Dict[str, Any]]:
    global _SOURCE_CATALOG_CACHE
    if _SOURCE_CATALOG_CACHE is not None:
        return _SOURCE_CATALOG_CACHE
    try:
        data = json.loads(_KB_SOURCE_PATH.read_text(encoding="utf-8"))
        catalog = data.get("sources") or {}
        if isinstance(catalog, dict):
            _SOURCE_CATALOG_CACHE = catalog
        else:
            _SOURCE_CATALOG_CACHE = {}
    except Exception:
        _SOURCE_CATALOG_CACHE = {}
    return _SOURCE_CATALOG_CACHE


def _source_entry(card_dict: dict) -> Dict[str, Any]:
    metadata = card_dict.get("metadata") or {}
    source_key = card_dict.get("source") or metadata.get("source")
    catalog_entry = {}
    if source_key:
        catalog_entry = _load_source_catalog().get(str(source_key), {}) or {}

    entry = dict(catalog_entry)
    for key in ("source", "source_type", "source_rank", "title", "url", "edition"):
        if card_dict.get(key) not in (None, ""):
            entry[key] = card_dict.get(key)
    for meta_key, target_key in (
        ("source", "source"),
        ("source_type", "source_type"),
        ("source_rank", "source_rank"),
        ("title", "title"),
        ("url", "url"),
        ("edition", "edition"),
    ):
        if metadata.get(meta_key) not in (None, "") and target_key not in entry:
            entry[target_key] = metadata.get(meta_key)
    return entry


def _classify_source_authority(card_dict: dict) -> Dict[str, Any]:
    entry = _source_entry(card_dict)
    source_type = entry.get("source_type") or entry.get("type")
    source_rank = entry.get("source_rank", entry.get("rank"))
    try:
        source_rank = int(source_rank) if source_rank is not None else None
    except (TypeError, ValueError):
        source_rank = None

    authoritative_types = {
        "manufacturer_datasheet",
        "manufacturer_technical_brochure",
        "manufacturer_guide",
        "manufacturer_brochure",
        "standard_specification",
        "standard_test_method",
        "peer_reviewed_paper",
        "peer_reviewed_review",
        "government_report",
    }
    if isinstance(source_type, str) and source_type in authoritative_types and source_rank in {1, 2}:
        return {"quality": "sufficient", "reason": f"authority:{source_type}:rank_{source_rank}"}
    if source_type or source_rank is not None:
        return {"quality": "insufficient", "reason": f"authority_insufficient:{source_type or 'unknown'}:rank_{source_rank}"}
    return {"quality": "unknown", "reason": "authority_missing"}


def _classify_source_temporal_validity(card_dict: dict) -> Dict[str, Any]:
    entry = _source_entry(card_dict)
    candidates = [
        str(entry.get("title") or ""),
        str(entry.get("url") or ""),
        str(entry.get("edition") or ""),
    ]
    years = []
    for candidate in candidates:
        years.extend(int(match) for match in _YEAR_PATTERN.findall(candidate))
    if years:
        return {"quality": "sufficient", "reason": f"temporal_year:{max(years)}", "year": max(years)}
    return {"quality": "unknown", "reason": "temporal_metadata_missing"}


def _extract_material_family(card_dict: dict) -> Optional[str]:
    metadata = card_dict.get("metadata") or {}
    explicit = _read_metadata_str(metadata, "material_family", "material", "family")
    if explicit:
        return explicit.upper()

    text = f"{card_dict.get('topic', '')} {card_dict.get('content', '')}"
    match = _MATERIAL_PATTERN.search(text)
    if match:
        return match.group(1).upper()
    return None


def _extract_filler_hint(card_dict: dict) -> Optional[str]:
    metadata = card_dict.get("metadata") or {}
    explicit = _read_metadata_str(metadata, "filler_hint", "filler", "fill")
    if explicit:
        return explicit

    text = f"{card_dict.get('topic', '')} {card_dict.get('content', '')}"
    match = _FILLER_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def _extract_grade_name(card_dict: dict) -> Optional[str]:
    metadata = card_dict.get("metadata") or {}
    explicit = _read_metadata_str(metadata, "grade_name", "grade", "compound_code", "compound")
    if explicit:
        return explicit

    text = f"{card_dict.get('topic', '')} {card_dict.get('content', '')}"
    match = _GRADE_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def _extract_manufacturer_name(card_dict: dict) -> Optional[str]:
    metadata = card_dict.get("metadata") or {}
    return _read_metadata_str(metadata, "manufacturer_name", "manufacturer", "brand")


def _identity_text_value(card_dict: dict, field_name: str) -> Optional[str]:
    text = f"{card_dict.get('topic', '')} {card_dict.get('content', '')}"
    if field_name == "material_family":
        match = _MATERIAL_PATTERN.search(text)
        return match.group(1).upper() if match else None
    if field_name == "filler_hint":
        match = _FILLER_PATTERN.search(text)
        return match.group(1) if match else None
    if field_name == "grade_name":
        match = _GRADE_PATTERN.search(text)
        return match.group(1) if match else None
    return None


def _metadata_identity_value(card_dict: dict, field_name: str) -> Optional[str]:
    metadata = card_dict.get("metadata") or {}
    if field_name == "material_family":
        value = _read_metadata_str(metadata, "material_family", "material", "family")
        return value.upper() if value else None
    if field_name == "filler_hint":
        return _read_metadata_str(metadata, "filler_hint", "filler", "fill")
    if field_name == "grade_name":
        return _read_metadata_str(metadata, "grade_name", "grade", "compound_code", "compound")
    if field_name == "manufacturer_name":
        return _read_metadata_str(metadata, "manufacturer_name", "manufacturer", "brand")
    return None


def _evaluate_identity_quality(card_dict: dict, field_name: str, resolved_value: Optional[str]) -> Dict[str, Any]:
    metadata_value = _metadata_identity_value(card_dict, field_name)
    text_value = _identity_text_value(card_dict, field_name)
    evidence_id = card_dict.get("evidence_id") or card_dict.get("id")
    source_ref = card_dict.get("source_ref")
    has_reference = bool(evidence_id) and bool(source_ref)

    if metadata_value and text_value and metadata_value.strip().upper() != text_value.strip().upper():
        return {
            "source": "metadata_conflict_text",
            "quality": "conflict",
            "reason": f"{field_name}_metadata_text_conflict",
        }
    if metadata_value and has_reference:
        return {
            "source": "metadata",
            "quality": "qualified",
            "reason": f"{field_name}_metadata_bound",
        }
    if metadata_value and not has_reference:
        return {
            "source": "metadata",
            "quality": "unqualified",
            "reason": f"{field_name}_metadata_missing_reference",
        }
    if text_value and resolved_value:
        return {
            "source": "text",
            "quality": "unqualified",
            "reason": f"{field_name}_text_extracted_only",
        }
    return {
        "source": "absent",
        "quality": "missing",
        "reason": f"{field_name}_missing",
    }


def _candidate_kind(
    family: Optional[str],
    filler_hint: Optional[str],
    grade_name: Optional[str],
    manufacturer_name: Optional[str],
) -> Optional[str]:
    if not family:
        return None
    if manufacturer_name and grade_name:
        return "manufacturer_grade"
    if grade_name:
        return "grade"
    if filler_hint:
        return "filled_family"
    return "family"


def _extract_temperature_limits(card_dict: dict) -> Tuple[Optional[float], Optional[float]]:
    metadata = card_dict.get("metadata") or {}
    temp_max = _read_metadata_float(metadata, "temperature_max_c", "temp_max_c", "temp_max", "max_temp_c")
    temp_min = _read_metadata_float(metadata, "temperature_min_c", "temp_min_c", "temp_min", "min_temp_c")
    if temp_max is not None:
        return temp_min if temp_min is not None else -50.0, temp_max

    content = card_dict.get("content", "")
    temp_max_match = re.search(r"(?:bis|max\.|maximal)\s*(-?\d+(?:[.,]\d+)?)\s*C", content, re.I)
    temp_min_match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*bis", content, re.I)
    if not temp_max_match:
        return None, None

    t_max = float(temp_max_match.group(1).replace(",", "."))
    t_min = float(temp_min_match.group(1).replace(",", ".")) if temp_min_match else -50.0
    return t_min, t_max


def _extract_pressure_max(card_dict: dict) -> Optional[float]:
    metadata = card_dict.get("metadata") or {}
    explicit = _read_metadata_float(metadata, "pressure_max_bar", "pressure_max", "max_pressure_bar")
    if explicit is not None:
        return explicit

    content = card_dict.get("content", "")
    match = re.search(
        r"(?:max(?:\.|imal|imalen)?\s*(?:druck|pressure)?\s*(?:von)?|druck\s*(?:bis|max(?:\.|imal|imalen)?)?)\s*(\d+(?:[.,]\d+)?)\s*(bar|psi)\b",
        content,
        re.I,
    )
    if not match:
        match = re.search(r"(?:bis|max\.|maximal)\s*(\d+(?:[.,]\d+)?)\s*(bar|psi)\b", content, re.I)
    if not match:
        return None

    value = float(match.group(1).replace(",", "."))
    unit = match.group(2).lower()
    if unit == "psi":
        return PhysicalParameter(value=value, unit="psi").to_base_unit()
    return value


def normalize_fact_card_evidence(card_dict: dict) -> Dict[str, Any]:
    family = _extract_material_family(card_dict)
    filler_hint = _extract_filler_hint(card_dict)
    grade_name = _extract_grade_name(card_dict)
    manufacturer_name = _extract_manufacturer_name(card_dict)
    temp_min, temp_max = _extract_temperature_limits(card_dict)
    pressure_max = _extract_pressure_max(card_dict)
    authority = _classify_source_authority(card_dict)
    temporal = _classify_source_temporal_validity(card_dict)
    identity_quality = {
        "material_family": _evaluate_identity_quality(card_dict, "material_family", family),
        "filler_hint": _evaluate_identity_quality(card_dict, "filler_hint", filler_hint),
        "grade_name": _evaluate_identity_quality(card_dict, "grade_name", grade_name),
        "manufacturer_name": _evaluate_identity_quality(card_dict, "manufacturer_name", manufacturer_name),
    }
    quality_reasons = [
        details["reason"]
        for details in identity_quality.values()
        if details["quality"] in {"conflict", "unqualified"}
    ]
    evidence_quality = "qualified_identity"
    if any(details["quality"] == "conflict" for details in identity_quality.values()):
        evidence_quality = "conflicted_identity"
    elif any(details["quality"] == "unqualified" for details in identity_quality.values()):
        evidence_quality = "unqualified_identity"

    return {
        "evidence_id": card_dict.get("evidence_id") or card_dict.get("id"),
        "source_ref": card_dict.get("source_ref"),
        "material_family": family,
        "filler_hint": filler_hint,
        "grade_name": grade_name,
        "manufacturer_name": manufacturer_name,
        "candidate_kind": _candidate_kind(family, filler_hint, grade_name, manufacturer_name),
        "normalized_temp_min": temp_min,
        "normalized_temp_max": temp_max,
        "normalized_pressure_max": pressure_max,
        "identity_quality": identity_quality,
        "evidence_quality": evidence_quality,
        "evidence_quality_reasons": quality_reasons,
        "authority_quality": authority["quality"],
        "authority_reason": authority["reason"],
        "temporal_quality": temporal["quality"],
        "temporal_reason": temporal["reason"],
        "temporal_year": temporal.get("year"),
    }

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
            normalized = card_dict.get("normalized_evidence") or normalize_fact_card_evidence(card_dict)
            mat_name = normalized.get("material_family")
            t_max = normalized.get("normalized_temp_max")
            if not mat_name or t_max is None:
                return None
            t_min = normalized.get("normalized_temp_min")
            if t_min is None:
                t_min = -50.0
            pressure_max = normalized.get("normalized_pressure_max")
            
            payload = {
                "material_id": mat_name,
                "temp_min": t_min,
                "temp_max": t_max,
                "v_surface_max": 0,
                "pv_limit_critical": 3.0,
            }
            model_fields = getattr(cls, "model_fields", {}) or {}
            if "pressure_max" in model_fields:
                payload["pressure_max"] = pressure_max
                return cls(**payload)
            instance = cls(**payload)
            object.__setattr__(instance, "pressure_max", pressure_max)
            return instance

except ImportError:
    # Fallback/Mock for standalone domain logic if backend is not in path
    class MaterialPhysicalProfile(BaseModel):
        material_id: str
        temp_min: float
        temp_max: float
        pressure_max: Optional[float] = None
        v_surface_max: float
        pv_limit_critical: float
        model_config = ConfigDict(extra="ignore")

        @classmethod
        def from_fact_card(cls, card_dict: dict) -> Optional["MaterialPhysicalProfile"]:
            """
            Factory-Methode (Phase H7): Erzeugt ein Profil aus einer RAG FactCard.
            """
            normalized = card_dict.get("normalized_evidence") or normalize_fact_card_evidence(card_dict)
            mat_name = normalized.get("material_family")
            t_max = normalized.get("normalized_temp_max")
            if not mat_name or t_max is None:
                return None
            t_min = normalized.get("normalized_temp_min")
            if t_min is None:
                t_min = -50.0
            pressure_max = normalized.get("normalized_pressure_max")
            
            return cls(
                material_id=mat_name,
                temp_min=t_min,
                temp_max=t_max,
                pressure_max=pressure_max,
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
        self.pressure_limit = None
        if getattr(profile, "pressure_max", None) is not None:
            self.pressure_limit = OperatingLimit(
                min_value=0.0,
                max_value=profile.pressure_max,
                unit="bar",
            )
        
        # Weitere Limits könnten hier initialisiert werden (PV, Speed etc.)

    def validate_temperature(self, temp: PhysicalParameter) -> bool:
        """Prüft, ob die Temperatur im zulässigen Bereich des Materials liegt."""
        return self.temp_limit.is_within_limits(temp)

    def validate_pressure(self, pressure: PhysicalParameter) -> bool:
        """Prüft, ob der Druck im zulässigen Bereich des Materials liegt, sofern explizit bekannt."""
        if self.pressure_limit is None:
            return True
        return self.pressure_limit.is_within_limits(pressure)

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

        if "pressure" in conditions and self.pressure_limit is not None:
            is_ok = self.validate_pressure(conditions["pressure"])
            report["checks"]["pressure"] = {
                "status": "OK" if is_ok else "CRITICAL",
                "value": conditions["pressure"].to_base_unit(),
                "limit_min": 0.0,
                "limit_max": self.profile.pressure_max,
                "unit": "bar"
            }
            if not is_ok:
                report["is_valid"] = False
                
        return report
