"""Constants for LangGraph v2 (models, namespaces, defaults)."""

CHECKPOINTER_NAMESPACE_V2 = ""

# Model tier defaults (can be overridden via env in later steps).
MODEL_NANO = "gpt-5-nano"
MODEL_MINI = "gpt-5-mini"
MODEL_PRO = "gpt-5.1"

QDRANT_DEFAULT_COLLECTION = "sealai-docs"

__all__ = [
    "CHECKPOINTER_NAMESPACE_V2",
    "MODEL_NANO",
    "MODEL_MINI",
    "MODEL_PRO",
    "QDRANT_DEFAULT_COLLECTION",
]
