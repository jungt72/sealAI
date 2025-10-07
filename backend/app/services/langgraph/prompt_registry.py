from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.services.langgraph.prompting import (
    render_template,
    build_system_prompt_from_parts,
)

_BASE = Path(__file__).resolve().parent / "prompts"

# ------------------------------------------------------------
# Registry laden (cached) – rein statisch und hashbar
# ------------------------------------------------------------
@functools.lru_cache(maxsize=64)
def _load_registry() -> Dict[str, Any]:
    p = _BASE / "registry.yaml"
    if not p.exists():
        return {"agents": {}}
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        return {"agents": {}}
    data.setdefault("agents", {})
    return data


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


# ------------------------------------------------------------
# Nur die Dateiliste (Pfade) cachen – KEIN context hier
# ------------------------------------------------------------
@functools.lru_cache(maxsize=256)
def _files_for(agent_id: str, lang: str = "de") -> Tuple[str, ...]:
    """
    Liefert die absoluten Pfade der Prompt-Bestandteile für einen Agenten.
    Rückgabe als Tuple[str,...] (hashbar für LRU).
    """
    reg = _load_registry()
    agents = reg.get("agents") or {}
    agent = agents.get(agent_id) or agents.get("supervisor") or {}
    files: List[str] = agent.get("files") or []
    paths: List[str] = []
    for rel in files:
        p = _BASE / rel
        if p.exists():
            paths.append(str(p.resolve()))
    return tuple(paths)


# ------------------------------------------------------------
# Öffentliches API – KEIN Cache wegen context (dict)!
# ------------------------------------------------------------
def get_agent_prompt(
    agent_id: str,
    lang: str = "de",
    context: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Baut den endgültigen Prompt für einen Agenten.
    - Statische Dateiliste kommt aus dem Cache (_files_for)
    - Rendering mit context (dict) erfolgt *ohne* Cache
    - Optionaler RAG-Anhang via build_system_prompt_from_parts
    """
    parts: List[str] = []
    for abs_path in _files_for(agent_id, lang):
        p = Path(abs_path)
        suf = p.suffix.lower()
        if suf == ".jinja2":
            # Jinja-Template mit dynamischem context – ohne Cache!
            try:
                # render_template erwartet den Template-Namen im prompts-Root
                parts.append(render_template(p.name, **(context or {})))
            except Exception as exc:
                # Fallback: Raw lesen, um Runtime nicht zu brechen
                try:
                    import logging
                    logging.getLogger(__name__).warning(
                        "[prompt_registry] render_failed %s %s", p, str(exc)
                    )
                except Exception:
                    pass
                parts.append(_read(p))
        elif suf in {".md", ".txt"}:
            parts.append(_read(p))
        else:
            # Unbekanntes Suffix – sicherheitshalber als Text laden
            parts.append(_read(p))

    joined = "\n\n".join(x for x in parts if x)

    # Token-budgetiertes Zusammenführen inkl. RAG-Kontext, falls vorhanden
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
