"""Shared builder for /api/v2 TestClient tests (M6c). NOT a test module (no ``test_`` prefix).

Overrides the auth + pipeline dependencies with a ``FakeAuthValidator`` + a fake-client pipeline, so
tenant/session are driven purely through the bearer token (the no-header-trust + cross-tenant
guarantees are exercised end-to-end without network or a real LLM)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sealai_v2.api import deps
from sealai_v2.api.main import app
from sealai_v2.core.contracts import ModelConfig, VerifiedIdentity
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.auth import FakeAuthValidator
from sealai_v2.tests._fakes import FakeLlmClient

IDS = {
    "tok-A": VerifiedIdentity("tenant-A", "sess-A", "user-A"),
    "tok-A2": VerifiedIdentity("tenant-A", "sess-A2", "user-A2"),
    "tok-B": VerifiedIdentity("tenant-B", "sess-B", "user-B"),
}


def make_pipeline(answer: str = "Antwort.", *, ground: bool = True) -> Pipeline:
    client = FakeLlmClient(answer)
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=InProcessRetriever() if ground else None,
        memory=InProcessConversationMemory(),
        cross_session=InProcessCrossSessionMemory(),
    )


def make_client(pipeline: Pipeline | None = None, identities: dict | None = None):
    pipeline = pipeline or make_pipeline()
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.get_validator] = lambda: FakeAuthValidator(
        identities or IDS
    )
    app.dependency_overrides[deps.get_pipeline] = lambda: pipeline
    return TestClient(app), pipeline


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
