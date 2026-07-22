"""Deterministic conversation governance for one sealingAI turn.

The model may formulate an answer, but it does not decide the conversational contract.  This
module maps the governed route and case state to a bounded response plan: answer first when safe,
acknowledge the user's actual goal, ask at most one discriminating question, explain why it matters,
and never turn an intake turn into an evidence/recommendation answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


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
    "Dichtungstyp oder Dichtstelle": (
        "Welche Dichtungsart oder konkrete Dichtstelle gehört zu diesem Fall?",
        "Damit ordne ich den Fall dem passenden Auslegungs- und Fragenpfad zu.",
    ),
    "Nächster Auswertungsschritt": (
        "Welche technische Entscheidung soll ich auf Basis des erfassten Falls als Nächstes ausarbeiten?",
        "So nutze ich den vorhandenen Case gezielt, statt bereits geklärte Angaben erneut abzufragen.",
    ),
}


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
) -> CommunicationPlan:
    """Build the single, deterministic communication contract for this turn."""

    case_bound = bool(case_fields or missing_fields or conflicts)
    next_question, reason = _next_case_question(missing_fields, conflicts)

    if route_name == "case_intake_invite":
        return CommunicationPlan(
            goal="start_case_collaboratively",
            response_moves=("acknowledge", "empathize", "clarify", "justify"),
            depth="brief",
            answer_first=True,
            max_questions=1,
            case_bound=False,
            next_question="Welche Anwendung und Dichtstelle möchtest du abdichten?",
            question_reason=(
                "Davon hängt ab, welche Betriebs-, Geometrie- und Sicherheitsangaben ich als "
                "Nächstes gezielt von dir brauche."
            ),
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
            max_questions=1 if next_question else 0,
            case_bound=case_bound,
            next_question=next_question,
            question_reason=reason,
            must_include=("direct_answer",),
            must_not_include=("unrequested_case_assumptions",),
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
    if "guten morgen" in lower:
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
