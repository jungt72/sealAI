# backend/app/langgraph/utils/llm.py
import os
from typing import Any, Dict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.langgraph.config.loader import AgentsConfig
from app.langgraph.nodes.members import _OfflineDomainModel, _use_offline_mode


def load_agent_config(domain: str) -> Dict[str, Any]:
    config = AgentsConfig.load()
    cfg = config.domain_cfg(domain)
    model_cfg = cfg.model.with_overrides(cfg.prompt.overrides)
    return {
        "model": {
            "name": model_cfg.name,
            "temperature": model_cfg.temperature,
            "max_output_tokens": model_cfg.max_output_tokens,
        },
        "tools": {"list": list(cfg.tools)},
        "prompt": {
            "system": cfg.prompt.system,
            "overrides": dict(cfg.prompt.overrides),
        },
        "routing": {"description": cfg.routing_description},
    }


def create_llm_for_domain(domain: str) -> BaseChatModel:
    cfg = AgentsConfig.load().domain_cfg(domain)
    model_cfg = cfg.model.with_overrides(cfg.prompt.overrides)
    if _use_offline_mode():
        # Offline-Stub entspricht dem Verhalten der Agenten-Fabrik.
        return _OfflineDomainModel(cfg, agent_name=cfg.name, resolved_model=model_cfg)

    kwargs: Dict[str, Any] = {
        "model": model_cfg.name,
        "openai_api_key": os.getenv("OPENAI_API_KEY"),
    }
    if model_cfg.temperature is not None:
        kwargs["temperature"] = model_cfg.temperature
    if model_cfg.max_output_tokens is not None:
        kwargs["max_tokens"] = model_cfg.max_output_tokens
    return ChatOpenAI(**kwargs)


async def call_llm(llm: BaseChatModel, prompt: str) -> str:
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    content = getattr(response, "content", None)
    if isinstance(content, str):
        return content
    return str(content or "")
