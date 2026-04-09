from __future__ import annotations

from typing import Literal, TypedDict

from app.agent.runtime.outward_names import normalize_outward_response_class


OutwardResponseClass = Literal[
    "conversational_answer",
    "structured_clarification",
    "governed_state_update",
    "technical_preselection",
    "candidate_shortlist",
    "inquiry_ready",
]


class SurfaceClaimsSpec(TypedDict):
    response_class: OutwardResponseClass
    allowed_claims: list[str]
    forbidden_claims: list[str]
    allowed_focus: list[str]
    forbidden_fragments: list[str]
    class_guard: str
    fallback_text: str


_MANUFACTURER_FRAGMENTS = [
    "freudenberg",
    "simrit",
    "skf",
    "parker",
    "trelleborg",
    "nok",
    "garlock",
    "merkel",
    "elring",
    "victor reinz",
    "hutchinson",
    "hallite",
    "busak",
]


SURFACE_CLAIMS_SPECS: dict[OutwardResponseClass, SurfaceClaimsSpec] = {
    "conversational_answer": {
        "response_class": "conversational_answer",
        "allowed_claims": [
            "Prozesserklaerung",
            "freie Orientierung",
            "leichte Exploration ohne fachliche Freigabe",
        ],
        "forbidden_claims": [
            "Requirement Class als Fakt",
            "Matching-Aussage",
            "RFQ-Reife oder Versandfaehigkeit",
        ],
        "allowed_focus": [
            "Bleibe bei Orientierung, Prozesserklaerung und freier Exploration.",
        ],
        "forbidden_fragments": [
            "requirement class",
            "anforderungsklasse",
            "matching",
            "matched_primary_candidate",
            "rfq-ready",
            "rfq ready",
            "versandfaehig",
            "versandfähig",
            "bestellbereit",
            "anfragebasis ist bereit",
            * _MANUFACTURER_FRAGMENTS,
        ],
        "class_guard": "Erklaere nur Orientierung und Prozess, aber keine Requirement-Class-, Matching- oder RFQ-Reife-Aussage.",
        "fallback_text": (
            "Ich kann den Ablauf kurz einordnen. Fuer eine technische Einengung "
            "brauche ich erst die belastbaren Betriebsdaten."
        ),
    },
    "structured_clarification": {
        "response_class": "structured_clarification",
        "allowed_claims": [
            "ein priorisierter Klaerfokus",
            "knapper technischer Grund",
            "Aufgreifen von Problem, Ziel oder Unsicherheit",
        ],
        "forbidden_claims": [
            "Empfehlung",
            "Herstellerkandidat",
            "RFQ-Aussage",
        ],
        "allowed_focus": [
            "Fokussiere auf die wichtigste Unsicherheit mit knapper technischer Einordnung.",
        ],
        "forbidden_fragments": [
            "empfehle",
            "empfehlung",
            "freigabe",
            "herstellerkandidat",
            "rfq-ready",
            "rfq ready",
            "anfragebasis",
            "versandfaehig",
            "versandfähig",
            * _MANUFACTURER_FRAGMENTS,
        ],
        "class_guard": "Frage nur den naechsten Klaerungspunkt ab und gib keine Empfehlung, keinen Hersteller und keine RFQ-Aussage.",
        "fallback_text": "Bitte nennen Sie den naechsten entscheidenden Betriebsparameter.",
    },
    "governed_state_update": {
        "response_class": "governed_state_update",
        "allowed_claims": [
            "belastbar erfasste Parameter",
            "Annahmen",
            "offene Pruefpunkte",
        ],
        "forbidden_claims": [
            "finale Empfehlungssprache",
            "Herstelleraussage ausserhalb des Status",
            "RFQ-Aussage ausserhalb des Status",
        ],
        "allowed_focus": [
            "Bleibe bei bestaetigten Parametern, Annahmen und offenen Pruefpunkten.",
        ],
        "forbidden_fragments": [
            "ich empfehle",
            "wir empfehlen",
            "passender hersteller",
            "herstellerkandidat",
            "rfq-ready",
            "rfq ready",
            "versandfaehig",
            "versandfähig",
            "bestellbereit",
            * _MANUFACTURER_FRAGMENTS,
        ],
        "class_guard": "Beschreibe nur den belastbaren Status, aber keine finale Empfehlung und keine Hersteller- oder RFQ-Freigabe.",
        "fallback_text": "Ich habe die belastbaren Parameter und offenen Pruefpunkte strukturiert zusammengefasst.",
    },
    "technical_preselection": {
        "response_class": "technical_preselection",
        "allowed_claims": [
            "Requirement Class",
            "Scope of Validity",
            "offene Pruefpunkte",
            "begrenzte technische Richtung",
        ],
        "forbidden_claims": [
            "finale Produktfreigabe",
            "Garantie- oder Sicherheitsbehauptung",
            "Versandfreigabe",
        ],
        "allowed_focus": [
            "Formuliere die Antwort als technische Orientierung, nicht als finale Freigabe.",
        ],
        "forbidden_fragments": [
            "final freigegeben",
            "final geeignet",
            "garantiert geeignet",
            "sicher geeignet",
            "bestellbereit",
            "versandfaehig",
            "versandfähig",
        ],
        "class_guard": "Beschreibe Requirement Class, Scope und offene Pruefpunkte, aber keine finale Freigabe, Garantie oder Versandfreigabe.",
        "fallback_text": "Ich kann die technische Richtung belastbar einordnen und die offenen Pruefpunkte klar benennen.",
    },
    "candidate_shortlist": {
        "response_class": "candidate_shortlist",
        "allowed_claims": [
            "Kandidatenrahmen",
            "Fit-Begruendung",
            "offene Herstellerpruefung",
        ],
        "forbidden_claims": [
            "finale Herstellerfreigabe",
            "behauptete Lieferfaehigkeit ohne Capability-Grundlage",
        ],
        "allowed_focus": [
            "Beschreibe Matching als technisch begruendeten Kandidatenrahmen, nicht als finale Herstellerfreigabe.",
        ],
        "forbidden_fragments": [
            "finaler hersteller",
            "verbindlich ausgewaehlt",
            "verbindlich ausgewählt",
            "lieferfaehig",
            "lieferfähig",
            "sofort lieferbar",
            "ohne weitere herstellerpruefung",
            "ohne weitere herstellerprüfung",
        ],
        "class_guard": "Bleibe beim Kandidatenrahmen, der Fit-Begruendung und offenen Herstellerpruefung.",
        "fallback_text": "Ich kann den Herstellerkandidatenrahmen technisch begruenden, aber keine finale Herstellerfreigabe vorwegnehmen.",
    },
    "inquiry_ready": {
        "response_class": "inquiry_ready",
        "allowed_claims": [
            "versandfaehige Anfragebasis",
            "offene Herstellerpruefpunkte",
            "Uebergabestatus",
        ],
        "forbidden_claims": [
            "Herstellerfinalpruefung ist entbehrlich",
            "Bestellung oder Versandvollzug ohne Send-Tool",
        ],
        "allowed_focus": [
            "Sprich nur ueber die vorhandene Anfragebasis, offene Herstellerpruefpunkte und den aktuellen Uebergabestatus.",
        ],
        "forbidden_fragments": [
            "ohne herstellerpruefung",
            "ohne herstellerprüfung",
            "bestellt",
            "beauftragt",
            "automatisch versendet",
            "sofort versendet",
            "versand ausgeloest",
            "versand ausgelöst",
        ],
        "class_guard": "Bleibe bei versandfaehiger Anfragebasis und Uebergabestatus, aber nicht bei Bestellung oder Versandvollzug.",
        "fallback_text": "Die Anfragebasis ist versandfaehig vorbereitet. Offene Herstellerpruefpunkte und der Uebergabestatus bleiben sichtbar.",
    },
}


def get_surface_claims_spec(
    response_class: str,
    *,
    fallback_text: str | None = None,
) -> SurfaceClaimsSpec:
    resolved_class: OutwardResponseClass
    normalized = normalize_outward_response_class(response_class)
    if normalized in SURFACE_CLAIMS_SPECS:
        resolved_class = normalized  # type: ignore[assignment]
    else:
        resolved_class = "structured_clarification"
    spec = dict(SURFACE_CLAIMS_SPECS[resolved_class])
    if str(fallback_text or "").strip():
        spec["fallback_text"] = str(fallback_text).strip()
    return spec  # type: ignore[return-value]
