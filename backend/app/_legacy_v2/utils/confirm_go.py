from __future__ import annotations

from typing import Dict, Literal, Optional

from pydantic import AliasChoices, BaseModel, Field, StrictBool, model_validator


class ConfirmGoEdits(BaseModel):
    working_profile: Dict[str, object] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("working_profile", "parameters"),
    )
    instructions: Optional[str] = None


class ConfirmGoRequest(BaseModel):
    chat_id: str = Field(..., description="Conversation/thread id")
    checkpoint_id: Optional[str] = Field(default=None, description="Checkpoint id to resume")
    decision: Optional[Literal["approve", "reject", "edit"]] = Field(default=None)
    edits: Optional[ConfirmGoEdits] = None
    go: Optional[StrictBool] = Field(default=None, description="Legacy boolean approval flag")

    @model_validator(mode="after")
    def _normalize_legacy_go(self) -> "ConfirmGoRequest":
        if self.decision is None and self.go is not None:
            self.decision = "approve" if self.go else "reject"
        return self


__all__ = ["ConfirmGoEdits", "ConfirmGoRequest"]
