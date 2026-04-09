from __future__ import annotations

import re
from typing import TypedDict

from app.core.prompts import PromptLoader
from app.agent.runtime.outward_names import normalize_outward_response_class
from app.agent.state.models import TurnContextContract
from app.agent.runtime.surface_claims import SurfaceClaimsSpec

_PHASE_PROMPT_LOADER = PromptLoader()
PHASE_TEMPLATE_MAP: dict[str, str] = {
    "rapport": "phase_rapport",
    "exploration": "phase_exploration",
    "narrowing": "structured_clarification",
    "clarification": "structured_clarification",
    "recommendation": "final_answer_recommendation_v2.j2",
}


class GovernedAllowedSurfaceClaims(SurfaceClaimsSpec):
    pass


def _select_governed_render_mode(
    *,
    response_class: str,
    turn_context: TurnContextContract | None,
) -> str:
    response_class = normalize_outward_response_class(response_class)
    if response_class != "structured_clarification" or turn_context is None:
        return "standard_governed"

    facts = [str(item or "").strip() for item in turn_context.confirmed_facts_summary if str(item or "").strip()]
    has_medium = any(item.lower().startswith("medium:") for item in facts)
    has_motion = any(item.lower().startswith("bewegungsart:") for item in facts)
    technical_fact_count = sum(
        1
        for item in facts
        if any(
            marker in item.lower()
            for marker in ("medium:", "wellendurchmesser:", "drehzahl:", "betriebsdruck:", "betriebstemperatur:")
        )
    )

    if turn_context.response_mode == "single_question" and has_medium and (has_motion or technical_fact_count >= 2):
        return "engineering_explainer_clarification"
    return "single_question"


def build_conversation_phase_prompt(
    *,
    turn_context: TurnContextContract | None,
    latest_user_text: str,
    case_summary: str | None = None,
) -> str | None:
    if turn_context is None:
        return None

    prompt_name = PHASE_TEMPLATE_MAP.get(str(turn_context.conversation_phase or ""))
    if prompt_name not in {"phase_rapport", "phase_exploration"}:
        return None

    rendered = _PHASE_PROMPT_LOADER.get_rendered(
        prompt_name,
        primary_question=turn_context.primary_question,
        primary_question_reason=(
            turn_context.primary_question_reason
            or str(turn_context.supporting_reason or "").strip()
        ),
        latest_user_text=str(latest_user_text or "").strip(),
        case_summary=str(case_summary or "").strip(),
    )
    return rendered["content"]


def build_turn_context_instruction(turn_context: TurnContextContract | None) -> str | None:
    """Render compact communication context without prescribing wording."""
    return _build_turn_context_instruction(
        turn_context,
        include_phase_guidance=True,
        include_focus=True,
        include_reason=True,
    )


def _build_turn_context_instruction(
    turn_context: TurnContextContract | None,
    *,
    include_phase_guidance: bool,
    include_focus: bool,
    include_reason: bool,
) -> str | None:
    """Render compact communication context without prescribing wording."""
    if turn_context is None:
        return None

    lines = [
        "KOMMUNIKATIONSKONTEXT FUER DIESEN ZUG:",
        f"- Phase: {turn_context.conversation_phase}",
        f"- Turn-Ziel: {turn_context.turn_goal}",
        f"- Antwortmodus: {turn_context.response_mode}",
    ]
    if include_phase_guidance and turn_context.response_mode == "open_invitation":
        lines.append("- Der Nutzer befindet sich noch in einer offenen Orientierungsphase.")
    if include_phase_guidance and turn_context.conversation_phase == "rapport":
        lines.append("- Im Einstieg steht Orientierung im Vordergrund.")
    if include_phase_guidance and turn_context.conversation_phase == "exploration":
        lines.append("- Das Problembild wird noch eingeordnet.")
    if turn_context.user_signal_mirror:
        lines.append(f"- Nutzer-Signal: {turn_context.user_signal_mirror}")
    if include_focus and turn_context.primary_question:
        lines.append(f"- Relevanter offener Fokus: {turn_context.primary_question}")
    reason = str(turn_context.primary_question_reason or turn_context.supporting_reason or "").strip()
    if include_reason and reason:
        lines.append(f"- Fachlicher Grund fuer diesen Fokus: {reason}")
    if turn_context.confirmed_facts_summary:
        lines.append("- Bestaetigte Fakten: " + " | ".join(turn_context.confirmed_facts_summary))
    if turn_context.open_points_summary:
        lines.append("- Offene Punkte: " + " | ".join(turn_context.open_points_summary))
    return "\n".join(lines)


def build_reflection_prefix(
    turn_context: TurnContextContract | None,
    *,
    response_class: str = "conversational_answer",
) -> str | None:
    response_class = normalize_outward_response_class(response_class, default="conversational_answer")
    if turn_context is None:
        return None

    user_signal = str(turn_context.user_signal_mirror or "").strip()
    if user_signal:
        return user_signal.rstrip(".!?") + "."

    facts = [str(item or "").strip() for item in turn_context.confirmed_facts_summary if str(item or "").strip()]
    open_points = [str(item or "").strip() for item in turn_context.open_points_summary if str(item or "").strip()]
    facts_text = ", ".join(facts[:2])

    if facts_text:
        if response_class == "structured_clarification":
            return f"Damit ist schon klarer: {facts_text}."
        if response_class == "governed_state_update":
            if open_points:
                return f"Damit ist die Lage schon enger: {facts_text}."
            return f"Stand jetzt: {facts_text}."
        if response_class == "technical_preselection":
            if open_points:
                return f"Die technische Richtung ist jetzt belastbarer: {facts_text}."
            return f"Die technische Richtung ist jetzt enger: {facts_text}."
        if response_class == "candidate_shortlist":
            return f"Auf dieser Grundlage steht jetzt: {facts_text}."
        if response_class == "inquiry_ready":
            return f"Die Anfragebasis steht jetzt auf: {facts_text}."
        if turn_context.conversation_phase in {"recommendation", "matching", "rfq_handover", "review"}:
            return f"Bisher steht: {facts_text}."
        if turn_context.conversation_phase in {"narrowing", "clarification"}:
            return f"Damit wird klarer: {facts_text}."
        return f"Ich habe bisher {facts_text} verstanden."

    if open_points and turn_context.conversation_phase in {"narrowing", "clarification", "recommendation"}:
        if response_class == "technical_preselection":
            return f"Die Richtung steht, jetzt pruefe ich noch {open_points[0]}."
        return f"Der naechste Hebel liegt jetzt bei {open_points[0]}."

    return None


def compose_user_facing_mouth_reply(
    reply_text: str,
    turn_context: TurnContextContract | None,
    *,
    response_class: str = "conversational_answer",
) -> str:
    response_class = normalize_outward_response_class(response_class, default="conversational_answer")
    reply = str(reply_text or "").strip()
    if not reply:
        return reply

    if turn_context is not None and turn_context.primary_question:
        lowered_reply = reply.lower()
        if lowered_reply.startswith(("es fehlen", "bitte geben sie", "zur weiteren bearbeitung", "bitte ergänzen")):
            reply = str(turn_context.primary_question).strip()
        if turn_context.response_mode in {"open_invitation", "single_question"}:
            question_count = len(re.findall(r"\?", reply))
            if question_count > 1:
                first_question_end = reply.find("?")
                if first_question_end >= 0:
                    reply = reply[: first_question_end + 1].strip()

    reflection_prefix = build_reflection_prefix(
        turn_context,
        response_class=response_class,
    )
    if not reflection_prefix:
        return reply

    lowered_reply = reply.lower()
    lowered_prefix = reflection_prefix.lower().rstrip(".")
    if lowered_reply.startswith(lowered_prefix):
        return reply
    return f"{reflection_prefix} {reply}"


def build_governed_render_prompt(
    *,
    response_class: str,
    turn_context: TurnContextContract | None,
    fallback_text: str,
    allowed_surface_claims: GovernedAllowedSurfaceClaims | list[str] | None = None,
) -> str:
    """Render a compact controlled prompt for governed visible chat replies."""
    response_class = normalize_outward_response_class(response_class)
    render_mode = _select_governed_render_mode(
        response_class=response_class,
        turn_context=turn_context,
    )
    lines = [
        "Du renderst die sichtbare Chat-Antwort fuer den governed Pfad von SealAI.",
        "Die fachliche Authority ist bereits deterministisch festgelegt.",
        "Bleibe innerhalb der vorgegebenen Signale.",
        f"- Response-Class: {response_class}",
        f"- Render-Modus: {render_mode}",
        "- Behalte den fachlichen Gehalt des Fallback-Texts bei.",
        "- Erfinde keine neuen Fakten, Freigaben, Produkte, Normen oder Zusagen.",
        "- Veraendere weder Freigabegrad noch technischen Status.",
    ]
    strategy = _build_turn_context_instruction(
        turn_context,
        include_phase_guidance=False,
        include_focus=False,
        include_reason=False,
    )
    if strategy:
        lines.append("")
        lines.append(strategy)
    if turn_context is not None:
        focus_label = (
            turn_context.open_points_summary[0]
            if turn_context.open_points_summary
            else None
        )
        reason = str(turn_context.primary_question_reason or turn_context.supporting_reason or "").strip()
        lines.append("")
        lines.append("STATE-DRIVEN FOKUS:")
        if turn_context.turn_goal:
            lines.append(f"- Turn-Ziel: {turn_context.turn_goal}")
        if focus_label:
            lines.append(f"- Naechster Fokus: {focus_label}")
        if reason:
            lines.append(f"- Fachlicher Grund: {reason}")
    if render_mode == "engineering_explainer_clarification":
        lines.append("")
        lines.append("RENDER-ANWEISUNG FUER DIESEN MODUS:")
        lines.append("- Beginne mit 1 bis 2 kurzen Saetzen fachlicher Einordnung auf Basis des vorhandenen Kontexts.")
        lines.append("- Schreibe wie ein praktischer Ingenieur im Gespraech, nicht wie ein Fachartikel oder Datenblatt.")
        lines.append("- Halte die Einordnung konkret und direkt, zum Beispiel in der Art 'weil Salzwasser korrosiv wirkt' oder 'weil die Einbausituation kritisch wird'.")
        lines.append("- Vermeide abstrakte Formulierungen wie 'entscheidend, um ... zu bestimmen' oder 'Anforderungen an die Dichtungstechnik'.")
        lines.append("- Keine verschachtelten Saetze und keine unnoetigen Fuellwoerter.")
        lines.append("- Nutze danach 1 kurzen Satz, der die bekannten technischen Fakten knapp verbindet.")
        lines.append("- Schliesse mit genau 1 natuerlichen, state-driven Rueckfrage ab.")
        lines.append("- Keine Materialwahl, keine Freigabe, keine konkrete Loesung vorwegnehmen.")
    elif render_mode == "single_question":
        lines.append("")
        lines.append("RENDER-ANWEISUNG FUER DIESEN MODUS:")
        lines.append("- Halte die Antwort knapp und ruhig.")
        lines.append("- Stelle genau 1 natuerliche Rueckfrage ohne Formularstil.")
    if allowed_surface_claims:
        lines.append("")
        lines.append("ERLAUBTE SICHTBARE CLAIMS:")
        if isinstance(allowed_surface_claims, list):
            lines.extend(f"- {claim}" for claim in allowed_surface_claims if str(claim).strip())
        else:
            lines.append(f"- Fokus: {' | '.join(allowed_surface_claims['allowed_focus'])}")
            lines.append(f"- Guard: {allowed_surface_claims['class_guard']}")
            lines.append(
                "- Verbotene Formulierungen / Behauptungen: "
                + " | ".join(allowed_surface_claims["forbidden_fragments"])
            )
    lines.append("")
    lines.append("DETERMINISTISCHE FACHBASIS:")
    lines.append(fallback_text.strip())
    lines.append("")
    lines.append("Gib nur die finale sichtbare Antwort aus.")
    return "\n".join(lines)


def guard_governed_rendered_text(
    rendered_text: str,
    *,
    fallback_text: str,
    allowed_surface_claims: GovernedAllowedSurfaceClaims | list[str] | None = None,
) -> str:
    """Keep rendered governed text inside a deterministic allowed-claims corridor."""
    text = str(rendered_text or "").strip()
    if not text:
        return str(fallback_text or "").strip()
    if allowed_surface_claims is None or isinstance(allowed_surface_claims, list):
        return text
    fallback = str(allowed_surface_claims.get("fallback_text") or fallback_text or "").strip()
    if not fallback:
        fallback = text

    lowered = text.lower()
    for fragment in allowed_surface_claims["forbidden_fragments"]:
        if fragment.lower() in lowered:
            return fallback
    if _violates_one_question_rule(text, allowed_surface_claims["response_class"]):
        return fallback
    if _violates_no_final_certainty_rule(lowered):
        return fallback
    if _violates_no_unauthorized_rfq_rule(lowered, allowed_surface_claims["response_class"]):
        return fallback
    if _violates_class_guard(lowered, allowed_surface_claims["response_class"]):
        return fallback
    return text


_FINAL_CERTAINTY_FRAGMENTS = (
    "garantiert",
    "sicher geeignet",
    "final geeignet",
    "final freigegeben",
    "uneingeschraenkt geeignet",
    "uneingeschränkt geeignet",
)

_UNAUTHORIZED_RFQ_FRAGMENTS = (
    "rfq-ready",
    "rfq ready",
    "versandfaehig",
    "versandfähig",
    "bestellbereit",
    "anfragebasis",
    "bestellt",
    "beauftragt",
    "versendet",
)

_CLASS_GUARD_FRAGMENTS: dict[str, tuple[str, ...]] = {
    "conversational_answer": (
        "requirement class",
        "anforderungsklasse",
        "matched_primary_candidate",
        "herstellerkandidat",
        "passender hersteller",
    ),
    "structured_clarification": (
        "empfehle",
        "herstellerkandidat",
        "passender hersteller",
        "requirement class",
    ),
    "governed_state_update": (
        "ich empfehle",
        "wir empfehlen",
        "passender hersteller",
        "herstellerkandidat",
    ),
    "technical_preselection": (
        "bestellt",
        "beauftragt",
        "versendet",
    ),
    "candidate_shortlist": (
        "finaler hersteller",
        "verbindlich ausgewaehlt",
        "verbindlich ausgewählt",
        "lieferfaehig",
        "lieferfähig",
    ),
    "inquiry_ready": (
        "bestellt",
        "beauftragt",
        "automatisch versendet",
        "sofort versendet",
    ),
}


def _violates_one_question_rule(text: str, response_class: str) -> bool:
    response_class = normalize_outward_response_class(response_class)
    if response_class != "structured_clarification":
        return False
    question_count = len(re.findall(r"\?", text))
    return question_count > 1


def _violates_no_final_certainty_rule(lowered_text: str) -> bool:
    return any(fragment in lowered_text for fragment in _FINAL_CERTAINTY_FRAGMENTS)


def _violates_no_unauthorized_rfq_rule(lowered_text: str, response_class: str) -> bool:
    if normalize_outward_response_class(response_class) == "inquiry_ready":
        return False
    return any(fragment in lowered_text for fragment in _UNAUTHORIZED_RFQ_FRAGMENTS)


def _violates_class_guard(lowered_text: str, response_class: str) -> bool:
    response_class = normalize_outward_response_class(response_class, default="conversational_answer")
    return any(
        fragment in lowered_text
        for fragment in _CLASS_GUARD_FRAGMENTS.get(response_class, ())
    )


def compose_clarification_reply(
    turn_context: TurnContextContract | None,
    *,
    fallback_text: str,
) -> str:
    """Compose a deterministic clarification reply from the shared turn-context."""
    if turn_context is None:
        return fallback_text
    primary_question = str(turn_context.primary_question or "").strip()
    if not primary_question:
        return str(fallback_text or "").strip()
    return compose_user_facing_mouth_reply(
        primary_question,
        turn_context,
        response_class="structured_clarification",
    )


def compose_result_reply(
    turn_context: TurnContextContract | None,
    *,
    fallback_text: str,
    response_class: str = "governed_state_update",
    facts_prefix: str | None = None,
    open_points_prefix: str | None = None,
) -> str:
    """Compose a compact governed result reply from the shared turn-context."""
    if turn_context is None:
        return fallback_text

    parts = [fallback_text.strip()]
    if facts_prefix and turn_context.confirmed_facts_summary:
        parts.append(f"{facts_prefix}: " + " | ".join(turn_context.confirmed_facts_summary))
    if open_points_prefix and turn_context.open_points_summary:
        parts.append(f"{open_points_prefix}: " + " | ".join(turn_context.open_points_summary[:2]))
    reply = "\n".join(part for part in parts if part)
    return compose_user_facing_mouth_reply(
        reply,
        turn_context,
        response_class=response_class,
    )
