"""Canonical RAG constants for SealAI."""

from __future__ import annotations

# The shared tenant ID for global/public knowledge
RAG_SHARED_TENANT_ID = "sealai"

# Visibility levels
RAG_VISIBILITY_PUBLIC = "public"
RAG_VISIBILITY_PRIVATE = "private"

# Allowed scopes for ingestion
RAG_SCOPE_GLOBAL = "global"
RAG_SCOPE_TENANT = "tenant"

ALLOWED_VISIBILITY = {RAG_VISIBILITY_PRIVATE, RAG_VISIBILITY_PUBLIC}
ALLOWED_SCOPES = {RAG_SCOPE_GLOBAL, RAG_SCOPE_TENANT}
