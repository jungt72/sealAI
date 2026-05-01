from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

from app.agent.communication.models import CommunicationTrace


class CommunicationTraceSink(Protocol):
    def emit(self, trace: CommunicationTrace) -> None: ...


class NoopCommunicationTraceSink:
    def emit(self, trace: CommunicationTrace) -> None:
        return None


class JsonlCommunicationTraceSink:
    """Append-only metadata sink for human-communication audit traces.

    The trace intentionally contains no prompt body, no raw user text and no
    environment secrets. Enable with SEALAI_COMMUNICATION_AUDIT_LOG=/path/file.jsonl.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @classmethod
    def from_env(cls) -> CommunicationTraceSink:
        path = os.environ.get("SEALAI_COMMUNICATION_AUDIT_LOG")
        if not path:
            return NoopCommunicationTraceSink()
        return cls(path)

    def emit(self, trace: CommunicationTrace) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trace.model_dump(mode="json"), ensure_ascii=True))
            handle.write("\n")
