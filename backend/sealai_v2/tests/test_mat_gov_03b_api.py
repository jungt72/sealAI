from __future__ import annotations

import builtins
import json
from types import SimpleNamespace

from sealai_v2.api import deps
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import Answer, Flags, PipelineResult, VerifiedIdentity
from sealai_v2.core.material_shadow import ShadowReadinessState
from sealai_v2.material_shadow.capture import capture_chat_shadow_after_response
from sealai_v2.tests._apiutil import auth, make_client


def _enabled() -> Settings:
    return Settings(
        material_ruleset_shadow_enabled=True,
        material_ruleset_shadow_persistence_enabled=True,
        material_ruleset_shadow_environment="staging",
        material_ruleset_shadow_redis_url="redis://cache.invalid/1",
        material_ruleset_shadow_hmac_active_key_id="key-v1",
        material_ruleset_shadow_hmac_keyring_json=json.dumps({"key-v1": "a" * 32}),
        database_url="postgresql://db.invalid/shadow",
    )


def _result() -> PipelineResult:
    return PipelineResult(
        question="raw customer question must never persist",
        tenant_id="tenant-a",
        flags=Flags(),
        understanding=None,
        answer=Answer("public answer", "fake"),
    )


def test_capture_is_disabled_or_ineligible_without_canonical_ids() -> None:
    identity = VerifiedIdentity("tenant-a", "session-a", "subject-a")
    disabled = capture_chat_shadow_after_response(
        settings=Settings(),
        identity=identity,
        session_id="session-a",
        result=_result(),
    )
    assert disabled.state is ShadowReadinessState.DISABLED
    ineligible = capture_chat_shadow_after_response(
        settings=_enabled(),
        identity=identity,
        session_id="session-a",
        result=_result(),
    )
    assert ineligible.state is ShadowReadinessState.INELIGIBLE_UNRESOLVED_INPUT
    assert ineligible.stable_error_code == "SHADOW_INPUT_INELIGIBLE"


def test_flag_off_chat_has_no_shadow_import_or_public_key(monkeypatch) -> None:
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "sealai_v2.material_shadow.capture":
            raise AssertionError("flag-off route imported material shadow capture")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    client, _pipeline = make_client()
    response = client.post(
        "/api/v2/chat", json={"message": "Was ist FKM?"}, headers=auth("tok-A")
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "Antwort."
    assert not any("shadow" in key for key in response.json())


def test_shadow_enabled_ineligible_path_is_byte_identical_for_chat_and_stream(
    monkeypatch,
) -> None:
    from sealai_v2.api.main import app

    monkeypatch.setattr(
        "sealai_v2.pipeline.timing.uuid.uuid4",
        lambda: SimpleNamespace(hex="1" * 32),
    )
    request = {"message": "Was ist FKM?"}
    headers = auth("tok-A")
    baseline_chat_client, _pipeline = make_client()
    baseline_chat = baseline_chat_client.post(
        "/api/v2/chat", json=request, headers=headers
    )
    baseline_stream_client, _pipeline = make_client()
    baseline_stream = baseline_stream_client.post(
        "/api/v2/chat/stream", json=request, headers=headers
    )
    shadow_chat_client, _pipeline = make_client()
    app.dependency_overrides[deps.get_settings] = _enabled
    try:
        shadow_chat = shadow_chat_client.post(
            "/api/v2/chat", json=request, headers=headers
        )
        shadow_stream_client, _pipeline = make_client()
        app.dependency_overrides[deps.get_settings] = _enabled
        shadow_stream = shadow_stream_client.post(
            "/api/v2/chat/stream", json=request, headers=headers
        )
    finally:
        app.dependency_overrides.pop(deps.get_settings, None)
    assert shadow_chat.content == baseline_chat.content
    assert shadow_stream.content == baseline_stream.content


def test_post_response_exception_cannot_change_normal_chat_response(
    monkeypatch,
) -> None:
    client, _pipeline = make_client()
    from sealai_v2.api.main import app

    app.dependency_overrides[deps.get_settings] = _enabled

    def explode(**_kwargs):
        raise RuntimeError("sensitive synthetic exception text")

    monkeypatch.setattr(
        "sealai_v2.material_shadow.capture.capture_chat_shadow_after_response",
        explode,
    )
    response = client.post(
        "/api/v2/chat", json={"message": "Was ist FKM?"}, headers=auth("tok-A")
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "Antwort."
    assert not any("shadow" in key for key in response.json())
    app.dependency_overrides.pop(deps.get_settings, None)
