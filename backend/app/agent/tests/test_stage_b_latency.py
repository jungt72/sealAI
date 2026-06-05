"""Stage B — low-risk latency acceptance (audit §5 Rang 2 + Rang 3 / W1 + W2).

Red-before-green:
- Router timeout: on the pre-B tree there is no `asyncio.wait_for`, so a hanging
  router LLM hangs unbounded (W1); after, it falls into the existing deterministic
  fallback with a `TimeoutError` reason.
- Prewarm: on the pre-B tree `prewarm_embeddings` never warmed the sparse embedder
  and `warmup_on_start` defaulted False (W2); after, sparse is warmed and the
  default is True.

No new control flow is introduced for the router — the timeout reuses the module's
existing `except Exception → _unchanged(deterministic)` fallback.
"""

from __future__ import annotations

import asyncio
import sys
import types

import app.services.semantic_intent_router as sir
import app.services.rag.rag_orchestrator as ro
from app.services.pre_gate_classifier import PreGateClassifier


# ── Rang 3 / W1: semantic-router LLM timeout → deterministic fallback ──────────


def test_router_llm_timeout_falls_back_to_deterministic(monkeypatch):
    det = PreGateClassifier().classify("Was ist FKM und wofür wird es verwendet?")
    monkeypatch.setattr(sir, "_router_timeout_s", lambda: 0.02)
    monkeypatch.setattr(sir, "semantic_pre_gate_candidate", lambda *a, **k: True)
    monkeypatch.setattr(sir, "get_async_llm", lambda name: (object(), "gpt-test"))
    monkeypatch.setattr(sir, "_router_payload", lambda **kw: {})

    async def _hang(**kw):
        await asyncio.sleep(1.0)
        return {}

    monkeypatch.setattr(sir, "_call_structured_router", _hang)

    decision = asyncio.run(
        sir.refine_pre_gate_classification(
            message="Was ist FKM und wofür wird es verwendet?", deterministic=det
        )
    )
    # timed out → safe deterministic fallback, reason names the TimeoutError
    assert "TimeoutError" in decision.reason
    assert decision.classification_result(det).classification == det.classification


def test_router_fast_path_is_not_capped(monkeypatch):
    """A fast router response is used (the cap only kills the tail)."""
    det = PreGateClassifier().classify("Was ist FKM?")
    monkeypatch.setattr(sir, "_router_timeout_s", lambda: 5.0)
    monkeypatch.setattr(sir, "semantic_pre_gate_candidate", lambda *a, **k: True)
    monkeypatch.setattr(sir, "get_async_llm", lambda name: (object(), "gpt-test"))
    monkeypatch.setattr(sir, "_router_payload", lambda **kw: {})

    async def _fast(**kw):
        return {"intent": "knowledge"}

    monkeypatch.setattr(sir, "_call_structured_router", _fast)
    # _decision_from_payload turns the payload into a real decision (not a fallback)
    captured = {}
    real_decision_from_payload = sir._decision_from_payload

    def _spy(payload, **kw):
        captured["payload"] = payload
        return real_decision_from_payload(payload, **kw)

    monkeypatch.setattr(sir, "_decision_from_payload", _spy)

    decision = asyncio.run(
        sir.refine_pre_gate_classification(message="Was ist FKM?", deterministic=det)
    )
    assert captured.get("payload") == {"intent": "knowledge"}
    assert "TimeoutError" not in (decision.reason or "")


# ── Rang 2 / W2: prewarm covers the sparse embedder (3rd lazy global) ─────────


def test_prewarm_warms_sparse_embedder(monkeypatch):
    class _Vec:
        def tolist(self):
            return [0.1, 0.2]

    class _FakeDense:
        def __init__(self, **kw):
            pass

        def embed(self, texts):
            return iter([_Vec()])

    class _FakeSparse:
        instantiated = False

        def __init__(self, **kw):
            _FakeSparse.instantiated = True

        def embed(self, texts):
            return iter([object()])

    class _FakeReranker:
        def __init__(self, *a, **k):
            pass

    fake_fastembed = types.ModuleType("fastembed")
    fake_fastembed.TextEmbedding = _FakeDense
    fake_fastembed.SparseTextEmbedding = _FakeSparse
    fake_st = types.ModuleType("sentence_transformers")
    fake_st.CrossEncoder = _FakeReranker
    monkeypatch.setitem(sys.modules, "fastembed", fake_fastembed)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_st)
    monkeypatch.setattr(ro, "USE_SPARSE_RETRIEVAL", True)
    monkeypatch.setattr(ro, "_sparse_embedder", None)

    ro.prewarm_embeddings()

    assert _FakeSparse.instantiated, "prewarm must warm the sparse embedder (Rang 2)"
    assert ro._sparse_embedder is not None
