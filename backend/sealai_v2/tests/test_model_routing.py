"""Per-role model routing (provider + model) — Part 1.

Proves: the no-override default resolves every role to its CURRENT model+temperature (byte-identical
object graph), per-role env overrides + provider routing work, and unknown-provider / missing-key
fail CLOSED at build time. All offline — fakes at the LlmClient boundary, no network, no key needed
(the two SDK-construction tests pass dummy key strings via Settings, never a real secret)."""

from __future__ import annotations

import asyncio

import pytest

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import Flags
from sealai_v2.llm.factory import (
    _resolve_provider,
    build_client_factory,
)
from sealai_v2.pipeline.pipeline import build_pipeline
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient

_T = TenantContext("t1")


# --- default byte-identity: roles resolve to the CURRENT models, unchanged ----------------


def test_default_role_models_and_temperatures_unchanged():
    p = build_pipeline(Settings(), FakeLlmClient("x"))
    # L1 + L3 = strong frontier; helpers = cheap tier — exactly today's defaults.
    assert (p.generator._model_config.model, p.generator._model_config.temperature) == (
        "gpt-5.1",
        None,
    )
    assert (p.verifier._model_config.model, p.verifier._model_config.temperature) == (
        "gpt-5.1",
        None,
    )
    assert (p.helper_model.model, p.helper_model.temperature) == ("gpt-5.6-luna", 0.0)
    assert (p.distiller._model_config.model, p.distiller._model_config.temperature) == (
        "gpt-5.6-luna",
        0.0,
    )


def test_default_run_uses_l1_and_helper_models():
    """A default sessionless turn: understand (helper) + L1 generate + L3 verify — no distill."""
    fake = FakeLlmClient("FAKE-ANSWER")
    asyncio.run(
        build_pipeline(Settings(), fake).run("Frage?", tenant=_T, flags=Flags())
    )
    models = {c["model"] for c in fake.calls}
    assert models == {
        "gpt-5.1",
        "gpt-5.6-luna",
    }  # L1/verify = gpt-5.1, understand = gpt-5.6-luna


# --- single-client mode ignores provider settings (test/default path unaffected) ----------


def test_single_client_mode_ignores_provider_settings():
    # No factory → the one client backs every role regardless of *_provider (preserves the
    # FakeLlmClient tests; provider routing is a factory-mode concern only).
    fake = FakeLlmClient("x")
    p = build_pipeline(
        Settings(verifier_provider="mistral", l1_provider="mistral"), fake
    )
    assert p.generator._client is fake
    assert p.verifier._client is fake
    assert p.client is fake


# --- per-role env overrides resolve independently -----------------------------------------


def test_env_overrides_resolve_per_role(monkeypatch):
    monkeypatch.setenv("SEALAI_V2_L1_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("SEALAI_V2_VERIFIER_MODEL", "gpt-5.1")
    monkeypatch.setenv("SEALAI_V2_HELPER_MODEL", "gpt-5.4-nano")
    p = build_pipeline(Settings(), FakeLlmClient("x"))
    assert p.generator._model_config.model == "gpt-5.4-mini"
    assert p.verifier._model_config.model == "gpt-5.1"
    assert p.helper_model.model == "gpt-5.4-nano"
    assert p.distiller._model_config.model == "gpt-5.4-nano"


# --- mixed-cell provider routing: each role lands on its provider's client -----------------


def test_per_role_provider_routing_mixed_cell():
    """L3=mistral-small-4 via the mistral client; L1 + helpers stay on the openai client."""
    openai_fake = FakeLlmClient("OAI")
    mistral_fake = FakeLlmClient("MISTRAL")
    clients = {"openai": openai_fake, "mistral": mistral_fake}

    settings = Settings(verifier_provider="mistral", verifier_model="mistral-small-4")
    p = build_pipeline(settings, client_for=lambda provider: clients[provider])
    # Wiring: verifier on mistral, generator + understand-helper on openai.
    assert p.verifier._client is mistral_fake
    assert p.generator._client is openai_fake
    assert p.client is openai_fake

    asyncio.run(p.run("Frage?", tenant=_T, flags=Flags()))
    # The L3 verify call went to mistral; understand + L1 to openai.
    assert mistral_fake.calls and all(
        c["model"] == "mistral-small-4" for c in mistral_fake.calls
    )
    oai_models = {c["model"] for c in openai_fake.calls}
    assert oai_models == {"gpt-5.1", "gpt-5.6-luna"}


# --- fail-closed: unknown provider / missing key raise (never a silent default) ------------


def test_unknown_provider_resolves_closed():
    with pytest.raises(RuntimeError, match="unsupported provider"):
        _resolve_provider(Settings(openai_api_key="sk-x"), "nope")


def test_unknown_provider_fails_at_pipeline_build():
    s = Settings(l1_provider="nope", openai_api_key="sk-x")
    with pytest.raises(RuntimeError, match="unsupported provider"):
        build_pipeline(s, client_for=build_client_factory(s))


def test_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY not set"):
        _resolve_provider(Settings(openai_api_key=None), "openai")
    with pytest.raises(RuntimeError, match="MISTRAL_API_KEY not set"):
        _resolve_provider(Settings(mistral_api_key=None), "mistral")


# --- provider→(base_url, key) resolve table (pure, no SDK construction) --------------------


def test_resolve_provider_table():
    s = Settings(openai_api_key="sk-x", mistral_api_key="ms-x")
    assert _resolve_provider(s, "openai") == (s.openai_base_url, "sk-x")
    assert _resolve_provider(s, "mistral") == ("https://api.mistral.ai/v1", "ms-x")


def test_client_factory_caches_one_per_provider():
    s = Settings(openai_api_key="sk-x", mistral_api_key="ms-x")
    client_for = build_client_factory(s)
    a, b = client_for("openai"), client_for("openai")
    assert (
        a is b
    )  # all-openai run shares ONE client across roles (byte-identical graph)
    assert client_for("mistral") is not a
