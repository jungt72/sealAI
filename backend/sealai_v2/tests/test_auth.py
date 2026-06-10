"""M6c — V2-owned auth-validate-IN-V2 seam (P0). Offline: a generated RSA keypair + an injected JWKS
fetcher (no network). Covers the classic JWT pitfalls: alg:none, alg-confusion, expiry, tamper,
audience/issuer, missing — plus JWKS refresh-on-unknown-kid. The no-header-trust + cross-tenant
isolation guarantees are route-level (test_api_*); here we lock the validator logic.
"""

from __future__ import annotations

import json

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from sealai_v2.core.contracts import AuthError, VerifiedIdentity
from sealai_v2.security.auth import FakeAuthValidator, KeycloakJwtValidator

_ISS = "https://kc.example/realms/sealai"
_AUD = "sealai-v2"


def _keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks(pub, kid="k1") -> dict:
    jwk = json.loads(RSAAlgorithm.to_jwk(pub))
    jwk.update(kid=kid, use="sig", alg="RS256")
    return {"keys": [jwk]}


def _tok(priv, *, kid="k1", alg="RS256", iss=_ISS, aud=_AUD, claims=None, exp_offset=3600) -> str:
    import time

    payload = {"iss": iss, "aud": aud, "sub": "user-1", "sid": "sess-1",
               "tenant_id": "tenant-A", "exp": int(time.time()) + exp_offset}
    payload.update(claims or {})
    headers = {"kid": kid}
    key = "secret" if alg.startswith("HS") else priv
    return jwt.encode(payload, key, algorithm=alg, headers=headers)


def _validator(jwks, *, fetcher=None) -> KeycloakJwtValidator:
    return KeycloakJwtValidator(
        jwks_url="https://kc.example/jwks", issuer=_ISS, audience=_AUD,
        jwks_fetcher=fetcher or (lambda: jwks),
    )


def test_valid_token_yields_identity_from_token():
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    ident = v.validate(_tok(priv))
    assert isinstance(ident, VerifiedIdentity)
    assert ident.tenant_id == "tenant-A" and ident.session_id == "sess-1" and ident.subject == "user-1"


def test_alg_none_is_rejected():
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    # an unsigned alg:none token
    tok = jwt.encode({"iss": _ISS, "aud": _AUD, "sub": "x", "tenant_id": "tenant-A"}, key=None,
                     algorithm="none", headers={"kid": "k1"})
    with pytest.raises(AuthError):
        v.validate(tok)


def test_alg_confusion_hs256_with_public_key_is_rejected():
    import base64
    import hashlib
    import hmac
    import time

    from cryptography.hazmat.primitives import serialization

    priv = _keypair()
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # Forge the alg-confusion token BY HAND (PyJWT's own encode guards against PEM-as-HMAC-secret):
    # attacker signs HS256 using the PUBLIC key as the HMAC secret, hoping the verifier uses HS256.
    def _b64(b: bytes) -> bytes:
        return base64.urlsafe_b64encode(b).rstrip(b"=")

    head = _b64(json.dumps({"alg": "HS256", "kid": "k1", "typ": "JWT"}).encode())
    body = _b64(json.dumps({"iss": _ISS, "aud": _AUD, "sub": "x", "sid": "s",
                            "tenant_id": "tenant-A", "exp": int(time.time()) + 3600}).encode())
    signing_input = head + b"." + body
    sig = _b64(hmac.new(pub_pem, signing_input, hashlib.sha256).digest())
    forged = (signing_input + b"." + sig).decode()

    v = _validator(_jwks(priv.public_key()))
    with pytest.raises(AuthError):
        v.validate(forged)  # alg HS256 not in pinned ["RS256"] → rejected before any key use


def test_expired_token_is_rejected():
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    with pytest.raises(AuthError):
        v.validate(_tok(priv, exp_offset=-10))


def test_wrong_audience_and_issuer_rejected():
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    with pytest.raises(AuthError):
        v.validate(_tok(priv, aud="someone-else"))
    with pytest.raises(AuthError):
        v.validate(_tok(priv, iss="https://evil/realms/x"))


def test_tampered_signature_rejected():
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    tok = _tok(priv)
    tampered = tok[:-3] + ("aaa" if not tok.endswith("aaa") else "bbb")
    with pytest.raises(AuthError):
        v.validate(tampered)


def test_missing_or_garbage_token_rejected():
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    for bad in ("", "not-a-jwt", "a.b.c"):
        with pytest.raises(AuthError):
            v.validate(bad)


def test_jwks_refresh_on_unknown_kid():
    priv = _keypair()
    # the cached JWKS has the OLD kid; the token is signed under a NEW kid (key rotation)
    old, new = _jwks(priv.public_key(), kid="old"), _jwks(priv.public_key(), kid="new")
    calls = {"n": 0}

    def fetcher():
        calls["n"] += 1
        return old if calls["n"] == 1 else new  # first fetch = stale, refresh = fresh

    v = _validator(new, fetcher=fetcher)
    ident = v.validate(_tok(priv, kid="new"))  # unknown kid → refresh once → resolves
    assert ident.tenant_id == "tenant-A" and calls["n"] >= 2


def test_missing_tenant_claim_fails_closed():
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    with pytest.raises(AuthError):
        v.validate(_tok(priv, claims={"tenant_id": None}))


def test_fake_validator_maps_tokens_and_rejects_unknown():
    fake = FakeAuthValidator({"tok-A": VerifiedIdentity("tenant-A", "sess-A", "user-A")})
    assert fake.validate("tok-A").tenant_id == "tenant-A"
    with pytest.raises(AuthError):
        fake.validate("tok-unknown")
