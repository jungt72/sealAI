from __future__ import annotations
from typing import Generic, TypeVar, Optional, List
from pydantic import BaseModel
from .enums import EngineStatus

T = TypeVar("T")


class EngineResult(BaseModel, Generic[T]):
    """
    Every deterministic service returns this. Never a raw value.
    The 'status' field is the primary signal – 'value' may be None even on partial success.
    """
    status: EngineStatus
    value: Optional[T] = None
    reason: Optional[str] = None
    missing_inputs: List[str] = []

    @property
    def is_usable(self) -> bool:
        return self.status == EngineStatus.COMPUTED and self.value is not None
