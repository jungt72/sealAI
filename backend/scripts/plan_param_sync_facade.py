"""
Parameter Sync Facade Plan — Blueprint Section 13
Read-Only Static Analysis — no files modified

Problem statement:
  The legacy system has a full parameter-patch pipeline
  (POST /api/v1/langgraph/parameters/patch) with versioning,
  3-layer state, identity normalization, and SSE broadcast.
  The SSoT (SESSION_STORE) has NO equivalent — parameters only
  enter via LLM turns. Blueprint Section 13 requires a direct
  REST path that bypasses the LLM.

Analyses:
  1. Legacy endpoint inventory (parameters/patch + state POST)
  2. SSoT sealing_state parameter structure
  3. Mapping: WorkingProfile keys → SSoT asserted layer sub-dicts
  4. 3-layer simplification for SSoT facade
  5. Staleness / cycle invalidation obligations
  6. SSE broadcast gap analysis
  7. Implementation recipe (step-by-step)
  8. Risk / open questions

No code is modified.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # → backend/


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        return f"# FILE NOT FOUND: {rel}"
    return p.read_text(encoding="utf-8")


def _hr(w: int = 80, c: str = "─") -> str:
    return c * w


def _section(title: str, c: str = "═") -> str:
    line = f"  {title}  "
    pad = c * ((80 - len(line)) // 2)
    return f"\n{pad}{line}{pad}"


# ─────────────────────────────────────────────────────────────────────────────
# Load sources
# ─────────────────────────────────────────────────────────────────────────────

lv2_src       = _read("app/api/v1/endpoints/langgraph_v2.py")
state_src     = _read("app/api/v1/endpoints/state.py")
param_src     = _read("app/_legacy_v2/utils/parameter_patch.py")
router_src    = _read("app/agent/api/router.py")
agent_st_src  = _read("app/agent/agent/state.py")
rag_state_src = _read("app/services/rag/state.py")

# ─────────────────────────────────────────────────────────────────────────────
# 1. Endpoint inventory
# ─────────────────────────────────────────────────────────────────────────────

LEGACY_PARAM_ENDPOINTS = [
    {
        "method": "POST",
        "path": "/api/v1/langgraph/parameters/patch",
        "file": "app/api/v1/endpoints/langgraph_v2.py",
        "request_model": "ParametersPatchRequest {chat_id, parameters, base_versions}",
        "state_source": "LangGraph Postgres checkpointer",
        "pipeline": "sanitize → stage_extracted → build_normalized → apply_LWW → assert → aupdate_state",
        "has_ssot_facade": "NO",
        "sse_broadcast": "YES — emits 'parameter_patch_ack' via sse_broadcast.broadcast()",
        "versioning": "YES — LWW per field, base_versions conflict detection",
        "staleness": "YES — build_assertion_cycle_update() marks derived artifacts stale",
    },
    {
        "method": "POST",
        "path": "/api/v1/langgraph/state",
        "file": "app/api/v1/endpoints/state.py",
        "request_model": "StateUpdate {working_profile: WorkingProfile, source, timestamp}",
        "state_source": "LangGraph Postgres checkpointer",
        "pipeline": "apply_parameter_patch_to_state_layers → aupdate_state",
        "has_ssot_facade": "NO",
        "sse_broadcast": "NO",
        "versioning": "Partial (delegates to apply_parameter_patch_to_state_layers)",
        "staleness": "NO — does not call build_assertion_cycle_update()",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# 2. SSoT sealing_state parameter structure
#    from app/agent/agent/state.py AssertedLayer
# ─────────────────────────────────────────────────────────────────────────────

SSOT_ASSERTED_SUB_DICTS = {
    "operating_conditions": ["pressure_bar", "temperature_c", "pressure_raw", "temperature_raw"],
    "machine_profile": [
        "shaft_diameter_mm", "bore_diameter_mm", "groove_width_mm",
        "groove_depth_mm", "piston_rod_diameter_mm", "rpm",
    ],
    "medium_profile": ["medium", "medium_raw", "medium_detail", "medium_type", "medium_additives"],
    "installation_profile": [
        "dynamic_type", "motion_type", "shaft_orientation",
        "installation_class",
    ],
    "sealing_requirement_spec": [],   # derived, not directly user-patchable
}

# WorkingProfile keys → SSoT asserted sub-dict (routing table)
WORKING_PROFILE_TO_ASSERTED_MAP = {
    # operating_conditions
    "pressure_bar":      "operating_conditions",
    "pressure_raw":      "operating_conditions",
    "temperature_c":     "operating_conditions",
    "temperature_C":     "operating_conditions",
    "temperature_raw":   "operating_conditions",
    "pressure_max_bar":  "operating_conditions",
    "pressure_min_bar":  "operating_conditions",
    # machine_profile
    "shaft_diameter_mm":      "machine_profile",
    "shaft_diameter":         "machine_profile",
    "bore_diameter_mm":       "machine_profile",
    "piston_rod_diameter_mm": "machine_profile",
    "groove_width_mm":        "machine_profile",
    "groove_depth_mm":        "machine_profile",
    "rpm":                    "machine_profile",
    "shaft_runout_mm":        "machine_profile",
    "shaft_hardness_hrc":     "machine_profile",
    # medium_profile
    "medium":             "medium_profile",
    "medium_detail":      "medium_profile",
    "medium_type":        "medium_profile",
    "medium_additives":   "medium_profile",
    "medium_viscosity":   "medium_profile",
    # installation_profile
    "dynamic_type":       "installation_profile",
    # top-level working_profile (no sub-dict equivalent)
    "material":           "working_profile_flat",
    "flange_standard":    "working_profile_flat",
    "emission_class":     "working_profile_flat",
    "industry_sector":    "working_profile_flat",
}

# ─────────────────────────────────────────────────────────────────────────────
# 3. Probe: does the SSoT have any parameter patch endpoint?
# ─────────────────────────────────────────────────────────────────────────────

has_param_patch_ssot = (
    "parameters/patch" in router_src
    or "param_patch" in router_src
    or "PATCH" in router_src and "parameter" in router_src.lower()
)
has_find_session = "_find_session" in router_src
has_save_session = "_save_session" in router_src
has_sanitize = "sanitize_v2_parameter_patch" in lv2_src
has_sse_broadcast = "sse_broadcast.broadcast" in lv2_src
has_assertion_cycle = "build_assertion_cycle_update" in lv2_src
has_facade_in_lv2 = "SEALAI_SSOT_FACADE_ENABLED" in lv2_src

# ─────────────────────────────────────────────────────────────────────────────
# 4. Count WorkingProfile fields for scope assessment
# ─────────────────────────────────────────────────────────────────────────────

wp_fields = []
try:
    tree = ast.parse(rag_state_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "WorkingProfile":
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if not item.target.id.startswith("_"):
                        wp_fields.append(item.target.id)
except Exception:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# Print report
# ─────────────────────────────────────────────────────────────────────────────

print()
print("╔" + "═" * 78 + "╗")
print("║" + "  SealAI Parameter Sync Facade Plan — Blueprint Section 13".center(78) + "║")
print("║" + "  Read-Only Static Analysis — no files modified".center(78) + "║")
print("╚" + "═" * 78 + "╝")

# ── SECTION 1: Endpoint Inventory ────────────────────────────────────────────
print(_section("1. EXISTING PARAMETER ENDPOINTS"))
print()
for ep in LEGACY_PARAM_ENDPOINTS:
    print(f"  {ep['method']} {ep['path']}")
    print(f"    File         : {ep['file']}")
    print(f"    Request      : {ep['request_model']}")
    print(f"    State source : {ep['state_source']}")
    print(f"    Pipeline     : {ep['pipeline']}")
    print(f"    SSoT facade  : {ep['has_ssot_facade']}")
    print(f"    SSE broadcast: {ep['sse_broadcast']}")
    print(f"    Versioning   : {ep['versioning']}")
    print(f"    Staleness    : {ep['staleness']}")
    print()

print(f"  SEALAI_SSOT_FACADE_ENABLED referenced in langgraph_v2.py : {'YES' if has_facade_in_lv2 else 'NO'}")
print(f"  SSoT parameter patch endpoint in router.py               : {'YES' if has_param_patch_ssot else 'NO — MISSING'}")

# ── SECTION 2: SSoT State Structure ──────────────────────────────────────────
print(_section("2. SSOT SEALING_STATE PARAMETER STRUCTURE"))
print()
print("  SESSION_STORE[session_id]['sealing_state'] contains:")
print()
print(f"  {'Sub-dict':<30} {'User-Patchable Fields'}")
print(f"  {_hr(28)} {_hr(46)}")
for sub, fields in SSOT_ASSERTED_SUB_DICTS.items():
    fields_str = ", ".join(fields) if fields else "(derived only)"
    print(f"  {sub:<30} {fields_str}")
print()
print("  ALSO: SESSION_STORE[session_id]['working_profile'] = flat dict")
print("        → mirrors the asserted layer for frontend consumption")
print()
print(f"  WorkingProfile has {len(wp_fields)} fields total.")
print(f"  Fields mapped to SSoT asserted sub-dicts: {len(WORKING_PROFILE_TO_ASSERTED_MAP)}")
print(f"  Fields that map to working_profile_flat (no asserted sub-dict): "
      f"{sum(1 for v in WORKING_PROFILE_TO_ASSERTED_MAP.values() if v == 'working_profile_flat')}")

# ── SECTION 3: The Gap ────────────────────────────────────────────────────────
print(_section("3. THE GAP — WHY THIS IS NEEDED"))
print("""
  CURRENT STATE (SSoT path):
  ─────────────────────────
  User types "increase pressure to 12 bar" in chat
    → LLM processes message
    → Agent extracts parameter
    → Graph writes to sealing_state['asserted']['operating_conditions']
    → SESSION_STORE updated
    → Frontend SSE receives working_profile update

  PROBLEM:
  ─────────────────────────
  1. Frontend parameter form (direct inline edit) calls
     POST /api/v1/langgraph/parameters/patch
     → This reads from Postgres checkpointer (legacy)
     → SSoT SESSION_STORE is NOT updated
     → Next LLM turn starts from stale SSoT state
     → Edited parameters LOST

  2. POST /api/v1/langgraph/state (state.py)
     → Same problem: writes to Postgres checkpointer only

  3. SSoT has no REST endpoint for direct parameter writes
     → Only path is through LLM turns (slow, non-deterministic)
     → Blueprint §13 explicitly requires bypassing the LLM

  BLUEPRINT §13 REQUIREMENT:
  ─────────────────────────
  "Direct parameter patch endpoint that:
   a. Validates the patch (allowed keys, types)
   b. Routes each field to the correct SSoT asserted sub-dict
   c. Updates SESSION_STORE['working_profile'] (flat mirror)
   d. Marks derived artifacts stale (governance cycle increment)
   e. Returns the updated CaseWorkspaceProjection"
""")

# ── SECTION 4: 3-Layer Simplification for SSoT ────────────────────────────────
print(_section("4. 3-LAYER SIMPLIFICATION FOR SSOT FACADE"))
print("""
  Legacy has 5 state layers: observed → staged → normalized → asserted → versions
  SSoT needs only 3 effective layers for the facade:

  ┌───────────────────────────────────────────────────────────────────────┐
  │  Layer         │ SSoT Path                       │ Updated by facade? │
  ├───────────────────────────────────────────────────────────────────────┤
  │  Asserted      │ sealing_state['asserted'][sub]  │ YES — primary write │
  │  Working flat  │ agent_state['working_profile']  │ YES — mirror write  │
  │  Governance    │ sealing_state['governance']     │ YES — mark stale    │
  │  Cycle         │ sealing_state['cycle']          │ YES — increment     │
  │  Observed      │ (optional) sealing_state['obs'] │ NO — skip in v1     │
  │  Versioning    │ (optional) per-field counter    │ NO — skip in v1     │
  └───────────────────────────────────────────────────────────────────────┘

  SIMPLIFICATION RATIONALE:
  - Full LWW versioning is important for concurrent multi-user edits.
    Phase 2B is single-user per session → skip base_versions conflict
    detection in v1, add in v2 if needed.
  - Identity normalization (medium: "Wasser"→"water") IS important.
    But rather than calling the full 800-line pipeline, we can use
    the already-existing sanitize_v2_parameter_patch() for key
    validation + a thin normalization lookup table for medium/material.
  - Observed inputs (audit trail) are nice-to-have; skip in v1.
""")

# ── SECTION 5: Field Routing Table ────────────────────────────────────────────
print(_section("5. FIELD ROUTING: WorkingProfile → SSoT asserted sub-dict"))
print()
print(f"  {'WorkingProfile key':<30} {'SSoT target path'}")
print(f"  {_hr(28)} {_hr(46)}")
for wp_key, ssot_sub in sorted(WORKING_PROFILE_TO_ASSERTED_MAP.items()):
    if ssot_sub == "working_profile_flat":
        target = "agent_state['working_profile'] only (no asserted sub-dict)"
    else:
        target = f"sealing_state['asserted']['{ssot_sub}']['{wp_key}']"
    print(f"  {wp_key:<30} {target}")

print()
print("  Fields NOT in mapping table → write to agent_state['working_profile'] only")
print("  (safe: they don't affect downstream gate checks)")

# ── SECTION 6: Staleness & Cycle Invalidation ─────────────────────────────────
print(_section("6. STALENESS & CYCLE INVALIDATION OBLIGATIONS"))
print("""
  When asserted parameters change, downstream artifacts MUST be marked stale:

  ┌──────────────────────────────────────────────────────────────────────┐
  │  Artifact              │ What to set                                │
  ├──────────────────────────────────────────────────────────────────────┤
  │  RFQ draft             │ sealing_state['handover']['rfq_confirmed']  │
  │                        │   = False  (confirmation invalidated)       │
  │  RFQ HTML document     │ sealing_state['handover']['rfq_html_report']│
  │                        │   = None   (document outdated)             │
  │  Selection result      │ sealing_state['governance']['release_status']│
  │                        │   stays as-is (selection not re-run)       │
  │  Assertion cycle       │ sealing_state['cycle']['state_revision']   │
  │                        │   += 1                                     │
  │  working_profile       │ agent_state['working_profile'] = merged    │
  └──────────────────────────────────────────────────────────────────────┘

  NOTE: Unlike legacy, we do NOT auto-invalidate governance.release_status.
  A parameter patch may refine a value (e.g., shaft_diameter 49→50mm)
  without changing the material-selection outcome. The next LLM turn
  or operator action will re-run governance if needed.
  Blueprint §13 says: "patch endpoint MUST NOT trigger LLM re-run."
""")

# ── SECTION 7: SSE Broadcast Gap ─────────────────────────────────────────────
print(_section("7. SSE BROADCAST GAP"))
print(f"""
  Legacy /parameters/patch emits 'parameter_patch_ack' via sse_broadcast.broadcast().
  sse_broadcast found in langgraph_v2.py: {'YES' if has_sse_broadcast else 'NO'}

  SSoT SESSION_STORE has no SSE broadcast mechanism.
  The SSoT SSE stream (app/agent/api/sse_runtime.py) is request-scoped
  (one stream per chat turn), not a persistent pub-sub bus.

  OPTIONS for v1:
  ─────────────────
  A. Skip SSE broadcast entirely in v1 — frontend polls GET /workspace
     after PATCH returns 200.  RECOMMENDED for Phase 2B.

  B. Reuse legacy sse_broadcast for SSoT sessions (cross-module).
     Risk: sse_broadcast keyed on scoped_user_id+chat_id which may
     not match SESSION_STORE keys. Non-trivial wiring.

  C. Add a dedicated SSoT SSE pub-sub channel (future work, Sprint 11+).

  RECOMMENDATION: Option A for now. Frontend refreshes workspace
  projection on PATCH 200. No wiring needed.
""")

# ── SECTION 8: Implementation Recipe ─────────────────────────────────────────
print(_section("8. IMPLEMENTATION RECIPE"))
print("""
  NEW ENDPOINT: POST /api/v1/langgraph/parameters/patch
  ─────────────────────────────────────────────────────
  Add SSoT facade branch BEFORE the existing try: block.
  Pattern is identical to rfq-confirm / rfq-generate-pdf.

  ┌─────────────────────────────────────────────────────────────────────┐
  │  if SEALAI_SSOT_FACADE_ENABLED:                                     │
  │      from app.agent.api.router import _find_session, _save_session  │
  │      from copy import deepcopy                                      │
  │                                                                     │
  │      ssot_state = _find_session(body.chat_id)                       │
  │      if ssot_state is None:                                         │
  │          raise HTTPException(404, "session_not_found")              │
  │                                                                     │
  │      # 1. Sanitize (reuse existing function — no change needed)     │
  │      patch = sanitize_v2_parameter_patch(body.parameters)           │
  │                                                                     │
  │      # 2. Route fields to SSoT asserted sub-dicts                   │
  │      updated = deepcopy(ssot_state)                                 │
  │      sealing = dict(updated['sealing_state'] or {})                 │
  │      asserted = dict(sealing.get('asserted') or {})                 │
  │      flat_wp = dict(updated.get('working_profile') or {})           │
  │                                                                     │
  │      for field, value in patch.items():                             │
  │          sub = PARAM_TO_ASSERTED_SUB.get(field)                     │
  │          if sub and sub != 'working_profile_flat':                  │
  │              sub_dict = dict(asserted.get(sub) or {})               │
  │              sub_dict[field] = value                                │
  │              asserted[sub] = sub_dict                               │
  │          flat_wp[field] = value   # always update flat mirror       │
  │                                                                     │
  │      # 3. Increment cycle revision + mark RFQ stale                 │
  │      cycle = dict(sealing.get('cycle') or {})                       │
  │      cycle['state_revision'] = cycle.get('state_revision', 0) + 1  │
  │      handover = dict(sealing.get('handover') or {})                 │
  │      handover['rfq_confirmed'] = False                              │
  │      handover['rfq_html_report'] = None                             │
  │                                                                     │
  │      # 4. Write back                                                │
  │      sealing['asserted'] = asserted                                 │
  │      sealing['cycle'] = cycle                                       │
  │      sealing['handover'] = handover                                 │
  │      updated['sealing_state'] = sealing                             │
  │      updated['working_profile'] = flat_wp                           │
  │      _save_session(body.chat_id, updated)                           │
  │                                                                     │
  │      # 5. Return updated workspace projection                        │
  │      state_vals = _synthesize_state_response_from_ssot(             │
  │                       updated, chat_id=body.chat_id)['state']       │
  │      return {                                                       │
  │          'ok': True,                                                │
  │          'chat_id': body.chat_id,                                   │
  │          'applied_fields': list(patch.keys()),                      │
  │          'asserted_fields': list(patch.keys()),                     │
  │          'rejected_fields': [],                                     │
  │          'versions': {},                                            │
  │          'updated_at': {},                                          │
  │      }                                                              │
  └─────────────────────────────────────────────────────────────────────┘

  ALSO PATCH: POST /api/v1/langgraph/state  (state.py)
  ─────────────────────────────────────────────────────
  Simpler envelope — same facade pattern, same routing table.
  Body uses WorkingProfile Pydantic model → call model_dump(exclude_none=True)
  to get the patch dict, then same routing logic.

  WHERE TO PUT THE ROUTING TABLE:
  ─────────────────────────────────────────────────────
  Option A: Inline dict in langgraph_v2.py (simple, no new file)
  Option B: New module app/api/v1/utils/ssot_param_router.py
            (reusable from state.py + langgraph_v2.py)
  RECOMMENDATION: Option B — both endpoints need it.
""")

# ── SECTION 9: Open Questions / Risks ────────────────────────────────────────
print(_section("9. OPEN QUESTIONS / RISKS"))
print(f"""
  Q1: Should medium normalization ("Wasser"→"water") run in the facade?
      → Short answer: YES for operating_conditions.medium.
        Use the existing _MEDIUM_EXACT_ALIASES dict from parameter_patch.py.
        Risk of NOT normalizing: sealing_state['asserted']['medium_profile']['medium']
        contains "Wasser" which breaks downstream gate checks (case-sensitive).
      → Implementation: import _MEDIUM_EXACT_ALIASES from parameter_patch.py
        and apply it for the 'medium' field before routing.

  Q2: Does the frontend actually call /parameters/patch today?
      → From static analysis: NOT in workspaceApi.ts.
        Likely called from useSealAIStream.ts or a parameter form component.
        Next step: grep frontend for the exact fetch call.

  Q3: The /parameters/patch endpoint uses body.chat_id (not query param).
      The SSoT uses thread_id as query param in other endpoints.
      → Mapping: body.chat_id == session_id in SESSION_STORE.
        _find_session() handles composite keys. No issue.

  Q4: Identity fields (material, medium) go through full normalization
      pipeline in legacy. SSoT facade only has 2 choices:
        a. Skip normalization → raw user value stored ("FKM-compound" not "FKM")
        b. Partial normalization → medium aliases + material family codes only
      → RECOMMENDATION: Partial normalization in v1 (b), full pipeline in v2.

  Q5: Legacy response includes 'versions' per field for conflict detection.
      SSoT facade returns empty versions dict.
      → The frontend currently ignores conflict-rejection on versions.
        Safe to return empty versions in v1.

  Q6: Does staleness invalidation of rfq_confirmed break the RFQ lifecycle?
      → Only if a parameter patch occurs AFTER rfq-confirm. In that case
        the operator must re-confirm — which is CORRECT behavior.
        The verify_rfq_facade.py flow is not affected because no param
        patches happen in the RFQ lifecycle test.

  EXISTING FACADE REFERENCES:
    _find_session in router.py   : {'YES' if has_find_session else 'NO'}
    _save_session in router.py   : {'YES' if has_save_session else 'NO'}
    sanitize_v2_parameter_patch  : {'YES' if has_sanitize else 'NO'}
    sse_broadcast.broadcast      : {'YES' if has_sse_broadcast else 'NO'} (skip in v1)
    build_assertion_cycle_update : {'YES' if has_assertion_cycle else 'NO'} (partially needed)
""")

# ── SECTION 10: Implementation Order ─────────────────────────────────────────
print(_section("10. IMPLEMENTATION ORDER (one session)"))
print("""
  Step 1  Create app/api/v1/utils/ssot_param_router.py
          Exports:
            PARAM_TO_ASSERTED_SUB: dict[str, str]  (routing table)
            route_patch_to_ssot(patch, ssot_state) -> AgentState
              (mutates deepcopy in-place, returns updated state)
            MEDIUM_ALIASES: dict[str, str]         (normalization)

  Step 2  Add SSoT facade branch to POST /parameters/patch
          in app/api/v1/endpoints/langgraph_v2.py
          Position: after request_id extraction, before try:

  Step 3  Add SSoT facade branch to POST /state
          in app/api/v1/endpoints/state.py
          (same routing util, WorkingProfile body → patch dict)

  Step 4  Write backend/scripts/verify_param_sync_facade.py:
          Lifecycle: seed → approve → PATCH parameters →
          GET workspace → assert patched values visible →
          assert state_revision incremented →
          assert rfq_confirmed=False (stale)

  TOTAL: ~150 lines of new code.
  NO schema changes, NO DB migrations, NO frontend changes.
""")

print("═" * 80)
print()
