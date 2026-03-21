"""Jinja2 render helper for prompt templates.

Recreated after app/common/jinja.py was lost during the _legacy_v2 cleanup.
Provides a simple render_template() function used by rag_ingest.py.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import jinja2

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


@lru_cache(maxsize=1)
def _env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(PROMPTS_DIR)),
        autoescape=False,
        undefined=jinja2.Undefined,  # permissive — missing vars render as empty string
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_template(template_name: str, context: Optional[Dict[str, Any]] = None) -> str:
    """Render a Jinja2 prompt template and return the rendered string.

    Args:
        template_name: filename relative to the prompts directory (e.g. "rag_metadata_extractor.j2")
        context: optional dict of template variables; defaults to empty dict
    """
    template = _env().get_template(template_name)
    return template.render(**(context or {}))


__all__ = ["render_template", "PROMPTS_DIR"]
