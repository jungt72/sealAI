"""V9 governed Dichtungsfall challenger.

The challenge engine is deterministic and bounded. It turns governed case
state into challenger findings, cautious solution hypotheses and exactly one
next-best question. It never selects a final material, never releases a design,
and never mutates upstream facts.
"""

from __future__ import annotations

from typing import Any

from app.agent.domain.medium_registry import is_medium_placeholder_value
from app.agent.domain.risk_readiness import evaluate_risks
from app.domain.seal_packs import pack_for_engineering_path
from app.agent.services.material_intelligence import (
    build_material_intelligence_projection,
)
from app.agent.state.models import (
    ChallengeFinding,
    ChallengeState,
    GovernedSessionState,
    NextBestQuestion,
    SolutionHypothesis,
)


_FIELD_LABELS: dict[str, str] = {
    "medium": "Medium",
    "medium_name": "Medium",
    "medium_qualifiers": "Mediumdetails",
    "temperature_c": "Temperatur",
    "temperature_max": "Temperatur",
    "pressure_bar": "Druck oder Druckdifferenz",
    "pressure_nominal": "Druck oder Druckdifferenz",
    "pressure_direction": "Druckrichtung",
    "sealing_type": "Dichtprinzip oder Dichtungstyp",
    "seal_type": "Dichtprinzip oder Dichtungstyp",
    "motion_type": "Bewegungsart",
    "shaft_diameter_mm": "Wellendurchmesser",
    "shaft_diameter": "Wellendurchmesser",
    "speed_rpm": "Drehzahl",
    "geometry_context": "Einbaugeometrie",
    "geometry": "Einbaugeometrie",
    "counterface_surface": "Gegenlaufpartner und Oberfläche",
    "contamination": "Partikel, Schmutz oder Feststoffe",
    "compliance": "Norm-, ATEX-, FDA- oder Branchenanforderung",
    "industry": "Norm-, ATEX-, FDA- oder Branchenanforderung",
    "installation": "Einbausituation",
    "material": "bestehender Werkstoff",
    "lubrication_context": "Schmierung, Flush oder Trockenlauf",
}

_QUESTION_BY_FOCUS: dict[str, tuple[str, str, str]] = {
    "medium": (
        "Welches Medium berührt die Dichtung genau, inklusive Konzentration, Additiven oder Reinigungsmedien?",
        "Ohne Mediumdetails bleiben Werkstoff-, Korrosions- und Quellrisiken nur grob eingegrenzt.",
        "text",
    ),
    "medium_qualifiers": (
        "Welche Mediumdetails sind bekannt, zum Beispiel Konzentration, Chloride, Feststoffe, pH-Wert oder Reinigungszyklen?",
        "Diese Details können eine scheinbar plausible Werkstoffrichtung deutlich schwächen.",
        "text",
    ),
    "temperature_c": (
        "Welche maximale Temperatur tritt direkt an der Dichtstelle auf, inklusive Spitzen oder Reinigungszyklen?",
        "Die Temperatur entscheidet, ob eine Werkstoffhypothese überhaupt im Prüfrahmen bleibt.",
        "number",
    ),
    "pressure_bar": (
        "Welcher Druck oder welche Druckdifferenz liegt direkt an der Dichtstelle an?",
        "Der Druck verschiebt Bauform, Stützringbedarf, Spaltmaß und Herstellerprüfung.",
        "number",
    ),
    "pressure_direction": (
        "Aus welcher Richtung wirkt der Druck an der Dichtstelle, und kann die Richtung wechseln?",
        "Druckrichtung und Druckwechsel entscheiden, ob eine Dichtgeometrie Druck einschließt, extrudiert oder korrekt entlastet.",
        "text",
    ),
    "sealing_type": (
        "Um welches Dichtprinzip geht es konkret, zum Beispiel RWDR, O-Ring, Flachdichtung, Packung oder Gleitringdichtung?",
        "Das Dichtprinzip bestimmt, welche Berechnungen und Gegenindikatoren überhaupt gelten.",
        "text",
    ),
    "motion_type": (
        "Ist die Dichtstelle rotierend, linear bewegt, statisch oder kombiniert belastet?",
        "Bewegung verändert Reibung, Verschleiß, Oberfläche und Wärmeentwicklung.",
        "choice",
    ),
    "speed_rpm": (
        "Welche Drehzahl liegt an der Welle an, und ist sie dauerhaft oder nur zeitweise erreicht?",
        "Die Drehzahl treibt Umfangsgeschwindigkeit, PV-Risiko und Wärmeentwicklung.",
        "number",
    ),
    "shaft_diameter_mm": (
        "Welchen Wellendurchmesser hat die Dichtstelle?",
        "Ohne Durchmesser lassen sich Umfangsgeschwindigkeit, DN-Wert und viele RWDR-Prüfungen nicht ableiten.",
        "number",
    ),
    "geometry_context": (
        "Welche Einbaugeometrie ist bekannt, inklusive Nut, Bauraum, Spaltmaß oder Gegenlauffläche?",
        "Geometrie entscheidet, ob eine Werkstoff- oder Bauformhypothese konstruktiv plausibel bleibt.",
        "text",
    ),
    "counterface_surface": (
        "Wie sind Gegenlaufpartner, Oberfläche, Rundlauf oder Härte an der Dichtstelle beschrieben?",
        "Die Oberfläche kann eine plausible Werkstoffrichtung praktisch entkräften.",
        "text",
    ),
    "lubrication_context": (
        "Wie ist die Dichtstelle geschmiert oder gespült, und ist Trockenlauf beim Start, Stillstand oder Störfall möglich?",
        "Schmierfilm, Flush und Trockenlauf bestimmen Reibwärme, Verschleiß und Support-System-Bedarf.",
        "text",
    ),
    "compliance": (
        "Gibt es Norm-, ATEX-, FDA-, Lebensmittel-, Pharma- oder Dokumentationsanforderungen?",
        "Regulatorische Anforderungen dürfen nicht implizit angenommen werden.",
        "text",
    ),
}

_MISSING_HINT_TO_FIELD: tuple[tuple[str, str], ...] = (
    ("Medium", "medium"),
    ("Temperatur", "temperature_c"),
    ("Druck", "pressure_bar"),
    ("Dichtprinzip", "sealing_type"),
    ("Dichtungstyp", "sealing_type"),
    ("Bewegungsart", "motion_type"),
    ("Drehzahl", "speed_rpm"),
    ("Wellendurchmesser", "shaft_diameter_mm"),
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        normalized = value.replace(",", ".").strip()
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _asserted_profile(state: GovernedSessionState) -> dict[str, Any]:
    profile: dict[str, Any] = {}
    for field_name, claim in state.asserted.assertions.items():
        value = getattr(claim, "asserted_value", None)
        if value not in (None, "", []):
            profile[field_name] = value
    for field_name, parameter in state.normalized.parameters.items():
        if field_name not in profile and parameter.value not in (None, "", []):
            profile[field_name] = parameter.value
    medium_label = (
        state.medium_classification.canonical_label
        or profile.get("medium")
        or profile.get("medium_name")
    )
    if medium_label and "medium" not in profile:
        profile["medium"] = medium_label
    if state.motion_hint.label and "motion_type" not in profile:
        profile["motion_type"] = state.motion_hint.label
    if state.application_hint.label and "application_context" not in profile:
        profile["application_context"] = state.application_hint.label
    return profile


def _engineering_path(profile: dict[str, Any]) -> str | None:
    text = " ".join(
        _text(profile.get(key))
        for key in (
            "sealing_type",
            "seal_type",
            "application_context",
            "installation",
            "motion_type",
            "geometry_context",
        )
    ).casefold()
    if any(token in text for token in ("rwdr", "radial", "welle", "rotier")):
        return "rwdr"
    if any(token in text for token in ("flansch", "flach", "statisch")):
        return "static"
    if any(
        token in text for token in ("hydraul", "pneum", "kolben", "stange", "linear")
    ):
        return "hyd_pneu"
    return None


def _field_label(field_name: str) -> str:
    return _FIELD_LABELS.get(field_name, field_name)


def _profile_text(profile: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(profile.get(key))
        if value:
            return value
    return ""


def _profile_number(profile: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _number(profile.get(key))
        if value is not None:
            return value
    return None


def _profile_present_field(profile: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        if profile.get(key) not in (None, "", [], {}):
            return key
    return None


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in markers)


def _has_specific_medium_depth(value: Any) -> bool:
    if value in (None, "", []):
        return False
    if isinstance(value, (list, tuple, set)):
        text = " ".join(_text(item) for item in value)
    else:
        text = _text(value)
    return _contains_any(
        text,
        (
            "%",
            "konz",
            "concentration",
            "ph",
            "chlorid",
            "chloride",
            "feststoff",
            "solid",
            "cip",
            "sip",
            "reinigung",
            "cleaning",
            "additiv",
            "additive",
            "leitfähigkeit",
            "leitfaehigkeit",
        ),
    )


def _finding_id(kind: str, key: str, index: int = 0) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in key.casefold()).strip("_")
    return f"{kind}.{safe or 'item'}.{index}"


def _compact_unique(items: list[str], *, limit: int = 8) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _focus_from_missing_hint(hint: str) -> str | None:
    for marker, field_name in _MISSING_HINT_TO_FIELD:
        if marker.casefold() in hint.casefold():
            return field_name
    return None


def _question_for_focus(focus_key: str) -> tuple[str, str, str]:
    return _QUESTION_BY_FOCUS.get(
        focus_key,
        (
            f"Können Sie den offenen Punkt {_field_label(focus_key)} genauer beschreiben?",
            "Dieser Punkt begrenzt die technische Vorqualifikation.",
            "text",
        ),
    )


def _severity_for_missing(field_name: str) -> str:
    if field_name in {
        "medium",
        "temperature_c",
        "pressure_bar",
        "sealing_type",
        "motion_type",
    }:
        return "blocking"
    return "watch"


def _findings_from_missing(
    state: GovernedSessionState,
    *,
    profile: dict[str, Any],
) -> list[ChallengeFinding]:
    fields = _compact_unique(
        list(state.asserted.blocking_unknowns)
        + list(state.governance.preselection_blockers)
        + list(state.governance.type_sensitive_required),
        limit=10,
    )
    findings: list[ChallengeFinding] = []
    for index, field_name in enumerate(fields):
        if profile.get(field_name) not in (None, "", []):
            continue
        label = _field_label(field_name)
        findings.append(
            ChallengeFinding(
                finding_id=_finding_id("missing", field_name, index),
                kind="missing_information",
                severity=_severity_for_missing(field_name),
                title=f"{label} fehlt für eine belastbare Einordnung",
                summary=(
                    f"{label} ist noch nicht als belastbarer Wert im Fall vorhanden."
                ),
                rfq_relevance=(
                    "Der Punkt gehört sichtbar in die Anfragebasis, weil der Hersteller "
                    "sonst Annahmen treffen müsste."
                ),
                related_fields=[field_name],
                action_mode="ASK_NEXT_BEST_QUESTION",
                claim_id=f"challenge_engine.missing.{field_name}",
                claim_type="missing_input_risk",
                subject_field=field_name,
                missing_fields=[field_name],
                blocked_reason="required_case_field_missing",
                allowed_user_wording=(
                    f"{label} ist noch offen und sollte fuer die technische Bewertung geklaert werden."
                ),
                forbidden_user_wording=[
                    f"{label} ist technisch kritisch.",
                    f"{label} ist freigegeben.",
                ],
            )
        )
    return findings


def _findings_from_risks(
    *,
    profile: dict[str, Any],
    engineering_path: str | None,
    compute_results: list[dict[str, Any]],
) -> list[ChallengeFinding]:
    findings: list[ChallengeFinding] = []
    risks = evaluate_risks(
        profile,
        engineering_path=engineering_path,
        missing_required_fields=[],
        checks=[],
    )
    for index, risk in enumerate(risks):
        if risk.score == 0:
            continue
        risk_payload = risk.to_dict()
        severity = "blocking" if risk.score == 9 or risk.score >= 4 else "watch"
        related_fields = [
            field
            for item in list(risk.missing_inputs or []) + list(risk.drivers or [])
            for field in (_focus_from_missing_hint(str(item)) or str(item),)
            if field
        ]
        findings.append(
            ChallengeFinding(
                finding_id=_finding_id("risk", risk.risk_name, index),
                kind="risk",
                severity=severity,
                title=risk.risk_name.replace("_", " "),
                summary=risk.explanation_short,
                rfq_relevance=(
                    "Dieser Risikopunkt muss als Prüfpunkt oder offene Angabe in "
                    "der Herstelleranfrage sichtbar bleiben."
                ),
                related_fields=_compact_unique(related_fields, limit=5),
                evidence_ref_ids=list(risk.rule_ids),
                action_mode="RUN_RISK_COMPLETENESS",
                claim_id=str(risk_payload.get("claim_id") or ""),
                claim_type=str(risk_payload.get("claim_type") or "context_advisory"),
                subject_field=str(risk_payload.get("subject_field") or ""),
                evidence_fields=list(risk_payload.get("evidence_fields") or []),
                missing_fields=list(risk_payload.get("missing_fields") or []),
                blocked_reason=risk_payload.get("blocked_reason"),
                allowed_user_wording=str(risk_payload.get("allowed_user_wording") or ""),
                forbidden_user_wording=list(risk_payload.get("forbidden_user_wording") or []),
            )
        )
    for index, result in enumerate(compute_results):
        if not isinstance(result, dict):
            continue
        notes = [str(item) for item in list(result.get("notes") or []) if item]
        values: list[str] = []
        if result.get("v_surface_m_s") is not None:
            values.append(
                f"Umfangsgeschwindigkeit {float(result['v_surface_m_s']):.2f} m/s"
            )
        if result.get("pv_value_mpa_m_s") is not None:
            values.append(f"PV-Wert {float(result['pv_value_mpa_m_s']):.3f} MPa*m/s")
        if not values and not notes:
            continue
        findings.append(
            ChallengeFinding(
                finding_id=_finding_id(
                    "derived", str(result.get("calc_type") or "calc"), index
                ),
                kind="derived_signal",
                severity="watch" if result.get("status") != "critical" else "blocking",
                title="Berechnetes Signal verändert die Prüfpriorität",
                summary="; ".join(values + notes),
                rfq_relevance=(
                    "Berechnete Signale sind keine Freigabe, aber sie bestimmen, "
                    "welche Daten der Hersteller gezielt prüfen muss."
                ),
                related_fields=["shaft_diameter_mm", "speed_rpm"],
                action_mode="RUN_DERIVED_CALCULATIONS",
                claim_id=_finding_id("derived_claim", str(result.get("calc_type") or "calc"), index),
                claim_type="context_advisory",
                subject_field="technical_derivation",
                evidence_fields=["shaft_diameter_mm", "speed_rpm"],
                allowed_user_wording=(
                    "Berechnete Signale veraendern die Pruefprioritaet, sind aber keine Freigabe."
                ),
                forbidden_user_wording=["Die Berechnung ist eine technische Freigabe."],
            )
        )
    return findings


def _findings_from_medium(
    profile: dict[str, Any],
    material_projection: dict[str, Any],
) -> list[ChallengeFinding]:
    summary = dict(material_projection.get("input_summary") or {})
    medium = _text(summary.get("medium") or profile.get("medium"))
    family = _text(summary.get("medium_family"))
    if (not medium or is_medium_placeholder_value(medium)) and family in {"", "unknown"}:
        return []
    triggers = (
        "salz",
        "chlor",
        "säure",
        "saeure",
        "dampf",
        "lösemittel",
        "loesemittel",
    )
    if family not in {
        "waessrig_salzhaltig",
        "chemisch_aggressiv",
        "loesungsmittel",
        "dampf",
    } and not any(token in medium.casefold() for token in triggers):
        return []
    return [
        ChallengeFinding(
            finding_id=_finding_id("medium", medium or family),
            kind="medium_challenge",
            severity="watch",
            title="Medium darf nicht nur als Name bewertet werden",
            summary=(
                f"'{medium or family}' braucht Kontext wie Konzentration, Temperatur, "
                "Additive, Reinigungsmedien und Kontaktpartner."
            ),
            rfq_relevance=(
                "Die Anfragebasis sollte Mediumdetails und betroffene Bauteile "
                "trennen, damit keine pauschale Werkstoffannahme entsteht."
            ),
            related_fields=["medium", "medium_qualifiers", "temperature_c"],
            action_mode="RUN_MEDIUM_CHALLENGE",
            claim_id=_finding_id("medium_claim", medium or family),
            claim_type="context_advisory",
            subject_field="medium",
            evidence_fields=["medium"] if medium and not is_medium_placeholder_value(medium) else [],
            missing_fields=["medium"] if not medium or is_medium_placeholder_value(medium) else [],
            blocked_reason=(
                "medium_missing_or_placeholder"
                if not medium or is_medium_placeholder_value(medium)
                else None
            ),
            allowed_user_wording=(
                "Das bekannte Medium braucht Kontext wie Konzentration, Temperatur, Additive und Kontaktpartner."
            ),
            forbidden_user_wording=[
                "Das Medium ist chemisch kritisch.",
                "Der Werkstoff ist freigegeben.",
            ],
        )
    ]


def _findings_from_scenario_matrix(
    profile: dict[str, Any],
    *,
    engineering_path: str | None,
) -> list[ChallengeFinding]:
    """Apply V9 scenario gates that sit above plain parameter completeness."""

    findings: list[ChallengeFinding] = []
    medium_text = _profile_text(profile, "medium", "medium_name")
    medium_known = bool(medium_text and not is_medium_placeholder_value(medium_text))
    material_text = _profile_text(profile, "material", "sealing_material_family")
    seal_text = _profile_text(profile, "sealing_type", "seal_type", "installation")
    motion_text = _profile_text(profile, "motion_type", "movement_type")
    has_medium_depth = _has_specific_medium_depth(profile.get("medium_qualifiers"))
    speed_rpm = _profile_number(profile, "speed_rpm", "rpm")
    diameter_mm = _profile_number(profile, "shaft_diameter_mm", "shaft_diameter")
    pressure_bar = _profile_number(
        profile,
        "pressure_at_seal_bar",
        "pressure_delta_bar",
        "pressure_bar",
        "pressure_nominal",
    )
    pressure_evidence_field = _profile_present_field(
        profile,
        "pressure_at_seal_bar",
        "pressure_delta_bar",
        "pressure_bar",
        "pressure_nominal",
    )
    system_pressure_bar = _profile_number(profile, "pressure_system_bar")
    ambiguous_pressure_bar = _profile_number(profile, "ambiguous_pressure_bar")
    has_counterface = bool(
        _profile_text(
            profile,
            "counterface_surface_condition",
            "counterface_surface",
            "shaft_roughness_ra_um",
            "surface_roughness",
            "shaft_hardness_hrc",
            "shaft_hardness",
            "runout_mm",
            "eccentricity_mm",
        )
    )
    has_lubrication_context = bool(
        _profile_text(
            profile,
            "lubrication_condition",
            "lubrication_context",
            "flush_plan",
            "duty_profile",
        )
    )
    aggressive_medium = medium_known and _contains_any(
        medium_text,
        (
            "salzsäure",
            "salzsaeure",
            "hcl",
            "säure",
            "saeure",
            "chlor",
            "solvent",
            "lösemittel",
            "loesemittel",
        ),
    )
    rotary_context = (
        pack_for_engineering_path(engineering_path) is not None
        or _contains_any(seal_text, ("rwdr", "radial", "welle", "rotier"))
        or _contains_any(motion_text, ("rotier", "rotary"))
    )

    if aggressive_medium and not has_medium_depth:
        findings.append(
            ChallengeFinding(
                finding_id=_finding_id("scenario", "medium_depth"),
                kind="application_challenge",
                severity="blocking",
                title="Aggressives Medium braucht Konzentration und Nebenmedien",
                summary=(
                    f"'{medium_text}' ist als Name nicht ausreichend: Konzentration, "
                    "Additive, Reinigungsmedien, Feststoffe und reale Kontaktpartner "
                    "bestimmen die Prüfhypothesen."
                ),
                rfq_relevance=(
                    "Die Mediumtiefe muss in die Anfragebasis, sonst entstehen pauschale "
                    "Werkstoffannahmen."
                ),
                related_fields=["medium", "medium_qualifiers", "temperature_c"],
                action_mode="RUN_SCENARIO_MATRIX",
                claim_id="challenge_engine.medium_depth",
                claim_type="context_advisory",
                subject_field="medium",
                evidence_fields=["medium"],
                missing_fields=["medium_qualifiers"],
                blocked_reason="medium_details_missing",
                allowed_user_wording=(
                    "Das bekannte Medium braucht Konzentration, Additive, Reinigungsmedien und Kontaktpartner als Pruefkontext."
                ),
                forbidden_user_wording=["Das Medium ist chemisch kritisch."],
            )
        )

    if aggressive_medium and _contains_any(material_text, ("nbr", "nitril")):
        findings.append(
            ChallengeFinding(
                finding_id=_finding_id("scenario", "nbr_aggressive_medium"),
                kind="contradiction",
                severity="blocking",
                title="NBR wirkt im bekannten Chemiefenster als Gegenindikator",
                summary=(
                    "Die vorhandene NBR-Richtung ist bei stark saurem oder chloridhaltigem "
                    "Medienkontext nicht belastbar als Startannahme. Sie muss sichtbar als "
                    "Gegenindikator geprüft werden."
                ),
                rfq_relevance=(
                    "Der Hersteller sollte erkennen, dass NBR nur vorhandene Annahme oder "
                    "Vergleichspunkt ist, nicht die freigegebene Zielrichtung."
                ),
                related_fields=["material", "medium", "medium_qualifiers"],
                action_mode="RUN_COUNTERINDICATOR_CHALLENGE",
                claim_id="challenge_engine.nbr_aggressive_medium",
                claim_type="context_advisory",
                subject_field="material",
                evidence_fields=["material", "medium"],
                missing_fields=["medium_qualifiers"],
                allowed_user_wording=(
                    "NBR ist im bekannten aggressiven Medienkontext ein Gegenindikator und bleibt Pruefhypothese."
                ),
                forbidden_user_wording=[
                    "NBR ist ungeeignet.",
                    "NBR ist freigegeben.",
                ],
            )
        )

    surface_speed = None
    if rotary_context and speed_rpm is not None and diameter_mm is not None:
        surface_speed = 3.141592653589793 * diameter_mm * speed_rpm / 60_000
        if surface_speed >= 4.0 and not has_counterface:
            findings.append(
                ChallengeFinding(
                    finding_id=_finding_id("scenario", "rotary_counterface"),
                    kind="application_challenge",
                    severity="blocking" if surface_speed >= 10.0 else "watch",
                    title="Gegenfläche fehlt bei dynamisch relevanter Umfangsgeschwindigkeit",
                    summary=(
                        f"Aus {diameter_mm:g} mm und {speed_rpm:g} rpm ergeben sich "
                        f"rund {surface_speed:.2f} m/s. Ohne Oberfläche, Härte, Rundlauf "
                        "und Bearbeitung bleibt die Rotationshypothese schwach."
                    ),
                    rfq_relevance=(
                        "Oberfläche, Härte und Rundlauf sollten als eigene Prüfpunkte in "
                        "die Anfragebasis."
                    ),
                    related_fields=[
                        "shaft_diameter_mm",
                        "speed_rpm",
                        "counterface_surface",
                    ],
                    action_mode="RUN_SURFACE_SPEED_CHALLENGE",
                    claim_id="challenge_engine.rotary_counterface_missing",
                    claim_type="missing_input_risk",
                    subject_field="counterface_surface",
                    evidence_fields=["shaft_diameter_mm", "speed_rpm"],
                    missing_fields=[
                        "counterface_surface_condition",
                        "runout_mm",
                        "shaft_hardness_hrc",
                    ],
                    blocked_reason="rotary_counterface_data_missing",
                    allowed_user_wording=(
                        "Bei rotierender Welle sind Oberflaeche, Haerte und Rundlauf offene Pruefgroessen."
                    ),
                    forbidden_user_wording=[
                        "Der Wellenschlag ist hoch.",
                        "Die Gegenlaufflaeche ist ungeeignet.",
                    ],
                )
            )

    if rotary_context and aggressive_medium and not has_lubrication_context:
        findings.append(
            ChallengeFinding(
                finding_id=_finding_id("scenario", "lubrication_flush"),
                kind="application_challenge",
                severity="watch",
                title="Schmierfilm, Flush oder Trockenlauf sind noch nicht beschrieben",
                summary=(
                    "Bei rotierendem Kontakt mit aggressivem Medium kann der Unterschied "
                    "zwischen nasser, gespülter, intermittierender oder trockener Dichtstelle "
                    "die Bauformhypothese verändern."
                ),
                rfq_relevance=(
                    "Flush, Quench, Trockenlauf und Stillstandsbedingungen gehören als "
                    "Prüfkontext in die Herstellerfrage."
                ),
                related_fields=["lubrication_context", "duty_profile", "medium"],
                action_mode="RUN_SUPPORT_SYSTEM_CHALLENGE",
                claim_id="challenge_engine.lubrication_context_missing",
                claim_type="missing_input_risk",
                subject_field="lubrication_context",
                evidence_fields=["medium"] if medium_known else [],
                missing_fields=["lubrication_context"],
                blocked_reason="lubrication_context_missing",
                allowed_user_wording=(
                    "Schmierfilm, Flush oder Trockenlauf sind noch nicht beschrieben."
                ),
                forbidden_user_wording=["Die Schmierung ist unzureichend."],
            )
        )

    if (
        pack_for_engineering_path(engineering_path) is not None
        and pressure_bar is not None
        and pressure_bar > 0.5
    ):
        findings.append(
            ChallengeFinding(
                finding_id=_finding_id("scenario", "rwdr_pressure"),
                kind="application_challenge",
                severity="watch",
                title="RWDR-Druck muss als Dichtstellendruck verifiziert werden",
                summary=(
                    f"{pressure_bar:g} bar an einer RWDR-nahen Dichtstelle kann die "
                    "Lippenlast, Wärme und Bauformprüfung stark beeinflussen. Entscheidend "
                    "ist der echte Differenzdruck direkt an der Dichtstelle."
                ),
                rfq_relevance=(
                    "Druckniveau und Druckrichtung sollten nicht als Systemdruck "
                    "übernommen, sondern an der Dichtstelle verifiziert werden."
                ),
                related_fields=[
                    pressure_evidence_field or "pressure_at_seal_bar",
                    "pressure_direction",
                    "sealing_type",
                ],
                action_mode="RUN_PRESSURE_DIRECTION_CHALLENGE",
                claim_id="challenge_engine.rwdr_pressure_at_seal",
                claim_type="context_advisory",
                subject_field=pressure_evidence_field or "pressure_at_seal_bar",
                evidence_fields=[pressure_evidence_field or "pressure_at_seal_bar"],
                missing_fields=["pressure_direction"],
                allowed_user_wording=(
                    "Der angegebene Druck direkt an der Dichtstelle bzw. Differenzdruck ist fuer RWDR ein Pruefpunkt."
                ),
                forbidden_user_wording=[
                    "RWDR ist ungeeignet.",
                    "RWDR ist freigegeben.",
                ],
            )
        )
    elif (
        pack_for_engineering_path(engineering_path) is not None
        and system_pressure_bar is not None
    ):
        findings.append(
            ChallengeFinding(
                finding_id=_finding_id("scenario", "rwdr_system_pressure"),
                kind="application_challenge",
                severity="watch",
                title="Systemdruck ist nicht der Dichtstellendruck",
                summary=(
                    f"{system_pressure_bar:g} bar ist als Systemdruck bekannt. Offen ist, "
                    "welcher Druck direkt an der Dichtstelle oder als Differenzdruck wirkt."
                ),
                rfq_relevance=(
                    "Systemdruck und Dichtstellendruck muessen in der Anfragebasis getrennt bleiben."
                ),
                related_fields=[
                    "pressure_system_bar",
                    "pressure_at_seal_bar",
                    "pressure_delta_bar",
                ],
                action_mode="RUN_PRESSURE_DIRECTION_CHALLENGE",
                claim_id="challenge_engine.rwdr_seal_pressure_missing",
                claim_type="missing_input_risk",
                subject_field="pressure_at_seal_bar",
                evidence_fields=["pressure_system_bar"],
                missing_fields=["pressure_at_seal_bar"],
                blocked_reason="seal_pressure_missing_system_pressure_only",
                allowed_user_wording=(
                    "Der Systemdruck ist bekannt. Offen ist noch, welcher Druck direkt an der Dichtstelle anliegt."
                ),
                forbidden_user_wording=["Der Dichtungsdruck ist kritisch."],
            )
        )
    elif (
        pack_for_engineering_path(engineering_path) is not None
        and ambiguous_pressure_bar is not None
    ):
        findings.append(
            ChallengeFinding(
                finding_id=_finding_id("scenario", "rwdr_ambiguous_pressure"),
                kind="application_challenge",
                severity="blocking",
                title="Druckrolle ist unklar",
                summary=(
                    f"{ambiguous_pressure_bar:g} bar ist als Druckwert vorhanden, aber die Rolle "
                    "als Systemdruck, Dichtstellendruck oder Differenzdruck ist noch unklar."
                ),
                rfq_relevance=(
                    "Der Druckwert darf nicht als Dichtstellenbelastung uebernommen werden, "
                    "bis seine Rolle geklaert ist."
                ),
                related_fields=[
                    "ambiguous_pressure_bar",
                    "pressure_at_seal_bar",
                    "pressure_delta_bar",
                ],
                action_mode="RUN_PRESSURE_DIRECTION_CHALLENGE",
                claim_id="challenge_engine.rwdr_pressure_ambiguous",
                claim_type="ambiguity_risk",
                subject_field="ambiguous_pressure_bar",
                evidence_fields=["ambiguous_pressure_bar"],
                missing_fields=["pressure_at_seal_bar"],
                blocked_reason="pressure_role_ambiguous",
                allowed_user_wording=(
                    "Ein Druckwert ist vorhanden, aber die Rolle ist unklar: Systemdruck, Dichtstellendruck oder Differenzdruck."
                ),
                forbidden_user_wording=["Der Dichtungsdruck ist kritisch."],
            )
        )

    return findings


def _hypotheses_from_materials(
    material_projection: dict[str, Any],
) -> list[SolutionHypothesis]:
    hypotheses: list[SolutionHypothesis] = []
    for index, candidate in enumerate(
        list(material_projection.get("candidate_materials") or [])[:4]
    ):
        if not isinstance(candidate, dict):
            continue
        status = _text(candidate.get("status"))
        plausibility = _text(candidate.get("plausibility")) or "low"
        if status == "excluded_by_known_constraint":
            plausibility = "blocked"
        hypotheses.append(
            SolutionHypothesis(
                hypothesis_id=_finding_id(
                    "hypothesis", _text(candidate.get("material_key")) or str(index)
                ),
                label=f"{_text(candidate.get('label'))} als Prüfhypothese",
                plausibility_class=(
                    plausibility
                    if plausibility in {"low", "medium", "high", "blocked"}
                    else "low"
                ),
                status="active" if plausibility != "blocked" else "weakened",
                basis=_compact_unique(
                    list(candidate.get("score_drivers") or [])
                    + list(candidate.get("why_considered") or []),
                    limit=5,
                ),
                counterindicators=_compact_unique(
                    list(candidate.get("counterindicators") or [])
                    + list(candidate.get("score_cautions") or []),
                    limit=5,
                ),
                blocking_unknowns=_compact_unique(
                    list(candidate.get("blocking_unknowns") or []),
                    limit=5,
                ),
                required_checks=_compact_unique(
                    list(candidate.get("required_checks") or []),
                    limit=5,
                ),
                rfq_relevance=_text(candidate.get("rfq_relevance")),
            )
        )
    return hypotheses


def _select_next_best_question(
    findings: list[ChallengeFinding],
    hypotheses: list[SolutionHypothesis],
    material_projection: dict[str, Any],
) -> NextBestQuestion | None:
    for finding in findings:
        if finding.status != "open":
            continue
        if finding.severity == "blocking" and finding.related_fields:
            focus = finding.related_fields[0]
            question, reason, answer_type = _question_for_focus(focus)
            return NextBestQuestion(
                question=question,
                reason=reason,
                focus_key=focus,
                priority=1,
                expected_answer_type=answer_type,
                closes_findings=[finding.finding_id],
            )
    for hint in list(material_projection.get("missing_field_hints") or []):
        focus = _focus_from_missing_hint(str(hint))
        if focus:
            question, reason, answer_type = _question_for_focus(focus)
            return NextBestQuestion(
                question=question,
                reason=reason,
                focus_key=focus,
                priority=2,
                expected_answer_type=answer_type,
            )
    for hypothesis in hypotheses:
        if hypothesis.blocking_unknowns:
            focus = (
                _focus_from_missing_hint(hypothesis.blocking_unknowns[0])
                or "medium_qualifiers"
            )
            question, reason, answer_type = _question_for_focus(focus)
            return NextBestQuestion(
                question=question,
                reason=reason,
                focus_key=focus,
                priority=3,
                expected_answer_type=answer_type,
            )
    return None


def build_challenge_state(
    state: GovernedSessionState,
    *,
    compute_results: list[dict[str, Any]] | None = None,
) -> ChallengeState:
    """Build the canonical V9 challenge state from governed facts."""

    profile = _asserted_profile(state)
    engineering_path = _engineering_path(profile)
    medium_classification = state.medium_classification.model_dump(mode="python")
    seal_profile = {
        "seal_type": profile.get("sealing_type") or profile.get("seal_type"),
        "seal_family": profile.get("seal_family"),
        "motion_type": profile.get("motion_type"),
    }
    material_projection = build_material_intelligence_projection(
        profile=profile,
        medium_classification=medium_classification,
        seal_application_profile=seal_profile,
    )
    compute_payload = [
        item for item in list(compute_results or []) if isinstance(item, dict)
    ]
    findings = (
        _findings_from_missing(state, profile=profile)
        + _findings_from_medium(profile, material_projection)
        + _findings_from_scenario_matrix(
            profile,
            engineering_path=engineering_path,
        )
        + _findings_from_risks(
            profile=profile,
            engineering_path=engineering_path,
            compute_results=compute_payload,
        )
    )
    # Keep stable order: blocking first, then watch/info, preserving derivation order.
    severity_rank = {"blocking": 0, "watch": 1, "info": 2}
    findings = sorted(findings, key=lambda item: severity_rank.get(item.severity, 9))[
        :12
    ]
    hypotheses = _hypotheses_from_materials(material_projection)
    next_best_question = _select_next_best_question(
        findings, hypotheses, material_projection
    )
    action_modes = _compact_unique(
        [
            "CHALLENGE_KNOWN_INPUTS",
            *[finding.action_mode for finding in findings],
            "SHOW_HYPOTHESIS_SET" if hypotheses else "",
            "ASK_NEXT_BEST_QUESTION" if next_best_question else "",
        ],
        limit=8,
    )
    return ChallengeState(
        status=(
            "available"
            if findings or hypotheses or next_best_question
            else "insufficient_context"
        ),
        findings=findings,
        hypotheses=hypotheses,
        next_best_question=next_best_question,
        action_modes_run=action_modes,
    )
