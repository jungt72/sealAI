"""V2-owned Keycloak JWT validation with bounded, fail-closed JWKS rotation.

The validator intentionally remains synchronous because FastAPI executes the existing auth
dependency in its worker pool.  All mutable cache state is protected by a condition variable:
concurrent refreshes coalesce, random unknown ``kid`` values cannot amplify Keycloak traffic, and
an expired cache is never served when Keycloak is unavailable.
"""

from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

import jwt
from jwt.algorithms import RSAAlgorithm

from sealai_v2.core.contracts import AuthError, VerifiedIdentity

_ALGORITHMS = ("RS256",)  # PINNED — never trust the token header's alg
_KID_RE = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")
_MAX_JWKS_KEYS = 32
_MAX_CACHE_CONTROL_LENGTH = 1024
_MAX_IDENTITY_CLAIM_LENGTH = 255
_MAX_ROLES = 128
_MAX_ROLE_LENGTH = 128


def _personal_tenant_id(*, issuer: str, subject: str) -> str:
    """Stable private workspace for verified self-service identities without an organisation."""
    digest = sha256(f"{issuer}\x00{subject}".encode()).hexdigest()[:32]
    return f"personal-{digest}"


def _bounded_identity_claim(value: Any, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise AuthError("token rejected")
    if (not value and not allow_empty) or len(value) > _MAX_IDENTITY_CLAIM_LENGTH:
        raise AuthError("token rejected")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise AuthError("token rejected")
    return value


@dataclass(frozen=True)
class JwksFetchResult:
    """Validated transport envelope.  Tests may still inject a plain JWKS ``dict``."""

    payload: dict[str, Any]
    cache_control: str | None = None


def _cache_ttl(
    cache_control: str | None, *, default_ttl_s: float, max_ttl_s: float
) -> float:
    """Honor ``no-cache``/``no-store`` and max-age, but never exceed our revocation SLA."""
    if not cache_control:
        return min(default_ttl_s, max_ttl_s)
    if len(cache_control) > _MAX_CACHE_CONTROL_LENGTH:
        return 0.0
    directives = [part.strip().lower() for part in cache_control.split(",")]
    if "no-cache" in directives or "no-store" in directives:
        return 0.0
    for directive in directives:
        if not directive.startswith("max-age="):
            continue
        raw = directive.split("=", 1)[1].strip().strip('"')
        if raw.isdigit():
            return min(float(raw), max_ttl_s)
        return 0.0
    return min(default_ttl_s, max_ttl_s)


class KeycloakJwtValidator:
    """Validate Keycloak JWTs while bounding JWKS staleness and refresh amplification.

    ``jwks_max_ttl_s`` is the maximum signing-key revocation delay attributable to this cache.
    Once the TTL expires, a refresh failure rejects every token: stale keys are never accepted.
    A fresh unknown key may trigger at most one extra refresh per
    ``unknown_kid_refresh_interval_s`` across *all* unknown IDs, while the bounded negative cache
    prevents repeated misses for the same ID.
    """

    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str,
        audience: str,
        jwks_fetcher: Callable[[], dict[str, Any] | JwksFetchResult] | None = None,
        tenant_claim: str = "tenant_id",
        algorithms: tuple[str, ...] = _ALGORITHMS,
        jwks_ttl_s: float = 300.0,
        jwks_max_ttl_s: float = 600.0,
        unknown_kid_refresh_interval_s: float = 5.0,
        negative_kid_ttl_s: float = 30.0,
        max_negative_kids: int = 256,
        refresh_wait_timeout_s: float = 6.0,
        max_token_age_s: int = 300,
        clock_skew_s: int = 30,
        monotonic: Callable[[], float] = time.monotonic,
        epoch_time: Callable[[], float] = time.time,
    ) -> None:
        if not (0 < jwks_ttl_s <= jwks_max_ttl_s <= 900):
            raise ValueError("JWKS TTL bounds are invalid")
        if not (0 < unknown_kid_refresh_interval_s <= jwks_max_ttl_s):
            raise ValueError("unknown-kid refresh interval is invalid")
        if not (0 < negative_kid_ttl_s <= jwks_max_ttl_s):
            raise ValueError("negative-kid TTL is invalid")
        if not (1 <= max_negative_kids <= 4096):
            raise ValueError("negative-kid cache bound is invalid")
        if not (0 < refresh_wait_timeout_s <= 30):
            raise ValueError("JWKS refresh wait timeout is invalid")
        if not (60 <= max_token_age_s <= 900 and 0 <= clock_skew_s <= 60):
            raise ValueError("token-age bounds are invalid")

        self._jwks_url = jwks_url
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._tenant_claim = tenant_claim
        self._algorithms = tuple(algorithms)
        self._fetch = jwks_fetcher or self._http_fetch
        self._default_ttl_s = jwks_ttl_s
        self._max_ttl_s = jwks_max_ttl_s
        self._unknown_refresh_interval_s = unknown_kid_refresh_interval_s
        self._negative_ttl_s = negative_kid_ttl_s
        self._max_negative_kids = max_negative_kids
        self._refresh_wait_timeout_s = refresh_wait_timeout_s
        self._max_token_age_s = max_token_age_s
        self._clock_skew_s = clock_skew_s
        self._clock = monotonic
        self._epoch_time = epoch_time

        self._condition = threading.Condition(threading.Lock())
        self._refresh_inflight = False
        self._refresh_epoch = 0
        self._last_refresh_succeeded = True
        self._last_refresh_failure_at = float("-inf")
        self._keys: dict[str, Any] = {}
        self._has_fetched = False
        self._expires_at = 0.0
        self._last_unknown_refresh_at = float("-inf")
        self._negative_kids: OrderedDict[str, float] = OrderedDict()

    def _http_fetch(self) -> JwksFetchResult:
        import httpx  # lazy — never hit in offline tests (a fetcher is injected)

        response = httpx.get(self._jwks_url, timeout=5.0, follow_redirects=False)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("invalid JWKS payload")
        return JwksFetchResult(
            payload=payload,
            cache_control=response.headers.get("Cache-Control"),
        )

    def _normalize_fetch(
        self, raw: dict[str, Any] | JwksFetchResult
    ) -> JwksFetchResult:
        if isinstance(raw, JwksFetchResult):
            return raw
        if isinstance(raw, dict):
            return JwksFetchResult(payload=raw)
        raise ValueError("invalid JWKS fetch result")

    def _parse_keys(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_keys = payload.get("keys")
        if not isinstance(raw_keys, list) or not 1 <= len(raw_keys) <= _MAX_JWKS_KEYS:
            raise ValueError("invalid JWKS key set")
        parsed: dict[str, Any] = {}
        for raw in raw_keys:
            if not isinstance(raw, dict):
                raise ValueError("invalid JWK")
            kid = raw.get("kid")
            if not isinstance(kid, str) or not _KID_RE.fullmatch(kid) or kid in parsed:
                raise ValueError("invalid JWK id")
            if raw.get("kty") != "RSA":
                raise ValueError("invalid JWK type")
            if raw.get("use") not in (None, "sig") or raw.get("alg") not in (
                None,
                "RS256",
            ):
                raise ValueError("invalid JWK purpose")
            parsed[kid] = RSAAlgorithm.from_jwk(raw)
        return parsed

    def _prune_negative(self, now: float) -> None:
        for kid, expires_at in tuple(self._negative_kids.items()):
            if expires_at <= now:
                self._negative_kids.pop(kid, None)

    def _remember_negative(self, kid: str, now: float) -> None:
        self._negative_kids.pop(kid, None)
        self._negative_kids[kid] = now + self._negative_ttl_s
        while len(self._negative_kids) > self._max_negative_kids:
            self._negative_kids.popitem(last=False)

    def _fetch_and_publish(self) -> None:
        try:
            envelope = self._normalize_fetch(self._fetch())
            keys = self._parse_keys(envelope.payload)
            ttl = _cache_ttl(
                envelope.cache_control,
                default_ttl_s=self._default_ttl_s,
                max_ttl_s=self._max_ttl_s,
            )
        except Exception:
            with self._condition:
                self._refresh_epoch += 1
                self._last_refresh_succeeded = False
                self._last_refresh_failure_at = self._clock()
                self._refresh_inflight = False
                self._condition.notify_all()
            # No raw transport/parser exception crosses the auth boundary.
            raise AuthError("token validation unavailable") from None

        now = self._clock()
        with self._condition:
            self._keys = keys
            self._has_fetched = True
            self._expires_at = now + ttl
            for known_kid in keys:
                self._negative_kids.pop(known_kid, None)
            self._refresh_epoch += 1
            self._last_refresh_succeeded = True
            self._refresh_inflight = False
            self._condition.notify_all()

    def _key_for_kid(self, kid: str):
        """Resolve an exact signing key with bounded refresh and negative-cache behavior."""
        if not _KID_RE.fullmatch(kid):
            raise AuthError("token rejected")

        initial_rotation_retry = False
        while True:
            now = self._clock()
            with self._condition:
                self._prune_negative(now)
                fresh = self._has_fetched and now < self._expires_at
                key = self._keys.get(kid)
                if fresh and key is not None:
                    return key
                if kid in self._negative_kids:
                    raise AuthError("token rejected")

                if self._refresh_inflight:
                    observed_epoch = self._refresh_epoch
                    notified = self._condition.wait(
                        timeout=self._refresh_wait_timeout_s
                    )
                    if not notified:
                        raise AuthError("token validation unavailable")
                    # A zero-TTL/no-store response is valid for this coalesced request cohort but
                    # is never served to a later request. A failed refresh wakes every waiter into
                    # the same fail-closed result instead of a serial retry storm.
                    if self._refresh_epoch != observed_epoch:
                        if not self._last_refresh_succeeded:
                            raise AuthError("token validation unavailable")
                        key = self._keys.get(kid)
                        if key is not None:
                            return key
                        self._remember_negative(kid, self._clock())
                        raise AuthError("token rejected")
                    continue

                had_cache = self._has_fetched
                if (
                    not self._last_refresh_succeeded
                    and now - self._last_refresh_failure_at
                    < self._unknown_refresh_interval_s
                ):
                    raise AuthError("token validation unavailable")
                if not fresh and not initial_rotation_retry:
                    reason = "periodic"
                else:
                    if (
                        now - self._last_unknown_refresh_at
                        < self._unknown_refresh_interval_s
                    ):
                        self._remember_negative(kid, now)
                        raise AuthError("token rejected")
                    reason = "unknown"
                    self._last_unknown_refresh_at = now
                    initial_rotation_retry = False
                self._refresh_inflight = True

            self._fetch_and_publish()

            now = self._clock()
            with self._condition:
                key = self._keys.get(kid)
                # The just-fetched response may explicitly forbid caching (TTL=0); it is still
                # authoritative for this lookup and for threads that coalesced onto this fetch.
                if key is not None:
                    return key
                # Initial population may itself have raced a rotation. Permit exactly one
                # unknown-kid refresh; every later miss is negative-cached immediately.
                if reason == "periodic" and not had_cache:
                    initial_rotation_retry = True
                    continue
                self._remember_negative(kid, now)
                raise AuthError("token rejected")

    def validate(self, token: str) -> VerifiedIdentity:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError:
            raise AuthError("token rejected") from None

        if header.get("alg") not in self._algorithms:
            raise AuthError("token rejected")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise AuthError("token rejected")
        key = self._key_for_kid(kid)
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=list(self._algorithms),
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.InvalidTokenError:
            raise AuthError("token rejected") from None

        issued_at = claims.get("iat")
        if (
            isinstance(issued_at, bool)
            or not isinstance(issued_at, (int, float))
            or self._epoch_time() - float(issued_at)
            > self._max_token_age_s + self._clock_skew_s
        ):
            raise AuthError("token rejected")

        subject = _bounded_identity_claim(claims.get("sub"))
        raw_session = claims.get("sid")
        session_id = (
            subject
            if raw_session is None or raw_session == ""
            else _bounded_identity_claim(raw_session)
        )
        raw_tenant = claims.get(self._tenant_claim)
        tenant_id = (
            _personal_tenant_id(issuer=self._issuer, subject=subject)
            if raw_tenant is None or raw_tenant == ""
            else _bounded_identity_claim(raw_tenant)
        )
        realm = claims.get("realm_access")
        raw_roles = realm.get("roles") if isinstance(realm, dict) else None
        if raw_roles is None:
            roles = ()
        elif not isinstance(raw_roles, (list, tuple)) or len(raw_roles) > _MAX_ROLES:
            raise AuthError("token rejected")
        else:
            roles = tuple(
                _bounded_identity_claim(role)
                for role in raw_roles
                if isinstance(role, str) and 0 < len(role) <= _MAX_ROLE_LENGTH
            )
            if len(roles) != len(raw_roles):
                raise AuthError("token rejected")
        raw_hersteller_id = claims.get("hersteller_id")
        hersteller_id = (
            ""
            if raw_hersteller_id is None or raw_hersteller_id == ""
            else _bounded_identity_claim(raw_hersteller_id)
        )
        return VerifiedIdentity(
            tenant_id=tenant_id,
            session_id=session_id,
            subject=subject,
            roles=roles,
            hersteller_id=hersteller_id,
            email_verified=claims.get("email_verified") is True,
        )


class FakeAuthValidator:
    """Deterministic offline validator; never performs network I/O."""

    def __init__(self, identities: Mapping[str, VerifiedIdentity]) -> None:
        self._identities = dict(identities)

    def validate(self, token: str) -> VerifiedIdentity:
        ident = self._identities.get(token)
        if ident is None:
            raise AuthError("unknown token")
        return ident
