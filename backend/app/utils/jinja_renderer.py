"""Strict Jinja rendering helpers with cryptographic prompt tracing."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import jinja2

from app._legacy_v2.state import RenderedPrompt

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


@lru_cache(maxsize=1)
def _env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(PROMPTS_DIR)),
        autoescape=False,
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_and_hash(template_path: str, context: dict[str, Any], version: str = "1.0.0") -> RenderedPrompt:
    """
    Render a prompt template and return a cryptographically verifiable trace.

    Caller nodes MUST pass the full graph state as a dict in context (for example:
    ``context={"state": state.model_dump()}``) so templates can branch on current
    state and keep behavior fully auditable.
    """
    template = _env().get_template(template_path)
    rendered_text = template.render(**dict(context or {}))
    hash_sha256 = hashlib.sha256(rendered_text.encode("utf-8")).hexdigest()
    return RenderedPrompt(
        template_name=template_path,
        version=version,
        rendered_text=rendered_text,
        hash_sha256=hash_sha256,
    )


__all__ = ["PROMPTS_DIR", "render_and_hash"]
