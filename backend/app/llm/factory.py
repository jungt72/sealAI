"""
Central LLM Factory for SeaLAI.

This module provides a standardized way to obtain OpenAI clients (both sync and async)
pre-configured for specific functional roles using the central model registry.
"""

from typing import Tuple
from openai import OpenAI, AsyncOpenAI
from .registry import get_model_for_role


def get_sync_llm(role: str) -> Tuple[OpenAI, str]:
    """
    Creates a synchronous OpenAI client and resolves the model for a given role.
    
    Returns:
        A tuple of (client, model_name).
    """
    model = get_model_for_role(role)
    client = OpenAI()  # Automatically picks up OPENAI_API_KEY from env
    return client, model


def get_async_llm(role: str) -> Tuple[AsyncOpenAI, str]:
    """
    Creates an asynchronous OpenAI client and resolves the model for a given role.
    
    Returns:
        A tuple of (async_client, model_name).
    """
    model = get_model_for_role(role)
    client = AsyncOpenAI()  # Automatically picks up OPENAI_API_KEY from env
    return client, model
