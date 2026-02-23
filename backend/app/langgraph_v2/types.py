# path: backend/app/langgraph_v2/types.py
"""Lightweight type/literal definitions and helpers for LangGraph v2.

Wichtig:
- Die Literals (PhaseLiteral, IntentKey, KnowledgeType, MotionType) bleiben
  bewusst schlank und rein typseitig.
- Für `knowledge_type` gibt es eine Normalisierungs-Hilfsfunktion
  `normalize_knowledge_type`, die deutschsprachige/abweichende LLM-Ausgaben
  auf unsere canonical Werte mapped:
    - "material"
    - "lifetime"
    - "norms"

Verwendung (Beispiel im Intent-Pydantic-Model):

    from pydantic import BaseModel, field_validator
    from app.langgraph_v2.types import KnowledgeType, normalize_knowledge_type

    class Intent(BaseModel):
        knowledge_type: KnowledgeType | None = None
        ...

        @field_validator("knowledge_type", mode="before")
        @classmethod
        def _normalize_knowledge_type(cls, value):
            return normalize_knowledge_type(value)

Dadurch schlagen Eingaben wie "Werkstoffeigenschaften", "Normen", "Lebensdauer"
nicht mehr mit einem Literal-ValidationError fehl, sondern werden clean
auf unsere internen Werte gemappt.
"""

from __future__ import annotations

from typing import Any, Final
from typing_extensions import Literal, TypeAlias

# ---------------------------------------------------------------------------
# Phases / stages of the v2 orchestrator
# ---------------------------------------------------------------------------

# Keep in sync with app.langgraph_v2.phase.PHASE.
PhaseLiteral: TypeAlias = Literal[
    "routing",
    "entry",
    "frontdoor",
    "smalltalk",
    "intent",
    "supervisor",
    "aggregation",
    "panel",
    "confirm",
    "preflight_use_case",
    "preflight_parameters",
    "extraction",
    "calculation",
    "quality_gate",
    "procurement",
    "consulting",
    "knowledge",
    "validation",
    "rag",
    "final",
    "error",
]

# ---------------------------------------------------------------------------
# High-level intent keys (Routing / Orchestrator-Intents)
# ---------------------------------------------------------------------------

IntentKey: TypeAlias = Literal[
    "consulting_preflight",
    "failure_analysis",
    "optimization_tco",
    "knowledge_material",
    "knowledge_lifetime",
    "knowledge_norms",
    "tender_support",
    "training_onboarding",
    "meta_system",
    "generic_sealing_qa",
    "out_of_scope",
    "smalltalk",
]

# ---------------------------------------------------------------------------
# Domain-specific enums / literals
# ---------------------------------------------------------------------------

#: Canonical knowledge types, wie sie intern im Graph verwendet werden.
KnowledgeType: TypeAlias = Literal["material", "lifetime", "norms"]

#: Bewegungsarten für Dichtungen.
MotionType: TypeAlias = Literal["rotary", "linear", "static"]

# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

#: Mapping von möglichen LLM-Ausgaben (de/en) auf unsere canonical KnowledgeType-Werte.
_KNOWLEDGE_TYPE_NORMALIZATION: Final[dict[str, KnowledgeType]] = {
    # Material / Werkstoffe
    "material": "material",
    "werkstoff": "material",
    "werkstoffe": "material",
    "werkstoffeigenschaft": "material",
    "werkstoffeigenschaften": "material",
    "werkstoffdaten": "material",
    "materialdaten": "material",

    # Lebensdauer
    "lifetime": "lifetime",
    "lebensdauer": "lifetime",
    "haltbarkeit": "lifetime",
    "standzeit": "lifetime",

    # Normen / Standards
    "norms": "norms",
    "norm": "norms",
    "normen": "norms",
    "standards": "norms",
}


def normalize_knowledge_type(value: Any) -> KnowledgeType | None:
    """Normalisiere freie LLM-Ausgaben zu einem `KnowledgeType`.

    - `None` → `None`
    - str → getrimmt + lowercased, anschließend Mapping auf canonical Wert,
      falls bekannt.
    - Andere Typen → werden unverändert zurückgegeben (Pydantic kümmert sich).

    Diese Funktion ist bewusst side-effect-frei und kann gefahrlos in
    Pydantic-Validatoren verwendet werden.
    """
    if value is None:
        return None

    if isinstance(value, str):
        v = value.strip().lower()
        if not v:
            return None
        if v in _KNOWLEDGE_TYPE_NORMALIZATION:
            return _KNOWLEDGE_TYPE_NORMALIZATION[v]
        # Rückgabe des rohen Strings → Pydantic prüft anschließend gegen Literal
        # und wir sehen klar, wenn ein völlig unpassender Wert durchsickert.
        return v  # type: ignore[return-value]

    # Für Nicht-Strings lassen wir Pydantic entscheiden.
    return value  # type: ignore[return-value]


__all__ = [
    "PhaseLiteral",
    "IntentKey",
    "KnowledgeType",
    "MotionType",
    "normalize_knowledge_type",
]
