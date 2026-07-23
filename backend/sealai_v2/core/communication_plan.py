"""Deterministic conversation governance for one sealingAI turn.

The model may formulate an answer, but it does not decide the conversational contract.  This
module maps the governed route and case state to a bounded response plan: answer first when safe,
acknowledge the user's actual goal, ask at most one discriminating question, explain why it matters,
and never turn an intake turn into an evidence/recommendation answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sealai_v2.core.user_goal import requests_replacement_identification


@dataclass(frozen=True)
class CommunicationPlan:
    goal: str
    response_moves: tuple[str, ...]
    depth: str
    answer_first: bool
    max_questions: int
    case_bound: bool
    next_question: str = ""
    question_reason: str = ""
    must_include: tuple[str, ...] = ()
    must_not_include: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "response_moves": list(self.response_moves),
            "depth": self.depth,
            "answer_first": self.answer_first,
            "max_questions": self.max_questions,
            "case_bound": self.case_bound,
            "next_question": self.next_question,
            "question_reason": self.question_reason,
            "must_include": list(self.must_include),
            "must_not_include": list(self.must_not_include),
        }


@dataclass(frozen=True)
class CommunicationGuardVerdict:
    passed: bool
    violations: tuple[str, ...] = ()


_FIELD_QUESTIONS: dict[str, tuple[str, str]] = {
    "Anwendungsziel": (
        "Geht es um eine Neuauslegung, einen Austausch, eine Optimierung oder die Analyse eines Schadens?",
        "Das Ziel bestimmt, ob wir Bestand, Einbauraum oder Fehlerursachen zuerst betrachten.",
    ),
    "Medium": (
        "Welches konkrete Medium liegt an der Dichtstelle an, einschließlich Produktbezeichnung und möglicher Additive?",
        "Die genaue Zusammensetzung ist für Werkstoff- und Beständigkeitsfragen entscheidend.",
    ),
    "Betriebstemperatur": (
        "Welche minimale, normale und maximale Temperatur tritt an der Dichtstelle auf?",
        "Dauerbetrieb und Temperaturspitzen können den zulässigen Lösungsraum unterschiedlich begrenzen.",
    ),
    "Druck": (
        "Welcher normale und maximale Differenzdruck liegt an der Dichtstelle an?",
        "Der Differenzdruck beeinflusst Dichtprinzip, Bauform und Belastung.",
    ),
    "Wellendurchmesser": (
        "Wie groß ist der Wellendurchmesser direkt an der Dichtlaufspur?",
        "Das Maß wird für Geometrie und die deterministische Geschwindigkeitsberechnung benötigt.",
    ),
    "Drehzahl": (
        "Welche Drehzahl liegt im Normalbetrieb und maximal an?",
        "Damit lässt sich die dynamische Belastung der Dichtstelle einordnen.",
    ),
    "Einheit der Drehzahl": (
        "In welcher Einheit ist die bereits genannte Drehzahl angegeben, zum Beispiel U/min?",
        "Ohne die Einheit darf der Rechenkern den vorhandenen Zahlenwert nicht als Drehzahl binden.",
    ),
    "Einheit des Wellendurchmessers": (
        "In welcher Einheit ist der bereits genannte Wellendurchmesser angegeben, zum Beispiel mm?",
        "Ohne die Einheit darf der Rechenkern den vorhandenen Zahlenwert nicht als Länge binden.",
    ),
    "Dichtungstyp oder Dichtstelle": (
        "Welche Dichtungsart oder konkrete Dichtstelle gehört zu diesem Fall?",
        "Damit ordne ich den Fall dem passenden Auslegungs- und Fragenpfad zu.",
    ),
    "Nächster Auswertungsschritt": (
        "Welche technische Entscheidung soll ich auf Basis des erfassten Falls als Nächstes ausarbeiten?",
        "So nutze ich den vorhandenen Case gezielt, statt bereits geklärte Angaben erneut abzufragen.",
    ),
}

_NBR_ENVIRONMENTAL_CRACK_RE = re.compile(
    r"\bnbr\b.*\b(?:au[sß]en|fre(?:ien|iland)|ozon|uv|witterung)\w*\b|"
    r"\b(?:au[sß]en|fre(?:ien|iland)|ozon|uv|witterung)\w*\b.*\bnbr\b",
    re.IGNORECASE,
)
_NBR_THERMAL_AGING_RE = re.compile(
    r"\bnbr\b.*\b(?:hart|verh[aä]rt\w*|verspr[oö]d\w*|riss\w*)\b|"
    r"\b(?:hart|verh[aä]rt\w*|verspr[oö]d\w*|riss\w*)\b.*\bnbr\b",
    re.IGNORECASE,
)
_APPLICATION_CONTRAST_RE = re.compile(
    r"\br[uü]hrwerk\w*\b.*\bgetriebe\w*\b|\bgetriebe\w*\b.*\br[uü]hrwerk\w*\b",
    re.IGNORECASE,
)
_BARE_APPLICATION_REQUEST_RE = re.compile(
    r"^\s*(?:ich\s+(?:brauche|ben[oö]tige|suche)\s+(?:eine[nr]?\s+)?dichtung|"
    r"welche\s+dichtung\s+(?:brauche|ben[oö]tige|nehme)\s+ich|"
    r"dichtung(?:sl[oö]sung)?\s+gesucht)\s+f[uü]r\s+"
    r"(?:meine|unsere|eine|einen|die|den)?\s*"
    r"(?:pumpe|r[uü]hrwerk|mischer|ventil|zylinder|kompressor|reaktor|bioreaktor)\w*"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)
_MATERIAL_SELECTION_REQUEST_RE = re.compile(
    r"\b(?:empfiehl|empfehl)\w*[^?!.]{0,55}\b(?:material|werkstoff|elastomer|compound)\b|"
    r"\bwelche[rns]?\s+(?:material|werkstoff|elastomer|compound)\b[^?!.]{0,80}"
    r"(?:eign\w*|passt|w[aä]re|pr[uü]fen|nehmen|w[aä]hlen)\b|"
    r"\b(?:material|werkstoff|elastomer|compound)\b[^?!.]{0,55}\b"
    r"(?:empfehl\w*|ausw[aä]hl\w*|passt)\b|"
    r"\bworauf\s+sollte\s+ich\s+bei\s+(?:der|einer)\s+"
    r"(?:werkstoff|material)(?:wahl|auswahl)\s+achten\b",
    re.IGNORECASE,
)
_STEAM_CONTEXT_RE = re.compile(
    r"\b(?:wasser|satt|hei[sß]|[uü]berhitzt)\w*dampf\w*\b|\bdampf\w*\b|\bsip\b",
    re.IGNORECASE,
)
_DYNAMIC_TIGHTNESS_TARGET_RE = re.compile(
    r"\b(?:maximale\s+dichtheit|leckage\s*(?:[:=]\s*)?(?:null|0)|leckagefrei\w*)\b"
    r"[^?!.]{0,100}\b(?:welle|rotierend\w*|dynamisch\w*|dichtung|optimal)\w*\b|"
    r"\b(?:welle|rotierend\w*|dynamisch\w*)\w*\b[^?!.]{0,100}"
    r"\b(?:maximale\s+dichtheit|leckage\s*(?:null|0)|leckagefrei\w*)\b",
    re.IGNORECASE,
)
_PROCESS_SEAL_STRESS_RE = re.compile(
    r"\b(?:gleitringdichtung|gleitdichtung|glrd|r[uü]hrwerk|mischer|reaktor)\w*\b",
    re.IGNORECASE,
)
_ABRASIVE_OR_VISCOUS_RE = re.compile(
    r"\b(?:abrasiv\w*|feststoff\w*|partikel\w*|schlamm\w*|kristall\w*|"
    r"z[aä]hfl[uü]ssig\w*|viskos\w*)\b",
    re.IGNORECASE,
)


def _next_case_question(
    missing_fields: tuple[str, ...], conflicts: tuple[str, ...]
) -> tuple[str, str]:
    if conflicts:
        field = conflicts[0].replace("_", " ").strip()
        return (
            f"Welche Angabe gilt aktuell für {field}?",
            "Im Fall liegen dazu widersprüchliche Werte vor; ich verwende keinen davon ungeprüft.",
        )
    if not missing_fields:
        return "", ""
    field = missing_fields[0]
    if field in _FIELD_QUESTIONS:
        return _FIELD_QUESTIONS[field]
    return (
        f"Welche konkrete Angabe gilt für {field}?",
        "Diese Information ist der nächste offene, entscheidungsrelevante Punkt im Fall.",
    )


def build_communication_plan(
    *,
    question: str,
    route_name: str,
    case_fields: tuple[str, ...] = (),
    missing_fields: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
    solution_requested: bool = False,
    case_active: bool = False,
) -> CommunicationPlan:
    """Build the single, deterministic communication contract for this turn."""

    case_bound = bool(case_active or case_fields or missing_fields or conflicts)
    next_question, reason = _next_case_question(missing_fields, conflicts)

    if route_name == "case_intake_invite":
        if case_bound:
            next_question = (
                "Möchtest du den aktuellen Fall weiterführen oder eine neue "
                "Dichtungslösung beginnen?"
            )
            reason = (
                "So verwende ich vorhandene Angaben nur dann weiter, wenn sie wirklich "
                "zu deinem Anliegen gehören."
            )
        else:
            next_question = "Welche Anwendung und Dichtstelle möchtest du abdichten?"
            reason = (
                "Davon hängt ab, welche Betriebs-, Geometrie- und Sicherheitsangaben ich "
                "als Nächstes gezielt von dir brauche."
            )
        return CommunicationPlan(
            goal="start_case_collaboratively",
            response_moves=("acknowledge", "empathize", "clarify", "justify"),
            depth="brief",
            answer_first=True,
            max_questions=1,
            case_bound=case_bound,
            next_question=next_question,
            question_reason=reason,
            must_include=("user_goal_acknowledgement", "question_reason"),
            must_not_include=(
                "technical_claims",
                "citations",
                "recommendations",
                "unrelated_examples",
            ),
        )

    if route_name == "smalltalk_navigation":
        return CommunicationPlan(
            goal="respond_socially_and_offer_navigation",
            response_moves=("acknowledge", "recover"),
            depth="brief",
            answer_first=True,
            max_questions=1,
            case_bound=False,
            must_not_include=("technical_claims", "citations", "recommendations"),
        )

    if route_name == "unsupported_or_ambiguous":
        return CommunicationPlan(
            goal="recover_intent_without_guessing",
            response_moves=("acknowledge", "clarify", "recover"),
            depth="brief",
            answer_first=False,
            max_questions=1,
            case_bound=case_bound,
            next_question=(
                "Möchtest du eine Wissensfrage klären oder einen konkreten Dichtungsfall bearbeiten?"
            ),
            question_reason="So wähle ich den passenden fachlichen Pfad, ohne dein Anliegen zu erraten.",
            must_not_include=("invented_intent", "unrelated_technical_claims"),
        )

    if route_name in {
        "general_sealing_knowledge",
        "material_knowledge",
        "material_comparison",
    }:
        return CommunicationPlan(
            goal="answer_requested_knowledge",
            response_moves=("answer", "explain", "summarize"),
            depth="deep" if route_name == "material_comparison" else "normal",
            answer_first=True,
            max_questions=(
                1 if route_name == "material_comparison" or next_question else 0
            ),
            case_bound=case_bound,
            next_question=next_question,
            question_reason=reason,
            must_include=("direct_answer",),
            must_not_include=("unrequested_case_assumptions",),
        )

    if route_name == "engineering_case" and requests_replacement_identification(
        question
    ):
        return CommunicationPlan(
            goal="identify_replacement_seal",
            response_moves=("acknowledge", "answer", "clarify", "justify"),
            depth="brief",
            answer_first=True,
            max_questions=1,
            case_bound=True,
            next_question=(
                "Kannst du Innen- und Außendurchmesser sowie Breite nennen und ein Foto von "
                "beiden Seiten samt vorhandener Kennzeichnung bereitstellen?"
            ),
            question_reason=(
                "Damit lassen sich Grundabmessung, Lippenbauform, Feder und mögliche "
                "Drehrichtung zuerst belastbar eingrenzen."
            ),
            must_include=("identification_steps", "one_discriminating_question"),
            must_not_include=("premature_replacement_release", "failure_diagnosis_detour"),
        )

    if route_name == "leakage_troubleshooting":
        diagnostic_must_include = (
            "cause_before_replacement",
            "next_diagnostic_step",
        )
        if solution_requested:
            diagnostic_must_include += ("provisional_solution_direction",)
        if _NBR_ENVIRONMENTAL_CRACK_RE.search(question):
            next_question = (
                "Kommt die betroffene Außenfläche zusätzlich mit Öl oder Fett in Kontakt, "
                "und steht das Elastomer dort unter Dehnung?"
            )
            reason = (
                "Damit lässt sich der naheliegende Ozon-/Witterungsriss bestätigen und eine "
                "spätere Abhilfe zugleich gegen den realen Medienkontakt abgrenzen."
            )
        elif _NBR_THERMAL_AGING_RE.search(question):
            next_question = (
                "Welche maximale Temperatur tritt direkt an der Dichtlippe auf, und welches "
                "genaue Öl samt Basis und Additivpaket wird eingesetzt?"
            )
            reason = (
                "Damit lässt sich thermische Alterung von einem zusätzlichen Angriff durch "
                "Synthetiköl oder Additive unterscheiden."
            )
        elif _APPLICATION_CONTRAST_RE.search(question):
            next_question = (
                "Wie unterscheiden sich Rundlauf, Wellenauslenkung und Bewegungsprofil am "
                "Rührwerk gegenüber dem Getriebe?"
            )
            reason = (
                "Dieser Vergleich prüft direkt, ob die Anwendung den dynamischen Kontakt der "
                "Dichtlippe verliert, obwohl Bauform und Werkstoff gleich sind."
            )
            diagnostic_must_include = (
                "cause_before_replacement",
                "next_diagnostic_step",
                "application_contrast",
            )
            if solution_requested:
                diagnostic_must_include += ("provisional_solution_direction",)
        elif (
            solution_requested
            and _PROCESS_SEAL_STRESS_RE.search(question)
            and _ABRASIVE_OR_VISCOUS_RE.search(question)
        ):
            next_question = (
                "Welches konkrete Medium liegt an der Dichtstelle an, einschließlich "
                "Feststoffanteil und typischer Partikelgröße?"
            )
            reason = (
                "Damit lassen sich Abrasionsrisiko, Schmierfähigkeit und Phasenverhalten "
                "zuerst gegen den passenden Dichtungs- und Versorgungspfad prüfen."
            )
        elif not next_question:
            next_question = (
                "Trat die Leckage direkt nach Montage oder erst nach Betriebszeit auf, und "
                "welche Spur ist an Dichtlippe und Wellenlaufbahn sichtbar?"
            )
            reason = (
                "Das trennt Montagefehler von thermischer, schmierungsbedingter oder "
                "oberflächenbedingter Schädigung."
            )
        return CommunicationPlan(
            goal="diagnose_failure",
            response_moves=("answer", "explain", "clarify", "justify"),
            depth="normal" if solution_requested else "brief",
            answer_first=True,
            max_questions=1,
            case_bound=True,
            next_question=next_question,
            question_reason=reason,
            must_include=diagnostic_must_include,
            must_not_include=(
                "premature_material_recommendation",
                "unplanned_question_list",
            ),
        )

    if route_name == "engineering_case" and _DYNAMIC_TIGHTNESS_TARGET_RE.search(
        question
    ):
        return CommunicationPlan(
            goal="resolve_dynamic_sealing_tradeoff",
            response_moves=("answer", "compare", "clarify", "justify"),
            depth="brief",
            answer_first=True,
            max_questions=1,
            case_bound=True,
            next_question=(
                "Welche Priorität hat Vorrang – die kleinstmögliche zulässige Leckage, "
                "Lebensdauer und Effizienz oder geringe Wartung – und welche Leckagerate ist "
                "messbar noch akzeptabel?"
            ),
            question_reason=(
                "Erst diese Priorität macht den Zielkonflikt zwischen Dichtwirkung, "
                "Schmierfilm, Reibung und Verschleiß technisch entscheidbar."
            ),
            must_include=("explicit_tradeoff", "evidence_bound_candidate_space"),
            must_not_include=(
                "zero_leakage_promise",
                "unqualified_architecture_choice",
                "unplanned_question_list",
            ),
        )

    if route_name == "engineering_case" and _BARE_APPLICATION_REQUEST_RE.fullmatch(
        question
    ):
        return CommunicationPlan(
            goal="clarify_under_specified_case",
            response_moves=("acknowledge", "clarify", "justify"),
            depth="brief",
            answer_first=True,
            max_questions=1,
            case_bound=True,
            next_question=(
                "Geht es um eine rotierende Wellenabdichtung, eine statische Gehäusestelle "
                "oder eine andere Dichtstelle, und welches Medium liegt dort an?"
            ),
            question_reason=(
                "Diese beiden Angaben trennen zuerst das Dichtprinzip und den maßgeblichen "
                "Beständigkeitspfad, ohne den Fall mit einem Vollkatalog zu überfrachten."
            ),
            must_include=("bounded_case_clarification", "question_reason"),
            must_not_include=(
                "technical_claims",
                "recommendations",
                "unplanned_question_list",
            ),
        )

    if route_name == "engineering_case" and _MATERIAL_SELECTION_REQUEST_RE.search(
        question
    ):
        if _STEAM_CONTEXT_RE.search(question):
            next_question = (
                "Handelt es sich um gesättigten oder überhitzten Dampf, und welche maximale "
                "Temperatur sowie welcher maximale Druck treten auf?"
            )
            reason = (
                "Dampfzustand, Temperatur und Druck bestimmen gemeinsam das belastbare "
                "Compound- und Lebensdauerfenster."
            )
        elif not next_question:
            next_question = (
                "Welche genaue Medienzusammensetzung und welches Temperaturprofil liegen an der "
                "Dichtstelle vor?"
            )
            reason = (
                "Eine Werkstofffamilie ist erst mit Medium, Konzentration beziehungsweise "
                "Additivpaket und Temperaturprofil belastbar einzugrenzen."
            )
        return CommunicationPlan(
            goal="orient_material_selection",
            response_moves=("answer", "explain", "clarify", "justify"),
            depth="brief",
            answer_first=True,
            max_questions=1,
            case_bound=True,
            next_question=next_question,
            question_reason=reason,
            must_include=("provisional_orientation", "one_discriminating_question"),
            must_not_include=(
                "unbounded_candidate_list",
                "unplanned_question_list",
                "unqualified_release",
            ),
        )

    return CommunicationPlan(
        goal="advance_engineering_case",
        response_moves=("acknowledge", "answer", "explain", "clarify", "justify"),
        depth="normal",
        answer_first=True,
        max_questions=1,
        case_bound=True,
        next_question=next_question,
        question_reason=reason,
        must_include=("case_context_considered", "answer_before_question_when_safe"),
        must_not_include=(
            "repeat_known_case_facts_as_questions",
            "unplanned_question_list",
        ),
    )


def render_case_intake_response(question: str, plan: CommunicationPlan) -> str:
    """Render the no-claim intake response without a generative model."""

    lower = (question or "").casefold()
    if plan.case_bound:
        opening = "Gern – ich habe den bestehenden Fallkontext im Blick."
    elif "guten morgen" in lower:
        opening = "Guten Morgen – gern, wir entwickeln die Dichtungslösung Schritt für Schritt."
    elif re.search(r"\b(?:hallo|hi|hey|moin|servus)\b", lower):
        opening = (
            "Hallo – gern, wir entwickeln die Dichtungslösung Schritt für Schritt."
        )
    else:
        opening = "Gern, wir entwickeln die Dichtungslösung Schritt für Schritt."
    return f"{opening} {plan.next_question} {plan.question_reason}".strip()


def render_case_clarification(plan: CommunicationPlan) -> str:
    """Render one calm, justified next step for an already active case."""

    if plan.goal == "clarify_under_specified_case":
        return (
            "Gern – ich grenze den Fall mit dir in wenigen Schritten ein. "
            f"{plan.next_question} {plan.question_reason}"
        )

    if not plan.next_question:
        return (
            "Den bisherigen Fallkontext habe ich berücksichtigt. Welcher Punkt soll als Nächstes "
            "technisch geklärt werden?"
        )
    return (
        "Danke, den bisherigen Fallkontext habe ich berücksichtigt. "
        f"{plan.next_question} {plan.question_reason}"
    )


def evaluate_communication(
    text: str, plan: CommunicationPlan
) -> CommunicationGuardVerdict:
    """Check objective delivery constraints; never judge technical truth or tone sentiment."""

    violations: list[str] = []
    if not (text or "").strip():
        violations.append("empty_response")
    if (text or "").count("?") > plan.max_questions:
        violations.append("question_budget_exceeded")
    if plan.goal == "start_case_collaboratively":
        lowered = (text or "").casefold()
        if any(
            token in lowered for token in ("[quelle", "fachkarte", "**belege", "zitat")
        ):
            violations.append("intake_contains_evidence")
        if not plan.next_question or plan.next_question not in (text or ""):
            violations.append("planned_question_missing")
        if plan.question_reason and plan.question_reason not in (text or ""):
            violations.append("question_reason_missing")
    elif plan.goal == "orient_material_selection" and plan.next_question:
        if plan.next_question not in (text or ""):
            violations.append("planned_question_missing")
        if plan.question_reason and plan.question_reason not in (text or ""):
            violations.append("question_reason_missing")
    return CommunicationGuardVerdict(not violations, tuple(violations))


def _cap_question_marks(text: str, maximum: int) -> str:
    kept = 0
    result: list[str] = []
    for character in text:
        if character == "?":
            if kept < maximum:
                kept += 1
                result.append(character)
            else:
                result.append(".")
        else:
            result.append(character)
    return "".join(result)


def enforce_communication(text: str, plan: CommunicationPlan) -> str:
    """Deterministically enforce objective delivery constraints after model generation.

    This repair owns punctuation and the governed next question only; it never invents, removes or
    rewrites a technical claim.  Static intake is rendered from the plan if it somehow reaches this
    defensive boundary empty or malformed.
    """

    rendered = (text or "").strip()
    if plan.goal == "start_case_collaboratively":
        return render_case_intake_response("", plan)
    if not rendered:
        if plan.next_question:
            return render_case_clarification(plan)
        return (
            "Ich konnte die Antwort in diesem Durchlauf nicht verlässlich formulieren. "
            "Bitte formuliere dein Anliegen noch einmal kurz."
        )

    if plan.next_question:
        # The governed question must be the sole question and appear once, at the end.  Remove exact
        # copies first, neutralise every other question mark, then append the trusted plan wording.
        rendered = rendered.replace(plan.next_question, "").strip()
        if plan.question_reason:
            rendered = rendered.replace(plan.question_reason, "").strip()
        rendered = _cap_question_marks(rendered, 0).rstrip()
        separator = "\n\n" if rendered else ""
        return (
            f"{rendered}{separator}{plan.next_question} {plan.question_reason}".strip()
        )

    return _cap_question_marks(rendered, plan.max_questions)
