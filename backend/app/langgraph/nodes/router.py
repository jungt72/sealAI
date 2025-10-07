from __future__ import annotations
from typing import Dict, Any, List
from .base import IOValidatedNode
from ..io.schema import (
    HandoffSpec, ExpectedOutputSpec, Intent, Constraint, ParameterBag, ParamValue, Unit
)
from ..io.validation import ensure_handoff
from ..io.units import normalize_bag

REQUIRED_FOR_AGENT = {
    Intent.material: ["medium", "temperatur", "druck"],
    Intent.anwendung: ["ziel", "medium"],
    Intent.normen: ["normen"],
}

class RouterNode(IOValidatedNode):
    _in_validator = None  # erwartet IntentClassification + Roh-Parameter
    _out_validator = staticmethod(lambda x: ensure_handoff(x))

    def _run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        intent = payload["intent"]  # aus IntentClassification (string oder Enum)
        ziel = payload.get("ziel", "unbekannt")
        params_raw = payload.get("parameter", {})

        bag = ParameterBag(items=[
            ParamValue(
                name=k,
                value=v,
                unit=Unit.celsius if k == "temperatur" else (Unit.bar if k == "druck" else Unit.none),
                source="user"
            )
            for k, v in params_raw.items()
        ])
        bag = normalize_bag(bag)

        restr = [Constraint(key="max_parallel_agents", value="3", rationale="Performance/UX")]
        expected = ExpectedOutputSpec(
            schema_name="AgentOutput",
            muessen_enthalten=["empfehlung", "begruendung", "annahmen", "unsicherheiten"]
        )

        auftrag = {
            Intent.material.value: "Empfehle geeigneten Werkstoff mit Begründung; beachte Normen/Temperatur/Druck.",
            Intent.anwendung.value: "Präzisiere Anwendung und notwendige Betriebsgrenzen; erkenne fehlende Pflichtparameter.",
            Intent.normen.value: "Prüfe relevante Normen/Kompatibilität; gib Zitate/Abschnitte als Evidenz an.",
        }.get(str(intent), "Beantworte die Anfrage im Kontext der Dichtungstechnik.")

        spec = HandoffSpec(
            agent=Intent(intent),
            auftrag=auftrag,
            eingaben=bag,
            restriktionen=restr,
            erwartete_ausgabe=expected,
            rag_hinweis="nur_fakten" if str(intent) == "normen" else "auto",
            max_tokens_hint=400
        )
        return spec.model_dump()
