from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import psycopg

from app.core.config import settings

log = logging.getLogger(__name__)


def _table_exists(cur) -> bool:
    try:
        cur.execute("select to_regclass('public.user_profiles')")
        row = cur.fetchone()
        return bool(row and row[0])
    except Exception:
        return False


def get_user_profile(user_id: Optional[str]) -> Dict[str, Any]:
    """
    Load user profile from Postgres table `user_profiles` if present.

    Expected schema (if present):
      user_profiles(user_id text primary key, role text NULL, prefs jsonb NULL, params_patch jsonb NULL)

    Returns dict with keys: user_id, role?, prefs?, params_patch?
    Fails softly (returns {}).
    """
    if not user_id:
        return {}
    dsn = settings.POSTGRES_SYNC_URL
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                if not _table_exists(cur):
                    return {}
                cur.execute(
                    """
                    select user_id, role, prefs, params_patch
                    from public.user_profiles
                    where user_id = %s
                    limit 1
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                if not row:
                    return {}
                uid, role, prefs, params_patch = row
                def _jsonify(x: Any) -> Any:
                    if x is None:
                        return None
                    if isinstance(x, (dict, list)):
                        return x
                    try:
                        return json.loads(x)
                    except Exception:
                        return x
                profile: Dict[str, Any] = {"user_id": uid}
                if role:
                    profile["role"] = role
                p = _jsonify(prefs)
                if p is not None:
                    profile["prefs"] = p
                pp = _jsonify(params_patch)
                if pp is not None:
                    profile["params_patch"] = pp
                return profile
    except Exception as e:
        try:
            log.warning("profile_loader_failed", exc=str(e))
        except Exception:
            pass
        return {}


def profile_to_context(profile: Dict[str, Any], max_len: int = 600) -> str:
    if not profile:
        return ""
    role = profile.get("role")
    prefs = profile.get("prefs") or {}
    parts = []
    if role:
        parts.append(f"User-Rolle: {role}")
    if isinstance(prefs, dict) and prefs:
        kv = ", ".join([f"{k}={v}" for k, v in list(prefs.items())[:8]])
        parts.append(f"Präferenzen: {kv}")
    ctx = "\n".join(parts)
    return ctx[:max_len]

