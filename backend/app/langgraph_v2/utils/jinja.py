"""Jinja2 helpers for LangGraph v2 prompt rendering."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, StrictUndefined

# Default prompt directory (shared across v2 nodes).
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


@lru_cache(maxsize=1)
def _env() -> Environment:
    loader = FileSystemLoader(str(PROMPTS_DIR))
    return Environment(
        loader=loader,
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_template(template_name: str, context: Dict[str, Any] | None = None, /, **kwargs: Any) -> str:
    """
    Render a prompt template from PROMPTS_DIR with strict evaluation.

    Raises FileNotFoundError if the template does not exist.
    """
    template = _env().get_template(template_name)
    data = dict(context or {})
    if kwargs:
        data.update(kwargs)
    return template.render(**data)


__all__ = ["PROMPTS_DIR", "render_template"]
