"""Intent classifier node based on lightweight heuristics."""
from __future__ import annotations

from typing import Dict, Iterable, Tuple

from app.langgraph.io.schema import Intent, Risk, RoutingScores, SCHEMA_VERSION
from app.langgraph.io.validation import ensure_discovery, ensure_intent
from .base import IOValidatedNode

_KEYWORDS = {
    Intent.normen: ("norm", "iso", "din", "richtlinie", "compliance"),
    Intent.material: ("material", "werkstoff", "dichtung", "werkstoffe", "legierung"),
    Intent.anwendung: ("anwendung", "use-case", "einsatz", "prozess"),
    Intent.produkt: ("produkt", "teil", "komponente"),
    Intent.markt: ("markt", "pricing", "wettbewerb", "customer"),
    Intent.safety: ("safety", "sicherheit", "gefahr", "risiko"),
}

_RISK_HINTS = {
    Risk.high: ("explosion", "betriebssicherheit", "kritisch", "ausfall"),
    Risk.med: ("schaden", "verschlei", "grenzwert"),
}


def _text_index(payload: Dict[str, object]) -> str:
    parts: Iterable[str] = (
        str(payload.get("ziel") or ""),
        str(payload.get("zusammenfassung") or ""),
        " ".join(payload.get("fehlende_parameter", []) or []),
    )
    return " ".join(p for p in parts if p).lower()


def _select_intent(text: str) -> Intent:
    for intent, keywords in _KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return intent
    if "markt" in text:
        return Intent.markt
    return Intent.sonstiges


def _risk_from_text(text: str) -> Risk:
    for risk, hints in _RISK_HINTS.items():
        if any(h in text for h in hints):
            return risk
    return Risk.low


def _scores(missing_count: int) -> Tuple[float, float, float, float]:
    coverage = max(0.0, min(1.0, 1.0 - 0.15 * missing_count))
    confidence = max(0.55, min(0.95, coverage + 0.1))
    hybrid = (confidence + coverage) / 2
    routing = RoutingScores(confidence=confidence, coverage=coverage, hybrid_score=hybrid, risk=1.0 - coverage / 2)
    return routing.confidence, routing.coverage, routing.hybrid_score, routing.risk


class IntentClassifierNode(IOValidatedNode):
    """Maps discovery metadata to a structured intent classification."""

    _out_validator = ensure_intent

    def _run(self, payload: Dict[str, object]) -> Dict[str, object]:
        raw = {k: payload.get(k) for k in ("schema_version", "ziel", "zusammenfassung", "fehlende_parameter", "ready_to_route") if k in payload}
        discovery = ensure_discovery(raw)
        exporter = getattr(discovery, "model_dump", None)
        data = exporter() if callable(exporter) else discovery.dict()
        text = _text_index(data)
        intent = _select_intent(text)
        dom = intent

        missing = list(data.get("fehlende_parameter", []))
        confidence, coverage, hybrid, _ = _scores(len(missing))
        risk = _risk_from_text(text)
        if risk is Risk.high:
            confidence = min(confidence, 0.7)
        elif risk is Risk.med:
            confidence = min(confidence, 0.8)

        routing_modus = "single"
        if missing and not discovery.ready_to_route:
            routing_modus = "fallback"
        elif intent in (Intent.normen, Intent.safety):
            routing_modus = "parallel"

        agents = (intent,) if intent != Intent.sonstiges else (Intent.material,)

        return {
            "schema_version": SCHEMA_VERSION,
            "intent": intent.value,
            "domäne": dom.value if isinstance(dom, Intent) else str(dom),
            "confidence": confidence,
            "coverage": coverage,
            "hybrid_score": hybrid,
            "risk": risk.value,
            "empfohlene_agenten": [agent.value if isinstance(agent, Intent) else str(agent) for agent in agents],
            "routing_modus": routing_modus,
        }


__all__ = ["IntentClassifierNode"]
