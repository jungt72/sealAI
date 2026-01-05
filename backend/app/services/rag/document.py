"""Document type helper that survives missing langchain installs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

try:
    from langchain.schema import Document  # type: ignore[import]
except ModuleNotFoundError:  # pragma: no cover - rare local development path
    try:
        from langchain_core.schema import Document  # type: ignore[import]
    except ModuleNotFoundError:
        @dataclass
        class Document:
            """Lightweight fallback that mimics LangChain's shape."""

            page_content: str = ""
            metadata: Dict[str, Any] = field(default_factory=dict)
            id: Optional[str] = None

            def __post_init__(self) -> None:
                self.page_content = self.page_content or ""
                self.metadata = dict(self.metadata or {})

            def to_dict(self) -> Dict[str, Any]:
                """Keep a familiar helper from the real Document class."""
                return {
                    "page_content": self.page_content,
                    "metadata": self.metadata,
                    "id": self.id,
                }

__all__ = ["Document"]
