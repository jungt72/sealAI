from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.agent.domain.medium_registry import resolve_medium_entry


MediumContextStatus = Literal["unavailable", "available"]
MediumContextConfidence = Literal["low", "medium", "high"]
MediumContextScope = Literal["orientierend"]
MediumContextSourceType = Literal["llm_general_knowledge"]


class MediumContext(BaseModel):
    medium_label: str | None = None
    status: MediumContextStatus = "unavailable"
    scope: MediumContextScope = "orientierend"
    summary: str | None = None
    properties: list[str] = Field(default_factory=list)
    challenges: list[str] = Field(default_factory=list)
    followup_points: list[str] = Field(default_factory=list)
    confidence: MediumContextConfidence | None = None
    source_type: MediumContextSourceType | None = None
    not_for_release_decisions: bool = True
    disclaimer: str | None = None
    source_medium_key: str | None = None


def _compact_unique(items: list[str], *, limit: int | None = None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        normalized = text.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result


def _claim_safe(items: list[str]) -> list[str]:
    blocked_fragments = (
        "geeignet",
        "ungeeignet",
        "freigabe",
        "freigegeben",
        "beständig",
        "chemisch beständig",
        "rfq",
        "matching",
        "hersteller",
        "werkstofffreigabe",
        "zulassung",
        "normkonform",
        "kompatibel",
    )
    safe_items: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        lowered = text.casefold()
        if any(fragment in lowered for fragment in blocked_fragments):
            continue
        safe_items.append(text)
    return _compact_unique(safe_items)


def _default_followup_points() -> list[str]:
    return [
        "Temperatur",
        "Druck",
        "statisch oder dynamisch",
        "Verunreinigungen oder Partikel",
    ]


_MEDIUM_LIBRARY: dict[str, dict[str, object]] = {
    "salzwasser": {
        "medium_label": "Salzwasser",
        "summary": "Salzwasser ist ein wasserbasiertes, salzhaltiges Medium mit typischer korrosionsfoerdernder Wirkung auf metallische Komponenten.",
        "properties": [
            "wasserbasiert",
            "salzhaltig",
            "elektrisch leitfaehig",
            "korrosionsfoerdernd",
        ],
        "challenges": [
            "Korrosionsrisiko an Metallkomponenten beachten",
            "Materialvertraeglichkeit von Dichtungs- und Konstruktionswerkstoffen pruefen",
            "moegliche Ablagerungen oder Kristallisation beruecksichtigen",
            "Einfluss auf Werkstoff- und Einsatzrahmen frueh einordnen",
        ],
        "followup_points": [
            "Salzkonzentration",
            "Temperatur",
            "Druck",
            "statisch oder dynamisch",
        ],
        "confidence": "medium",
    },
    "meerwasser": {
        "medium_label": "Meerwasser",
        "summary": "Meerwasser ist ein natuerlich salzhaltiges, wasserbasiertes Medium mit erhöhter Korrosions- und Ablagerungsrelevanz fuer metallische Baugruppen.",
        "properties": [
            "wasserbasiert",
            "salzhaltig",
            "leitfaehig",
            "korrosionsfoerdernd",
        ],
        "challenges": [
            "Korrosionsbeanspruchung von metallischen Kontaktflaechen einordnen",
            "Belagbildung oder biologische Einfluesse im Betrieb beruecksichtigen",
            "Werkstoff- und Einsatzrahmen sauber abgrenzen",
        ],
        "followup_points": [
            "Salinitaet",
            "Temperatur",
            "Druck",
            "Ablagerungen oder Fouling",
        ],
        "confidence": "medium",
    },
    "wasser": {
        "medium_label": "Wasser",
        "summary": "Wasser ist ein wasserbasiertes Medium, dessen Verhalten je nach Reinheit, Temperatur und Additiven technisch deutlich variieren kann.",
        "properties": [
            "wasserbasiert",
            "typisch gering viskos",
            "temperaturabhaengig",
            "je nach Qualitaet mit geloesten Stoffen oder Additiven",
        ],
        "challenges": [
            "Zusatzstoffe oder Wasserqualitaet frueh klaeren",
            "Temperatur- und Druckeinfluss auf den Einsatzrahmen einordnen",
            "moegliche Korrosions- oder Ablagerungsthemen im Gesamtsystem beachten",
        ],
        "followup_points": [
            "Wasserqualitaet",
            "Temperatur",
            "Druck",
            "Zusatzstoffe oder Reinigungsmedien",
        ],
        "confidence": "medium",
    },
    "luft": {
        "medium_label": "Luft",
        "summary": "Luft ist ein gasfoermiges Medium mit typischerweise geringer Viskositaet und hoher Leckagesensitivitaet bei Druckdifferenzen.",
        "properties": [
            "gasfoermig",
            "geringe Viskositaet",
            "kompressibel",
            "leckagesensitiv bei Druckunterschieden",
        ],
        "challenges": [
            "Dichtheit gegen Leckage sauber absichern",
            "Druckschwankungen und Dynamik im Betrieb beruecksichtigen",
            "Partikel, Feuchte oder Oeleintrag im Luftsystem klaeren",
        ],
        "followup_points": [
            "Druckniveau",
            "Temperatur",
            "trocken oder feucht",
            "statisch oder dynamisch",
        ],
        "confidence": "medium",
    },
    "oel": {
        "medium_label": "Oel",
        "summary": "Oel ist typischerweise ein fluessiges, schmierendes Medium mit viskositaets- und temperaturabhaengigem Verhalten.",
        "properties": [
            "fluessig",
            "typisch schmierend",
            "viskositaetsabhaengig",
            "temperaturabhaengig",
        ],
        "challenges": [
            "Viskositaet und Temperaturfenster frueh einordnen",
            "Zusatzstoffe oder Alterung des Mediums beruecksichtigen",
            "Dynamik und Oberflaechengeschwindigkeit fuer die Dichtungsauslegung klaeren",
        ],
        "followup_points": [
            "Oeltyp oder Basis",
            "Viskositaet",
            "Temperatur",
            "statisch oder dynamisch",
        ],
        "confidence": "medium",
    },
    "chemikalien": {
        "medium_label": "Chemikalien",
        "summary": "Chemikalien sind ein Sammelbegriff fuer stofflich sehr unterschiedliche Medien; fuer die Auslegung ist die genaue Zusammensetzung entscheidend.",
        "properties": [
            "stofflich stark variabel",
            "teils reaktiv",
            "haeufig konzentrationsabhaengig",
            "anwendungsabhaengig",
        ],
        "challenges": [
            "genaue Stoffbezeichnung oder Zusammensetzung klaeren",
            "Konzentration und Temperatur sauber abgrenzen",
            "offene Punkte fuer Werkstoff- und Einsatzrahmen explizit halten",
        ],
        "followup_points": [
            "genaue Stoffbezeichnung",
            "Konzentration",
            "Temperatur",
            "Druck",
        ],
        "confidence": "low",
    },
    "dampf": {
        "medium_label": "Dampf",
        "summary": "Dampf ist ein heisses gasfoermiges Medium, bei dem Temperatur, Druck und Kondensationsverhalten die technische Einengung stark beeinflussen.",
        "properties": [
            "gasfoermig",
            "heiss",
            "kompressibel",
            "kondensationsrelevant",
        ],
        "challenges": [
            "Temperatur- und Druckfenster sauber abgrenzen",
            "Kondensation oder Feuchtewechsel im Betrieb beachten",
            "Dynamik und thermische Wechselbeanspruchung frueh einordnen",
        ],
        "followup_points": [
            "Sattdampf oder Heissdampf",
            "Temperatur",
            "Druck",
            "kontinuierlicher oder wechselnder Betrieb",
        ],
        "confidence": "medium",
    },
}

_FAMILY_LIBRARY: dict[str, dict[str, object]] = {
    "waessrig_salzhaltig": {
        "medium_label": "Salzhaltiges waessriges Medium",
        "summary": "Salzhaltige waessrige Medien sind typischerweise leitfaehig und korrosionsrelevant fuer angrenzende metallische Komponenten.",
        "properties": ["wasserbasiert", "salzhaltig", "leitfaehig"],
        "challenges": [
            "Korrosionsbeanspruchung frueh einordnen",
            "Ablagerungen oder Kristallisation im Betrieb beachten",
        ],
        "followup_points": ["Salzkonzentration", "Temperatur", "Druck"],
        "confidence": "low",
    },
    "chemisch_aggressiv": {
        "medium_label": "Chemisch aggressives Medium",
        "summary": "Chemisch aggressive Medien muessen ueber Stofftyp, Konzentration und Temperatur sauber eingegrenzt werden, bevor technische Aussagen belastbar sind.",
        "properties": ["stofflich variabel", "reaktionsrelevant", "temperaturabhaengig"],
        "challenges": [
            "Exakte Stoffbezeichnung oder Zusammensetzung klaeren",
            "Konzentration und Temperatur sauber abgrenzen",
        ],
        "followup_points": ["Stofftyp", "Konzentration", "Temperatur"],
        "confidence": "low",
    },
}


def normalize_medium_context_key(medium_label: str | None) -> str | None:
    text = str(medium_label or "").strip()
    if not text:
        return None
    entry, _matched_alias = resolve_medium_entry(text)
    if entry is not None:
        return entry.registry_key
    lowered = text.casefold()
    return lowered if lowered in _MEDIUM_LIBRARY else None


def build_medium_context(
    medium_label: str | None,
    *,
    medium_family: str | None = None,
) -> MediumContext:
    key = normalize_medium_context_key(medium_label)
    payload = dict(_MEDIUM_LIBRARY.get(key) or {})
    if not payload and medium_family:
        payload = dict(_FAMILY_LIBRARY.get(str(medium_family).strip()) or {})
    if not payload:
        return MediumContext()

    resolved_label = str(payload.get("medium_label") or medium_label or "").strip()
    if not resolved_label:
        return MediumContext()

    summary = str(payload.get("summary") or "").strip()
    generic_followups = list(payload.get("followup_points") or []) + _default_followup_points()
    properties = _claim_safe(list(payload.get("properties") or []))
    challenges = _claim_safe(list(payload.get("challenges") or []))
    followup_points = _claim_safe(generic_followups)

    return MediumContext(
        medium_label=resolved_label,
        status="available",
        scope="orientierend",
        summary=summary or f"{resolved_label} wird hier als allgemeiner Medium-Kontext eingeordnet.",
        properties=properties[:4],
        challenges=challenges[:4],
        followup_points=followup_points[:4],
        confidence=str(payload.get("confidence") or "medium"),  # type: ignore[arg-type]
        source_type="llm_general_knowledge",
        not_for_release_decisions=True,
        disclaimer="Allgemeiner Medium-Kontext, nicht als Freigabe.",
        source_medium_key=key or str(medium_family or "").strip() or None,
    )


def resolve_medium_context(
    medium_label: str | None,
    *,
    medium_family: str | None = None,
    previous: MediumContext | dict[str, object] | None = None,
) -> MediumContext:
    key = normalize_medium_context_key(medium_label)
    effective_key = key or (str(medium_family or "").strip() or None)
    if not effective_key:
        return MediumContext()

    if isinstance(previous, MediumContext):
        previous_context = previous
    elif isinstance(previous, dict):
        previous_context = MediumContext.model_validate(previous)
    else:
        previous_context = MediumContext()

    if (
        previous_context.status == "available"
        and previous_context.source_medium_key == effective_key
    ):
        return previous_context

    return build_medium_context(medium_label, medium_family=medium_family)
