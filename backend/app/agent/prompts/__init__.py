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
