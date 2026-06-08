"""L1 system-prompt assembly (Jinja2, StrictUndefined).

Prinzipien §4.1 / build-spec §12: Jinja **assembles** context (anrede, grounding facts,
case context, flags); it **never decides** domain content. StrictUndefined makes a missing
variable a hard error rather than a silent gap.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from sealai_v2.core.contracts import Flags, GroundingFact

_TEMPLATE_DIR = Path(__file__).resolve().parent
_TEMPLATE_NAME = "system_l1.jinja"


class PromptAssembler:
    """Renders ``system_l1.jinja`` into the L1 system prompt. Template file read happens once
    here (at construction) — keeping the pure ``core`` generator I/O-free."""

    def __init__(self, template_dir: Path | None = None) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(template_dir or _TEMPLATE_DIR)),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
        )
        self._template = self._env.get_template(_TEMPLATE_NAME)

    def system_prompt(
        self,
        *,
        anrede: str = "du",
        grounding_facts: list[GroundingFact] | None = None,
        case_context: list[dict] | None = None,
        flags: Flags | None = None,
    ) -> str:
        flags = flags or Flags()
        gf = [{"text": f.text, "quelle": f.quelle} for f in (grounding_facts or [])]
        return self._template.render(
            anrede=anrede,
            grounding_facts=gf,
            case_context=case_context or [],
            compliance_hint=flags.compliance_hint,
            safety_critical=flags.safety_critical,
        )
