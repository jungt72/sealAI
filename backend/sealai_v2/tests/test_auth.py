"""M6c — V2-owned auth-validate-IN-V2 seam (P0). Offline: a generated RSA keypair + an injected JWKS
fetcher (no network). Covers the classic JWT pitfalls: alg:none, alg-confusion, expiry, tamper,
audience/issuer, missing — plus JWKS refresh-on-unknown-kid. The no-header-trust + cross-tenant
isolation guarantees are route-level (test_api_*); here we lock the validator logic.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from sealai_v2.core.contracts import AuthError, VerifiedIdentity
from sealai_v2.security.auth import (
    FakeAuthValidator,
    JwksFetchResult,
    KeycloakJwtValidator,
)

_ISS = "https://kc.example/realms/sealai"
_AUD = "sealai-v2"


def _keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks(pub, kid="k1") -> dict:
    jwk = json.loads(RSAAlgorithm.to_jwk(pub))
    jwk.update(kid=kid, use="sig", alg="RS256")
    return {"keys": [jwk]}


def _tok(
    priv, *, kid="k1", alg="RS256", iss=_ISS, aud=_AUD, claims=None, exp_offset=3600
) -> str:
    now = int(time.time())
    payload = {
        "iss": iss,
        "aud": aud,
        "sub": "user-1",
        "sid": "sess-1",
        "tenant_id": "tenant-A",
        "iat": now,
        "exp": now + exp_offset,
    }
    payload.update(claims or {})
    headers = {"kid": kid} if kid is not None else {}
    key = "secret" if alg.startswith("HS") else priv
    return jwt.encode(payload, key, algorithm=alg, headers=headers)


def _validator(jwks, *, fetcher=None) -> KeycloakJwtValidator:
    return KeycloakJwtValidator(
        jwks_url="https://kc.example/jwks",
        issuer=_ISS,
        audience=_AUD,
        jwks_fetcher=fetcher or (lambda: jwks),
    )


def test_valid_token_yields_identity_from_token():
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    ident = v.validate(_tok(priv))
    assert isinstance(ident, VerifiedIdentity)
    assert (
        ident.tenant_id == "tenant-A"
        and ident.session_id == "sess-1"
        and ident.subject == "user-1"
    )
    assert ident.email_verified is False


def test_email_verified_must_be_the_literal_boolean_true():
    priv = _keypair()
    validator = _validator(_jwks(priv.public_key()))
    assert (
        validator.validate(_tok(priv, claims={"email_verified": True})).email_verified
        is True
    )
    assert (
        validator.validate(_tok(priv, claims={"email_verified": "true"})).email_verified
        is False
    )


def test_alg_none_is_rejected():
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    # an unsigned alg:none token
    tok = jwt.encode(
        {"iss": _ISS, "aud": _AUD, "sub": "x", "tenant_id": "tenant-A"},
        key=None,
        algorithm="none",
        headers={"kid": "k1"},
    )
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
    body = _b64(
        json.dumps(
            {
                "iss": _ISS,
                "aud": _AUD,
                "sub": "x",
                "sid": "s",
                "tenant_id": "tenant-A",
                "exp": int(time.time()) + 3600,
            }
        ).encode()
    )
    signing_input = head + b"." + body
    sig = _b64(hmac.new(pub_pem, signing_input, hashlib.sha256).digest())
    forged = (signing_input + b"." + sig).decode()

    v = _validator(_jwks(priv.public_key()))
    with pytest.raises(AuthError):
        v.validate(
            forged
        )  # alg HS256 not in pinned ["RS256"] → rejected before any key use


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


def test_parallel_unknown_kids_are_single_flight_and_globally_rate_limited():
    """Different random kids must not bypass an exact-kid negative cache and fan out fetches."""
    priv = _keypair()
    calls = 0
    entered = threading.Event()
    release = threading.Event()

    def fetcher():
        nonlocal calls
        calls += 1
        if calls == 2:
            entered.set()
            assert release.wait(timeout=2)
        return _jwks(priv.public_key(), kid="known")

    clock = [100.0]
    validator = KeycloakJwtValidator(
        jwks_url="https://kc.example/jwks",
        issuer=_ISS,
        audience=_AUD,
        jwks_fetcher=fetcher,
        monotonic=lambda: clock[0],
    )
    # Populate with a known key first. The next miss gets the single permitted rotation refresh.
    assert validator.validate(_tok(priv, kid="known")).subject == "user-1"

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [
            pool.submit(validator.validate, _tok(priv, kid=f"random-{idx}"))
            for idx in range(12)
        ]
        assert entered.wait(timeout=2)
        release.set()
        for future in futures:
            with pytest.raises(AuthError):
                future.result(timeout=2)

    assert calls == 2  # one population + one coalesced unknown-kid refresh


def test_negative_kid_cache_is_bounded_and_repeated_miss_does_not_refetch():
    priv = _keypair()
    calls = 0
    clock = [10.0]

    def fetcher():
        nonlocal calls
        calls += 1
        return _jwks(priv.public_key(), kid="known")

    validator = KeycloakJwtValidator(
        jwks_url="https://kc.example/jwks",
        issuer=_ISS,
        audience=_AUD,
        jwks_fetcher=fetcher,
        monotonic=lambda: clock[0],
        max_negative_kids=3,
    )
    validator.validate(_tok(priv, kid="known"))
    for kid in ("missing-a", "missing-a", "missing-b", "missing-c", "missing-d"):
        with pytest.raises(AuthError):
            validator.validate(_tok(priv, kid=kid))
    assert calls == 2
    assert len(validator._negative_kids) == 3  # noqa: SLF001 - security invariant


def test_cache_control_max_age_is_capped_and_expired_cache_fails_closed():
    priv = _keypair()
    clock = [0.0]
    calls = 0

    def fetcher():
        nonlocal calls
        calls += 1
        if calls == 1:
            return JwksFetchResult(_jwks(priv.public_key()), "public, max-age=999999")
        raise RuntimeError("sensitive upstream detail")

    validator = KeycloakJwtValidator(
        jwks_url="https://kc.example/jwks",
        issuer=_ISS,
        audience=_AUD,
        jwks_fetcher=fetcher,
        jwks_max_ttl_s=60,
        jwks_ttl_s=30,
        monotonic=lambda: clock[0],
    )
    validator.validate(_tok(priv))
    clock[0] = 59.9
    validator.validate(_tok(priv))
    clock[0] = 60.0
    with pytest.raises(AuthError, match="validation unavailable") as error:
        validator.validate(_tok(priv))
    assert "sensitive" not in str(error.value)


def test_removed_signing_key_is_rejected_after_bounded_ttl():
    old_priv, new_priv = _keypair(), _keypair()
    clock = [0.0]
    fetches = [
        JwksFetchResult(_jwks(old_priv.public_key(), "old"), "max-age=10"),
        JwksFetchResult(_jwks(new_priv.public_key(), "new"), "max-age=10"),
    ]
    validator = KeycloakJwtValidator(
        jwks_url="https://kc.example/jwks",
        issuer=_ISS,
        audience=_AUD,
        jwks_fetcher=lambda: fetches.pop(0),
        jwks_ttl_s=10,
        jwks_max_ttl_s=10,
        unknown_kid_refresh_interval_s=1,
        negative_kid_ttl_s=5,
        monotonic=lambda: clock[0],
    )
    validator.validate(_tok(old_priv, kid="old"))
    clock[0] = 10.0
    with pytest.raises(AuthError):
        validator.validate(_tok(old_priv, kid="old"))


def test_no_store_jwks_is_usable_once_but_never_served_as_a_stale_cache():
    priv = _keypair()
    calls = 0

    def fetcher():
        nonlocal calls
        calls += 1
        return JwksFetchResult(_jwks(priv.public_key()), "no-store")

    validator = _validator(_jwks(priv.public_key()), fetcher=fetcher)
    assert validator.validate(_tok(priv)).subject == "user-1"
    assert validator.validate(_tok(priv)).subject == "user-1"
    assert calls == 2
    for _ in range(2):
        with pytest.raises(AuthError):
            validator.validate(_tok(priv, kid="unknown-no-store"))
    assert calls == 3


def test_parallel_keycloak_outage_is_single_flight_and_backed_off():
    priv = _keypair()
    calls = 0
    entered = threading.Event()
    release = threading.Event()

    def fetcher():
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(timeout=2)
        raise RuntimeError("upstream outage with sensitive detail")

    validator = _validator(_jwks(priv.public_key()), fetcher=fetcher)
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(validator.validate, _tok(priv)) for _ in range(12)]
        assert entered.wait(timeout=2)
        release.set()
        for future in futures:
            with pytest.raises(AuthError, match="validation unavailable"):
                future.result(timeout=2)
    assert calls == 1
    with pytest.raises(AuthError, match="validation unavailable"):
        validator.validate(_tok(priv))
    assert calls == 1


def test_backend_caps_access_token_age_even_if_exp_is_misconfigured_longer():
    priv = _keypair()
    now = int(time.time())
    validator = KeycloakJwtValidator(
        jwks_url="https://kc.example/jwks",
        issuer=_ISS,
        audience=_AUD,
        jwks_fetcher=lambda: _jwks(priv.public_key()),
        max_token_age_s=300,
        clock_skew_s=0,
        epoch_time=lambda: float(now),
    )
    stale = _tok(priv, claims={"iat": now - 301, "exp": now + 3600})
    with pytest.raises(AuthError):
        validator.validate(stale)


def test_token_errors_never_expose_kid_token_or_library_exception_details():
    priv = _keypair()
    validator = _validator(_jwks(priv.public_key()))
    malicious_kid = "attacker-secret-kid"
    with pytest.raises(AuthError) as error:
        validator.validate(_tok(priv, kid=malicious_kid))
    rendered = str(error.value)
    assert malicious_kid not in rendered
    assert "JWKS" not in rendered


def test_missing_kid_is_rejected():
    """Cutover hardening: a token with NO kid header must be rejected — never fall back to the
    first JWKS key (a signed-by-anything token must not get a free key guess)."""
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    with pytest.raises(AuthError):
        v.validate(_tok(priv, kid=None))


def test_jwks_key_without_kid_never_matches():
    """A JWKS entry lacking kid must never satisfy a token's kid — exact match only."""
    priv = _keypair()
    jwks = _jwks(priv.public_key(), kid="k1")
    del jwks["keys"][0]["kid"]
    v = _validator(jwks)
    with pytest.raises(AuthError):
        v.validate(_tok(priv, kid="k1"))


def test_missing_tenant_claim_gets_stable_private_workspace():
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    first = v.validate(_tok(priv, claims={"tenant_id": None}))
    second = v.validate(_tok(priv, claims={"tenant_id": None, "sid": "another"}))
    assert first.tenant_id.startswith("personal-")
    assert first.tenant_id == second.tenant_id
    assert first.tenant_id != "tenant-A"


def test_fake_validator_maps_tokens_and_rejects_unknown():
    fake = FakeAuthValidator(
        {"tok-A": VerifiedIdentity("tenant-A", "sess-A", "user-A")}
    )
    assert fake.validate("tok-A").tenant_id == "tenant-A"
    with pytest.raises(AuthError):
        fake.validate("tok-unknown")


def test_realm_roles_extracted_from_token():
    # Keycloak puts realm roles under realm_access.roles — the validator carries them onto the
    # VerifiedIdentity (used ONLY for admin gating; identity itself never depends on roles).
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    ident = v.validate(
        _tok(priv, claims={"realm_access": {"roles": ["sealai-admin", "user"]}})
    )
    assert ident.roles == ("sealai-admin", "user")


def test_no_realm_access_yields_empty_roles():
    # A token without realm_access is a valid identity with zero roles (no admin access) — never an error.
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    assert v.validate(_tok(priv)).roles == ()


def test_hersteller_id_claim_extracted():
    # The manufacturer self-service surface is scoped by this claim (a Keycloak user-attribute mapper).
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    ident = v.validate(_tok(priv, claims={"hersteller_id": "acme"}))
    assert ident.hersteller_id == "acme"


def test_no_hersteller_id_yields_empty():
    priv = _keypair()
    v = _validator(_jwks(priv.public_key()))
    assert v.validate(_tok(priv)).hersteller_id == ""


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "x" * 256},
        {"sid": "x" * 256},
        {"sid": 0},
        {"tenant_id": "x" * 256},
        {"tenant_id": 0},
        {"tenant_id": {"forged": "scope"}},
        {"realm_access": {"roles": ["ok", 7]}},
        {"realm_access": {"roles": ["x" * 129]}},
        {"hersteller_id": "bad\nclaim"},
        {"hersteller_id": 0},
    ],
)
def test_identity_boundary_rejects_unbounded_or_non_string_claims(claims):
    priv = _keypair()
    validator = _validator(_jwks(priv.public_key()))
    with pytest.raises(AuthError, match="token rejected"):
        validator.validate(_tok(priv, claims=claims))
