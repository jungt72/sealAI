from __future__ import annotations
import functools
from pathlib import Path
from typing import Dict, List
import yaml

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
def get_agent_prompt(agent_id: str, lang: str = "de") -> str:
    reg = _load_registry()
    agent = (reg.get("agents") or {}).get(agent_id) or (reg.get("agents") or {}).get("supervisor")
    if not agent:
        return ""
    files: List[str] = agent.get("files") or []
    parts: List[str] = []
    for rel in files:
        p = _BASE / rel
        if p.suffix.lower() in {".md", ".txt", ".jinja2"} and p.exists():
            parts.append(_read(p))
    return "\n\n".join(x for x in parts if x)
