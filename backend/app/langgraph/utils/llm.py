# MIGRATION: LLM Utility für OpenAI API

import os
from typing import Dict, Any
from langchain_openai import ChatOpenAI
import yaml

def load_agent_config(domain: str) -> Dict[str, Any]:
    config_path = os.path.join(os.path.dirname(__file__), "../config/agents.yaml")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config.get(domain, {})

def create_llm_for_domain(domain: str) -> ChatOpenAI:
    config = load_agent_config(domain)
    model_config = config.get("model", {})
    # Override with ENV if set (from .env.dev)
    model_name = os.getenv("OPENAI_MODEL", model_config.get("name", "gpt-4o-mini"))
    return ChatOpenAI(
        model=model_name,
        temperature=model_config.get("temperature", 0.7),
        max_tokens=model_config.get("max_output_tokens", 1000),
        openai_api_key=os.getenv("OPENAI_API_KEY")
    )

async def call_llm(llm: ChatOpenAI, prompt: str) -> str:
    response = await llm.ainvoke(prompt)
    return response.content