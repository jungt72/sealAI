from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, StrictBool, model_validator


class ConfirmGoEdits(BaseModel):
    parameters: Dict[str, object] = Field(default_factory=dict)
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


async def apply_confirm_decision(
    *,
    graph: Any,
    config: Dict[str, Any],
    decision: Literal["approve", "reject", "edit"],
    edits: Dict[str, Any],
    as_node: str = "confirm_checkpoint_node",
    extra_updates: Optional[Dict[str, Any]] = None,
) -> Any:
    updates: Dict[str, Any] = {
        "confirm_decision": decision,
        "confirm_edits": edits,
    }
    if extra_updates:
        updates.update(extra_updates)
    await graph.aupdate_state(config, updates, as_node=as_node)
    return await graph.ainvoke({}, config=config)


__all__ = ["ConfirmGoEdits", "ConfirmGoRequest", "apply_confirm_decision"]
