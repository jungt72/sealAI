"""Helpers for loading LangGraph prompt templates from disk."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, StrictUndefined
from langchain_core.prompts import ChatPromptTemplate

PROMPTS_DIR = Path(__file__).resolve().parent
_JINJA_ENV = Environment(autoescape=False, undefined=StrictUndefined)


def _resolve_template_path(filename: str) -> Path:
    """Return an absolute path for the given template name inside PROMPTS_DIR."""
    normalized = filename.strip()
    if not normalized:
        raise ValueError("Template filename must not be empty.")
    candidate = (PROMPTS_DIR / normalized).resolve()
    try:
        candidate.relative_to(PROMPTS_DIR)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Template '{filename}' must be located inside {PROMPTS_DIR}.") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"Prompt template '{filename}' not found in {PROMPTS_DIR}.")
    return candidate


@lru_cache(maxsize=None)
def _load_template_source(filename: str) -> str:
    path = _resolve_template_path(filename)
    return path.read_text(encoding="utf-8")

@lru_cache(maxsize=None)
def _load_compiled_template(filename: str):
    source = _load_template_source(filename)
    return _JINJA_ENV.from_string(source)


def load_template_text(filename: str) -> str:
    """Return the raw template text (cached)."""
    return _load_template_source(filename)


def load_jinja_chat_prompt(filename: str) -> ChatPromptTemplate:
    """Build a ChatPromptTemplate backed by the given Jinja2 template."""
    template = _load_template_source(filename)
    return ChatPromptTemplate.from_template(template, template_format="jinja2")


def render_prompt(filename: str, context: Dict[str, Any] | None = None, /, **kwargs: Any) -> str:
    """Render a template to plain text using strict evaluation."""
    template = _load_compiled_template(filename)
    data = dict(context or {})
    if kwargs:
        data.update(kwargs)
    return template.render(**data)


__all__ = ["load_jinja_chat_prompt", "load_template_text", "render_prompt", "PROMPTS_DIR"]
