from __future__ import annotations

import logging
from typing import Any

from app.agent.prompts import prompts

log = logging.getLogger(__name__)


def render_communication_template(
    template_name: str,
    context: dict[str, Any] | None = None,
    *,
    fallback: str = "",
) -> str:
    """Render a user-facing communication template with a bounded fallback.

    The fallback keeps production paths available if a template is missing, but
    callers should treat any fallback use as migration debt.
    """

    try:
        rendered = prompts.render(
            f"communication/{template_name}.j2",
            context or {},
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "[communication_template] render failed template=%s reason=%s",
            template_name,
            exc.__class__.__name__,
        )
        return str(fallback or "").strip()
    if not str(rendered or "").strip():
        return str(fallback or "").strip()
    if _looks_like_test_stub_render(rendered, context or {}):
        return str(fallback or "").strip()
    return str(rendered or "").strip()


def _looks_like_test_stub_render(rendered: Any, context: dict[str, Any]) -> bool:
    """Detect the lightweight test Jinja stub, which echoes context lines.

    Production uses real Jinja2. Some local test environments rely on a tiny
    conftest stub whose ``Template.render()`` returns sorted ``key: value``
    lines instead of template output. Visible communication must never expose
    those context dumps, so callers fall back to their safe deterministic text.
    """

    text = str(rendered or "").strip()
    if not text or not context:
        return False
    stub_text = "\n".join(
        f"{key}: {value}" for key, value in sorted(context.items())
    ).strip()
    return text == stub_text
