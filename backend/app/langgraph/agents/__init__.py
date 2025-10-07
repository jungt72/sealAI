"""Adapters bridging unified IO models with legacy agents."""

from .adapters import adapt_agent_input, adapt_agent_output, build_legacy_agent_state

__all__ = ["adapt_agent_input", "adapt_agent_output", "build_legacy_agent_state"]
