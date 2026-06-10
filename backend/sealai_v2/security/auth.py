"""M6c — the V2-owned auth adapter (P0). Validates a Keycloak JWT INSIDE V2 and derives identity ONLY
from the verified token (never a client header). I/O (JWKS fetch) lives here; the ``AuthValidator``
Protocol + ``VerifiedIdentity`` are pure ``core`` types. A ``FakeAuthValidator`` serves offline tests.

Classic-pitfall hardening: the verification algorithm is PINNED (``["RS256"]``) so the token's own
``alg`` header cannot dictate the method — ``alg:none`` and RS/HS alg-confusion are rejected. JWKS is
cached and refreshed ONCE on an unknown ``kid`` (so Keycloak key rotation does not break valid tokens).
"""

from __future__ import annotations

import json
from collections.abc import Callable

import jwt
from jwt.algorithms import RSAAlgorithm

from sealai_v2.core.contracts import AuthError, VerifiedIdentity

_ALGORITHMS = ("RS256",)  # PINNED — never trust the token header's alg


class KeycloakJwtValidator:
    """Implements the ``AuthValidator`` Protocol against a Keycloak realm's JWKS."""

    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str,
        audience: str,
        jwks_fetcher: Callable[[], dict] | None = None,
        tenant_claim: str = "tenant_id",
        algorithms: tuple[str, ...] = _ALGORITHMS,
    ) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._audience = audience
        self._tenant_claim = tenant_claim
        self._algorithms = tuple(algorithms)
        self._fetch = jwks_fetcher or self._http_fetch
        self._jwks: dict | None = None

    def _http_fetch(self) -> dict:
        import httpx  # lazy — never hit in offline tests (a fetcher is injected)

        return httpx.get(self._jwks_url, timeout=5.0).json()

    def _key_for_kid(self, kid: str | None):
        """Resolve the signing key for ``kid``; refresh the JWKS ONCE on a miss (key rotation)."""
        for allow_refresh in (True, False):
            if self._jwks is None:
                self._jwks = self._fetch()
            for jwk in self._jwks.get("keys", []):
                if kid is None or jwk.get("kid") == kid:
                    return RSAAlgorithm.from_jwk(json.dumps(jwk))
            if allow_refresh:
                self._jwks = None  # force a single refresh, then retry
        raise AuthError(f"no JWKS key for kid={kid!r}")

    def validate(self, token: str) -> VerifiedIdentity:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise AuthError(f"unparseable token: {exc}") from exc
        # PIN the algorithm: the token's alg must be one we accept — rejects alg:none + alg-confusion
        # BEFORE any key handling (never feed an RSA JWKS key into an HMAC verify).
        if header.get("alg") not in self._algorithms:
            raise AuthError(f"algorithm {header.get('alg')!r} not allowed (pinned {self._algorithms})")
        key = self._key_for_kid(header.get("kid"))
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=list(self._algorithms),
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp"]},
            )
        except jwt.InvalidTokenError as exc:
            raise AuthError(f"token rejected: {exc}") from exc

        tenant_id = claims.get(self._tenant_claim)
        subject = claims.get("sub")
        session_id = claims.get("sid") or subject  # conversation scope from the verified session
        if not tenant_id or not session_id or not subject:
            raise AuthError("token missing required identity claims (fail-closed)")
        return VerifiedIdentity(
            tenant_id=str(tenant_id), session_id=str(session_id), subject=str(subject)
        )


class FakeAuthValidator:
    """Deterministic offline validator: maps a bearer string → ``VerifiedIdentity`` (else rejects).
    Lets route tests drive tenant/session purely through the token (no network, no header-trust)."""

    def __init__(self, identities: dict[str, VerifiedIdentity]) -> None:
        self._identities = dict(identities)

    def validate(self, token: str) -> VerifiedIdentity:
        ident = self._identities.get(token)
        if ident is None:
            raise AuthError("unknown token")
        return ident
