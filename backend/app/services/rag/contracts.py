from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RAGInput:
    query: str
    parameters: dict[str, Any] = field(default_factory=dict)
    language: str = "de"


@dataclass(frozen=True)
class RAGOutput:
    chunks: list[dict[str, Any]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass(frozen=True)
class RenderedPrompt:
    template_name: str
    version: str
    rendered_text: str
    hash_sha256: str

