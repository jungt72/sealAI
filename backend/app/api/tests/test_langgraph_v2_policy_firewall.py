"""Tests for deterministic policy firewall fail-closed behavior."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure backend is on path (tests run from repo root in some setups).
sys.path.append(str(Path(__file__).resolve().parents[3]))

# Minimal env defaults for settings to load (avoid import-time config failures).
os.environ.setdefault("openai_api_key", "sk-test")

from app.langgraph_v2.nodes.nodes_policy import policy_firewall_node  # noqa: E402
from app.langgraph_v2.sealai_graph_v2 import _policy_gate_router  # noqa: E402
from app.langgraph_v2.state import SealAIState  # noqa: E402


def _missing_fields(request: Any) -> List[str]:
    if request is None:
        return []
    if hasattr(request, "model_dump"):
        data: Dict[str, Any] = request.model_dump()
    elif isinstance(request, dict):
        data = request
    else:
        data = getattr(request, "__dict__", {})
    missing = data.get("missing_fields") or []
    return list(missing)


def test_policy_firewall_blocks_when_material_and_profile_missing() -> None:
    state = SealAIState()

    patch = policy_firewall_node(state)
    report = patch.get("policy_report") or {}

    assert report.get("status") == "skipped"
    violations = report.get("violations") or []
    assert violations, "policy_report should explain why the policy gate blocked"
    assert any(v.get("reason") == "missing_material_or_profile" for v in violations)

    assert patch.get("awaiting_user_input") is True
    assert patch.get("ask_missing_request") is not None
    missing_fields = _missing_fields(patch.get("ask_missing_request"))
    assert "material" in missing_fields
    assert "profile" in missing_fields

    routed_state = state.model_copy(update=patch)
    assert _policy_gate_router(routed_state) == "ask_missing"
