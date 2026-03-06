import re
from typing import List, Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass, field
from pydantic import BaseModel
from jinja2 import Environment, StrictUndefined

# ============================================================================
# 1. ENUMS & KONSTANTEN (Die physikalischen Leitplanken)
# ============================================================================
class PipelineStatus(str, Enum):
    PARSED = "PARSED"
    QUARANTINED = "QUARANTINED"
    VALIDATED = "VALIDATED"
    PUBLISHED = "PUBLISHED"
    DEPRECATED = "DEPRECATED"

class Operator(str, Enum):
    EQ = "eq"
    GTE = "gte"
    LTE = "lte"

PHYSICAL_LIMITS = {
    "pressure_max_bar": (0.0, 1000.0),
    "speed_max_m_s": (0.0, 200.0),
    "temperature_max_c": (-273.15, 1000.0),
    "temperature_min_c": (-273.15, 1000.0)
}

UNQUANTIFIED_TIME_TERMS = ["kurzzeitig", "briefly", "temporär", "short-term"]

# ============================================================================
# 2. NORMALIZER V2 (Sicher gegen Tausendertrennzeichen und Ranges)
# ============================================================================
class NormalizerError(ValueError):
    pass

class RangeDetectedError(NormalizerError):
    def __init__(self, raw: str, min_val: float, max_val: float):
        self.min_val = min_val
        self.max_val = max_val
        super().__init__(f"Range erkannt in '{raw}': [{min_val}, {max_val}].")

class Normalizer:
    _RANGE_PATTERN = re.compile(r"([-+]?\d+[\.,]?\d*)\s*[-–—bis]\s*([-+]?\d+[\.,]?\d*)")
    _SINGLE_PATTERN = re.compile(r"[-+]?\d+[\.,]?\d*")

    @classmethod
    def _normalize_decimal(cls, s: str) -> str:
        s = s.strip()
        if re.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$", s):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        return s

    @classmethod
    def extract_float(cls, raw: str) -> float:
        range_match = cls._RANGE_PATTERN.search(raw)
        if range_match:
            lo = float(cls._normalize_decimal(range_match.group(1)))
            hi = float(cls._normalize_decimal(range_match.group(2)))
            raise RangeDetectedError(raw, lo, hi)
            
        single_match = cls._SINGLE_PATTERN.search(raw)
        if not single_match:
            raise NormalizerError(f"Kein numerischer Wert in '{raw}' gefunden.")
            
        normalized_str = cls._normalize_decimal(single_match.group(0))
        try:
            return float(normalized_str)
        except ValueError:
            raise NormalizerError(f"Float-Konvertierung fehlgeschlagen: '{normalized_str}' aus '{raw}'")

# ============================================================================
# 3. LLM EXTRACTION SCHEMA (Input aus dem Vision-LLM)
# ============================================================================
class LLMCondition(BaseModel):
    parameter: str
    raw_value: str
    inferred_operator: Operator
    evidence_ref: str

class LLMLimit(BaseModel):
    limit_type: str
    raw_value: str
    condition_context: Optional[str] = None
    evidence_ref: str

class LLMOperatingPoint(BaseModel):
    conditions: List[LLMCondition]
    limits: List[LLMLimit]

class LLMDocumentExtraction(BaseModel):
    manufacturer: str
    product_name: str
    operating_points: List[LLMOperatingPoint]
    safety_exclusions: List[str]

# ============================================================================
# 4. GATEKEEPER & PIPELINE (Deterministische Prüfung)
# ============================================================================
REQUIRED_LIMIT_FIELDS = {
    "operating_limit": []  # Alle Felder optional: kein INCOMPLETE_POINT wenn LLM Key-Namen variiert
}

@dataclass
class LimitProcessingResult:
    limits: Dict[str, Any] = field(default_factory=dict)
    skipped_limits: List[Dict[str, str]] = field(default_factory=list)
    quarantine_reasons: List[str] = field(default_factory=list)
    
    def has_required_fields(self, point_type: str = "operating_limit") -> bool:
        required = REQUIRED_LIMIT_FIELDS.get(point_type, [])
        return all(f in self.limits for f in required)

class GatekeeperResult(BaseModel):
    status: PipelineStatus
    logical_document_key: str
    extracted_points: List[Dict[str, Any]]
    quarantine_report: List[str]

def process_document_pipeline(
    llm_output: LLMDocumentExtraction,
    logical_doc_key: str,
    additional_metadata: Optional[Dict[str, Any]] = None,
) -> GatekeeperResult:
    # Safety-Exclusions sind non-blocking: sie gehen in safety_warnings, NICHT in quarantine_reasons.
    # Das entkoppelt SAFETY_EXCLUSION vom QUARANTINED-Status (Fix 3).
    safety_warnings: List[str] = []
    quarantine_reasons: List[str] = []
    valid_qdrant_points = []

    if llm_output.safety_exclusions:
        safety_warnings.append(
            f"SAFETY_EXCLUSION_DETECTED: {llm_output.safety_exclusions}. HITL-Review empfohlen."
        )

    for op_idx, op in enumerate(llm_output.operating_points):
        point_payload = {
            "point_type": "operating_limit",
            "conditions": {},
            "limits": {},
            "skipped_limits": []
        }
        
        # Bedingungen verarbeiten
        for cond in op.conditions:
            try:
                val = Normalizer.extract_float(cond.raw_value)
                point_payload["conditions"][cond.parameter] = {
                    "raw_value": cond.raw_value, "normalized": val,
                    "operator": cond.inferred_operator.value, "evidence_ref": cond.evidence_ref
                }
            except NormalizerError:
                point_payload["conditions"][cond.parameter] = {
                    "raw_value": cond.raw_value, "operator": cond.inferred_operator.value,
                    "evidence_ref": cond.evidence_ref
                }

        # Limits verarbeiten
        limit_result = LimitProcessingResult()
        for limit in op.limits:
            if limit.condition_context and any(term in limit.condition_context.lower() for term in UNQUANTIFIED_TIME_TERMS):
                msg = f"UNQUANTIFIED_CONDITION: '{limit.limit_type}' = '{limit.raw_value}' an unklare Bedingung geknüpft. [Ref: {limit.evidence_ref}]"
                limit_result.quarantine_reasons.append(msg)
                limit_result.skipped_limits.append({"limit_type": limit.limit_type, "raw_value": limit.raw_value, "reason": msg})
                continue

            try:
                num_val = Normalizer.extract_float(limit.raw_value)
                limit_entry = {"raw_value": limit.raw_value, "normalized": num_val, "evidence_ref": limit.evidence_ref, "is_range": False}
            except RangeDetectedError as e:
                limit_entry = {"raw_value": limit.raw_value, "normalized": e.min_val, "range_min": e.min_val, "range_max": e.max_val, "evidence_ref": limit.evidence_ref, "is_range": True}
                if "pressure" in limit.limit_type:
                    limit_result.quarantine_reasons.append(f"RANGE_DETECTED: {limit.limit_type} Bereich [{e.min_val}, {e.max_val}]. Minimum verwendet. HITL-Review empfohlen.")
                num_val = e.min_val
            except NormalizerError as e:
                limit_result.quarantine_reasons.append(f"PARSE_ERROR: {e}")
                limit_result.skipped_limits.append({"limit_type": limit.limit_type, "raw_value": limit.raw_value, "reason": str(e)})
                continue

            bounds = PHYSICAL_LIMITS.get(limit.limit_type, (-9999, 9999))
            if not (bounds[0] <= num_val <= bounds[1]):
                limit_result.quarantine_reasons.append(f"PHYSICS_VIOLATION: {limit.limit_type} = {num_val} außerhalb {bounds}.")
                continue
                
            limit_result.limits[limit.limit_type] = limit_entry

        point_payload["limits"] = limit_result.limits
        point_payload["skipped_limits"] = limit_result.skipped_limits
        quarantine_reasons.extend(limit_result.quarantine_reasons)

        if not limit_result.has_required_fields():
            quarantine_reasons.append(f"INCOMPLETE_POINT [op_idx={op_idx}]: Pflichtfelder fehlen. Point wird verworfen.")
            continue

        # Vector Text generieren — material_family + polymer_name aus additional_metadata (Fix 1)
        _meta = additional_metadata or {}
        _material_family = str(_meta.get("material_family") or "").strip()
        _polymer_name = str(_meta.get("polymer_name") or "").strip()
        template_str = (
            "Spezifikation: {{ doc_name }}\n"
            "{% if material_family %}Material: {{ material_family }}\n{% endif %}"
            "{% if polymer_name %}Polymer: {{ polymer_name }}\n{% endif %}"
            "Bedingungen:\n"
            "{% for k, v in p.conditions.items() %}"
            "- {{ k }} {{ v.operator }} {{ v.raw_value }} [Ref: {{ v.evidence_ref }}]\n"
            "{% endfor %}"
            "Grenzwerte:\n"
            "{% for k, v in p.limits.items() %}"
            "- {{ k }}: {{ v.normalized }} (Original: {{ v.raw_value }})"
            "{% if v.is_range %} [RANGE: {{ v.range_min }}-{{ v.range_max }}]{% endif %}"
            " [Ref: {{ v.evidence_ref }}]\n"
            "{% endfor %}"
        )
        env = Environment(undefined=StrictUndefined)
        point_payload["vector_text"] = env.from_string(template_str).render(
            doc_name=f"{llm_output.manufacturer} {llm_output.product_name}",
            p=point_payload,
            material_family=_material_family,
            polymer_name=_polymer_name,
        ).strip()
        
        valid_qdrant_points.append(point_payload)

    if llm_output.operating_points and not valid_qdrant_points:
        quarantine_reasons.append("CRITICAL_EMPTY_RESULT: Alle Operating Points wurden herausgefiltert.")

    # Status hängt NUR von quarantine_reasons ab; safety_warnings sind informativ (Fix 3).
    final_status = PipelineStatus.QUARANTINED if quarantine_reasons else PipelineStatus.VALIDATED

    return GatekeeperResult(
        status=final_status,
        logical_document_key=logical_doc_key,
        extracted_points=valid_qdrant_points,
        quarantine_report=safety_warnings + quarantine_reasons,
    )
