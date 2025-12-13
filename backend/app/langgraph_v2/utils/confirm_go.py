from __future__ import annotations

from pydantic import BaseModel, Field, StrictBool


class ConfirmGoRequest(BaseModel):
    chat_id: str = Field(..., description="Conversation/thread id")
    go: StrictBool = Field(..., description="Explicit approval gate for design flow")


__all__ = ["ConfirmGoRequest"]

