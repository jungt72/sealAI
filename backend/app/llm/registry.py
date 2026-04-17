"""
Central LLM Model Registry for SeaLAI.

This module serves as the single source of truth for mapping functional roles 
to specific LLM model identifiers. It allows for role-based model selection 
without hardcoding model names in the business logic.
"""

import os
from typing import Dict, Final

# Central mapping of functional roles to model identifiers.
# Defaults are mirrored from the current production state identified in Phase 0.
LLM_REGISTRY: Final[Dict[str, str]] = {
    "extraction": "gpt-4o-mini",
    "gate": "gpt-4o-mini",
    "routing": "gpt-4o-mini",
    "exploration": "gpt-4o-mini",
    "conversation": "gpt-4o-mini",
    "governed_reformulate": "gpt-4o-mini",
    "medium_intelligence": "gpt-4o-mini",
    "medium_fallback": "gpt-4o-mini",
    "rag_dynamic_metadata": "gpt-4.1-mini",
    # Roles for future hardening and critical validation paths.
    "critique": "gpt-4o",
    "rfq": "gpt-4o",
}

# Mapping of functional roles to their respective environment variable overrides.
ROLE_ENV_MAPPING: Final[Dict[str, str]] = {
    "extraction": "SEALAI_EXTRACTION_MODEL",
    "gate": "SEALAI_GATE_MODEL",
    "routing": "SEALAI_ROUTING_MODEL",
    "exploration": "SEALAI_EXPLORATION_MODEL",
    "conversation": "SEALAI_CONVERSATION_MODEL",
    "governed_reformulate": "SEALAI_CONVERSATION_MODEL",
    "medium_intelligence": "SEALAI_MEDIUM_INTELLIGENCE_MODEL",
    "medium_fallback": "SEALAI_MEDIUM_FALLBACK_MODEL",
    "rag_dynamic_metadata": "RAG_DYNAMIC_METADATA_LLM_MODEL",
    "critique": "SEALAI_CRITIQUE_MODEL",
    "rfq": "SEALAI_RFQ_MODEL",
}

DEFAULT_MODEL: Final[str] = "gpt-4o-mini"


def get_model_for_role(role: str) -> str:
    """
    Returns the assigned model identifier for a given functional role.
    
    Priority:
    1. Environment variable override (if defined and non-empty)
    2. Static registry default
    3. Global default model
    
    Args:
        role: The functional role (e.g., 'extraction', 'routing').
        
    Returns:
        The model string assigned to that role.
    """
    # 1. Check for environment variable override
    env_var_name = ROLE_ENV_MAPPING.get(role)
    if env_var_name:
        env_value = os.getenv(env_var_name, "").strip()
        if env_value:
            return env_value

    # 2. Fallback to static registry or global default
    return LLM_REGISTRY.get(role, DEFAULT_MODEL)
