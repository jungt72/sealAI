"""Constants for LangGraph v2 (models, namespaces, defaults)."""

import os

CHECKPOINTER_NAMESPACE_V2 = os.getenv("LANGGRAPH_V2_NAMESPACE", "sealai:v2:").strip()
CHECKPOINT_PREFIX_V2 = f"{CHECKPOINTER_NAMESPACE_V2}checkpoint"
CHECKPOINT_BLOB_PREFIX_V2 = f"{CHECKPOINTER_NAMESPACE_V2}checkpoint_blob"
CHECKPOINT_WRITE_PREFIX_V2 = f"{CHECKPOINTER_NAMESPACE_V2}checkpoint_write"

# Model tier defaults (can be overridden via env in later steps).
MODEL_NANO = "gpt-5-nano"
MODEL_MINI = "gpt-5-mini"
MODEL_PRO = "gpt-5.1"

QDRANT_DEFAULT_COLLECTION = "sealai-docs"

__all__ = [
    "CHECKPOINTER_NAMESPACE_V2",
    "CHECKPOINT_PREFIX_V2",
    "CHECKPOINT_BLOB_PREFIX_V2",
    "CHECKPOINT_WRITE_PREFIX_V2",
    "MODEL_NANO",
    "MODEL_MINI",
    "MODEL_PRO",
    "QDRANT_DEFAULT_COLLECTION",
]
