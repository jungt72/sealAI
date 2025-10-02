from __future__ import annotations

from typing import Any, Dict, List

from ....tools.profile_loader import get_user_profile, profile_to_context


def profile_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Load user profile from Postgres (if available) and inject into state.

    - Sets state.user_profile
    - Merges profile params_patch into state.params (shallow)
    - Appends a compact profile context to state.context
    """
    user_id = state.get("user_id") or None
    profile = get_user_profile(user_id)
    if not profile:
        return {**state, "phase": "profile"}

    out: Dict[str, Any] = {**state, "user_profile": profile, "phase": "profile"}

    # Merge params_patch into params
    if isinstance(profile.get("params_patch"), dict):
        params = dict(out.get("params") or {})
        for k, v in profile["params_patch"].items():
            params.setdefault(k, v)
        out["params"] = params

    # Context augmentation
    ctx = profile_to_context(profile)
    if ctx:
        existing = out.get("context") or ""
        if not isinstance(existing, str):
            existing = ""
        merged = "\n\n".join([p for p in [ctx, existing] if p])
        out["context"] = merged

    return out


__all__ = ["profile_node"]

