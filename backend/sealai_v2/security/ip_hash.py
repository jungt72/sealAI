"""Salted IP-address hashing (Legal-by-Design Goal 3). The Legal-Gate acceptance record stores
``accepted_ip_hash``, never a raw IP — proves "this acceptance came from a stable network origin"
(useful for dispute/abuse investigation) without persisting a directly-identifying value. Salted
with a server-side pepper (never derived from the request itself) so the hash isn't a trivial
rainbow-table lookup over the (small, guessable) IPv4 space.

This is de-identification, not a security-secret: the pepper defaults to a fixed non-secret string
when unset, matching this module's actual job (avoid storing raw IPs at rest) rather than a
cryptographic-authentication use case (which would demand a real managed secret).
"""

from __future__ import annotations

import hashlib


def hash_ip(ip: str, *, pepper: str) -> str:
    if not ip.strip():
        return ""
    return hashlib.sha256(f"{pepper}:{ip.strip()}".encode("utf-8")).hexdigest()
