"""Agent-Fabriken für die LangGraph-Domänen gemäß agents.yaml Version 1."""

from __future__ import annotations

import inspect
import os
import re
from functools import lru_cache
from importlib import import_module
from typing import Any, Callable, Dict, List, Sequence

from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.prebuilt import create_react_agent

from app.langgraph.config.loader import AgentsConfig, DomainCfg, ModelCfg

_TOOL_PACKAGE_PREFIX = "app.langgraph.tools"


@lru_cache(maxsize=1)
def _config() -> AgentsConfig:
    return AgentsConfig.load()


def _qualify_tool_path(path: str) -> str:
    candidate = (path or "").strip()
    if not candidate:
        raise ValueError("Toolpfad darf nicht leer sein.")
    if candidate.startswith(_TOOL_PACKAGE_PREFIX):
        return candidate
    if candidate.startswith("app."):
        return candidate
    if candidate.startswith("."):
        return f"{_TOOL_PACKAGE_PREFIX}{candidate}"
    return f"{_TOOL_PACKAGE_PREFIX}.{candidate}"


def _resolve_tools(path: str) -> List[Callable[..., Any]]:
    qualified = _qualify_tool_path(path)
    try:
        module = import_module(qualified)
    except ModuleNotFoundError as exc:
        if exc.name != qualified:
            raise
        module_name, attr_name = qualified.rsplit(".", 1)
        module = import_module(module_name)
        attr = getattr(module, attr_name, None)
        if attr is None:
            raise AttributeError(f"Tool '{path}' konnte nicht aufgelöst werden.")
        if inspect.ismodule(attr):
            return _collect_public_functions(attr)
        if not callable(attr):
            raise TypeError(f"'{path}' ist kein ausführbares Tool.")
        return [attr]

    return _collect_public_functions(module)


def _collect_public_functions(module: Any) -> List[Callable[..., Any]]:
    names: Sequence[str]
    if hasattr(module, "__all__"):
        names = module.__all__  # type: ignore[assignment]
    else:
        names = [name for name in dir(module) if not name.startswith("_")]

    functions: List[Callable[..., Any]] = []
    for name in names:
        attr = getattr(module, name, None)
        if inspect.isfunction(attr):
            functions.append(attr)
    if not functions:
        raise ValueError(f"Modul '{module.__name__}' enthält keine ausführbaren Funktionen.")
    return functions


def _create_agent_from_domain(cfg: DomainCfg, *, agent_name_override: str | None = None):
    tool_functions: List[Callable[..., Any]] = []
    seen: set[Callable[..., Any]] = set()

    for entry in cfg.tools:
        for tool in _resolve_tools(entry):
            if tool not in seen:
                seen.add(tool)
                tool_functions.append(tool)

    name = agent_name_override or cfg.name
    model = _build_model(cfg, agent_name=name)

    if not tool_functions:
        tools_arg: Sequence[Callable[..., Any]] = ()
    else:
        tools_arg = tool_functions

    return create_react_agent(
        model=model,
        tools=tools_arg,
        name=name,
        prompt=cfg.prompt.system,
    )


def create_domain_agent(name: str):
    """Erzeugt einen Agenten anhand der Domain-Konfiguration."""
    cfg = _config().domain_cfg(name)
    return _create_agent_from_domain(cfg, agent_name_override=name)


def create_material_agent():
    return create_domain_agent("material")


def create_profil_agent():
    return create_domain_agent("profil")


def create_validierung_agent():
    return create_domain_agent("validierung")


def create_standards_agent():
    return create_domain_agent("standards")


def _build_model(cfg: DomainCfg, *, agent_name: str) -> BaseChatModel:
    resolved_model = cfg.model.with_overrides(cfg.prompt.overrides)
    if _use_offline_mode():
        return _OfflineDomainModel(cfg, agent_name=agent_name, resolved_model=resolved_model)

    kwargs: Dict[str, Any] = {"model": resolved_model.name}
    if resolved_model.temperature is not None:
        kwargs["temperature"] = resolved_model.temperature
    if resolved_model.max_output_tokens is not None:
        kwargs["max_tokens"] = resolved_model.max_output_tokens

    return ChatOpenAI(**kwargs)


def _use_offline_mode() -> bool:
    forced = os.getenv("LANGGRAPH_USE_FAKE_LLM")
    if forced and forced.strip().lower() in {"1", "true", "yes", "on"}:
        return True
    api_key = os.getenv("OPENAI_API_KEY", "")
    return not api_key or api_key.lower() in {"dummy", "test"}


class _OfflineDomainModel(BaseChatModel):
    """Deterministischer Fallback, der Domain-Verhalten heuristisch simuliert."""

    def __init__(self, cfg: DomainCfg, *, agent_name: str, resolved_model: ModelCfg) -> None:
        super().__init__()
        self._cfg = cfg
        self._agent_name = agent_name
        self._model = resolved_model

    @property
    def _llm_type(self) -> str:  # pragma: no cover - debug helper
        return f"{self._cfg.name}_offline_stub"

    def _generate(  # type: ignore[override]
        self,
        messages: List[HumanMessage | AIMessage | Any],
        stop: List[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        content = self._respond(messages)
        message = AIMessage(content=content, name=self._agent_name)
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(  # pragma: no cover - sync fallback
        self,
        messages: List[HumanMessage | AIMessage | Any],
        stop: List[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    def bind_tools(self, *_args: Any, **_kwargs: Any) -> "_OfflineDomainModel":
        return self

    def _respond(self, messages: List[Any]) -> str:
        user_text = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                user_text = msg.content if isinstance(msg.content, str) else str(msg.content)
                break
            if isinstance(msg, dict) and msg.get("role") in {"user", "human"}:
                user_text = str(msg.get("content") or "")
                break

        handler = _OFFLINE_HANDLERS.get(self._cfg.name, _offline_default)
        return handler(user_text)


def _offline_material_handler(user_text: str) -> str:
    numbers: List[float] = []
    for match in re.findall(r"([\d.,]+)", user_text):
        cleaned = match.replace(",", ".")
        if cleaned.strip(".") == "":
            continue
        try:
            numbers.append(float(cleaned))
        except ValueError:
            continue
        if len(numbers) >= 4:
            break
    if len(numbers) >= 4:
        length, width, thickness, density = numbers[:4]
    else:
        length = width = thickness = density = None

    if None in (length, width, thickness, density):
        return (
            "Zur Berechnung benötige ich Länge, Breite, Stärke und Dichte. "
            "Beispiel: 2m x 1m x 0.01m, Dichte 7800 kg/m³."
        )

    volume = length * width * thickness
    weight = volume * density
    return (
        f"Berechne Gewicht: Volumen={volume:.3f} m³, Gewicht={weight:.2f} kg. "
        "Verschnitt optional separat angeben."
    )


def _offline_profil_handler(user_text: str) -> str:
    goal = "Profiling-Ziel unbekannt"
    context = "Kein Kontext angegeben"
    if "marketing" in user_text.lower():
        goal = "Marketing-Persona erstellen"
        context = "Branche: Marketing, Fokus auf Kampagnen"
    return (
        '{ "ziel": "%s", "kontext": "%s", "anforderungen": ["Daten sammeln"], "risiken": ["Unklare Datenqualität"] }'
        % (goal, context)
    )


def _offline_validierung_handler(user_text: str) -> str:
    issues = []
    lowered = user_text.lower()
    if "temperatur" not in lowered:
        issues.append({"regel": "Temperatur angegeben", "schwere": "hoch", "hinweis": "Temperatur ergänzen"})
    if "druck" not in lowered:
        issues.append({"regel": "Druck definiert", "schwere": "mittel", "hinweis": "Betriebsdruck angeben"})
    if issues:
        return f'Fail, {{"verstöße": {issues}, "zusammenfassung": "Parameter fehlen"}}'
    return 'Pass, {"verstöße": [], "zusammenfassung": "Alle Regeln erfüllt"}'


def _offline_standards_handler(user_text: str) -> str:
    match = re.search(r"(DIN\s*EN(?:\s*ISO)?\s*[0-9\-]+)", user_text, flags=re.IGNORECASE)
    if match:
        code = match.group(1).strip()
        from app.langgraph.tools.standards_lookup import find_standard

        return find_standard(code)
    return "Bitte nenne die konkrete Norm (z.B. DIN EN ISO 3302-1)."


def _offline_default(_user_text: str) -> str:
    return "Offline-Modus aktiv – bitte im Produktivbetrieb erneut versuchen."


_OFFLINE_HANDLERS: Dict[str, Callable[[str], str]] = {
    "material": _offline_material_handler,
    "profil": _offline_profil_handler,
    "validierung": _offline_validierung_handler,
    "standards": _offline_standards_handler,
}
