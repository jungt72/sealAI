"""Jinja2 helpers for LangGraph v2 prompt rendering."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, StrictUndefined, FileSystemBytecodeCache, TemplateNotFound

# Default prompt directory (shared across v2 nodes).
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
CACHE_DIR =  Path("/tmp/sealai_jinja_cache")


@lru_cache(maxsize=1)
def _env() -> Environment:
    loader = FileSystemLoader(str(PROMPTS_DIR))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return Environment(
        loader=loader,
        autoescape=False,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        bytecode_cache=FileSystemBytecodeCache(directory=str(CACHE_DIR)),
    )


def render_template(
    template_name: str, 
    context: Dict[str, Any] | None = None, 
    /, 
    *,
    tenant_id: str | None = None,
    **kwargs: Any
) -> str:
    """
    Render a prompt template from PROMPTS_DIR with strict evaluation.
    
    Supports Multi-Tenancy:
    If 'tenant_id' is provided, attempts to load 'prompts/{tenant_id}/{template_name}'.
    Falls back to 'prompts/{template_name}' if the tenant override does not exist.

    Raises FileNotFoundError/TemplateNotFound if the template does not exist.
    """
    env = _env()
    target_name = template_name

    # Tenant Override Logic
    if tenant_id:
        # Check if tenant specific template exists (e.g. "acme/supervisor_prompt.j2")
        tenant_template_name = f"{tenant_id}/{template_name}"
        try:
            # Try to load (will raise TemplateNotFound if missing)
            env.get_template(tenant_template_name)
            target_name = tenant_template_name
        except TemplateNotFound:
            # Fallback to default
            pass

    template = env.get_template(target_name)
    data = dict(context or {})
    if kwargs:
        data.update(kwargs)
    return template.render(**data)


__all__ = ["PROMPTS_DIR", "render_template"]
