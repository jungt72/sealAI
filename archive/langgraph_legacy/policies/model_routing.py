# backend/app/services/langgraph/policies/model_routing.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal, Dict, Any
import os

ModelName = Literal["gpt-5-nano", "gpt-5-mini", "gpt-5"]

@dataclass
class RoutingContext:
    node: str
    confidence: Optional[float] = None
    red_flags: bool = False
    regulatory: bool = False
    ambiguous: bool = False
    hint: Optional[ModelName] = None

# Defaults stärker auf gpt-5-mini ausgerichtet
DEFAULTS: Dict[str, ModelName] = {
    "normalize_intent": "gpt-5-mini",
    "pre_extract": "gpt-5-mini",
    "domain_router": "gpt-5-mini",
    "ask_missing": "gpt-5-mini",
    "critic_light": "gpt-5-mini",
    "explain": "gpt-5-mini",
    "info_graph": "gpt-5-mini",
    "market_graph": "gpt-5-mini",
    "service_graph": "gpt-5-mini",
}

def select_model(ctx: RoutingContext) -> ModelName:
    if ctx.hint:
        return ctx.hint
    if ctx.red_flags or ctx.regulatory:
        return "gpt-5"
    if ctx.confidence is not None:
        if ctx.confidence < 0.70:
            return "gpt-5"
        if 0.70 <= ctx.confidence <= 0.84:
            return "gpt-5-mini"
        return "gpt-5-mini"  # statt nano
    if ctx.ambiguous and ctx.node in ("domain_router", "info_graph"):
        return "gpt-5-mini"
    return DEFAULTS.get(ctx.node, "gpt-5-mini")

def should_use_llm(node: str) -> bool:
    deterministic = {
        "intake_validate", "calc_core", "calc_advanced",
        "rag_retrieve", "rules_filter",
        "generate_rfq_pdf", "deliver_pdf"
    }
    return node not in deterministic

def llm_params_for(node: str, ctx: RoutingContext) -> Dict[str, Any]:
    model = select_model(ctx)
    temperature = float(os.getenv("SEALAI_LLM_TEMPERATURE", "0.2"))
    top_p = float(os.getenv("SEALAI_LLM_TOP_P", "0.9"))
    max_tokens = {"gpt-5-nano": 512, "gpt-5-mini": 2048, "gpt-5": 4096}[model]
    return {"model": model, "temperature": temperature, "top_p": top_p, "max_tokens": max_tokens}
