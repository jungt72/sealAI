import pytest

from app.services.auth import token as auth_token


def _setup_common_stubs(monkeypatch, claims):
    monkeypatch.setattr(
        auth_token, "_safe_get_unverified_header", lambda _t: {"kid": "k1", "alg": "RS256"}
    )
    monkeypatch.setattr(auth_token, "_get_key", lambda _kid: {"x5c": ["dummy"]})
    monkeypatch.setattr(auth_token, "_jwk_to_pem", lambda _jwk: "pem")
    monkeypatch.setattr(auth_token.jwt, "decode", lambda *_args, **_kwargs: claims)


def test_verify_access_token_accepts_sealai_backend_aud_list(monkeypatch):
    claims = {"aud": ["sealai-backend", "account"], "azp": "sealai-dev-cli"}
    _setup_common_stubs(monkeypatch, claims)

    assert auth_token.verify_access_token("dummy-token") == claims


def test_verify_access_token_rejects_unknown_aud(monkeypatch):
    claims = {"aud": ["some-other"], "azp": "sealai-dev-cli"}
    _setup_common_stubs(monkeypatch, claims)

    with pytest.raises(ValueError, match="audience not allowed"):
        auth_token.verify_access_token("dummy-token")
