from __future__ import annotations
from typing import List, Dict, Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, field_validator

SCHEMA_VERSION = "1.0.0"


class Intent(str, Enum):
    material = "material"
    anwendung = "anwendung"
    normen = "normen"
    produkt = "produkt"
    markt = "markt"
    safety = "safety"
    sonstiges = "sonstiges"


class Risk(str, Enum):
    low = "low"
    med = "med"
    high = "high"


class Unit(str, Enum):
    kelvin = "K"
    pascal = "Pa"
    celsius = "°C"
    bar = "bar"
    none = "none"


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ParamValue(FrozenModel):
    name: str
    value: float | str | int | bool
    unit: Unit = Unit.none
    source: Literal["user", "memory", "default", "inferred"] = "user"


class ParameterBag(FrozenModel):
    items: List[ParamValue] = Field(default_factory=list)

    def get(self, name: str) -> Optional[ParamValue]:
        for p in self.items:
            if p.name == name:
                return p
        return None


class Constraint(FrozenModel):
    key: str
    value: str
    rationale: Optional[str] = None


class Evidence(FrozenModel):
    kind: Literal["internal", "external"]
    ref: str  # doc id, url, section
    claim: Optional[str] = None


class DiscoveryOutput(FrozenModel):
    schema_version: str = Field(default=SCHEMA_VERSION)
    ziel: str
    zusammenfassung: str
    fehlende_parameter: List[str] = Field(default_factory=list)
    ready_to_route: bool = False


class IntentClassification(FrozenModel):
    schema_version: str = Field(default=SCHEMA_VERSION)
    intent: Intent
    domäne: Intent  # identisch mit intent
    confidence: float = Field(ge=0.0, le=1.0)
    coverage: float = Field(ge=0.0, le=1.0)
    hybrid_score: float = Field(ge=0.0, le=1.0)
    risk: Risk = Risk.low
    empfohlene_agenten: List[Intent] = Field(default_factory=list)
    routing_modus: Literal["single", "parallel", "sequenziell", "fallback"]


class ExpectedOutputSpec(FrozenModel):
    # WICHTIG: kein Feld "schema" benutzen (kollidiert mit BaseModel)
    schema_name: str = Field(default="AgentOutput")
    muessen_enthalten: List[str] = Field(default_factory=list)


class HandoffSpec(FrozenModel):
    schema_version: str = Field(default=SCHEMA_VERSION)
    agent: Intent
    auftrag: str
    eingaben: ParameterBag
    restriktionen: List[Constraint] = Field(default_factory=list)
    erwartete_ausgabe: ExpectedOutputSpec = Field(default_factory=ExpectedOutputSpec)
    rag_hinweis: Literal["auto", "nur_fakten", "nie"] = "auto"
    max_tokens_hint: int = 400


class AgentInput(FrozenModel):
    schema_version: str = Field(default=SCHEMA_VERSION)
    ziel: str
    parameter: ParameterBag
    constraints: List[Constraint] = Field(default_factory=list)


class AgentOutput(FrozenModel):
    schema_version: str = Field(default=SCHEMA_VERSION)
    empfehlung: str
    begruendung: str
    annahmen: List[str] = Field(default_factory=list)
    unsicherheiten: List[str] = Field(default_factory=list)
    evidenz: List[Evidence] = Field(default_factory=list)


class SynthesisOutput(FrozenModel):
    schema_version: str = Field(default=SCHEMA_VERSION)
    empfehlung: str
    alternativen: List[str] = Field(default_factory=list)
    unsicherheiten: List[str] = Field(default_factory=list)
    naechste_schritte: List[str] = Field(default_factory=list)


class SafetyVerdict(FrozenModel):
    schema_version: str = Field(default=SCHEMA_VERSION)
    result: Literal["pass", "block_with_reason"]
    reason: Optional[str] = None


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


class RoutingScores(FrozenModel):
    confidence: float
    coverage: float
    hybrid_score: float
    risk: Risk

    @field_validator("confidence", "coverage", "hybrid_score")
    @classmethod
    def _clamp(cls, v: float) -> float:
        return clamp01(v)
