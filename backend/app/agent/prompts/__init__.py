"""PromptRegistry — Jinja2-basierter Singleton fuer alle SealAI-Prompts.

Invariante: Kein f-string fuer Prompts in Python.
Alle Prompts werden ausschliesslich ueber diesen Registry geladen und gerendert.

Verwendung:
    from app.agent.prompts import prompts

    system = prompts.render("gate/gate_classify.j2", {})
    system = prompts.renderer_system_prompt("technical_preselection", context)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent

# Mapping outward_class → Template-Pfad relativ zu PROMPTS_DIR
_RENDERER_TEMPLATE_MAP: dict[str, str] = {
    "conversational_answer": "renderer/conversational.j2",
    "structured_clarification": "renderer/clarification.j2",
    "governed_state_update": "renderer/state_update.j2",
    "technical_preselection": "renderer/preselection.j2",
    "candidate_shortlist": "renderer/candidate_list.j2",
    "inquiry_ready": "renderer/inquiry_ready.j2",
}

_BASE_TEMPLATE = "renderer/base.j2"
_FALLBACK_RENDERER_TEMPLATE = "renderer/conversational.j2"


class PromptRegistry:
    """Jinja2-basierter Template-Registry fuer alle SealAI-Prompts.

    Laedt Templates aus dem ``prompts/``-Verzeichnis on demand.
    Unbekannte Variablen im Template fuehren zu einem Fehler (StrictUndefined),
    damit fehlende Context-Keys sofort auffallen.
    """

    def __init__(self, prompts_dir: Path | None = None) -> None:
        self._prompts_dir = prompts_dir or PROMPTS_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(self._prompts_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )

    def render(self, template_path: str, context: dict[str, Any]) -> str:
        """Rendere ein einzelnes Template.

        Args:
            template_path: Relativer Pfad innerhalb des prompts/-Verzeichnisses,
                           z.B. "gate/gate_classify.j2".
            context: Variablen fuer das Template.

        Returns:
            Gerenderter String.

        Raises:
            TemplateNotFound: Wenn das Template nicht gefunden wird.
            jinja2.UndefinedError: Wenn eine Variable im Template fehlt.
        """
        template = self._env.get_template(template_path)
        return template.render(**context)

    def renderer_system_prompt(
        self,
        outward_class: str,
        context: dict[str, Any],
    ) -> str:
        """Erzeuge den kombinierten System-Prompt fuer den Response-Renderer.

        Laedt immer ``renderer/base.j2`` (Disclaimer + Rahmenbedingungen) und
        haengt das outward-class-spezifische Template an.

        Args:
            outward_class: z.B. "technical_preselection", "conversational_answer".
            context: State-Snapshot (von ``build_renderer_context()``).

        Returns:
            Kombinierter System-Prompt (base + class-specific).
        """
        ctx = {"outward_class": outward_class, **context}

        base = self.render(_BASE_TEMPLATE, ctx)

        template_path = _RENDERER_TEMPLATE_MAP.get(outward_class)
        if template_path is None:
            logger.warning(
                "[prompts] Unbekannte outward_class '%s' — Fallback auf %s",
                outward_class,
                _FALLBACK_RENDERER_TEMPLATE,
            )
            template_path = _FALLBACK_RENDERER_TEMPLATE

        class_specific = self.render(template_path, ctx)
        return f"{base}\n\n{class_specific}"

    def list_templates(self) -> list[str]:
        """Alle bekannten Template-Pfade auflisten (fuer Tests / Debugging)."""
        return sorted(self._env.loader.list_templates())  # type: ignore[union-attr]


# Singleton — einmalig beim Import erstellt
prompts = PromptRegistry()

# ---------------------------------------------------------------------------
# Legacy prompt version constants — moved from agent/agent/prompts.py (G1.1 Move 16)
# ---------------------------------------------------------------------------
import hashlib
from prompts.builder import PromptBuilder  # top-level prompts package

REASONING_PROMPT_VERSION: str = PromptBuilder.PROMPT_VERSION
REASONING_PROMPT_HASH: str = hashlib.sha256(REASONING_PROMPT_VERSION.encode()).hexdigest()[:12]

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
    "deterministic_result": "Direkte Antwort — kurz, präzise, faktenbasiert.",
    "qualified_case": "Direkte Antwort — kurz, präzise, faktenbasiert.",
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
    """Return the fast-path system prompt adapted to the result_form."""
    mode = _FAST_GUIDANCE_PROMPT_MODE.get(result_form, _FAST_GUIDANCE_PROMPT_MODE["direct_answer"])
    return FAST_GUIDANCE_PROMPT_TEMPLATE.format(
        context=context or "Kein spezifischer Kontext verfügbar.",
        answer_mode=mode,
        history=history or "Noch kein Verlauf.",
        current_params=current_params or "Noch keine Parameter erfasst.",
    )
