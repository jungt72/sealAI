"""Frontdoor node: intent discovery and parameter extraction."""
from __future__ import annotations

import re
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import structlog

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import (
    Intent,
    IntentGoal,
    SealAIState,
    TechnicalParameters,
    WorkingMemory,
)
from app.langgraph_v2.utils.llm_factory import get_model_tier, run_llm
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.parameter_extraction import extract_parameters_from_text
from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_with_provenance
from app.langgraph_v2.utils.state_debug import log_state_debug
from app.langgraph_v2.utils.json_sanitizer import extract_json_obj

# [NEW] v2.2 Infrastructure
from app.prompts.registry import PromptRegistry
from app.prompts.contexts import GreetingContext

logger = structlog.get_logger("langgraph_v2.nodes_frontdoor")

def _get_working_memory(state: SealAIState, updates: Dict[str, Any]) -> WorkingMemory:
    wm = state.working_memory or WorkingMemory()
    return wm.model_copy(update=updates)

def frontdoor_discovery_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """
    Refactored Frontdoor Node (v2.2 Platinum Standard).
    - Uses PromptRegistry for managed prompts.
    - Calculates is_first_visit.
    - separates Persona (System) from Analysis (User).
    - Deterministic greeting generation.
    - [NEW] Traceability: Logs prompt_id, version, fingerprint.
    """
    log_state_debug("frontdoor_discovery_node", state)
    
    # 1. Calculate State
    messages = state.messages or []
    # logic: if only 1 message (User's first msg), it's first visit? 
    # Or if empty? Usually starts with user message.
    # If len=1 (User), then previous was 0. So yes? 
    # Let's say <= 1 to be safe for initial state.
    is_first_visit = len(messages) <= 1
    user_text = latest_user_text(messages) or ""
    
    # 2. Build Context
    ctx = GreetingContext(
        trace_id=state.run_id or "unknown",
        session_id=state.thread_id or "unknown",
        language="de",
        is_first_visit=is_first_visit,
        formality_score=5
    )
    
    # 3. Render Prompts
    registry = PromptRegistry()
    
    # System Prompt: Persona
    system_content, sys_fp, sys_ver = registry.render("greeting/system_v1", ctx.to_dict())
    
    # User Prompt: Analysis
    analysis_ctx = ctx.to_dict()
    analysis_ctx["user_message"] = user_text
    analysis_content, ana_fp, ana_ver = registry.render("discovery/analysis_v1", analysis_ctx)
    
    # Greeting Reply
    reply_content, rep_fp, rep_ver = registry.render("greeting/reply_v1", ctx.to_dict())
    
    # Traceability Data (We log the main reasoning prompt, usually Analysis or System+Analysis)
    # Combining IDs? Or just listing main? 
    # User said: "prompt_id_used", "prompt_version_used", "prompt_fingerprint".
    # Typically referencing the specific task prompt (Analysis).
    prompt_id = "discovery/analysis"
    prompt_ver = ana_ver
    prompt_fp = ana_fp
    
    # 4. Execute LLM
    try:
        response_text = run_llm(
            model=get_model_tier("nano"),
            prompt=analysis_content,
            system=system_content,
            temperature=0.0,
            max_tokens=500,
            metadata={
                "node": "frontdoor_discovery_node",
                "run_id": state.run_id,
                "prompt_id_used": prompt_id,
                "prompt_version_used": prompt_ver,
                "prompt_fingerprint": prompt_fp
            },
        )
        
        data, _ = extract_json_obj(response_text, default={})
        
    except Exception as exc:
        logger.error("frontdoor_llm_failed", error=str(exc))
        data = {
            "intent": "design_recommendation",
            "confidence": 0.5,
            "parameters": {},
            "missing_info": []
        }

    # 5. Process Result
    intent_str = data.get("intent", "design_recommendation")
    confidence = data.get("confidence", 0.0)
    
    intent = Intent(
        goal=intent_str if intent_str in getattr(IntentGoal, "__args__", []) else "design_recommendation",
        confidence=confidence,
        domain="sealing_technology"
    )
    
    extracted_params = data.get("parameters", {})
    parameters = state.parameters or TechnicalParameters()
    parameter_provenance = state.parameter_provenance
    
    if extracted_params:
         merged_params, parameter_provenance = apply_parameter_patch_with_provenance(
            parameters.as_dict(),
            extracted_params,
            state.parameter_provenance,
            source="llm_discovery"
        )
         parameters = TechnicalParameters.model_validate(merged_params)

    # 6. Return State Update
    wm_updates = {"frontdoor_reply": reply_content}
    wm = _get_working_memory(state, wm_updates)
    
    return {
        "intent": intent,
        "working_memory": wm,
        "parameters": parameters,
        "parameter_provenance": parameter_provenance,
        "phase": PHASE.FRONTDOOR,
        "last_node": "frontdoor_discovery_node",
        "is_first_visit": is_first_visit,
        # Traceability Limits: We set checking strictly strict logic
        "prompt_id_used": prompt_id,
        "prompt_version_used": prompt_ver,
        "prompt_fingerprint": prompt_fp,
    }
