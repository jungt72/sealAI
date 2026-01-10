"""Constants for LangGraph v2 (models, namespaces, defaults)."""

import os


def resolve_checkpointer_namespace_v2(override: str | None = None) -> str:
    namespace = (
        override
        or os.getenv("LANGGRAPH_CHECKPOINT_NS")
        or os.getenv("CHECKPOINT_NS")
        or os.getenv("LANGGRAPH_V2_NAMESPACE")
        or "sealai:v2:"
    ).strip()
    return namespace or "sealai:v2:"


CHECKPOINTER_NAMESPACE_V2 = resolve_checkpointer_namespace_v2()

# Model tier defaults (can be overridden via env in later steps).
MODEL_NANO = "gpt-5-nano"
MODEL_MINI = "gpt-5-mini"
MODEL_PRO = "gpt-5.1"

QDRANT_DEFAULT_COLLECTION = "sealai-docs"

__all__ = [
    "CHECKPOINTER_NAMESPACE_V2",
    "resolve_checkpointer_namespace_v2",
    "MODEL_NANO",
    "MODEL_MINI",
    "MODEL_PRO",
    "QDRANT_DEFAULT_COLLECTION",
]
