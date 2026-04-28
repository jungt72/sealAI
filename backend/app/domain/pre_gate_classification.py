"""Domain enum for the pre-gate runtime classification layer.

This module is intentionally limited to the SeaLAI v0.7 routing classes.
It has no runtime routing logic.
"""

from __future__ import annotations

from enum import Enum


class PreGateClassification(str, Enum):
    """Case-creation boundary classification before the three-mode gate."""

    GREETING = "GREETING"
    META_QUESTION = "META_QUESTION"
    KNOWLEDGE_QUERY = "KNOWLEDGE_QUERY"
    BLOCKED = "BLOCKED"
    DOMAIN_INQUIRY = "DOMAIN_INQUIRY"
    DEEP_DIVE = "DEEP_DIVE"
    RECOVERY = "RECOVERY"
