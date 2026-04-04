import hashlib

from prompts.builder import PromptBuilder

# ---------------------------------------------------------------------------
# Structured-path prompt — migrated to PromptBuilder v2.0
# SYSTEM_PROMPT_TEMPLATE removed; governed path uses PromptBuilder.governed()
# ---------------------------------------------------------------------------

REASONING_PROMPT_VERSION: str = PromptBuilder.PROMPT_VERSION
REASONING_PROMPT_HASH: str = hashlib.sha256(REASONING_PROMPT_VERSION.encode()).hexdigest()[:12]

# ---------------------------------------------------------------------------
# Fast-path prompt — guidance & direct answers (Phase 0A.3)
# No claim submission. No binding qualification. No governance decisions.
# ---------------------------------------------------------------------------

FAST_GUIDANCE_PROMPT_TEMPLATE = """
Du bist SealAI — ein erfahrener Dichtungstechniker mit 20+ Jahren Praxis in der industriellen Anwendung.
Du denkst wie ein Ingenieur, nicht wie ein Formular.

Antwortmodus: {answer_mode}

---
BISHERIGER GESPRÄCHSVERLAUF (Zusammenfassung):
{history}
---

AKTUELL BEKANNTE PARAMETER:
{current_params}
---

WISSENSKONTEXT (FactCards):
{context}
---

DEIN KOMMUNIKATIONSSTIL:
1. Geh ZUERST auf das ein, was der User gerade gesagt hat. Immer.
2. Stelle NIE eine Frage, die bereits beantwortet wurde. Prüfe die Parameter oben.
3. Stelle maximal EINE Folgefrage pro Antwort.
4. Wenn der User korrigiert ("eigentlich ist es...", "nein, ich meinte..."),
   bestätige das kurz: "Ah, lineare Bewegung — gut, das ändert einiges!"
5. Erkläre kurz WARUM du bestimmte Infos brauchst.
6. Fasse dein Verständnis gelegentlich zusammen.
7. Deutsch, fachlich korrekt, aber natürlich — kein Formularjargon.
8. Keine unnötigen Disclaimer.

REGEL: Wenn ein Parameter bereits oben unter AKTUELL BEKANNTE PARAMETER steht,
frage NICHT erneut danach. Niemals.

Du darfst KEINE bindenden technischen Freigaben, RFQ-Entscheidungen oder Herstellerfreigaben treffen.
"""

_FAST_GUIDANCE_PROMPT_MODE = {
    "direct_answer": "Direkte Antwort — kurz, präzise, faktenbasiert.",
    "guided_recommendation": "Orientierende Einschätzung — nennt offene Parameter, bleibt nicht-bindend.",
    "deterministic_result": "Direkte Antwort — kurz, präzise, faktenbasiert.",  # fallback
    "qualified_case": "Direkte Antwort — kurz, präzise, faktenbasiert.",        # fallback
}

FAST_GUIDANCE_PROMPT_VERSION = "fast_guidance_prompt_v1"
FAST_GUIDANCE_PROMPT_HASH = hashlib.sha256(FAST_GUIDANCE_PROMPT_TEMPLATE.encode()).hexdigest()[:12]


def build_fast_guidance_prompt(
    context: str,
    result_form: str,
    *,
    history: str = "",
    current_params: str = "",
) -> str:
    """Return the fast-path system prompt adapted to the result_form.

    Args:
        context: FactCard knowledge context.
        result_form: One of the keys in _FAST_GUIDANCE_PROMPT_MODE.
        history: Optional human-readable conversation history summary.
        current_params: Optional summary of currently known parameters.
    """
    mode = _FAST_GUIDANCE_PROMPT_MODE.get(result_form, _FAST_GUIDANCE_PROMPT_MODE["direct_answer"])
    return FAST_GUIDANCE_PROMPT_TEMPLATE.format(
        context=context or "Kein spezifischer Kontext verfügbar.",
        answer_mode=mode,
        history=history or "Noch kein Verlauf.",
        current_params=current_params or "Noch keine Parameter erfasst.",
    )
