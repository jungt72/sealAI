"""Strict Jinja2 rendering helpers for RAG report templates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import jinja2


@dataclass(frozen=True)
class RenderedPrompt:
    template_name: str
    version: str
    rendered_text: str
    hash_sha256: str

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


@lru_cache(maxsize=1)
def _env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=False,
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_rag_template(template_name: str, context: dict[str, Any]) -> str:
    """Render a RAG template with StrictUndefined enforcement.

    Raises ``jinja2.UndefinedError`` if any required variable is missing.
    """
    template = _env().get_template(template_name)
    return template.render(**dict(context or {}))


def render_and_hash_rag(
    template_name: str,
    context: dict[str, Any],
    version: str = "1.0.0",
) -> RenderedPrompt:
    """Render a RAG template and return a cryptographically traceable result."""
    rendered_text = render_rag_template(template_name, context)
    hash_sha256 = hashlib.sha256(rendered_text.encode("utf-8")).hexdigest()
    return RenderedPrompt(
        template_name=template_name,
        version=version,
        rendered_text=rendered_text,
        hash_sha256=hash_sha256,
    )


__all__ = ["TEMPLATES_DIR", "render_rag_template", "render_and_hash_rag"]
