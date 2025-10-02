from __future__ import annotations
import functools
from pathlib import Path
from typing import Dict, List, Optional, Any
import os
import yaml

from app.services.langgraph.prompting import render_template, build_system_prompt_from_parts

_BASE = Path(__file__).resolve().parent / "prompts"


@functools.lru_cache(maxsize=64)
def _load_registry() -> Dict:
    p = _BASE / "registry.yaml"
    if not p.exists():
        return {"agents": {}}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"agents": {}}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


@functools.lru_cache(maxsize=256)
def get_agent_prompt(agent_id: str, lang: str = "de", context: Optional[Dict[str, Any]] = None) -> str:
    """Lädt den Agentenprompt. Rendert Jinja‑Templates und hängt optional
    `context['rag_context']` bzw. `context['rag_docs']` tokenbewusst an.
    """
    reg = _load_registry()
    agent = (reg.get("agents") or {}).get(agent_id) or (reg.get("agents") or {}).get("supervisor")
    if not agent:
        return ""
    files: List[str] = agent.get("files") or []
    parts: List[str] = []
    for rel in files:
        p = _BASE / rel
        if not p.exists():
            continue
        suf = p.suffix.lower()
        if suf == ".jinja2":
            try:
                parts.append(render_template(p.name, **(context or {})))
                continue
            except Exception as exc:
                # Log and fallback to raw template text to avoid breaking runtime
                try:
                    import logging

                    logging.getLogger(__name__).warning(
                        "[prompt_registry] render_failed %s %s", p, str(exc)
                    )
                except Exception:
                    pass
                parts.append(_read(p))
                continue
        if suf in {".md", ".txt"}:
            parts.append(_read(p))

    joined = "\n\n".join(x for x in parts if x)

    # If context contains rag_context (summary) or rag_docs, try to build a
    # token-budgeted system prompt. Default max tokens from ENV or 3000.
    try:
        max_toks = int(os.getenv("PROMPT_MAX_TOKENS", "3000"))
    except Exception:
        max_toks = 3000
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    if context and (context.get("rag_context") or context.get("rag_docs")):
        return build_system_prompt_from_parts(
            joined,
            summary=context.get("rag_context"),
            rag_docs=context.get("rag_docs"),
            max_tokens=max_toks,
            model=model,
        )

    return joined
