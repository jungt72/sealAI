"""Hash-based Mistral/OpenAI prompt-cache key construction (Phase 1 of the LangGraph-suitability
audit).

Audit finding: the pipeline's ``prompt_cache_key`` values were static string literals
(``"sealai-v2-l1"`` etc.) — safe (no dynamic/tenant data embedded) but not versioned: a prompt
change does not roll the key, so a stale cache-key mapping to changed content is possible. This
module adds a hash-based scheme WITHOUT requiring every call site to switch — existing literal keys
may remain wherever a clean static-only prompt string isn't already available (see
``pipeline.build_pipeline`` for which stage(s) were switched and why).

Target format: ``sealai:global:{stage}:{model}:{static_prompt_hash}``. The hash is over the STATIC
prompt only — callers must never pass a fully-rendered, per-turn prompt (with case data inlined)
here, or the "global" cache key stops being shared across turns/tenants, defeating its purpose.
"""

from __future__ import annotations

import hashlib


def normalize_prompt(text: str) -> str:
    """Deterministic normalization before hashing: strip trailing whitespace per line and drop
    trailing blank lines, so a purely cosmetic re-save (trailing spaces, one extra newline) does not
    roll the cache key, while any real content change still does."""
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def static_prompt_hash(static_prompt: str) -> str:
    """Short, stable, deterministic hash of a STATIC prompt string. 16 hex chars (64 bits) is ample
    to avoid accidental collisions between genuinely different prompts while keeping the resulting
    cache-key string short."""
    return hashlib.sha256(normalize_prompt(static_prompt).encode("utf-8")).hexdigest()[
        :16
    ]


def build_prompt_cache_key(stage: str, model: str, static_prompt: str) -> str:
    """``sealai:global:{stage}:{model}:{static_prompt_hash}``. ``stage``/``model`` are short,
    caller-controlled labels (e.g. ``"l1"``, ``"gpt-5.1"``) — never tenant/case/user/session/date/
    raw-text data. The hash carries no recoverable content; changing ``static_prompt`` changes the
    key, so an old cache entry is never silently reused against different prompt content."""
    return f"sealai:global:{stage}:{model}:{static_prompt_hash(static_prompt)}"
