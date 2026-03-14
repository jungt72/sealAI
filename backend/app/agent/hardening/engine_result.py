from __future__ import annotations

from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel

from .enums import EngineStatus

T = TypeVar("T")


class EngineResult(BaseModel, Generic[T]):
    """
    Every deterministic service wraps its output in this type.

    The ``status`` field is the primary signal — ``value`` may be ``None`` even
    on partial success.  Callers should always check ``is_usable`` before
    consuming ``value``.
    """

    status: EngineStatus
    value: Optional[T] = None
    reason: Optional[str] = None
    missing_inputs: List[str] = []

    @property
    def is_usable(self) -> bool:
        """Return True only when the computation succeeded and produced a value."""
        return self.status == EngineStatus.COMPUTED and self.value is not None
