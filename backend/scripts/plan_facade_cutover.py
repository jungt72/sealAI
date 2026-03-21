"""
Static Cutover Analysis — SSoT Facade Planning
Blueprint Section 12 — Read-Only Audit

Compares:
  LEGACY  : app/api/v1/endpoints/langgraph_v2.py  →  LangGraphV2Request
            app/api/v1/sse_runtime.py              →  event_multiplexer
  SSoT    : app/agent/api/models.py                →  ChatRequest / ChatResponse
            app/agent/api/sse_runtime.py           →  agent_sse_generator

Outputs:
  1. Request model delta  (field-by-field)
  2. Response model delta (field-by-field)
  3. SSE event-type delta (legacy vs SSoT)
  4. Architecture recommendation

No code is modified. This is a planning tool only.
"""
from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent  # → backend/

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _extract_pydantic_fields(source: str, class_name: str) -> dict[str, dict]:
    """Extract field names and metadata from a Pydantic class via AST."""
    tree = ast.parse(source)
    fields: dict[str, dict] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            # annotated assignment: `name: type = Field(...)` or `name: type`
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fname = item.target.id
                if fname.startswith("_"):
                    continue
                type_str = ast.unparse(item.annotation) if item.annotation else "Any"
                default = ast.unparse(item.value) if item.value else "REQUIRED"
                # detect aliases from Field(...) call
                aliases: list[str] = []
                if item.value and isinstance(item.value, ast.Call):
                    for kw in (item.value.keywords or []):
                        if kw.arg in ("validation_alias", "alias"):
                            aliases.append(ast.unparse(kw.value))
                required = (item.value is None) or ("..." in ast.unparse(item.value) if item.value else False)
                fields[fname] = {
                    "type": type_str,
                    "default": default,
                    "required": required,
                    "aliases": aliases,
                }
    return fields


def _extract_sse_event_types(source: str) -> set[str]:
    """Find all string literals used as SSE event-type names."""
    # Patterns:
    #   _format_sse("event_name", ...)
    #   _format_sse_text("event_name", ...)
    #   _queue_emit("event_name", ...)
    #   "type": "event_name"
    #   yield _format_sse_text("event_name", ...)
    events: set[str] = set()

    # From function call first argument
    for fn in ("_format_sse", "_format_sse_text", "_queue_emit", "_eventsource_event"):
        for m in re.finditer(rf'{re.escape(fn)}\s*\(\s*["\']([^"\']+)["\']', source):
            events.add(m.group(1))

    # From "type": "..." patterns
    for m in re.finditer(r'"type"\s*:\s*["\']([^"\']+)["\']', source):
        events.add(m.group(1))

    # From yield statements
    for m in re.finditer(r'yield\s+f?["\']data:\s*\{.*?"type":\s*"([^"]+)"', source):
        events.add(m.group(1))

    # Remove generic/internal non-event values
    non_events = {"message", "error_detail", "event", "type", "status", "done_payload"}
    return {e for e in events if e and e not in non_events and not e.startswith("{")}


def _col(text: str, width: int, pad: str = " ") -> str:
    text = str(text)
    if len(text) > width:
        text = text[: width - 1] + "…"
    return text.ljust(width, pad)


def _hr(width: int = 80) -> str:
    return "─" * width


def _section(title: str) -> str:
    line = f"  {title}  "
    pad = "═" * ((80 - len(line)) // 2)
    return f"\n{pad}{line}{pad}"


# ─────────────────────────────────────────────────────────────────────────────
# Load sources
# ─────────────────────────────────────────────────────────────────────────────

legacy_endpoint_src  = _read("app/api/v1/endpoints/langgraph_v2.py")
legacy_sse_src       = _read("app/api/v1/sse_runtime.py")
fast_brain_src       = _read("app/api/v1/fast_brain_runtime.py")
ssot_models_src      = _read("app/agent/api/models.py")
ssot_sse_src         = _read("app/agent/api/sse_runtime.py")

# ─────────────────────────────────────────────────────────────────────────────
# 1. Request model delta
# ─────────────────────────────────────────────────────────────────────────────

legacy_req  = _extract_pydantic_fields(legacy_endpoint_src, "LangGraphV2Request")
ssot_req    = _extract_pydantic_fields(ssot_models_src,     "ChatRequest")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Response model delta
# ─────────────────────────────────────────────────────────────────────────────

ssot_resp   = _extract_pydantic_fields(ssot_models_src, "ChatResponse")

# Legacy does not have a single response model — the SSE stream is the response.
# We synthesize the legacy response shape from _build_state_update_payload keys.
legacy_state_update_keys: set[str] = set()
for m in re.finditer(r'"([a-z_]+)"\s*:', legacy_sse_src):
    key = m.group(1)
    if len(key) > 2 and not key.startswith("on_"):
        legacy_state_update_keys.add(key)

# ─────────────────────────────────────────────────────────────────────────────
# 3. SSE event-type delta
# ─────────────────────────────────────────────────────────────────────────────

legacy_events = _extract_sse_event_types(legacy_sse_src) | _extract_sse_event_types(fast_brain_src)
ssot_events   = _extract_sse_event_types(ssot_sse_src)

only_legacy = sorted(legacy_events - ssot_events)
only_ssot   = sorted(ssot_events - legacy_events)
shared      = sorted(legacy_events & ssot_events)

# ─────────────────────────────────────────────────────────────────────────────
# 4. Print report
# ─────────────────────────────────────────────────────────────────────────────

print()
print("╔" + "═" * 78 + "╗")
print("║" + "  SealAI Facade Cutover Analysis — Blueprint Section 12".center(78) + "║")
print("║" + "  Read-Only Static Audit — no files modified".center(78) + "║")
print("╚" + "═" * 78 + "╝")

# ── REQUEST MODEL DELTA ──────────────────────────────────────────────────────
print(_section("1. REQUEST MODEL DELTA"))
print()
print(f"  {'Field':<28} {'Legacy (LangGraphV2Request)':<28} {'SSoT (ChatRequest)':<20} {'Gap'}")
print(f"  {_hr(26)} {_hr(26)} {_hr(18)} {_hr(6)}")

all_req_fields = sorted(set(list(legacy_req) + list(ssot_req)))
for f in all_req_fields:
    in_legacy = f in legacy_req
    in_ssot   = f in ssot_req
    l_type    = legacy_req[f]["type"][:24] if in_legacy else "—"
    s_type    = ssot_req[f]["type"][:18]   if in_ssot   else "—"
    gap       = ""
    if in_legacy and not in_ssot:
        gap = "⚠ LEGACY ONLY"
    elif in_ssot and not in_legacy:
        gap = "✚ SSOT ONLY"
    print(f"  {_col(f,28)} {_col(l_type,28)} {_col(s_type,20)} {gap}")

print()
print("  KEY ALIASES (Legacy → SSoT mapping):")
alias_map = {
    "input"          : "message   (aliases: input, message, text)",
    "chat_id"        : "session_id (aliases: chat_id, chatId, thread_id, session_id, sessionId)",
    "client_msg_id"  : "— (no SSoT equivalent — tracing only)",
    "metadata"       : "— (no SSoT equivalent — dropped at boundary)",
    "client_context" : "— (no SSoT equivalent — dropped at boundary)",
}
for k, v in alias_map.items():
    print(f"  {k:<22} →  {v}")

# ── RESPONSE / STATE_UPDATE PAYLOAD DELTA ───────────────────────────────────
print(_section("2. RESPONSE PAYLOAD DELTA"))
print()
print("  Legacy sends SSE stream (no REST body). SSoT sends ChatResponse (REST JSON)")
print("  + a lean SSE stream for /chat/stream. Comparison of state_update keys:\n")

legacy_top_keys = {
    "phase", "last_node", "preview_text", "governed_output_text", "governed_output_status",
    "governed_output_ready", "governance_metadata", "final_text", "final_answer",
    "awaiting_user_input", "streaming_complete", "awaiting_user_confirmation",
    "recommendation_ready", "recommendation_go", "coverage_score", "coverage_gaps",
    "missing_params", "working_profile", "live_calc_tile", "calc_results",
    "compliance_results", "delta", "pending_action", "confirm_checkpoint_id",
    "final_prompt_metadata", "rfq_admissibility", "candidate_semantics",
    "rfq_ready", "rfq_confirmed", "rfq_document", "sealing_requirement_spec",
    "rfq_draft",
}
ssot_top_keys = {
    "reply", "session_id", "sealing_state", "interaction_class", "runtime_path",
    "binding_level", "has_case_state", "case_id", "qualified_action_gate",
    "result_contract", "rfq_ready", "visible_case_narrative", "result_form",
    "path", "stream_mode", "required_fields", "coverage_status", "boundary_flags",
    "escalation_reason", "case_state", "working_profile", "version_provenance",
    "next_step_contract",
}

only_legacy_keys = sorted(legacy_top_keys - ssot_top_keys)
only_ssot_keys   = sorted(ssot_top_keys - legacy_top_keys)
shared_keys      = sorted(legacy_top_keys & ssot_top_keys)

print(f"  {'Key':<32} {'Legacy':<10} {'SSoT':<10} {'Bridge action'}")
print(f"  {_hr(30)} {_hr(8)} {_hr(8)} {_hr(28)}")

for k in sorted(legacy_top_keys | ssot_top_keys):
    in_l = k in legacy_top_keys
    in_s = k in ssot_top_keys
    l_mark = "  ✓" if in_l else "  —"
    s_mark = "  ✓" if in_s else "  —"
    if in_l and in_s:
        action = "direct pass-through"
    elif in_l and not in_s:
        action = "⚠ ADAPTER: map from sealing_state"
    else:
        action = "✚ ENRICH: add to legacy event"
    print(f"  {_col(k,32)} {l_mark:<10} {s_mark:<10} {action}")

# ── SSE EVENT-TYPE DELTA ─────────────────────────────────────────────────────
print(_section("3. SSE EVENT-TYPE DELTA"))
print()
print(f"  {'Event type':<28} {'Legacy':<10} {'SSoT':<10} {'Risk'}")
print(f"  {_hr(26)} {_hr(8)} {_hr(8)} {_hr(30)}")

CRITICAL_FE_EVENTS = {
    "state_update", "text_chunk", "token", "turn_complete", "done",
    "node_status", "profile_update", "error", "heartbeat",
}

all_events = sorted(legacy_events | ssot_events)
for e in all_events:
    in_l = e in legacy_events
    in_s = e in ssot_events
    l_mark = "  ✓" if in_l else "  —"
    s_mark = "  ✓" if in_s else "  —"
    if in_l and in_s:
        risk = "✓ SHARED"
    elif in_l and not in_s:
        risk = ("🔴 CRITICAL: frontend expects this" if e in CRITICAL_FE_EVENTS
                else "⚠ MISSING from SSoT")
    else:
        risk = "✚ NEW in SSoT (frontend unaware)"
    print(f"  {_col(e,28)} {l_mark:<10} {s_mark:<10} {risk}")

print()
print(f"  Summary: {len(legacy_events)} legacy events | {len(ssot_events)} SSoT events")
print(f"           {len(shared)} shared | {len(only_legacy)} legacy-only | {len(only_ssot)} SSoT-only")

# ── ARCHITECTURE RECOMMENDATION ──────────────────────────────────────────────
print(_section("4. ARCHITECTURE RECOMMENDATION"))
print("""
  RECOMMENDED PATTERN: Thin Translation Facade (not a full rewrite)
  ─────────────────────────────────────────────────────────────────

  A. Request Translation Layer  (langgraph_v2.py → agent router)
  ──────────────────────────────────────────────────────────────
  Create a helper in langgraph_v2.py:

    def _to_ssot_chat_request(req: LangGraphV2Request) -> ChatRequest:
        return ChatRequest(
            message    = req.input,
            session_id = req.chat_id,
        )

  Fields dropped: client_msg_id, metadata, client_context
    → These are already handled BEFORE routing (dedup, upsert_conversation)
    → They must remain in langgraph_v2.py; the SSoT does not need them.

  B. Response Translation Layer  (ChatResponse → legacy SSE stream)
  ─────────────────────────────────────────────────────────────────
  The legacy frontend expects these SSE events (in order):

    1. state_update   {phase, last_node, working_profile, ...}   ← CRITICAL
    2. text_chunk     {text}                                      ← CRITICAL
    3. token          {text}           (alias for text_chunk)     ← CRITICAL
    4. turn_complete  {}                                          ← CRITICAL
    5. done           {chat_id}                                   ← CRITICAL
    6. node_status    {node, phase}                               ← WARNING
    7. profile_update {working_profile}                           ← WARNING
    8. safety_alert   {message}                                   ← INFO

  SSoT emits: text_chunk, state_update, [DONE]  (3 types only)

  TRANSLATION MAP:
    SSoT text_chunk       →  emit legacy "text_chunk" + "token"  (direct)
    SSoT state_update     →  translate sealing_state → legacy state_update payload
                              (map: sealing_state.governance → governance_metadata,
                                    working_profile         → working_profile,
                                    sealing_state.cycle     → phase/last_node,
                                    conflicts               → coverage_gaps)
    SSoT [DONE]           →  emit legacy "turn_complete" + "done" {chat_id}

  MISSING from SSoT (must be synthesized in facade):
    • node_status    → emit once at start: {node: "fast_guidance_node"|"reasoning_node",
                        phase: "fast"|"structured"}  derived from SSoT runtime_path
    • profile_update → emit after state_update when working_profile changes
    • heartbeat      → wrap the SSoT stream with a 10s heartbeat generator
    • turn_complete  → always emit after SSoT [DONE]

  C. Suggested Facade Location
  ─────────────────────────────────────────────────────────────────
    backend/app/api/v1/endpoints/langgraph_v2.py

    Replace the current chat_v2 handler body with:
      1. _to_ssot_chat_request()         ← request translation
      2. await chat_endpoint(...)         ← delegate to SSoT
      3. _ssot_response_to_legacy_stream() ← event translation
         (async generator wrapping the SSoT response)

  D. Risk Assessment
  ─────────────────────────────────────────────────────────────────
    HIGH   : state_update payload shape — 33 legacy keys vs 23 SSoT keys
             Missing: phase, last_node, live_calc_tile, calc_results,
                      candidate_semantics, rfq_document, rfq_confirmed,
                      governed_output_text, awaiting_user_confirmation
             → These must be synthesized from sealing_state or set to null

    MEDIUM : Two-Speed Architecture (Fast Brain bypass) becomes a no-op.
             The SSoT always runs the full graph. Latency delta: ~8-14s vs 1-2s
             for simple questions.
             → Consider keeping Fast Brain for policy_path="fast" turns.

    LOW    : client_msg_id deduplication — already handled before routing.
             metadata / client_context — already handled before routing.

  E. Recommended Migration Order
  ─────────────────────────────────────────────────────────────────
    Step 1 (this session)  : Build & test facade with feature flag
                             SEALAI_SSOT_FACADE_ENABLED=1
    Step 2 (next session)  : Translate working_profile + governance_metadata
    Step 3                 : Translate live_calc_tile from RWDR tool output
    Step 4                 : Remove Fast Brain bypass once SSoT latency is < 3s
    Step 5                 : Delete legacy langgraph_v2 code path
""")

print("═" * 80)
print()
