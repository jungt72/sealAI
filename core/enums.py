from enum import StrEnum


class ExtractionCertainty(StrEnum):
    """
    How a value was obtained. This is NOT a confidence score.
    It is structurally derived from the extraction method, never self-assessed by the LLM.
    """
    EXPLICIT_VALUE = "explicit_value"           # User stated a clear value: "150°C"
    EXPLICIT_RANGE = "explicit_range"           # User stated a range: "120–180°C"
    INFERRED_FROM_CONTEXT = "inferred"          # LLM derived from context: "hot water app" → ~95°C
    AMBIGUOUS = "ambiguous"                     # Multiple interpretations: "1500, maybe 2000"
    ASSUMED_DEFAULT = "assumed"                 # No user input; system assumed a default


class VerbindlichkeitsStufe(StrEnum):
    KNOWLEDGE = "knowledge"
    ORIENTATION = "orientation"
    CALCULATION = "calculation"
    QUALIFIED_PRESELECTION = "qualified_preselection"
    RFQ_BASIS = "rfq_basis"


class QualificationLevel(StrEnum):
    NOT_STARTED = "not_started"
    INCOMPLETE = "incomplete"
    BLOCKED = "blocked"                        # Hard stop active
    PREQUALIFIED = "prequalified"
    RFQ_READY = "rfq_ready"


class EngineStatus(StrEnum):
    COMPUTED = "computed"
    INSUFFICIENT_DATA = "insufficient_data"
    OUT_OF_RANGE = "out_of_range"
    NO_MATCH = "no_match"
    CONTRADICTION_DETECTED = "contradiction_detected"
