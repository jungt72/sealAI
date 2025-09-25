# backend/app/services/langgraph/prompting.py
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Iterable, List, Dict

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

log = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Template-Verzeichnisse einsammeln (mit ENV-Override)
# -------------------------------------------------------------------
_BASE = Path(__file__).resolve().parent
_GLOBAL_PROMPTS = _BASE / "prompts"
_GLOBAL_PROMPT_TEMPLATES = _BASE / "prompt_templates"
_GRAPH_CONSULT_PROMPTS = _BASE / "graph" / "consult" / "prompts"
_DOMAINS_ROOT = _BASE / "domains"


def _collect_template_dirs() -> List[Path]:
    # Optional: zusätzliche Pfade per ENV (z. B. "/app/custom_prompts:/mnt/prompts")
    env_paths: List[Path] = []
    raw = os.getenv("SEALAI_TEMPLATE_DIRS", "").strip()
    if raw:
        for p in raw.split(":"):
            pp = Path(p).resolve()
            if pp.is_dir():
                env_paths.append(pp)

    fixed: List[Path] = [
        _GLOBAL_PROMPTS,
        _GLOBAL_PROMPT_TEMPLATES,
        _GRAPH_CONSULT_PROMPTS,
    ]

    domain_prompts: List[Path] = []
    if _DOMAINS_ROOT.is_dir():
        for p in _DOMAINS_ROOT.glob("**/prompts"):
            if p.is_dir():
                domain_prompts.append(p)

    all_candidates = env_paths + fixed + domain_prompts

    seen = set()
    result: List[Path] = []
    for p in all_candidates:
        try:
            rp = p.resolve()
        except Exception:
            rp = p
        if rp.is_dir():
            key = str(rp)
            if key not in seen:
                seen.add(key)
                result.append(rp)

    if not result:
        result = [_BASE]
        log.warning("[prompting] Keine Template-Verzeichnisse gefunden; Fallback=%s", _BASE)

    try:
        log.info("[prompting] template search dirs: %s", ", ".join(str(p) for p in result))
    except Exception:
        pass

    return result


_ENV = Environment(
    loader=FileSystemLoader([str(p) for p in _collect_template_dirs()]),
    autoescape=False,
    undefined=StrictUndefined,  # Fail-fast
    trim_blocks=True,
    lstrip_blocks=True,
)

# -------------------------------------------------------------------
# Jinja2 Filter
# -------------------------------------------------------------------
def _regex_search(value: Any, pattern: str) -> bool:
    try:
        return re.search(pattern, str(value or ""), flags=re.I) is not None
    except Exception:
        return False


def _tojson_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _tojson_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


_ENV.filters["regex_search"] = _regex_search
_ENV.filters["tojson_compact"] = _tojson_compact
_ENV.filters["tojson_pretty"] = _tojson_pretty

# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------
def render_template(name: str, /, **kwargs: Any) -> str:
    """Rendert ein Jinja2-Template und loggt die Quelle; fügt params_json automatisch hinzu."""
    if "params" in kwargs and "params_json" not in kwargs:
        try:
            kwargs["params_json"] = safe_json(kwargs["params"])
        except Exception:
            kwargs["params_json"] = "{}"

    tpl = _ENV.get_template(name)
    src_file = getattr(tpl, "filename", None)
    log.info("[prompting] loaded template '%s' from '%s'", name, src_file or "?")
    return tpl.render(**kwargs)


def messages_for_template(seq: Iterable[Any]) -> List[Dict[str, str]]:
    """Normalisiert Nachrichten in [{type, content}]."""
    out: List[Dict[str, str]] = []

    def _norm_one(m: Any) -> Dict[str, str]:
        if isinstance(m, HumanMessage):
            return {"type": "user", "content": (m.content or "").strip()}
        if isinstance(m, AIMessage):
            return {"type": "ai", "content": (m.content or "").strip()}
        if isinstance(m, SystemMessage):
            return {"type": "system", "content": (m.content or "").strip()}

        if isinstance(m, dict):
            role = (m.get("role") or m.get("type") or "").lower()
            content = (m.get("content") or "").strip()
            if role in ("user", "human"):
                t = "user"
            elif role in ("assistant", "ai"):
                t = "ai"
            elif role == "system":
                t = "system"
            else:
                t = "user"
            return {"type": t, "content": content}

        return {"type": "user", "content": (str(m) if m is not None else "").strip()}

    for m in (seq or []):
        norm = _norm_one(m)
        if norm["content"]:
            out.append(norm)
    return out


# -------------------------------------------------------------------
# JSON-Utilities
# -------------------------------------------------------------------
_CODE_FENCE_RX = re.compile(r"^```(?:json|JSON)?\s*(.*?)\s*```$", re.DOTALL)


def _extract_balanced_json(s: str) -> str:
    """Extrahiert den ersten ausgewogenen JSON-Block ({...} oder [...]) aus s."""
    if not s:
        return ""
    start_idx = None
    opener = None
    closer = None
    for i, ch in enumerate(s):
        if ch in "{[":
            start_idx = i
            opener = ch
            closer = "}" if ch == "{" else "]"
            break
    if start_idx is None:
        return s.strip()

    depth = 0
    in_string = False
    escape = False
    for j in range(start_idx, len(s)):
        ch = s[j]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return s[start_idx : j + 1].strip()
    return s[start_idx:].strip()


def strip_json_fence(text: str) -> str:
    """Entfernt ```json fences``` ODER extrahiert den ersten ausgewogenen JSON-Block."""
    if not isinstance(text, str):
        return ""
    s = text.strip()

    m = _CODE_FENCE_RX.match(s)
    if m:
        inner = m.group(1).strip()
        if inner.startswith("{") or inner.startswith("["):
            return _extract_balanced_json(inner)
        return inner

    if s.startswith("{") or s.startswith("["):
        return _extract_balanced_json(s)

    return _extract_balanced_json(s)


def safe_json(obj: Any) -> str:
    """Kompaktes JSON (UTF-8) für Prompt-Übergaben."""
    return json.dumps(obj or {}, ensure_ascii=False, separators=(",", ":"))
