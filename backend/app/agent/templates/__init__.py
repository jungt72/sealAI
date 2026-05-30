"""V1.6 chat-style Jinja2 template family and registry (Blueprint §10 / §18).

Additive to the existing prompt infrastructure under ``app/agent/prompts``.
Templates live under ``chat/`` and are rendered through the canonical
``PromptRegistry`` class. See :mod:`app.agent.templates.registry`.
"""

from __future__ import annotations

from app.agent.templates.no_go_guard import (
    FINAL_RELEASE_PATTERNS,
    FORBIDDEN_NORMAL_TURN_PHRASES,
    VISUAL_FORBIDDEN_PHRASES,
    NoGoPhraseError,
    assert_no_no_go,
    detect_no_go_phrases,
    sanitize_no_go,
)
from app.agent.templates.registry import (
    CHAT_TEMPLATE_REGISTRY,
    ChatTemplateMeta,
    get_chat_template_meta,
    render_chat_reply,
)

__all__ = [
    "CHAT_TEMPLATE_REGISTRY",
    "ChatTemplateMeta",
    "get_chat_template_meta",
    "render_chat_reply",
    "FORBIDDEN_NORMAL_TURN_PHRASES",
    "VISUAL_FORBIDDEN_PHRASES",
    "FINAL_RELEASE_PATTERNS",
    "NoGoPhraseError",
    "assert_no_no_go",
    "detect_no_go_phrases",
    "sanitize_no_go",
]
