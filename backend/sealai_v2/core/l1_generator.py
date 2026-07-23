"""L1 Generator — the trust-spine layer that covers the infinite answer space (build-spec §4).

Pure orchestration: assemble the system prompt (via an injected assembler), call the injected
LLM client, wrap the result. No I/O of its own — the client is the only I/O (``core`` stays
framework-/I/O-free, build-spec §3).
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace

from sealai_v2.core.contracts import (
    Answer,
    CalcResult,
    Flags,
    GroundingFact,
    LlmClient,
    LlmResult,
    ModelConfig,
    SystemPromptAssembler,
)
from sealai_v2.core.engineering_answer import (
    EngineeringAnswerValidationError,
    EngineeringClaim,
    EngineeringKnowledgeAnswer,
    validate_engineering_answer,
)
from sealai_v2.core.knowledge_answer import _fact_matches_subject
from sealai_v2.core.technical_answer import (
    TechnicalAnswer,
    TechnicalClaim,
    TechnicalAnswerValidationError,
    calibrate_technical_answer,
    validate_technical_answer,
)
from sealai_v2.core.sourcing_guard import strip_sourcing
from sealai_v2.llm.structured import StructuredOutputError, generate_structured
from sealai_v2.render.engineering_answer import render_engineering_answer
from sealai_v2.render.technical_answer import render_technical_answer


logger = logging.getLogger(__name__)

_UNCLEAR_MEDIUM_RE = re.compile(
    r"\b(?:synthetische[snmr]?\s+[öo]l|unspezifiziert\w*|unbekannt\w*|unklar\w*|"
    r"exotisch\w*|genaue\s+(?:sorte|zusammensetzung)\s+(?:ist\s+)?"
    r"(?:nicht\s+bekannt|unbekannt)|(?:keine?|ohne)\s+(?:gepr[uü]fte\w*\s+)?"
    r"vertr[aä]glichkeits(?:angabe|daten|nachweis)\w*)\b",
    re.IGNORECASE,
)
_MATERIAL_SELECTION_RE = re.compile(
    r"\b(?:dichtungswerkstoff|werkstoff|material|elastomer|compound)\b[^?!.]{0,80}"
    r"\b(?:passt|geeign(?:et|ung)|wählen|waehlen)\b|"
    r"\bwelche(?:r|s)?\s+(?:dichtungswerkstoff|werkstoff|material|elastomer|compound)\b",
    re.IGNORECASE,
)
_QUANTITATIVE_DETAIL_RE = re.compile(
    r"\b(?:kennwerte?|zahlen?|werte?|temperaturbereich|druckgrenze|"
    r"geschwindigkeitsgrenze|einsatzgrenze|wie\s+hoch|wie\s+viel|"
    r"konkrete[rs]?\s+(?:wert|bereich|grenze))\b",
    re.IGNORECASE,
)
_COMPOUND_IDENTIFIER_REQUEST_RE = re.compile(
    r"\bcompound(?:[-\s]?(?:nummer|code|grade))\w*\b|"
    r"\b(?:nummer|code|grade)\b[^?!.]{0,60}\bcompound\w*\b",
    re.IGNORECASE,
)
_VENDOR_OR_ORDER_CONTEXT_RE = re.compile(
    r"\b(?:hersteller|anbieter|lieferant|händler|haendler|portfolio|produktlinie|"
    r"bestellen|kaufen)\w*\b",
    re.IGNORECASE,
)
_VERIFIED_VENDOR_EVIDENCE_RE = re.compile(
    r"(?:manufacturer|hersteller)", re.IGNORECASE
)


def _requires_material_abstention(question: str) -> bool:
    return bool(
        _UNCLEAR_MEDIUM_RE.search(question or "")
        and _MATERIAL_SELECTION_RE.search(question or "")
    )


def _requests_quantitative_detail(question: str) -> bool:
    """A broad "details" request asks for depth, not an unsolicited catalogue of limit values."""

    return bool(_QUANTITATIVE_DETAIL_RE.search(question or ""))


def _vendor_compound_boundary_answer(
    question: str, grounding_facts: tuple[GroundingFact, ...]
) -> str | None:
    """State the manufacturer-data boundary and still leave the user with a usable next step."""

    if not (
        _COMPOUND_IDENTIFIER_REQUEST_RE.search(question or "")
        and _VENDOR_OR_ORDER_CONTEXT_RE.search(question or "")
    ):
        return None
    if any(
        fact.sources
        and (
            fact.subject_type == "manufacturer"
            or _VERIFIED_VENDOR_EVIDENCE_RE.search(fact.card_id or "")
        )
        for fact in grounding_facts
    ):
        return None
    return (
        "Eine genaue herstellerspezifische Compound-Nummer nenne ich dir hier nicht: Ohne "
        "kuratierte Herstellerdaten und die vollständige Anwendungsspezifikation wäre sie weder "
        "neutral noch verlässlich, sondern geraten.\n\n"
        "Ich kann dir stattdessen ein neutrales Matching-Briefing erstellen. Darin halten wir "
        "Werkstofffamilie und geforderte Härte, exaktes Medium einschließlich Konzentration und "
        "Additiven, Temperaturprofil, Druck, statische oder dynamische Bewegung, Dichtungsbauform "
        "und erforderliche Zulassungen fest. Mit diesem Briefing kann der Hersteller oder Händler "
        "die passende interne Compound-Nummer zuordnen und mit Datenblatt sowie Freigabe bestätigen.\n\n"
        "Nenne mir dafür zuerst Anwendung, Medium und Temperaturprofil; dann formuliere ich das "
        "Briefing so, dass du es direkt für das Hersteller-Matching verwenden kannst."
    )


def _engineering_conclusion(plan: dict, *, question: str = "") -> str:
    if _requires_material_abstention(question):
        return (
            "Ohne geprüfte Verträglichkeitsdaten für das konkrete Medium lässt sich noch kein "
            "Dichtungswerkstoff seriös auswählen. Zuerst werden Stoffidentität und Betriebsfenster "
            "geklärt; anschließend wird ein konkreter Compound datenblatt- und testgestützt "
            "qualifiziert."
        )
    subjects = tuple(
        str(subject) for subject in plan.get("subjects", ()) if str(subject)
    )
    profile = str(plan.get("profile") or "engineering_knowledge")
    if plan.get("comparison") and len(subjects) >= 2:
        return (
            f"{subjects[0]} und {subjects[1]} sind entlang identischer Prüf- und Betriebsbedingungen "
            "zu vergleichen; ein einzelner Kennwert ergibt noch keine belastbare Werkstoffentscheidung."
        )
    subject = subjects[0] if subjects else "Der technische Gegenstand"
    if profile.startswith("material_"):
        return (
            f"Bei {subject} sind Werkstofffamilie, konkreter Compound, Prüfwert und "
            "anwendungsbezogene Einsatzgrenze strikt zu trennen."
        )
    if profile.startswith("seal_"):
        return (
            f"Die technische Funktion von {subject} ergibt sich aus Dichtprinzip, Bauform, "
            "Werkstoff, Gegenpartner und Betriebsbedingungen."
        )
    if profile.startswith("medium_"):
        return (
            f"Die Wirkung von {subject} auf ein Dichtsystem hängt von Zusammensetzung, "
            "Konzentration, Temperatur, Dauer und konkretem Compound ab."
        )
    return "Die technische Einordnung folgt den geprüften Quellen und den benannten Randbedingungen."


def _engineering_missing_information(plan: dict) -> list[str]:
    if plan.get("comparison"):
        return [
            "Für eine Auswahlentscheidung: konkrete Compounds beziehungsweise Grades, Medium mit "
            "Additiven, Temperaturprofil, Druck, Bewegungsart, Geschwindigkeit, Bauform und Nachweisbasis."
        ]
    profile = str(plan.get("profile") or "")
    if profile.startswith("material_"):
        return [
            "Für eine anwendungsbezogene Auswahl: konkreter Compound beziehungsweise Grade, "
            "Dichtungsbauform, Medium einschließlich Additiven, Temperaturprofil, Druck, "
            "Bewegungsart, Gegenpartner und geforderter Nachweis."
        ]
    if profile.startswith("seal_type_"):
        return [
            "Für eine konkrete Auslegung: Baugröße und Einbauraum, Werkstoffpaarung, Medium, "
            "Temperaturprofil, Druck, Bewegung beziehungsweise Geschwindigkeit, Gegenflächen, "
            "Lastkollektiv, zulässige Leckage und Qualifikationsnachweis."
        ]
    if profile.startswith("medium_"):
        return [
            "Für eine Verträglichkeitsbewertung: exakte Produktbezeichnung und Zusammensetzung, "
            "Konzentration, Additive und Verunreinigungen, Temperatur-Dauer-Profil, Druck, "
            "Dichtungswerkstoff und anwendungsnaher Prüfplan."
        ]
    return []


def _fact_subjects(fact: GroundingFact, subjects: tuple[str, ...]) -> frozenset[str]:
    """Bind evidence only when its stable identity or reviewed text names the subject.

    Broad scope tags may mention alternatives, so they are unsuitable as primary-subject ownership.
    Card IDs are preferred, while the same boundary-aware alias matcher used by the knowledge planner
    also supports reviewed claim text.  Retrieval rank alone never makes an unrelated fact evidence
    for a single-subject answer.
    """
    card_tokens = {
        re.sub(r"[^a-z0-9]+", "", token.casefold())
        for token in re.split(r"[-_:/.]+", fact.card_id)
        if token
    }
    matched = {
        subject
        for subject in subjects
        if re.sub(r"[^a-z0-9]+", "", subject.casefold()) in card_tokens
    }
    if matched:
        return frozenset(matched)
    return frozenset(
        subject for subject in subjects if _fact_matches_subject(fact, subject)
    )


def _fallback_engineering_answer(
    *,
    plan: dict,
    evidence_facts: dict[str, GroundingFact],
    evidence_subjects: dict[str, frozenset[str]],
    case_revision: int,
    question: str = "",
) -> EngineeringKnowledgeAnswer:
    """Fail closed to exact reviewed statements, preserving subject and facet identity."""
    claims: list[EngineeringClaim] = []
    planned_subjects = tuple(plan.get("subjects", ()))
    subjects = planned_subjects or ("Dichtungstechnik",)
    evidence_metadata = {
        evidence_id: (
            fact,
            tuple(fact.answer_facets) or ("properties",),
            (
                evidence_subjects.get(evidence_id, frozenset())
                if planned_subjects
                else frozenset(subjects)
            ),
        )
        for evidence_id, fact in evidence_facts.items()
    }
    used: set[tuple[str, str]] = set()

    # First fill every render cell from one exact reviewed statement. This keeps the fallback useful
    # and symmetric even when the provider returns invalid JSON or incomplete coverage.
    for subject in subjects:
        for section in plan.get("sections", ()):
            section_facets = tuple(section.get("facets", ()))
            candidates = [
                (evidence_id, fact, facets)
                for evidence_id, (
                    fact,
                    facets,
                    bound_subjects,
                ) in evidence_metadata.items()
                if subject in bound_subjects
                and any(facet in facets for facet in section_facets)
            ]
            # A missing facet is safer and more truthful than duplicating the same reviewed claim
            # under a second heading.  The previous ``candidates[0]`` fallback produced apparently
            # different sections with byte-identical content after a validation failure.
            selected = next(
                (
                    candidate
                    for candidate in candidates
                    if (subject, candidate[0]) not in used
                ),
                None,
            )
            if selected is None:
                continue
            evidence_id, fact, facets = selected
            facet = next(facet for facet in section_facets if facet in facets)
            claims.append(
                EngineeringClaim(
                    subject=subject,
                    facet=facet,
                    statement=fact.text,
                    evidence_ids=[evidence_id],
                    criticality=(
                        "limit" if facet in {"limits", "failure_modes"} else "context"
                    ),
                )
            )
            used.add((subject, evidence_id))

    # Then retain additional reviewed facts while respecting the bounded chat contract.
    for evidence_id, (fact, facets, bound_subjects) in evidence_metadata.items():
        for subject in sorted(bound_subjects):
            if len(claims) >= 20 or (subject, evidence_id) in used:
                continue
            claims.append(
                EngineeringClaim(
                    subject=subject,
                    facet=facets[0],
                    statement=fact.text,
                    evidence_ids=[evidence_id],
                    criticality=(
                        "limit"
                        if "limits" in facets or "failure_modes" in facets
                        else "context"
                    ),
                )
            )
        if len(claims) >= 20:
            break
    return EngineeringKnowledgeAnswer(
        schema_version=2,
        profile=str(plan.get("profile") or "engineering_knowledge"),
        case_revision=case_revision,
        conclusion=_engineering_conclusion(plan, question=question),
        claims=claims,
        assumptions=[],
        missing_information=_engineering_missing_information(plan),
    )


def _knowledge_evidence_context(
    grounding_facts: tuple[GroundingFact, ...],
) -> tuple[tuple[GroundingFact, ...], dict[str, GroundingFact]]:
    """Give the model compact local aliases while retaining canonical evidence internally."""
    canonical_aliases: dict[str, str] = {}
    prompt_facts: list[GroundingFact] = []
    evidence_facts: dict[str, GroundingFact] = {}
    for fact in grounding_facts:
        canonical_id = fact.claim_id or fact.card_id
        if not canonical_id:
            prompt_facts.append(fact)
            continue
        alias = canonical_aliases.setdefault(
            canonical_id, f"E{len(canonical_aliases) + 1}"
        )
        evidence_facts[alias] = fact
        prompt_facts.append(replace(fact, claim_id=alias))
    return tuple(prompt_facts), evidence_facts


def _deterministic_knowledge_answer(
    *,
    knowledge_answer_plan: dict,
    evidence_facts: dict[str, GroundingFact],
    case_revision: int,
) -> TechnicalAnswer:
    """Fail closed to reviewed claim text when provider output violates the contract."""
    profile = str(knowledge_answer_plan.get("profile") or "engineering_knowledge")
    return TechnicalAnswer(
        schema_version=1,
        intent=profile,
        case_revision=case_revision,
        conclusion="Technische Übersicht auf Basis der geprüften Fachquellen.",
        assumptions=[],
        missing_information=[],
        claims=[
            TechnicalClaim(
                text=fact.text,
                evidence_ids=[evidence_id],
                criticality="supporting",
            )
            for evidence_id, fact in list(evidence_facts.items())[:8]
        ],
        recommendation={"summary": "", "status": "none", "conditions": []},
        needs_human_review=False,
    )


def _deterministic_archetype_answer(
    *,
    question: str,
    archetype_context: dict,
    evidence_facts: dict[str, GroundingFact],
    case_revision: int,
) -> TechnicalAnswer | None:
    """Render an exact reviewed machine profile without gambling on model claim selection."""

    key = str(archetype_context.get("archetyp") or "").strip().casefold()
    card_id = f"ARCHETYPE-{key.upper()}"
    profile_facts = [
        (evidence_id, fact)
        for evidence_id, fact in evidence_facts.items()
        if fact.card_id == card_id
    ]
    if not key or not profile_facts:
        return None
    profile_facts.sort(key=lambda item: item[0])
    normalized = (question or "").casefold()
    if key == "getriebe":
        conclusion = (
            "Beim Getriebe sind hier drei gekoppelte Punkte entscheidend: die "
            "Umfangsgeschwindigkeit, die Beständigkeit gegen das konkrete Öl samt Additiven und "
            "Temperatur sowie eine ausreichend harte und drallfreie Wellenoberfläche. Erst danach "
            "ist eine Werkstoff- oder Bauformfreigabe belastbar."
        )
    elif key == "ruehrwerk":
        is_application_contrast = bool(
            re.search(r"\br[uü]hrwerk\w*\b", normalized)
            and re.search(r"\bgetriebe\w*\b", normalized)
        )
        has_reactor_duty = bool(
            re.search(r"\b(?:reaktor|vakuum|unterdruck|druck|aggressiv\w*)\b", normalized)
        )
        if is_application_contrast and has_reactor_duty:
            conclusion = (
                "Die gleiche RWDR-Bauform ist im Rührwerk nicht automatisch so einsetzbar wie im "
                "Getriebe. Wellenauslenkung beziehungsweise Taumeln können den dynamischen "
                "Lippenkontakt verlieren lassen; im Vakuum-Reaktor kommen das direkt anliegende "
                "Prozessmedium und das Druck-/Vakuum-Regime hinzu. Deshalb ist hier eine "
                "Gleitringdichtung als Bauform-Kandidat zu prüfen, bevor nur der Werkstoff "
                "gewechselt wird."
            )
        elif is_application_contrast:
            conclusion = (
                "Die gleiche RWDR-Bauform ist nicht automatisch in beiden Anwendungen gleich "
                "einsetzbar. Beim Rührwerk können Wellenauslenkung beziehungsweise Taumeln den "
                "dynamischen Lippenkontakt verlieren lassen; zusätzlich wirken Prozessmedium und "
                "möglicher Trockenlauf anders als im ölgeschmierten Getriebe. Deshalb sind zuerst "
                "Rundlauf und Wellenführung konstruktiv zu prüfen; wenn diese Belastung nicht "
                "beherrscht wird, ist eine passend ausgelegte Gleitringdichtung als "
                "Bauform-Kandidat zu bewerten, statt reflexhaft nur den Werkstoff zu wechseln."
            )
        elif has_reactor_duty:
            conclusion = (
                "Beim Rührwerk im Reaktor stehen Medienverträglichkeit und Bauform vor einer "
                "Werkstofffestlegung. Das Prozessmedium liegt direkt an, und Druck beziehungsweise "
                "Vakuum sowie möglicher Trockenlauf müssen gemeinsam bewertet werden; für diesen "
                "anspruchsvolleren Betrieb ist eine Gleitringdichtung ein zu prüfender "
                "Bauform-Kandidat, keine pauschale Freigabe."
            )
        else:
            conclusion = (
                "Für das Rührwerk wäre eine sofortige Werkstofffestlegung noch zu früh: Zuerst "
                "zählen das direkt anliegende Prozessmedium, möglicher Trockenlauf beim Anfahren "
                "und Wellenauslenkung beziehungsweise Taumeln. Diese Punkte entscheiden mit, ob "
                "ein klassischer RWDR überhaupt die passende Bauform ist."
            )

        # A reviewed profile contains several independent application dimensions.  Select the ones
        # that answer this turn instead of blindly taking catalog order (which previously injected
        # an unrelated CIP/food sentence into a vacuum-reactor question and triggered a false L3
        # food-grade block).  The facts remain exact owner-reviewed text; only selection changes.
        priority_terms = (
            ("vakuum", "gleitringdichtung", "wellenauslenkung", "prozessmedium")
            if is_application_contrast and has_reactor_duty
            else (
                ("wellenauslenkung", "prozessmedium", "trockenlauf", "gleitringdichtung")
                if is_application_contrast
                else (
                    ("vakuum", "gleitringdichtung", "prozessmedium", "trockenlauf")
                    if has_reactor_duty
                    else ("prozessmedium", "trockenlauf", "wellenauslenkung")
                )
            )
        )
        selected: list[tuple[str, GroundingFact]] = []
        for term in priority_terms:
            for item in profile_facts:
                if item in selected or term not in item[1].text.casefold():
                    continue
                selected.append(item)
                break
        if selected:
            profile_facts = selected
    else:
        conclusion = (
            f"Für den Anwendungstyp {key} werden zuerst die geprüften anwendungsspezifischen "
            "Belastungen und blinden Flecken geklärt; eine konkrete Werkstoff- oder "
            "Bauformfreigabe folgt erst danach."
        )
    return TechnicalAnswer(
        schema_version=1,
        intent="reviewed_archetype_orientation",
        case_revision=case_revision,
        conclusion=conclusion,
        assumptions=[],
        missing_information=[],
        claims=[
            TechnicalClaim(
                text=fact.text,
                evidence_ids=[evidence_id],
                criticality="supporting",
            )
            for evidence_id, fact in profile_facts[:4]
        ],
        recommendation={"summary": "", "status": "none", "conditions": []},
        needs_human_review=True,
    )


def _render_compact_reviewed_archetype(
    answer: TechnicalAnswer, communication_plan: dict | None
) -> str:
    """Render first-turn archetype guidance as a conversation, not a mini specification."""

    paragraphs = [answer.conclusion.strip()]
    claims = [claim.text.strip().rstrip(".") for claim in answer.claims if claim.text.strip()]
    if claims:
        paragraphs.append(
            "Zur Eingrenzung prüfe diese Punkte zusammen: "
            + "; ".join(claims)
            + ". (quellengebunden)"
        )
    if answer.needs_human_review:
        paragraphs.append(
            "Die konkrete Ausführung und Freigabe muss anschließend der Hersteller oder die "
            "zuständige Fachstelle bestätigen."
        )
    plan = communication_plan or {}
    planned_question = str(plan.get("next_question") or "").strip()
    if planned_question:
        reason = str(plan.get("question_reason") or "").strip()
        paragraphs.append(
            "Als nächsten Schritt: "
            + planned_question
            + (f" {reason}" if reason else "")
        )
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def _deterministic_evidence_answer(
    *,
    question: str,
    evidence_facts: dict[str, GroundingFact],
    case_revision: int,
    calc: CalcResult | None = None,
    work_solution_candidate: bool = False,
    communication_plan: dict | None = None,
) -> TechnicalAnswer:
    """Senior-shaped fallback that only restates evidence and deterministic kernel output."""
    normalized = (question or "").casefold()
    rwdr_context = any(
        alias in normalized
        for alias in (
            "rwdr",
            "radialwellendichtring",
            "radial-wellendichtring",
            "simmerring",
            "wellendichtring",
        )
    ) or any(
        fact.card_id == "FK-RWDR-ENGINEERING-PROFILE"
        for fact in evidence_facts.values()
    )
    if rwdr_context:
        missing = [
            "Druckdifferenz einschließlich Druckspitzen und Druckrichtung.",
            "Exakte Ölbezeichnung, Additivpaket sowie minimale, maximale und an der Dichtkante erwartete Temperatur.",
            "Wellenhärte, Rauheit und Drallfreiheit sowie Rundlauf und Exzentrizität am Dichtsitz.",
            "Einbauraum, Gehäusebohrung, Montageweg und verfügbare Schutz- beziehungsweise Staublippenbauform.",
            "Geforderte Lebensdauer, zulässige Leckage und Art, Größe sowie Menge des Schmutzeintrags.",
        ]
        conclusion = (
            "Die vorliegenden Daten erlauben eine technische Vorprüfung, aber noch keine belastbare "
            "Bauform- oder Werkstofffreigabe. Druck, Schmierfilm, Gegenlauffläche, Schmutzschutz und "
            "die gekoppelte Druck-Geschwindigkeits-Temperatur-Belastung sind gemeinsam zu prüfen."
        )
    else:
        missing = [
            "Konkrete Bauform und Werkstoffausführung sowie alle relevanten Gegenpartner.",
            "Medium einschließlich Additiven und Verunreinigungen, Temperatur-Dauer-Profil und Druckkollektiv.",
            "Bewegungsart, Geschwindigkeit, Lastwechsel, Einbauschnittstellen und geforderte Lebensdauer.",
            "Zulässige Leckage, Sicherheits- und Zulassungsanforderungen sowie anwendungsbezogener Nachweisplan.",
        ]
        conclusion = (
            "Belastbar festhalten lässt sich auf Basis der geprüften Fachquellen:"
        )

    selected_evidence = list(evidence_facts.items())
    query_terms = {
        term
        for term in re.findall(r"[a-zäöüß][a-zäöüß-]{3,}", normalized)
        if term
        not in {
            "welche",
            "welcher",
            "wäre",
            "waere",
            "sinnvoll",
            "ansatz",
            "lösung",
            "loesung",
            "bitte",
            "kannst",
        }
    }
    facet_priority = {
        "failure_modes": 10,
        "variants": 9,
        "design_interfaces": 8,
        "selection_inputs": 7,
        "tradeoffs": 6,
        "applications": 5,
        "operating_factors": 4,
        "mechanism": 3,
        "media_compatibility": 2,
        "limits": 1,
    }

    def lexical_overlap(item: tuple[str, GroundingFact]) -> int:
        _evidence_id, fact = item
        fact_terms = set(re.findall(r"[a-zäöüß][a-zäöüß-]{3,}", fact.text.casefold()))
        return len(query_terms & fact_terms)

    def relevance(item: tuple[str, GroundingFact]) -> tuple[int, int, int, str]:
        evidence_id, fact = item
        facet_score = max(
            (facet_priority.get(facet, 0) for facet in fact.answer_facets),
            default=0,
        )
        # A sourced, owner-reviewed policy fact is already high-precision matched by the trap
        # retriever.  It must outrank a broad profile card in the fail-closed path; otherwise a
        # perfectly relevant policy fact is present but the user still receives the first generic
        # paragraphs of a seal handbook.
        return (
            -int(fact.kind == "trap"),
            -lexical_overlap(item),
            -facet_score,
            evidence_id,
        )

    selected_evidence.sort(key=relevance)
    policy_evidence = [item for item in selected_evidence if item[1].kind == "trap"]
    policy_ids: set[str] = set()
    if policy_evidence:
        selected_evidence = policy_evidence[:2]
        missing = []
        policy_ids = {fact.card_id for _evidence_id, fact in policy_evidence}
        if "SAFETY-RGD-HD-GAS" in policy_ids:
            hydrogen_stated = bool(re.search(r"\b(?:wasserstoff|h2|h₂)\b", normalized))
            high_pressure_stated = bool(
                "hochdruck" in normalized
                or re.search(r"\b\d+(?:[.,]\d+)?\s*bar\b", normalized)
            )
            if hydrogen_stated and high_pressure_stated:
                case_label = "Hochdruck-Wasserstofffall"
            elif hydrogen_stated:
                case_label = "Wasserstoff-Gasdichtungsfall"
            elif high_pressure_stated:
                case_label = "Hochdruck-Gasdichtungsfall"
            else:
                case_label = "Gasdichtungsfall"
            conclusion = (
                f"Das ist ein sicherheitskritischer {case_label}. Eine konkrete "
                "Auswahl oder Freigabe wäre mit den vorliegenden Angaben nicht verantwortbar."
            )
        elif "CALC-UMFANGSGESCHWINDIGKEIT" in policy_ids:
            conclusion = (
                "Die Umfangsgeschwindigkeit ist hier eine Pflichtberechnung; ohne den "
                "deterministischen Befund gibt es keine Werkstoff- oder Bauformfreigabe."
            )
        elif "TRAP-FKM-DAMPF" in policy_ids:
            conclusion = (
                "Für Wasserdampf ist peroxidvernetztes EPDM der belastbare erste "
                "Kandidatenraum; Standard-FKM ist trotz seiner Temperaturfestigkeit in "
                "anderen Medien kein sicherer Dampf-Default."
            )
            if re.search(r"\b(?:pharma|bioreaktor|produktkontakt)\b", normalized):
                pharma_evidence = [
                    item
                    for item in evidence_facts.items()
                    if item[1].card_id == "FK-PHARMA-SIP-VALIDIERUNG"
                ]
                if pharma_evidence:
                    selected_evidence = policy_evidence[:1] + pharma_evidence[:2]
                    conclusion += (
                        " Im Pharma-Produktkontakt gehören die konkrete "
                        "Qualifikations-/Zulassungsdokumentation, hygienische Ausführung sowie "
                        "Extractables/Leachables zur Systemvalidierung."
                    )
        elif "POLICY-TRINKWASSER-FAMILIE-ZULASSUNG" in policy_ids:
            conclusion = (
                "Bei Trinkwasser entscheidet nicht die maximal breite Werkstofffamilie, "
                "sondern die konkrete technische Eignung samt gültigem Trinkwassernachweis."
            )
        elif "POLICY-SYNTHETIKOEL-KLASSE-OFFEN" in policy_ids:
            conclusion = (
                "Die Werkstoffwahl bleibt bei der noch unklaren Synthetiköl-Klasse "
                "ausdrücklich offen und muss anhand von Ölbasis, Additivpaket und "
                "konkreter Werkstoffausführung produktbezogen verifiziert werden."
            )
        else:
            conclusion = "Der entscheidende fachliche Punkt ist:"

    oring_compression_evidence = [
        item
        for item in evidence_facts.items()
        if item[1].card_id == "FK-ORING-VERPRESSUNG"
    ]
    if (
        not policy_evidence
        and oring_compression_evidence
        and re.search(r"\bo[- ]?ring\w*\b", normalized)
        and re.search(r"\b(?:verpress\w*|squeeze)\b", normalized)
    ):
        selected_evidence = oring_compression_evidence[:4]
        missing = []
        conclusion = (
            "Für einen statischen O-Ring ist nicht nur die Verpressung maßgebend: Der Nutfüllgrad "
            "muss zugleich Reserve für Toleranzen, Wärmedehnung und medienbedingte Quellung lassen."
        )
    if work_solution_candidate:
        profile_items = [
            item
            for item in selected_evidence
            if item[1].card_id
            in {
                "FK-RWDR-ENGINEERING-PROFILE",
                "FK-GLRD-ENGINEERING-PROFILE",
            }
            or item[1].card_id.startswith("ARCHETYPE-")
            or item[1].kind in {"matrix", "trap"}
        ]
        if profile_items:
            selected_evidence = profile_items
        selected_evidence.sort(key=relevance)
        selected_evidence = selected_evidence[:4]
        if not policy_evidence:
            conclusion = (
                "Auf Basis der geprüften Fachquellen lässt sich der Lösungsraum technisch "
                "eingrenzen; entscheidend sind:"
            )

    if (communication_plan or {}).get("goal") == "resolve_dynamic_sealing_tradeoff":
        tradeoff_terms = {
            "schmierfilm": 8,
            "reibung": 7,
            "wärme": 6,
            "verschleiß": 6,
            "leckage": 5,
            "anpress": 5,
            "gleitringdichtung": 4,
            "rwdr": 3,
            "niederdruck": 3,
        }

        def tradeoff_score(item: tuple[str, GroundingFact]) -> tuple[int, int, str]:
            evidence_id, fact = item
            fact_text = fact.text.casefold()
            score = sum(
                weight for term, weight in tradeoff_terms.items() if term in fact_text
            )
            return (-score, -lexical_overlap(item), evidence_id)

        tradeoff_evidence = [
            item
            for item in evidence_facts.items()
            if item[1].claim_kind != "example_value"
            and (
                item[1].card_id
                in {"FK-RWDR-ENGINEERING-PROFILE", "FK-GLRD-ENGINEERING-PROFILE"}
                or {"tradeoffs", "mechanism", "operating_factors"}.intersection(
                    item[1].answer_facets
                )
            )
            and any(term in item[1].text.casefold() for term in tradeoff_terms)
        ]
        if tradeoff_evidence:
            tradeoff_evidence.sort(key=tradeoff_score)
            selected_evidence = tradeoff_evidence[:2]
        missing = []
        conclusion = (
            "‚Null Leckage‘ ist bei einer dynamischen Berührungsdichtung physikalisch kaum "
            "erreichbar, weil ein dünner Schmierfilm für die Funktion gewollt ist. Maximale "
            "Dichtheit beziehungsweise höhere Anpressung erhöht Reibung, Wärme und Verschleiß "
            "und kann Wirkungsgrad und Lebensdauer senken. Das ist kein einzelnes Optimum, "
            "sondern ein offenzulegender Zielkonflikt, der nach zulässiger Leckage, Lebensdauer, "
            "Effizienz und Wartungsaufwand priorisiert werden muss."
        )

    if (communication_plan or {}).get(
        "goal"
    ) == "diagnose_failure" and not policy_evidence:
        nbr_thermal_aging = bool(
            re.search(r"\bnbr\b", normalized)
            and re.search(
                r"\b(?:hart|verh[aä]rt\w*|verspr[oö]d\w*|riss\w*)\b",
                normalized,
            )
            and not re.search(
                r"\b(?:au[sß]en|freien|freiland|ozon|uv|witter\w*|wetter|sonne)\b",
                normalized,
            )
        )
        diagnostic_facets = {
            "failure_modes",
            "mechanism",
            "design_interfaces",
            "operating_factors",
        }
        diagnostic_evidence = [
            item
            for item in selected_evidence
            if item[1].claim_kind != "example_value"
            and diagnostic_facets.intersection(item[1].answer_facets)
        ]
        nbr_thermal_evidence = [
            item
            for item in evidence_facts.items()
            if item[1].card_id == "FK-NBR-DAUERTEMP"
            and {"failure_modes", "limits", "media_compatibility"}.intersection(
                item[1].answer_facets
            )
        ]
        if nbr_thermal_aging and nbr_thermal_evidence:
            # The reviewed temperature claim contains catalogue example values.  They are useful
            # evidence for the causal direction but the user asked for a diagnosis, not a numerical
            # limit.  Prefer the reviewed fix and conditional media claim in the visible answer;
            # this avoids turning an application-specific diagnosis into a falsely universal
            # temperature threshold.
            non_numeric_nbr_evidence = [
                item
                for item in evidence_facts.items()
                if item[1].card_id == "FK-NBR-DAUERTEMP"
                and not re.search(r"\d", item[1].text)
            ]
            selected_evidence = non_numeric_nbr_evidence[:2]
        elif diagnostic_evidence:
            application_contrast = "application_contrast" in set(
                (communication_plan or {}).get("must_include", ())
            )
            diagnostic_evidence.sort(
                key=lambda item: (
                    -lexical_overlap(item) if application_contrast else 0,
                    -int("failure_modes" in item[1].answer_facets),
                    -int(item[1].claim_kind == "safety_caution"),
                    -int("mechanism" in item[1].answer_facets),
                    -lexical_overlap(item),
                    item[0],
                )
            )
            selected_evidence = diagnostic_evidence
        selected_evidence = selected_evidence[: (2 if nbr_thermal_aging else 1)]
        missing = []
        if nbr_thermal_aging and nbr_thermal_evidence:
            conclusion = (
                "Das Schadensbild passt vorläufig zu thermischer Alterung beziehungsweise "
                "Dauer-Übertemperatur von NBR. Als Abhilfe ist die reale Temperatur direkt an der "
                "Dichtlippe zu prüfen und ein höher temperaturbeständiger Werkstoff in Richtung "
                "HNBR oder FKM zu bewerten; Medium und Additive bleiben als mögliche Verstärker "
                "separat zu prüfen. Die endgültige Werkstofffreigabe muss der Hersteller oder die "
                "zuständige Fachstelle bestätigen."
            )
        else:
            conclusion = (
                "Bei einer Undichtigkeit sollte zuerst der Versagenspfad eingegrenzt werden; "
                "ein Werkstoffwechsel allein wäre noch keine belastbare Ursachenbehebung."
            )

    if (communication_plan or {}).get(
        "goal"
    ) == "identify_replacement_seal" and not policy_evidence:
        replacement_evidence = [
            item
            for item in evidence_facts.items()
            if item[1].card_id == "FK-ERSATZDICHTUNG-IDENTIFIKATION"
        ]
        if replacement_evidence:
            selected_evidence = replacement_evidence[:1]
            missing = []
            conclusion = (
                "Ja – auch ohne lesbaren Code lässt sich die alte Dichtung systematisch "
                "identifizieren. Entscheidend sind zuerst Geometrie, Lippen- und Federbauform "
                "sowie alle noch erkennbaren Kennzeichnungen; die Betriebsdaten sichern danach "
                "ab, ob ein maßgleicher Ersatz technisch passt."
            )
        else:
            selected_evidence = []
            missing = []
            conclusion = (
                "Die alte Dichtung kann ich mit der in diesem Durchlauf abgerufenen Evidenz noch "
                "nicht belastbar identifizieren. Ich grenze deshalb zuerst das Altteil ein."
            )

    if (
        (communication_plan or {}).get("general_material_orientation")
        and rwdr_context
        and not policy_evidence
    ):
        variant_evidence = [
            item
            for item in evidence_facts.items()
            if item[1].card_id == "FK-RWDR-ENGINEERING-PROFILE"
            and "variants" in item[1].answer_facets
        ]
        selection_evidence = [
            item
            for item in evidence_facts.items()
            if item[1].card_id == "FK-RWDR-ENGINEERING-PROFILE"
            and "selection_inputs" in item[1].answer_facets
            and item not in variant_evidence
        ]
        if variant_evidence:
            selected_evidence = (variant_evidence + selection_evidence)[:2]
            missing = []
            conclusion = (
                "Grundsätzlich kommen für einen RWDR elastomere Lippenwerkstoffe und "
                "PTFE-basierte Lippenlösungen infrage. Aus Wellendurchmesser und Drehzahl allein "
                "lässt sich die passende Werkstofffamilie aber nicht seriös wählen; Medium samt "
                "Additiven, Temperatur an der Dichtlippe, Druck, Schmierung und Wellenzustand "
                "entscheiden gemeinsam. Die genannten Betriebswerte sind für die spätere Prüfung "
                "notiert, ohne hier ungefragt einen Geschwindigkeitswert vorwegzunehmen."
            )

    computed = (
        ()
        if (communication_plan or {}).get("general_material_orientation")
        and not policy_evidence
        else (tuple(calc.computed) if calc is not None else ())
    )
    if computed:
        if (
            "CALC-UMFANGSGESCHWINDIGKEIT" in policy_ids
            and "SAFETY-RGD-HD-GAS" not in policy_ids
        ):
            values = "; ".join(
                f"{item.name} = {item.value:g} {item.unit} ({item.formula}"
                + (
                    f"; Eingaben: {', '.join(item.input_origins)}"
                    if item.input_origins
                    else ""
                )
                + ")"
                for item in computed
            )
            conclusion = f"Der Rechenkern ergibt: {values}."
        else:
            values = "; ".join(
                f"{item.name} = {item.value:g} {item.unit} ({item.formula})"
                for item in computed
            )
            conclusion += f" Deterministisch berechnet: {values}."
        warnings = tuple(
            dict.fromkeys(
                warning for item in computed for warning in item.warnings if warning
            )
        )
        if warnings:
            label = (
                "Kernwarnung"
                if "CALC-UMFANGSGESCHWINDIGKEIT" in policy_ids
                and "SAFETY-RGD-HD-GAS" not in policy_ids
                else "Einordnung des Rechenkerns"
            )
            conclusion += f" {label}: " + " ".join(warnings) + "."
    if "CALC-UMFANGSGESCHWINDIGKEIT" in policy_ids:
        conclusion += (
            " Für die nächste Einordnung brauche ich die Temperatur an der Dichtstelle "
            "und den Differenzdruck beziehungsweise die Entlüftung."
        )
    return TechnicalAnswer(
        schema_version=1,
        intent="evidence_bound_technical_answer",
        case_revision=case_revision,
        conclusion=conclusion,
        assumptions=[],
        missing_information=missing,
        claims=[
            TechnicalClaim(
                text=fact.text,
                evidence_ids=[evidence_id],
                criticality="supporting",
            )
            for evidence_id, fact in selected_evidence[:4]
        ],
        recommendation={"summary": "", "status": "none", "conditions": []},
        needs_human_review=True,
    )


def _render_reviewed_policy_answer(
    answer: TechnicalAnswer, *, question: str = ""
) -> str:
    """Render a matched reviewed policy as a short conversation, not a mini-document."""

    paragraphs = [answer.conclusion.strip()]
    policy_ids = {
        evidence_id for claim in answer.claims for evidence_id in claim.evidence_ids
    }
    if "TRAP-FKM-DAMPF" in policy_ids and re.search(
        r"\b(?:genau|exakt|bis\s+(?:zu\s+)?welche|wie\s+viel)\b",
        question or "",
        re.IGNORECASE,
    ):
        return (
            "Eine universell genaue Grenztemperatur kann ich aus der aktuell geprüften Evidenz "
            "nicht belastbar ableiten. Für Sattdampf ist peroxidvernetztes EPDM der geprüfte "
            "Kandidatenraum; die konkrete Obergrenze muss für den tatsächlichen Compound, seine "
            "Vernetzung, Druck und Expositionsdauer gegen Datenblatt beziehungsweise Hersteller "
            "verifiziert werden. Eine einzelne exakte Zahl würde hier Scheingenauigkeit erzeugen."
        )
    if policy_ids.intersection(
        {"TRAP-FKM-DAMPF", "POLICY-TRINKWASSER-FAMILIE-ZULASSUNG"}
    ):
        # These policies already contain the complete, user-facing reviewed decision.  Rendering
        # the summary plus a second labelled evidence paragraph recreates the document-like answer
        # that the policy is meant to replace.  Keep the exact reviewed fact; the communication
        # contract appends the single governed question where the case still needs one.
        return " ".join(
            claim.text.strip() for claim in answer.claims if claim.text.strip()
        )
    if any(
        "CALC-UMFANGSGESCHWINDIGKEIT" in evidence_id
        for claim in answer.claims
        for evidence_id in claim.evidence_ids
    ):
        # The calculation conclusion already contains the governed value, formula, input origins,
        # kernel warning and bounded next need.  Repeating the full internal calculation policy is
        # safe but document-like and obscures the actual answer.
        return paragraphs[0]
    if answer.claims:
        paragraphs.append(
            " ".join(
                f"{claim.text.strip()} (quellengebunden)" for claim in answer.claims
            )
        )
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def _render_diagnostic_evidence_answer(
    answer: TechnicalAnswer, communication_plan: dict | None
) -> str:
    """Lead one troubleshooting turn as short prose with one governed next question."""

    paragraphs = [answer.conclusion.strip()]
    if answer.claims:
        paragraphs.append(
            " ".join(
                f"{claim.text.strip()} (quellengebunden)" for claim in answer.claims
            )
        )
    plan = communication_plan or {}
    question = str(plan.get("next_question") or "").strip()
    if question:
        reason = str(plan.get("question_reason") or "").strip()
        paragraphs.append(question + (f" {reason}" if reason else ""))
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def _calc_payload(calc: CalcResult | None) -> tuple[list[dict], list[dict], list[str]]:
    """Flatten a CalcResult into template data: computed values, not-computed reasons, notes."""
    if calc is None:
        return [], [], []
    computed = [
        {
            "name": c.name,
            "value": c.value,
            "unit": c.unit,
            "formula": c.formula,
            "stage": c.stage,
            "estimate": c.estimate,
            "assumptions": list(c.assumptions),
            "inputs_used": list(c.inputs_used),
            "input_origins": list(c.input_origins),  # M8-A: provenance visible to L1
            "warnings": list(c.warnings),
        }
        for c in calc.computed
    ]
    not_computed = [
        {"calc_id": n.calc_id, "reason": n.reason} for n in calc.not_computed
    ]
    return computed, not_computed, list(calc.notes)


@dataclass(frozen=True)
class L1StreamEvent:
    """One item from ``L1Generator.generate_stream`` (Phase 3B, draft-token streaming): EITHER a RAW
    text delta (``delta`` set, ``answer`` None) forwarded verbatim from the client stream, OR the
    terminal event (``answer`` set, ``delta`` None) carrying the finished, ``strip_sourcing``-cleaned
    Answer. Deltas stream RAW — never per-delta stripped (stripping a fragment mid-token would corrupt
    it); ``strip_sourcing`` is applied to the FULL accumulated final text ONCE, so the terminal
    ``answer`` is byte-identical to what the non-streaming ``generate`` returns for the same completion
    + the same inputs. Exactly one terminal event per SUCCESSFUL stream, always yielded LAST; a
    mid-stream exception propagates unchanged (a failed stream is a failed call — no partial/synthetic
    Answer is ever emitted, identical to ``generate``'s and ``LlmStreamEvent``'s failure contract).

    This mirrors ``pipeline.smalltalk_generator.SmalltalkStreamEvent`` exactly, but for the full L1
    engineering generator. It is a pure OBSERVABILITY channel: the terminal ``answer`` still goes
    through the UNCHANGED output_guard + L3 verify pipeline downstream — draft deltas are never
    treated as, or substituted for, the delivered/verified answer."""

    delta: str | None = None
    answer: Answer | None = None


class L1Generator:
    def __init__(
        self,
        client: LlmClient,
        assembler: SystemPromptAssembler,
        model_config: ModelConfig,
        *,
        structured_output_enabled: bool = False,
    ) -> None:
        self._client = client
        self._assembler = assembler
        self._model_config = model_config
        self._structured_output_enabled = structured_output_enabled

    @property
    def supports_token_streaming(self) -> bool:
        return not self._structured_output_enabled

    def with_reasoning_effort(self, effort: str | None) -> "L1Generator":
        """Return a turn-scoped generator without mutating the shared pipeline object."""
        return L1Generator(
            self._client,
            self._assembler,
            replace(self._model_config, reasoning_effort=effort),
            structured_output_enabled=self._structured_output_enabled,
        )

    def doctrine_system_prompt(self, *, flags: Flags) -> str:
        """P1.4: the STATIC doctrine system prompt (flags only — NO grounding, calc, memory or
        correction_note), exposed so the SERVE-path deterministic exfiltration gate can use the
        confidential doctrine as its leak reference. This MIRRORS the eval's reference
        (``eval/harness`` builds ``PromptAssembler().system_prompt(flags=...)``), so the SERVE gate
        and the eval gate score against the byte-identical doctrine surface. Using the doctrine-only
        prompt (not the per-turn assembly) is also what AVOIDS a false-positive: the live prompt
        legitimately embeds reviewed correction facts that a deterministic L3 hedge is allowed to
        state verbatim. KB-claim dumps are covered by the gate's separate ``kb_claims`` channel.
        Pure: the assembler is injected (``core`` stays I/O-free)."""
        return self._assembler.system_prompt(flags=flags)

    def _assemble_system(
        self,
        *,
        flags: Flags,
        grounding_facts: tuple[GroundingFact, ...],
        case_context: list[dict] | None,
        durable_context: list[dict] | None,
        conversation_window: list[dict] | None,
        correction_note: str | None,
        calc: CalcResult | None,
        untrusted: list[dict] | None,
        archetype_context: dict | None,
        pack_suggestion_context: dict | None,
        medium_hint_context: dict | None,
        coverage: dict | None,
        contract: dict | None,
        baseline_hardening: bool,
        material_params: list | None,
        knowledge_answer_plan: dict | None,
        communication_plan: dict | None,
        risk_flags: list[str] | None,
    ) -> str:
        """The SINGLE prompt-assembly path shared by ``generate`` and ``generate_stream`` so the two
        can never drift: streaming assembles a byte-identical system prompt to the non-streaming call
        for the same inputs, guaranteeing the streamed draft is generated from the exact same prompt
        as the delivered answer would be."""
        computed_values, not_computed, calc_notes = _calc_payload(calc)
        return self._assembler.system_prompt(
            anrede="du",
            grounding_facts=list(grounding_facts),
            case_context=case_context,
            durable_context=durable_context,
            conversation_window=conversation_window,
            flags=flags,
            correction_note=correction_note,
            computed_values=computed_values,
            not_computed=not_computed,
            calc_notes=calc_notes,
            untrusted=untrusted,
            archetype_context=archetype_context,
            pack_suggestion_context=pack_suggestion_context,
            medium_hint_context=medium_hint_context,
            coverage=coverage,
            contract=contract,
            baseline_hardening=baseline_hardening,
            material_params=material_params,
            knowledge_answer_plan=knowledge_answer_plan,
            communication_plan=communication_plan,
            risk_flags=risk_flags,
        )

    async def generate(
        self,
        question: str,
        *,
        flags: Flags,
        grounding_facts: tuple[GroundingFact, ...] = (),
        case_context: list[dict] | None = None,
        durable_context: list[dict] | None = None,
        conversation_window: list[dict] | None = None,
        correction_note: str | None = None,
        calc: CalcResult | None = None,
        untrusted: list[dict] | None = None,
        archetype_context: dict | None = None,
        pack_suggestion_context: dict | None = None,
        medium_hint_context: dict | None = None,
        coverage: dict | None = None,
        contract: dict | None = None,
        baseline_hardening: bool = False,
        material_params: list | None = None,
        knowledge_answer_plan: dict | None = None,
        communication_plan: dict | None = None,
        require_evidence_for_all_claims: bool = False,
        compact_technical_answer: bool = False,
        work_solution_candidate: bool = False,
        risk_flags: list[str] | None = None,
        case_revision: int = 0,
        evidence_query: str | None = None,
    ) -> Answer:
        prompt_grounding_facts = grounding_facts
        knowledge_evidence_facts: dict[str, GroundingFact] = {}
        suppress_example_values = bool(
            knowledge_answer_plan is not None
            and not _requests_quantitative_detail(question)
        )
        if suppress_example_values:
            # Broad explanations should be deep in mechanisms and trade-offs, not long catalog
            # dumps of otherwise sourced limit values. Numeric/example claims remain available when
            # the user explicitly requests ranges, limits or values.
            prompt_grounding_facts = tuple(
                fact
                for fact in prompt_grounding_facts
                if fact.claim_kind != "example_value"
            )
        if self._structured_output_enabled and knowledge_answer_plan is not None:
            prompt_grounding_facts, knowledge_evidence_facts = (
                _knowledge_evidence_context(prompt_grounding_facts)
            )
        system = self._assemble_system(
            flags=flags,
            grounding_facts=prompt_grounding_facts,
            case_context=case_context,
            durable_context=durable_context,
            conversation_window=conversation_window,
            correction_note=correction_note,
            calc=calc,
            untrusted=untrusted,
            archetype_context=archetype_context,
            pack_suggestion_context=pack_suggestion_context,
            medium_hint_context=medium_hint_context,
            coverage=coverage,
            contract=contract,
            baseline_hardening=baseline_hardening,
            material_params=material_params,
            knowledge_answer_plan=knowledge_answer_plan,
            communication_plan=communication_plan,
            risk_flags=risk_flags,
        )
        if self._structured_output_enabled:
            vendor_boundary = _vendor_compound_boundary_answer(question, grounding_facts)
            if vendor_boundary is not None:
                return Answer(
                    text=vendor_boundary,
                    model=self._model_config.model,
                    grounding_facts=grounding_facts,
                    finish_reason="deterministic_vendor_compound_boundary",
                )
            evidence_facts = dict(knowledge_evidence_facts)
            if knowledge_answer_plan is None:
                for index, fact in enumerate(grounding_facts):
                    if fact.card_id:
                        evidence_id = fact.claim_id or fact.card_id
                        if evidence_id in evidence_facts:
                            evidence_id = f"{fact.card_id}:{index}"
                        evidence_facts[evidence_id] = fact
            allowed_ids = frozenset(evidence_facts)
            source_bound_policy_present = any(
                fact.kind == "trap" and bool(fact.sources)
                for fact in evidence_facts.values()
            )
            if (
                knowledge_answer_plan is None
                and require_evidence_for_all_claims
                and archetype_context
                and not source_bound_policy_present
            ):
                technical = _deterministic_archetype_answer(
                    question=evidence_query or question,
                    archetype_context=archetype_context,
                    evidence_facts=evidence_facts,
                    case_revision=case_revision,
                )
                if technical is not None:
                    rendered = (
                        _render_compact_reviewed_archetype(
                            technical, communication_plan
                        )
                        if compact_technical_answer
                        else render_technical_answer(
                            technical,
                            communication_plan=communication_plan,
                        )
                    )
                    return Answer(
                        text=strip_sourcing(rendered),
                        model=self._model_config.model,
                        grounding_facts=grounding_facts,
                        finish_reason="deterministic_reviewed_archetype",
                        verification_claims=tuple(
                            claim.text for claim in technical.claims
                        ),
                    )
            if (
                knowledge_answer_plan is None
                and require_evidence_for_all_claims
                and source_bound_policy_present
            ):
                # Reviewed trap facts reach this branch only through the catalog's explicit,
                # high-precision retrieval terms and carry primary-source provenance.  Letting a
                # generative pass expand such a policy fact can reintroduce the exact unsafe or
                # over-specific recommendation the policy is meant to prevent.  Render the exact
                # reviewed statement and deterministic kernel output instead.
                technical = _deterministic_evidence_answer(
                    question=evidence_query or question,
                    evidence_facts=evidence_facts,
                    case_revision=case_revision,
                    calc=calc,
                    work_solution_candidate=work_solution_candidate,
                    communication_plan=communication_plan,
                )
                return Answer(
                    text=strip_sourcing(
                        _render_reviewed_policy_answer(technical, question=question)
                    ),
                    model=self._model_config.model,
                    grounding_facts=grounding_facts,
                    finish_reason="deterministic_reviewed_policy",
                    verification_claims=tuple(
                        claim.text
                        for claim in sorted(
                            technical.claims,
                            key=lambda claim: (
                                claim.criticality != "decision_relevant"
                            ),
                        )
                    ),
                )
            if (
                knowledge_answer_plan is None
                and require_evidence_for_all_claims
                and not source_bound_policy_present
                and not any(fact.kind == "trap" for fact in evidence_facts.values())
                and any(
                    fact.card_id == "FK-ORING-VERPRESSUNG"
                    for fact in evidence_facts.values()
                )
                and re.search(r"\bo[- ]?ring\w*\b", (evidence_query or question), re.I)
                and re.search(
                    r"\b(?:verpress\w*|squeeze)\b",
                    (evidence_query or question),
                    re.I,
                )
            ):
                # The reviewed O-ring card already contains both coupled design axes.  Rendering
                # them deterministically prevents a valid but incomplete sample from mentioning
                # squeeze while silently dropping gland-fill reserve for swelling.
                technical = _deterministic_evidence_answer(
                    question=evidence_query or question,
                    evidence_facts=evidence_facts,
                    case_revision=case_revision,
                    calc=calc,
                    communication_plan=communication_plan,
                )
                return Answer(
                    text=strip_sourcing(
                        render_technical_answer(
                            technical,
                            communication_plan=communication_plan,
                        )
                    ),
                    model=self._model_config.model,
                    grounding_facts=grounding_facts,
                    finish_reason="deterministic_reviewed_oring_design",
                    verification_claims=tuple(claim.text for claim in technical.claims),
                )
            if (
                knowledge_answer_plan is None
                and require_evidence_for_all_claims
                and evidence_facts
                and (communication_plan or {}).get("general_material_orientation")
            ):
                technical = _deterministic_evidence_answer(
                    question=evidence_query or question,
                    evidence_facts=evidence_facts,
                    case_revision=case_revision,
                    calc=calc,
                    communication_plan=communication_plan,
                )
                return Answer(
                    text=strip_sourcing(
                        render_technical_answer(
                            technical,
                            communication_plan=communication_plan,
                        )
                    ),
                    model=self._model_config.model,
                    grounding_facts=grounding_facts,
                    finish_reason="deterministic_material_orientation",
                    verification_claims=tuple(claim.text for claim in technical.claims),
                )
            if (
                knowledge_answer_plan is None
                and require_evidence_for_all_claims
                and evidence_facts
                and (communication_plan or {}).get("goal") == "diagnose_failure"
            ):
                technical = _deterministic_evidence_answer(
                    question=evidence_query or question,
                    evidence_facts=evidence_facts,
                    case_revision=case_revision,
                    calc=calc,
                    communication_plan=communication_plan,
                )
                return Answer(
                    text=strip_sourcing(
                        _render_diagnostic_evidence_answer(
                            technical, communication_plan
                        )
                    ),
                    model=self._model_config.model,
                    grounding_facts=grounding_facts,
                    finish_reason="deterministic_diagnostic_evidence",
                    verification_claims=tuple(claim.text for claim in technical.claims),
                )
            if (
                knowledge_answer_plan is None
                and require_evidence_for_all_claims
                and evidence_facts
                and (communication_plan or {}).get("goal")
                == "identify_replacement_seal"
            ):
                technical = _deterministic_evidence_answer(
                    question=evidence_query or question,
                    evidence_facts=evidence_facts,
                    case_revision=case_revision,
                    calc=calc,
                    communication_plan=communication_plan,
                )
                return Answer(
                    text=strip_sourcing(
                        _render_diagnostic_evidence_answer(
                            technical, communication_plan
                        )
                    ),
                    model=self._model_config.model,
                    grounding_facts=grounding_facts,
                    finish_reason="deterministic_replacement_identification",
                    verification_claims=tuple(claim.text for claim in technical.claims),
                )
            if (
                knowledge_answer_plan is None
                and require_evidence_for_all_claims
                and evidence_facts
                and (communication_plan or {}).get("goal")
                == "resolve_dynamic_sealing_tradeoff"
            ):
                technical = _deterministic_evidence_answer(
                    question=evidence_query or question,
                    evidence_facts=evidence_facts,
                    case_revision=case_revision,
                    calc=calc,
                    work_solution_candidate=True,
                    communication_plan=communication_plan,
                )
                return Answer(
                    text=strip_sourcing(
                        render_technical_answer(
                            technical,
                            communication_plan=communication_plan,
                        )
                    ),
                    model=self._model_config.model,
                    grounding_facts=grounding_facts,
                    finish_reason="deterministic_tradeoff_evidence",
                    verification_claims=tuple(claim.text for claim in technical.claims),
                )
            if knowledge_answer_plan is not None:
                from sealai_v2.core.knowledge_answer import facets_for_fact
                from sealai_v2.knowledge.material_parameters import parameter_text

                subjects = tuple(
                    str(subject)
                    for subject in knowledge_answer_plan.get("subjects", ())
                    if str(subject)
                )
                evidence_facets_v2 = {
                    evidence_id: frozenset(facets_for_fact(fact))
                    for evidence_id, fact in evidence_facts.items()
                }
                evidence_subjects_v2 = {
                    evidence_id: _fact_subjects(fact, subjects)
                    for evidence_id, fact in evidence_facts.items()
                }
                evidence_texts_v2 = {
                    evidence_id: fact.text
                    for evidence_id, fact in evidence_facts.items()
                }
                coverage_by_subject = {
                    str(entry.get("subject")): (
                        set(entry.get("covered_facets", ()))
                        - ({"parameters"} if suppress_example_values else set())
                    )
                    for entry in knowledge_answer_plan.get("subject_coverage", ())
                }
                required_cells = {
                    subject: tuple(
                        frozenset(
                            set(section.get("facets", ()))
                            & coverage_by_subject.get(subject, set())
                        )
                        for section in knowledge_answer_plan.get("sections", ())
                        if set(section.get("facets", ()))
                        & coverage_by_subject.get(subject, set())
                    )
                    for subject in subjects
                }
                evidence_map = "; ".join(
                    f"{evidence_id}=>subject[{','.join(sorted(evidence_subjects_v2[evidence_id])) or 'unbound'}]"
                    f";facets[{','.join(sorted(evidence_facets_v2[evidence_id])) or 'none'}]"
                    for evidence_id in sorted(evidence_facts)
                )
                instruction = (
                    "\n\nCreate exactly one internal EngineeringKnowledgeAnswer object. "
                    "Do not write Markdown and do not create tables. The deterministic renderer owns "
                    "all tables and parameter values. Copy each claim statement exactly from one "
                    "cited evidence item; do not paraphrase, merge or extend it. Each claim must "
                    "address exactly one declared "
                    "subject and one facet supported by every cited evidence ID. Never transfer a "
                    "property, limit or failure mechanism from one comparison subject to another. "
                    "Do not introduce a number, standard, product, filler, approval or limit absent "
                    "from the supplied reviewed evidence or material-parameter registry. Distinguish "
                    "family tendencies, compound-specific values, test values and application limits. "
                    "State mechanisms and consequences where the evidence supports them. Use concise "
                    "senior-engineer language, preserve uncertainty, and identify the minimum missing "
                    "inputs that would change a selection. "
                    f"profile must be {knowledge_answer_plan.get('profile')}; case_revision must be "
                    f"{case_revision}; allowed subjects: {', '.join(subjects) or 'Dichtungstechnik'}. "
                    f"Evidence ownership: {evidence_map or '(none)'}."
                )
                if suppress_example_values:
                    instruction += (
                        " The user did not request quantitative detail. Omit catalogue "
                        "ranges, example values, numeric limits and parameter tables; explain "
                        "mechanisms, trade-offs and selection inputs using only the remaining "
                        "reviewed evidence."
                    )
                try:
                    engineering, result = await generate_structured(
                        self._client,
                        output_type=EngineeringKnowledgeAnswer,
                        schema_name="sealingai_engineering_knowledge_answer_v2",
                        system=system + instruction,
                        user=question,
                        model_config=self._model_config,
                        max_repairs=0,
                    )
                    engineering = engineering.model_copy(
                        update={
                            "conclusion": _engineering_conclusion(
                                knowledge_answer_plan, question=question
                            ),
                            "assumptions": [],
                            "missing_information": _engineering_missing_information(
                                knowledge_answer_plan
                            ),
                        }
                    )
                    validate_engineering_answer(
                        engineering,
                        profile=str(knowledge_answer_plan.get("profile")),
                        case_revision=case_revision,
                        allowed_subjects=subjects,
                        evidence_facets=evidence_facets_v2,
                        evidence_subjects=evidence_subjects_v2,
                        evidence_texts=evidence_texts_v2,
                        required_cells=required_cells,
                        parameter_text=parameter_text(material_params),
                    )
                except (StructuredOutputError, EngineeringAnswerValidationError) as exc:
                    logger.warning(
                        "engineering knowledge answer failed validation; using exact-evidence "
                        "fallback (%s)",
                        exc,
                    )
                    engineering = _fallback_engineering_answer(
                        plan=knowledge_answer_plan,
                        evidence_facts=evidence_facts,
                        evidence_subjects=evidence_subjects_v2,
                        case_revision=case_revision,
                        question=question,
                    )
                    result = LlmResult(
                        text="",
                        model=self._model_config.model,
                        finish_reason="deterministic_engineering_fallback",
                    )
                return Answer(
                    text=strip_sourcing(
                        render_engineering_answer(
                            engineering,
                            knowledge_answer_plan=knowledge_answer_plan,
                            material_params=material_params,
                            communication_plan=communication_plan,
                        )
                    ),
                    model=result.model,
                    grounding_facts=grounding_facts,
                    finish_reason=result.finish_reason,
                    verification_claims=tuple(
                        claim.statement for claim in engineering.claims
                    ),
                )
            required_knowledge_facets: set[str] = set()
            evidence_facets: dict[str, set[str]] = {}
            if knowledge_answer_plan is not None:
                from sealai_v2.core.knowledge_answer import facets_for_fact

                required_knowledge_facets = {
                    str(facet)
                    for section in knowledge_answer_plan.get("sections", ())
                    for facet in section.get("covered_facets", ())
                    if str(facet)
                }
                for evidence_id, fact in evidence_facts.items():
                    evidence_facets.setdefault(evidence_id, set()).update(
                        facets_for_fact(fact)
                    )
            structured_instruction = (
                "\n\nCreate the internal TechnicalAnswer object. Do not write user-facing "
                "Markdown. Use only these evidence_ids: "
                f"{', '.join(sorted(allowed_ids)) or '(none)'}. "
                f"case_revision must be {case_revision}. A decision_relevant claim must carry "
                "at least one allowed evidence_id. Never invent evidence IDs or tool results."
            )
            if knowledge_answer_plan is not None:
                structured_instruction += (
                    " This is a pure engineering knowledge answer: every technical claim must "
                    "carry at least one allowed evidence_id. Do not add named fillers, standards, "
                    "regulations, approvals, tests, products, values, or limits that are absent "
                    "from the supplied evidence/material parameters. Set recommendation.status "
                    "to none with an empty summary and no conditions; selection inputs belong in "
                    "the evidenced claims, not in a recommendation block."
                )
                if required_knowledge_facets:
                    facet_map = "; ".join(
                        f"{evidence_id}=>{','.join(sorted(facets)) or 'none'}"
                        for evidence_id, facets in evidence_facets.items()
                    )
                    structured_instruction += (
                        " Across all claims, the cited evidence_ids must collectively cover every "
                        "required engineering facet. Required facets: "
                        f"{', '.join(sorted(required_knowledge_facets))}. "
                        f"Evidence facet map: {facet_map}. Multiple evidence_ids may be attached "
                        "to one claim when that claim faithfully combines their content."
                    )
            elif require_evidence_for_all_claims:
                structured_instruction += (
                    " This is an evidence-bound technical answer: every technical claim must "
                    "carry at least one allowed evidence_id. User-provided case facts belong in "
                    "assumptions or missing_information, not as unsupported technical claims. "
                    "Do not add values, limits, materials, standards, products or suitability "
                    "statements that are absent from the supplied evidence or calculations. "
                    "If the user's compatibility, temperature, cost, lifetime or geometry goals "
                    "cannot all be evidenced at once, state that unresolved target conflict "
                    "explicitly instead of presenting a candidate list as a solution."
                )
                if work_solution_candidate:
                    structured_instruction += (
                        " The evidence supports engineering a seal-type solution candidate: name "
                        "one primary provisional candidate, explain its sealing mechanism and "
                        "conditions, and identify the next-best architecture alternative. Do not "
                        "replace this solution work with a generic manufacturer referral."
                    )
                if compact_technical_answer:
                    structured_instruction += (
                        " This is a compact first-turn response: put the decisive risk or result "
                        "first, use at most three technical claims and three discriminating "
                        "missing-information items, do not restate the user's inputs as assumptions, "
                        "and keep recommendation conditions to at most two."
                    )

            async def _call(current_system: str):
                technical, result = await generate_structured(
                    self._client,
                    output_type=TechnicalAnswer,
                    schema_name="sealingai_technical_answer_v1",
                    system=current_system,
                    user=question,
                    model_config=self._model_config,
                    max_repairs=0,
                )
                technical = calibrate_technical_answer(technical)
                if compact_technical_answer:
                    diagnose_failure = bool(
                        (communication_plan or {}).get("goal") == "diagnose_failure"
                    )
                    priority = {
                        "decision_relevant": 0,
                        "supporting": 1,
                        "context": 2,
                    }
                    technical = technical.model_copy(
                        update={
                            "assumptions": [],
                            "missing_information": technical.missing_information[:3],
                            "claims": sorted(
                                technical.claims,
                                key=lambda claim: priority[claim.criticality],
                            )[:3],
                            "recommendation": technical.recommendation.model_copy(
                                update={
                                    "summary": (
                                        ""
                                        if diagnose_failure
                                        else technical.recommendation.summary
                                    ),
                                    "status": (
                                        "none"
                                        if diagnose_failure
                                        else technical.recommendation.status
                                    ),
                                    "conditions": (
                                        []
                                        if diagnose_failure
                                        else technical.recommendation.conditions[:2]
                                    ),
                                }
                            ),
                        }
                    )
                if knowledge_answer_plan is not None:
                    technical = technical.model_copy(
                        update={
                            "recommendation": technical.recommendation.model_copy(
                                update={
                                    "summary": "",
                                    "status": "none",
                                    "conditions": [],
                                }
                            ),
                            "needs_human_review": False,
                        }
                    )
                calculation_context_text = " ".join(
                    " ".join(
                        (
                            item.name,
                            f"{item.value:g}",
                            item.unit,
                            item.formula,
                            *item.warnings,
                            *item.input_origins,
                        )
                    )
                    for item in (calc.computed if calc is not None else ())
                )
                validate_technical_answer(
                    technical,
                    case_revision=case_revision,
                    allowed_evidence_ids=allowed_ids,
                    require_evidence_for_all_claims=(
                        knowledge_answer_plan is not None
                        or require_evidence_for_all_claims
                    ),
                    evidence_text_by_id=(
                        {
                            evidence_id: fact.text
                            for evidence_id, fact in evidence_facts.items()
                        }
                        if knowledge_answer_plan is not None
                        or require_evidence_for_all_claims
                        else None
                    ),
                    calculation_context_text=calculation_context_text,
                    user_context_text=question,
                    forbid_material_recommendation=bool(
                        baseline_hardening and _requires_material_abstention(question)
                    ),
                )
                if required_knowledge_facets:
                    used_evidence = {
                        evidence_id
                        for claim in technical.claims
                        for evidence_id in claim.evidence_ids
                    }
                    covered_facets = {
                        facet
                        for evidence_id in used_evidence
                        for facet in evidence_facets.get(evidence_id, ())
                    }
                    missing_facets = required_knowledge_facets - covered_facets
                    if missing_facets:
                        supplemented = list(technical.claims)
                        unused_ids = [
                            evidence_id
                            for evidence_id in evidence_facts
                            if evidence_id not in used_evidence
                        ]
                        while missing_facets:
                            best_id = max(
                                unused_ids,
                                key=lambda evidence_id: len(
                                    evidence_facets.get(evidence_id, set())
                                    & missing_facets
                                ),
                                default="",
                            )
                            covered_now = (
                                evidence_facets.get(best_id, set()) & missing_facets
                            )
                            if not best_id or not covered_now:
                                raise TechnicalAnswerValidationError(
                                    "knowledge_facet_coverage:"
                                    + ",".join(sorted(missing_facets))
                                )
                            supplemented.append(
                                TechnicalClaim(
                                    text=evidence_facts[best_id].text,
                                    evidence_ids=[best_id],
                                    criticality="supporting",
                                )
                            )
                            unused_ids.remove(best_id)
                            missing_facets -= covered_now
                        technical = technical.model_copy(
                            update={"claims": supplemented}
                        )
                return technical, result

            try:
                technical, result = await _call(system + structured_instruction)
            except (StructuredOutputError, TechnicalAnswerValidationError) as exc:
                # A validation miss often means the model understood the case but attached a broad
                # card ID, introduced one uncited identifier, or omitted a required evidence ID.
                # Give evidence-bound answers one bounded repair using the exact deterministic
                # failure reason before discarding their case-specific synthesis.  The repaired
                # object passes the identical validator; a second miss still fails closed below.
                repaired = False
                if (
                    knowledge_answer_plan is None
                    and require_evidence_for_all_claims
                    and evidence_facts
                ):
                    repair = (
                        "\n\nThe previous object failed deterministic evidence validation "
                        f"({exc}). Repair it once: preserve the user's actual goal, remove every "
                        "unsupported name or number, cite the exact allowed evidence ID on each "
                        "technical claim, and keep a concrete provisional solution when the "
                        "evidence supports one. Return exactly one TechnicalAnswer object."
                    )
                    try:
                        technical, result = await _call(
                            system + structured_instruction + repair
                        )
                        repaired = True
                    except (
                        StructuredOutputError,
                        TechnicalAnswerValidationError,
                    ) as repair_exc:
                        logger.warning(
                            "structured technical answer repair failed; using reviewed-evidence "
                            "fallback (%s; repair=%s)",
                            exc,
                            repair_exc,
                        )
                if repaired:
                    pass
                elif knowledge_answer_plan is not None and evidence_facts:
                    logger.warning(
                        "structured knowledge answer failed validation; using reviewed-evidence "
                        "fallback (%s)",
                        exc,
                    )
                    technical = _deterministic_knowledge_answer(
                        knowledge_answer_plan=knowledge_answer_plan,
                        evidence_facts=evidence_facts,
                        case_revision=case_revision,
                    )
                    result = LlmResult(
                        text="",
                        model=self._model_config.model,
                        finish_reason="deterministic_knowledge_fallback",
                    )
                elif require_evidence_for_all_claims and evidence_facts:
                    technical = _deterministic_evidence_answer(
                        question=evidence_query or question,
                        evidence_facts=evidence_facts,
                        case_revision=case_revision,
                        calc=calc,
                        work_solution_candidate=work_solution_candidate,
                        communication_plan=communication_plan,
                    )
                    result = LlmResult(
                        text="",
                        model=self._model_config.model,
                        finish_reason="deterministic_evidence_fallback",
                    )
                else:
                    repair = (
                        "\n\nThe previous object failed deterministic validation "
                        f"({exc}). Repair it once. Return exactly one schema-valid "
                        "TechnicalAnswer and obey the allowed evidence IDs and case revision."
                    )
                    technical, result = await _call(
                        system + structured_instruction + repair
                    )
            return Answer(
                text=strip_sourcing(
                    render_technical_answer(
                        technical, communication_plan=communication_plan
                    )
                ),
                model=result.model,
                grounding_facts=grounding_facts,
                finish_reason=result.finish_reason,
                verification_claims=tuple(
                    claim.text
                    for claim in sorted(
                        technical.claims,
                        key=lambda claim: claim.criticality != "decision_relevant",
                    )
                ),
            )

        result = await self._client.generate(
            system=system, user=question, model_config=self._model_config
        )
        return Answer(
            text=strip_sourcing(result.text),
            model=result.model,
            grounding_facts=grounding_facts,
            finish_reason=result.finish_reason,
        )

    async def generate_stream(
        self,
        question: str,
        *,
        flags: Flags,
        grounding_facts: tuple[GroundingFact, ...] = (),
        case_context: list[dict] | None = None,
        durable_context: list[dict] | None = None,
        conversation_window: list[dict] | None = None,
        correction_note: str | None = None,
        calc: CalcResult | None = None,
        untrusted: list[dict] | None = None,
        archetype_context: dict | None = None,
        pack_suggestion_context: dict | None = None,
        medium_hint_context: dict | None = None,
        coverage: dict | None = None,
        contract: dict | None = None,
        baseline_hardening: bool = False,
        material_params: list | None = None,
        knowledge_answer_plan: dict | None = None,
        communication_plan: dict | None = None,
        require_evidence_for_all_claims: bool = False,
        compact_technical_answer: bool = False,
        work_solution_candidate: bool = False,
        risk_flags: list[str] | None = None,
        case_revision: int = 0,
        evidence_query: str | None = None,
    ) -> AsyncIterator[L1StreamEvent]:
        """Streaming variant of ``generate`` (Phase 3B, draft-token streaming). IDENTICAL keyword-arg
        signature and IDENTICAL prompt assembly (both go through ``_assemble_system``), but calls the
        client's ``generate_stream`` instead of ``generate``. Forwards each RAW content delta as an
        ``L1StreamEvent(delta=...)``, then yields exactly ONE terminal ``L1StreamEvent(answer=...)``
        whose Answer applies ``strip_sourcing`` to the FINAL accumulated text only — byte-identical to
        ``generate``'s Answer for the same completion + inputs (proven output-equivalent by the Phase
        3B tests). A mid-stream failure propagates unchanged (no partial Answer is ever emitted).

        This is a pure observability channel: the returned terminal Answer is fed into the SAME
        output_guard + L3 verify pipeline as the non-streaming path — draft deltas never bypass, skip,
        or weaken verification, and are never substituted for the delivered answer."""
        if self._structured_output_enabled:
            yield L1StreamEvent(
                answer=await self.generate(
                    question,
                    flags=flags,
                    grounding_facts=grounding_facts,
                    case_context=case_context,
                    durable_context=durable_context,
                    conversation_window=conversation_window,
                    correction_note=correction_note,
                    calc=calc,
                    untrusted=untrusted,
                    archetype_context=archetype_context,
                    pack_suggestion_context=pack_suggestion_context,
                    medium_hint_context=medium_hint_context,
                    coverage=coverage,
                    contract=contract,
                    baseline_hardening=baseline_hardening,
                    material_params=material_params,
                    knowledge_answer_plan=knowledge_answer_plan,
                    communication_plan=communication_plan,
                    require_evidence_for_all_claims=require_evidence_for_all_claims,
                    compact_technical_answer=compact_technical_answer,
                    work_solution_candidate=work_solution_candidate,
                    risk_flags=risk_flags,
                    case_revision=case_revision,
                    evidence_query=evidence_query,
                )
            )
            return

        system = self._assemble_system(
            flags=flags,
            grounding_facts=grounding_facts,
            case_context=case_context,
            durable_context=durable_context,
            conversation_window=conversation_window,
            correction_note=correction_note,
            calc=calc,
            untrusted=untrusted,
            archetype_context=archetype_context,
            pack_suggestion_context=pack_suggestion_context,
            medium_hint_context=medium_hint_context,
            coverage=coverage,
            contract=contract,
            baseline_hardening=baseline_hardening,
            material_params=material_params,
            knowledge_answer_plan=knowledge_answer_plan,
            communication_plan=communication_plan,
            risk_flags=risk_flags,
        )
        async for event in self._client.generate_stream(
            system=system, user=question, model_config=self._model_config
        ):
            if event.delta is not None:
                yield L1StreamEvent(delta=event.delta)
            elif event.result is not None:
                yield L1StreamEvent(
                    answer=Answer(
                        text=strip_sourcing(event.result.text),
                        model=event.result.model,
                        grounding_facts=grounding_facts,
                        finish_reason=event.result.finish_reason,
                    )
                )
