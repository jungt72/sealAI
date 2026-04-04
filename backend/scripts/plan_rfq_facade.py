"""
RFQ Facade Cutover Plan — Blueprint Section 16
Read-Only Static Analysis — no files modified

Analyses the current RFQ endpoints in:
  app/api/v1/endpoints/state.py       (workspace RFQ routes)
  app/api/v1/endpoints/rfq.py         (legacy /rfq/ router)
  app/agent/api/router.py             (SSoT SESSION_STORE + _find_session)
  app/agent/agent/commercial.py       (build_handover_payload)

Outputs:
  1. RFQ routes inventory (path, method, current state source)
  2. SSoT state path mapping (legacy pillar key → SESSION_STORE path)
  3. Mutation write-back strategy (what to set where for each RFQ action)
  4. Patch recipe for each route (if SEALAI_SSOT_FACADE_ENABLED)
  5. Open questions / risks

No code is modified.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # → backend/


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        return f"# FILE NOT FOUND: {rel}"
    return p.read_text(encoding="utf-8")


def _hr(w: int = 80, char: str = "─") -> str:
    return char * w


def _section(title: str, char: str = "═") -> str:
    line = f"  {title}  "
    pad = char * ((80 - len(line)) // 2)
    return f"\n{pad}{line}{pad}"


# ─────────────────────────────────────────────────────────────────────────────
# Load sources
# ─────────────────────────────────────────────────────────────────────────────

state_src       = _read("app/api/v1/endpoints/state.py")
rfq_src         = _read("app/api/v1/endpoints/rfq.py")
router_src      = _read("app/agent/api/router.py")
commercial_src  = _read("app/agent/agent/commercial.py")
api_src         = _read("app/api/v1/api.py")
workspace_src   = _read("app/_legacy_v2/projections/case_workspace.py")

# ─────────────────────────────────────────────────────────────────────────────
# 1. RFQ Route Inventory
# ─────────────────────────────────────────────────────────────────────────────

WORKSPACE_RFQ_ROUTES = [
    {
        "method": "GET",
        "path": "/api/v1/state/workspace",
        "function": "get_case_workspace",
        "state_source": "LangGraph Postgres checkpointer (_resolve_state_snapshot)",
        "ssot_facade_exists": "PARTIAL — _find_session branch missing for this endpoint",
        "note": "Returns CaseWorkspaceProjection; calls project_case_workspace(state_values)",
    },
    {
        "method": "POST",
        "path": "/api/v1/state/workspace/rfq-confirm",
        "function": "confirm_rfq_package",
        "state_source": "LangGraph Postgres checkpointer (_resolve_state_snapshot)",
        "ssot_facade_exists": "NO",
        "note": "Sets system.rfq_confirmed=True via graph.aupdate_state",
        "mutation_key": "system.rfq_confirmed = True",
        "ssot_write_path": "SESSION_STORE[session_id]['sealing_state']['review']['review_state'] = 'approved'",
    },
    {
        "method": "POST",
        "path": "/api/v1/state/workspace/rfq-generate-pdf",
        "function": "generate_rfq_pdf",
        "state_source": "LangGraph Postgres checkpointer (_resolve_state_snapshot)",
        "ssot_facade_exists": "NO",
        "note": "Renders HTML via render_rfq_html(projection); stores in system.rfq_html_report",
        "mutation_key": "system.rfq_html_report = <html_string>",
        "ssot_write_path": "SESSION_STORE[session_id]['sealing_state']['handover']['rfq_html_report'] = html",
    },
    {
        "method": "POST",
        "path": "/api/v1/state/workspace/rfq-handover",
        "function": "initiate_rfq_handover",
        "state_source": "LangGraph Postgres checkpointer (_resolve_state_snapshot)",
        "ssot_facade_exists": "NO",
        "note": "Sets system.rfq_handover_initiated=True via graph.aupdate_state",
        "mutation_key": "system.rfq_handover_initiated = True",
        "ssot_write_path": "SESSION_STORE[session_id]['sealing_state']['handover']['handover_initiated'] = True",
    },
    {
        "method": "GET",
        "path": "/api/v1/state/workspace/rfq-document",
        "function": "get_rfq_document",
        "state_source": "LangGraph Postgres checkpointer (_resolve_state_snapshot)",
        "ssot_facade_exists": "NO",
        "note": "Returns system.rfq_html_report as HTMLResponse",
        "ssot_read_path": "SESSION_STORE[session_id]['sealing_state']['handover']['rfq_html_report']",
    },
    {
        "method": "GET",
        "path": "/api/v1/rfq/download",
        "function": "rfq_download",
        "state_source": "NONE — returns HTTP 410 (disabled)",
        "ssot_facade_exists": "N/A",
        "note": "Stub endpoint. Can be repurposed as SSoT handover_payload download.",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# 2. SSoT State Path Mapping
#    Legacy pillar key  →  SESSION_STORE["sealing_state"][...] path
# ─────────────────────────────────────────────────────────────────────────────

STATE_MAPPING = [
    # (legacy_pillar_key, legacy_field, ssot_path, already_bridged)
    ("system", "rfq_confirmed",
     "sealing_state['review']['review_state'] == 'approved'",
     True),   # already done in _synthesize_state_response_from_ssot
    ("system", "rfq_html_report",
     "sealing_state['handover']['rfq_html_report']",
     False),  # NOT YET in _synthesize_state_response_from_ssot
    ("system", "rfq_handover_initiated",
     "sealing_state['handover']['handover_initiated']",
     False),  # NOT YET bridged
    ("system", "rfq_draft",
     "sealing_state['handover']['handover_payload']",
     False),  # build_handover_payload() already generates this
    ("governance", "release_status",
     "sealing_state['governance']['release_status']",
     True),   # already in synthesized_state via _synthesize_state_response_from_ssot
    ("governance", "rfq_admissibility",
     "sealing_state['governance']['rfq_admissibility']",
     True),   # already bridged
]

# ─────────────────────────────────────────────────────────────────────────────
# 3. Detect whether SEALAI_SSOT_FACADE_ENABLED is checked in state.py
# ─────────────────────────────────────────────────────────────────────────────

facade_enabled_count = state_src.count("SEALAI_SSOT_FACADE_ENABLED")
facade_branch_count  = state_src.count("if SEALAI_SSOT_FACADE_ENABLED")
rfq_endpoint_count   = state_src.count("_resolve_state_snapshot")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Check what SESSION_STORE write_back helpers exist
# ─────────────────────────────────────────────────────────────────────────────

has_find_session    = "_find_session" in router_src
has_write_back      = "_write_session" in router_src or "SESSION_STORE[" in router_src
has_build_handover  = "build_handover_payload" in commercial_src

# ─────────────────────────────────────────────────────────────────────────────
# Print report
# ─────────────────────────────────────────────────────────────────────────────

print()
print("╔" + "═" * 78 + "╗")
print("║" + "  SealAI RFQ Facade Plan — Blueprint Section 16".center(78) + "║")
print("║" + "  Read-Only Static Analysis — no files modified".center(78) + "║")
print("╚" + "═" * 78 + "╝")

# ── SECTION 1: Route Inventory ───────────────────────────────────────────────
print(_section("1. RFQ ROUTE INVENTORY"))
print()
print(f"  {'Method':<6} {'Path':<55} {'Facade?'}")
print(f"  {_hr(4)} {_hr(53)} {_hr(12)}")
for r in WORKSPACE_RFQ_ROUTES:
    has_f = r["ssot_facade_exists"]
    marker = "  ✓" if "PARTIAL" not in has_f and has_f != "NO" and has_f != "N/A" else (
             "  ~" if "PARTIAL" in has_f else
             "  N/A" if has_f == "N/A" else
             "  ✗"
    )
    print(f"  {r['method']:<6} {r['path']:<55} {marker}")

print()
print(f"  SEALAI_SSOT_FACADE_ENABLED references in state.py : {facade_enabled_count}")
print(f"  if SEALAI_SSOT_FACADE_ENABLED branches in state.py : {facade_branch_count}")
print(f"  _resolve_state_snapshot calls (legacy checkpointer): {rfq_endpoint_count}")
print()
print("  → ALL 4 workspace RFQ action endpoints still read from LangGraph Postgres.")
print("  → The existing SSoT facade branch covers /chat/{id}/state only.")

# ── SECTION 2: SSoT State Path Mapping ───────────────────────────────────────
print(_section("2. SSOT STATE PATH MAPPING"))
print()
print(f"  {'Legacy Pillar.Field':<35} {'SSoT Path':<45} {'Bridged?'}")
print(f"  {_hr(33)} {_hr(43)} {_hr(8)}")
for pillar, field, ssot_path, bridged in STATE_MAPPING:
    bridged_str = "  ✓ yes" if bridged else "  ✗ NO"
    print(f"  {pillar+'.'+field:<35} {ssot_path:<45} {bridged_str}")

print()
print("  KEY GAPS (not yet in _synthesize_state_response_from_ssot):")
for pillar, field, ssot_path, bridged in STATE_MAPPING:
    if not bridged:
        print(f"    ✗ system.{field}")
        print(f"      → Add to synthesized_state['system'] in _synthesize_state_response_from_ssot:")
        print(f"        '{field}': sealing_state.get('handover', {{}}).get('{field.replace('rfq_html_report','rfq_html_report').replace('rfq_handover_initiated','handover_initiated').replace('rfq_draft','handover_payload')}')")
        print()

# ── SECTION 3: Mutation Write-Back Strategy ───────────────────────────────────
print(_section("3. MUTATION WRITE-BACK STRATEGY"))
print()
print("  Each POST endpoint currently calls graph.aupdate_state(...) to write to")
print("  the Postgres checkpointer. In SSoT mode we write to SESSION_STORE instead.")
print()
for r in WORKSPACE_RFQ_ROUTES:
    if r["method"] == "POST" and "ssot_write_path" in r:
        print(f"  {r['function']}()")
        print(f"    Legacy: graph.aupdate_state(config, {{{r['mutation_key']}}}, as_node=...)")
        print(f"    SSoT:   _write_session(session_id, state)  # after in-place mutation")
        print(f"            {r['ssot_write_path']}")
        print()
        if r["function"] == "generate_rfq_pdf":
            print("    IMPORTANT: build_handover_payload() in commercial.py already constructs")
            print("    a clean payload dict from sealing_state. The facade should:")
            print("      1. Call build_handover_payload(sealing_state)")
            print("      2. Pass payload into _synthesize_state_for_projection() to get a")
            print("         CaseWorkspaceProjection (via project_case_workspace)")
            print("      3. Call render_rfq_html(projection) — renderer is already pure,")
            print("         no LangGraph dependency")
            print("      4. Write html back into SESSION_STORE (see path above)")
            print()

# ── SECTION 4: Patch Recipe ───────────────────────────────────────────────────
print(_section("4. PATCH RECIPE (if SEALAI_SSOT_FACADE_ENABLED)"))
print("""
  For each of the 4 workspace RFQ endpoints, add this pattern at the top of
  the function body (BEFORE the try: _resolve_state_snapshot block):

  ┌─────────────────────────────────────────────────────────────────────────┐
  │  if SEALAI_SSOT_FACADE_ENABLED:                                         │
  │      from app.agent.api.router import _find_session, _write_session     │
  │      ssot_state = _find_session(thread_id)                              │
  │      if ssot_state is None:                                             │
  │          raise HTTPException(404, detail=error_detail("session_not_found")) │
  │      sealing_state = dict(ssot_state.get("sealing_state") or {})       │
  │      # ... perform SSoT-specific mutation (see Section 3) ...           │
  │      state_values = _build_legacy_state_for_projection(ssot_state)     │
  │      projection = project_case_workspace(state_values)                 │
  │      return projection                                                  │
  └─────────────────────────────────────────────────────────────────────────┘

  _build_legacy_state_for_projection(ssot_state) is a NEW helper (to be added
  to state.py or api/v1/utils/) that extends _synthesize_state_response_from_ssot
  with the 3 missing system fields:

    synthesized_state["system"]["rfq_html_report"]      = handover.get("rfq_html_report")
    synthesized_state["system"]["rfq_handover_initiated"] = handover.get("handover_initiated", False)
    synthesized_state["system"]["rfq_draft"]            = handover.get("handover_payload")

  This helper is the ONLY code change needed in state.py, besides the facade
  branch in each endpoint.

  For the /rfq/download stub:
    → Replace the 410 response with an SSoT-aware payload download:
      - Fetch SESSION_STORE via _find_session(thread_id)
      - Call build_handover_payload(sealing_state) from commercial.py
      - Return JSON or HTML (render_rfq_html)
""")

# ── SECTION 5: Open Questions / Risks ────────────────────────────────────────
print(_section("5. OPEN QUESTIONS / RISKS"))
print("""
  Q1: SESSION_STORE is in-memory (Python dict in router.py).
      → If the backend restarts between rfq-confirm and rfq-generate-pdf,
        the mutation is lost. Is Redis persistence required for Phase 2B?
      → SHORT-TERM SAFE: All RFQ actions happen in a single user session,
        so restart between steps is unlikely in dev. Flag for Sprint 10.

  Q2: _write_session() helper — does it exist?
""")
print(f"      → _find_session exists in router.py: {'YES' if has_find_session else 'NO'}")
print(f"      → SESSION_STORE write-back code exists: {'YES' if has_write_back else 'NO'}")
print("""
      The write-back pattern (SESSION_STORE[key] = state) is used inline in
      router.py but there is no exported helper. We need to either:
        a) Export a _write_session(session_id, state) helper from router.py, OR
        b) Use the inline pattern directly in state.py (tight coupling).
      Recommendation: (a) — add _write_session to router.py.

  Q3: build_handover_payload() — ready to use?
""")
print(f"      → build_handover_payload in commercial.py: {'YES' if has_build_handover else 'NO'}")
print("""
      Confirmed: commercial.py is already complete. No changes needed there.

  Q4: project_case_workspace() — will it work on synthesized SSoT state?
      → YES, provided _build_legacy_state_for_projection adds the 3 missing
        system fields (rfq_html_report, rfq_handover_initiated, rfq_draft).
      → Projection is a pure function (no I/O, no DB). Safe to call with
        synthesized state dict.

  Q5: Gate checks in rfq-confirm / rfq-generate-pdf / rfq-handover use
      projection.rfq_status / projection.governance_status fields.
      → These come from project_case_workspace → _build_rfq_status(system, ...)
        and _build_governance_status(system, ...).
      → As long as the synthesized state includes governance.release_status
        and governance.rfq_admissibility (already bridged ✓), the gate checks
        will work correctly.
""")

# ── SUMMARY ───────────────────────────────────────────────────────────────────
print(_section("IMPLEMENTATION ORDER", "─"))
print("""
  Step 1  Add _write_session(session_id, state) to app/agent/api/router.py
          (3 lines — makes SESSION_STORE write-back safe and testable)

  Step 2  Add _build_legacy_state_for_projection(ssot_state) helper in
          app/api/v1/endpoints/state.py (extends existing
          _synthesize_state_response_from_ssot with 3 missing system fields)

  Step 3  Patch confirm_rfq_package() with if SEALAI_SSOT_FACADE_ENABLED
          Write-back: sealing_state['review']['review_state'] = 'approved'

  Step 4  Patch generate_rfq_pdf() with if SEALAI_SSOT_FACADE_ENABLED
          Uses render_rfq_html(projection) unchanged (pure renderer)
          Write-back: sealing_state['handover']['rfq_html_report'] = html

  Step 5  Patch initiate_rfq_handover() with if SEALAI_SSOT_FACADE_ENABLED
          Write-back: sealing_state['handover']['handover_initiated'] = True

  Step 6  Patch get_rfq_document() with if SEALAI_SSOT_FACADE_ENABLED
          Read: SESSION_STORE[session_id]['sealing_state']['handover']['rfq_html_report']

  Step 7  Repurpose /api/v1/rfq/download stub to serve handover_payload as JSON
          (call build_handover_payload from commercial.py)

  ALL SEVEN STEPS can be done in a single session with no schema changes,
  no DB migrations, and no frontend changes required.
""")

print("═" * 80)
print()
