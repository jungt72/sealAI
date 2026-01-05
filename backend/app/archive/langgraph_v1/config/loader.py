"""Konfigurations-Loader für den Multi-Agent-Orchestrator."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import yaml

_AGENT_FILE_NAMES: tuple[str, ...] = ("agents.yaml", "agents.yml")
_ENV_DIRECTIVE = re.compile(r"^\$\{([A-Z0-9_]+)(?::([^}]+))?\}$")


@dataclass(frozen=True)
class ModelCfg:
    """Konfiguration für ein LLM-Modell."""

    name: str
    temperature: Optional[float] = None
    max_output_tokens: Optional[int] = None

    def with_overrides(self, overrides: Mapping[str, Any] | None) -> "ModelCfg":
        if not overrides:
            return self
        temperature = self.temperature
        max_tokens = self.max_output_tokens
        if "temperature" in overrides and overrides["temperature"] is not None:
            temperature = float(overrides["temperature"])
        if "max_output_tokens" in overrides and overrides["max_output_tokens"] is not None:
            max_tokens = int(overrides["max_output_tokens"])
        if "max_tokens" in overrides and overrides["max_tokens"] is not None:
            max_tokens = int(overrides["max_tokens"])
        return ModelCfg(name=self.name, temperature=temperature, max_output_tokens=max_tokens)


@dataclass(frozen=True)
class DomainPromptCfg:
    system: str
    overrides: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DomainCfg:
    name: str
    model: ModelCfg
    tools: List[str]
    routing_description: str
    prompt: DomainPromptCfg


@dataclass(frozen=True)
class SupervisorWorkerCfg:
    name: str
    description: str | None = None


@dataclass(frozen=True)
class SupervisorCfg:
    model: ModelCfg
    prompt: str
    output_mode: str
    allow_forward_message: bool
    handoff_tool_prefix: str
    workers: List[SupervisorWorkerCfg]
    max_handoffs: int


class AgentsConfig:
    """Loader und Accessor für agents.yaml Version 1."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        if data is not None:
            self._path = Path(config_path) if config_path else Path("<memory>")
            self._data = dict(data)
        else:
            path = _discover_config_path(config_path)
            self._path = path
            self._data = _read_yaml(path)

        version = int(self._data.get("version", 1))
        if version != 1:
            raise ValueError(f"Unsupported agents.yaml version: {version}")

        self._domains = self._parse_domains(self._data.get("domains") or {})
        self._supervisor = self._parse_supervisor(self._data.get("supervisor") or {})

    @property
    def path(self) -> Path:
        return self._path

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "AgentsConfig":
        return cls(config_path)

    def domain_cfg(self, name: str) -> DomainCfg:
        try:
            return self._domains[name]
        except KeyError as exc:
            raise KeyError(f"Domain '{name}' not configured in agents.yaml") from exc

    def supervisor_cfg(self) -> SupervisorCfg:
        return self._supervisor

    def domain_names(self) -> List[str]:
        return list(self._domains.keys())

    # ------------------------------------------------------------------
    # Parsing

    def _parse_domains(self, payload: Mapping[str, Any]) -> Dict[str, DomainCfg]:
        if not isinstance(payload, Mapping) or not payload:
            raise ValueError("agents.yaml muss einen Abschnitt 'domains' mit mindestens einer Domäne enthalten.")

        result: Dict[str, DomainCfg] = {}
        for name, section in payload.items():
            if not isinstance(section, Mapping):
                raise ValueError(f"Domain '{name}' muss ein Mapping sein.")

            model_cfg = _parse_model(section.get("model"), default_env="OPENAI_MODEL")
            tools = _parse_tools(section.get("tools"))

            routing_section = section.get("routing") or {}
            routing_description = str(routing_section.get("description") or "").strip()
            if not routing_description:
                raise ValueError(f"Domain '{name}' benötigt routing.description.")

            prompt_section = section.get("prompt") or {}
            if not isinstance(prompt_section, Mapping):
                raise ValueError(f"Domain '{name}' prompt muss ein Mapping sein.")
            system_prompt = str(prompt_section.get("system") or "").strip()
            if not system_prompt:
                raise ValueError(f"Domain '{name}' benötigt prompt.system.")
            overrides = dict(prompt_section.get("overrides") or {})

            prompt_cfg = DomainPromptCfg(system=system_prompt, overrides=overrides)

            result[name] = DomainCfg(
                name=name,
                model=model_cfg,
                tools=tools,
                routing_description=routing_description,
                prompt=prompt_cfg,
            )

        return result

    def _parse_supervisor(self, section: Mapping[str, Any]) -> SupervisorCfg:
        if not isinstance(section, Mapping) or not section:
            raise ValueError("agents.yaml benötigt einen Abschnitt 'supervisor'.")

        model_cfg = _parse_model(section.get("model"), fallback_value=section.get("model_name"), default_env="SUPERVISOR_MODEL")

        prompt = str(section.get("prompt") or "").strip()

        output_mode = str(section.get("output_mode") or "final").strip().lower()
        allowed_modes = {"final", "stream", "accumulate"}
        if output_mode not in allowed_modes:
            raise ValueError(f"Ungültiges supervisor.output_mode '{output_mode}'. Erlaubt: {', '.join(sorted(allowed_modes))}.")

        allow_forward_message = bool(section.get("allow_forward_message", True))

        prefix = str(section.get("handoff_tool_prefix") or "").strip() or "handoff_to_"

        workers_section = section.get("workers") or []
        if not isinstance(workers_section, list) or not workers_section:
            raise ValueError("supervisor.workers muss eine nicht-leere Liste sein.")

        workers: List[SupervisorWorkerCfg] = []
        for entry in workers_section:
            if isinstance(entry, str):
                workers.append(SupervisorWorkerCfg(name=entry.strip(), description=None))
                continue
            if not isinstance(entry, Mapping):
                raise ValueError("Jeder Eintrag in supervisor.workers muss String oder Mapping sein.")
            name = str(entry.get("name") or "").strip()
            if not name:
                raise ValueError("Jeder Worker benötigt einen Namen.")
            description = entry.get("description")
            if description is not None:
                description = str(description).strip()
            workers.append(SupervisorWorkerCfg(name=name, description=description or None))

        max_handoffs = int(section.get("max_handoffs") or 5)
        if max_handoffs <= 0:
            raise ValueError("supervisor.max_handoffs muss > 0 sein.")

        return SupervisorCfg(
            model=model_cfg,
            prompt=prompt,
            output_mode=output_mode,
            allow_forward_message=allow_forward_message,
            handoff_tool_prefix=prefix,
            workers=workers,
            max_handoffs=max_handoffs,
        )


# ---------------------------------------------------------------------------
# Hilfsfunktionen

def _discover_config_path(explicit_path: str | Path | None) -> Path:
    candidates: List[Path] = []

    def push(entry: Optional[Path]) -> None:
        if entry is None:
            return
        entry = entry.expanduser()
        if entry not in candidates:
            candidates.append(entry)

    env_path = os.getenv("AGENTS_CONFIG_PATH")
    if env_path:
        push(Path(env_path))

    if explicit_path:
        push(Path(explicit_path))

    module_dir = Path(__file__).resolve().parent
    search_roots = [
        module_dir,
        module_dir.parent,
        Path.cwd() / "app" / "langgraph" / "config",
        Path.cwd() / "backend" / "app" / "langgraph" / "config",
        Path("/app") / "app" / "langgraph" / "config",
        Path("/app") / "backend" / "app" / "langgraph" / "config",
    ]
    for root in search_roots:
        push(root)

    expanded: List[Path] = []
    for candidate in candidates:
        expanded.extend(_expand_candidate(candidate))

    seen: set[Path] = set()
    for path in expanded:
        if path in seen:
            continue
        seen.add(path)
        if path.is_file():
            return path

    display = ", ".join(str(p) for p in expanded) or "keine Kandidaten"
    raise FileNotFoundError(f"agents.yaml konnte nicht gefunden werden. Geprüfte Pfade: {display}.")


def _expand_candidate(path: Path) -> List[Path]:
    if path.suffix in {".yaml", ".yml"}:
        return [path]
    return [path / name for name in _AGENT_FILE_NAMES]


def _read_yaml(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, Mapping):
        raise ValueError(f"{path} muss ein YAML-Mapping enthalten.")
    return dict(data)


def _parse_model(
    entry: Any,
    *,
    fallback_value: Any = None,
    default_env: Optional[str],
) -> ModelCfg:
    if entry is None:
        entry = fallback_value

    temperature: Optional[float] = None
    max_output_tokens: Optional[int] = None

    if isinstance(entry, Mapping):
        name_raw = entry.get("name") or entry.get("model")
        temperature = _ensure_optional_float(entry.get("temperature"))
        max_output_tokens = _ensure_optional_int(entry.get("max_output_tokens") or entry.get("max_tokens"))
    else:
        name_raw = entry

    name = _resolve_env_reference(name_raw, fallback_env=default_env)
    if not name:
        raise ValueError("Modellname darf nicht leer sein.")

    return ModelCfg(name=name, temperature=temperature, max_output_tokens=max_output_tokens)


def _parse_tools(entry: Any) -> List[str]:
    if entry is None:
        return []
    if isinstance(entry, str):
        values = [entry]
    elif isinstance(entry, (list, tuple, set)):
        values = [str(item) for item in entry if item is not None]
    else:
        raise ValueError("tools muss Liste oder String sein.")

    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = value.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result


def _resolve_env_reference(value: Any, *, fallback_env: Optional[str]) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        match = _ENV_DIRECTIVE.match(stripped)
        if match:
            key, fallback = match.groups()
            replacement = os.getenv(key, fallback if fallback is not None else "")
            if replacement:
                return replacement
            return fallback or ""
        if stripped:
            return stripped

    if fallback_env:
        env_val = os.getenv(fallback_env)
        if env_val:
            return env_val

    if value is not None:
        return str(value)

    return ""


def _ensure_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ensure_optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
