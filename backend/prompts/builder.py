"""
PromptBuilder — SealAI Jinja2 prompt construction layer.

All LLM prompts pass through this class. No raw prompt strings in
production code. StrictUndefined enforced — missing template variables
raise immediately rather than silently rendering empty.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from prompts.personas.thomas_reiter import PRODUCT_LAWS, THOMAS_REITER_PERSONA

log = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class PromptBuilder:
    """Builds SealAI prompts from Jinja2 templates with Thomas Reiter persona."""

    PROMPT_VERSION: str = "v2.0"

    def __init__(self, template_dir: Optional[Path] = None) -> None:
        resolved = template_dir or _TEMPLATE_DIR
        self.env = Environment(
            loader=FileSystemLoader(str(resolved)),
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
            keep_trailing_newline=True,
            autoescape=False,
        )

    def _build(
        self,
        template_name: str,
        context: dict,
        include_laws: bool = False,
    ) -> str:
        start = time.perf_counter()
        template = self.env.get_template(template_name)
        rendered = template.render(**context)
        persona_prefix = THOMAS_REITER_PERSONA
        laws_block = f"\n{PRODUCT_LAWS}" if include_laws else ""
        result = f"{persona_prefix}{laws_block}\n\n{rendered}".strip()
        # Collapse triple+ blank lines to double
        import re
        result = re.sub(r"\n{3,}", "\n\n", result)
        elapsed_ms = (time.perf_counter() - start) * 1000
        tokens_approx = len(result) // 4
        log.info(
            "[PromptBuilder] template=%s version=%s tokens_approx=%d ms=%.1f",
            template_name,
            self.PROMPT_VERSION,
            tokens_approx,
            elapsed_ms,
        )
        return result

    def fast_brain(
        self,
        parameters: dict,
        missing_params: list[str],
    ) -> str:
        """Prompt for the fast-brain / pre-qualification step."""
        return self._build(
            "fast_brain.j2",
            {
                "parameters": parameters,
                "missing_params": missing_params,
                "assumptions": [],
            },
            include_laws=False,
        )

    def governed(
        self,
        parameters: dict,
        assumptions: list,
        fact_cards: list,
        req_class: Optional[str] = None,
        include_tools: bool = False,
    ) -> str:
        """Prompt for the governed qualification step (includes product laws).

        Args:
            include_tools: If True, the submit_claim tool instructions are injected
                           via the tool_section block. Set True for reasoning_node.
        """
        return self._build(
            "governed_context.j2",
            {
                "parameters": parameters,
                "assumptions": assumptions,
                "fact_cards": fact_cards,
                "req_class": req_class,
                "include_tools": include_tools,
            },
            include_laws=True,
        )

    def conversation(
        self,
        case_summary: Optional[str] = None,
    ) -> str:
        """Prompt for the conversation / free-dialog layer."""
        return self._build(
            "conversation.j2",
            {
                "parameters": {},
                "assumptions": [],
                "case_summary": case_summary,
            },
            include_laws=False,
        )

    def final_answer(
        self,
        parameters: dict,
        assumptions: list,
        req_class: str,
        open_points: list[str],
        rfq_admissible: bool,
    ) -> str:
        """Prompt for final answer / RFQ-ready summary (includes product laws)."""
        return self._build(
            "final_answer.j2",
            {
                "parameters": parameters,
                "assumptions": assumptions,
                "req_class": req_class,
                "open_points": open_points,
                "rfq_admissible": rfq_admissible,
            },
            include_laws=True,
        )
