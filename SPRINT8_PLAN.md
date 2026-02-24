# Sprint 8: P5 Procurement Engine + tenant_id in Auth

## Target Topology (Graph)
```
node_router —(rfq_trigger)→ node_p5_procurement → response_node → END
```
(The `no_blockers` path from P4.5 remains → `resume_router_node`, unchanged.)

---

## Files to Create (3)

### 1. `backend/app/services/rag/nodes/p5_procurement.py`
Pure-Python procurement engine — no LLM. Implements 4-stage partner matching:

**Models:**
- `PartnerRecord(BaseModel)`: partner_id, name, is_paying_partner, supported_bauformen, supported_media, pressure_max_bar, locations, delivery_days
- `ProcurementResult(BaseModel)`: matched_partners, fallback, stages_completed, fallback_reason, warning

**Static registry** `_PARTNER_REGISTRY` (5 hardcoded partners for test/demo):
- P001 Müller Dichtungstechnik: paying, DE, Spiraldichtung/Kammprofil/Flachdichtung, steam/gas/liquid/water, 200 bar, 7 days
- P002 Alpine Seals AG: paying, AT/CH, Spiraldichtung/O-Ring, H2/O2/gas/liquid, 500 bar, 10 days
- P003 NonPaying KG: NOT paying → Stage 1 filter
- P004 TechSeal BV: paying, DE/NL, PTFE-Dichtung/Flachdichtung, liquid/steam, 150 bar, 14 days
- P005 FastSeal GmbH: paying, DE, all bauformen, all media, 300 bar, 3 days

**Matching logic:**
```
Stage 1 (MUST): filter partner.is_paying_partner == True
Stage 2 (MUST): filter partner.supported_bauformen intersects with [seal_family]
                → fallback=True if 0 left after Stage 2
Stage 3 (SHOULD): prefer partners where medium in supported_media AND pressure <= pressure_max_bar
                  (non-blocking — keeps all Stage 2 survivors if none match Stage 3)
Stage 4 (NICE): sort by delivery_days ASC
```

**PDF render:**
- `_render_rfq_pdf(result, profile, calc_result, critique_log, is_critical) -> str`
- Renders `rfq_template.j2` via StrictUndefined `render_template()`
- Template context includes: all WorkingProfile fields, CalcOutput fields, critique_log,
  matched_partners list, fallback flag, fallback_reason, is_critical_application, generated_at

**Node:**
```python
def node_p5_procurement(state: SealAIState) -> Dict[str, Any]:
    # reads: working_profile, seal_family, calculation_result, critique_log, is_critical_application
    # returns: procurement_result, rfq_pdf_text, phase=PHASE.PROCUREMENT, last_node
```

### 2. `backend/app/prompts/rfq_template.j2`
German-language RFQ text document (StrictUndefined). Sections:
1. KRITISCHE ANWENDUNG watermark block (conditional: `{% if is_critical_application %}`)
2. BETRIEBSPROFIL — all WorkingProfile fields
3. AUSLEGUNGSERGEBNISSE (P4b) — CalcOutput fields
4. QUALITÄTSPRÜFUNG (P4.5) — critique_log entries
5. PARTNERVERMITTLUNG — matched_partners or fallback note
6. Footer with generated_at timestamp

### 3. `backend/app/langgraph_v2/tests/test_p5_procurement.py`
~40 tests across test classes:
- `TestStage1Paying` (3): paying filter, non-paying rejected, empty → fallback
- `TestStage2Bauform` (4): match, no match → fallback, seal_family None → fallback
- `TestStage3MediumDruck` (4): medium match preferred, pressure limit, combined SHOULD
- `TestStage4Geo` (3): sort by delivery_days, single partner, empty list
- `TestFallback` (4): fallback=True, fallback_reason set, neutral PDF (no partner names), fallback_reason in PDF
- `TestWatermark` (3): watermark present when is_critical=True, absent when False, exact text check
- `TestRFQPDFRendering` (5): full render, StrictUndefined honored (missing var raises), all sections, profile data in PDF
- `TestNodeP5Integration` (6): returns correct fields, phase=procurement, skip if no working_profile, skip if no calculation_result, reads is_critical from state, reads critique_log from state
- `TestProcurementResult` (3): model validation, model_dump round-trip

### 4. `backend/app/langgraph_v2/tests/test_tenant_id_auth.py`
~6 tests:
- JWT `tenant_id` claim → RequestUser.tenant_id populated
- Custom `AUTH_TENANT_ID_CLAIM` env var → uses that claim
- JWT without claim → tenant_id=None
- _resolve_tenant_id return type is Optional[str]
- RequestUser is frozen dataclass with tenant_id field
- tenant_id injected into SealAIState via endpoint (unit test with monkeypatched state)

---

## Files to Modify (6)

### 5. `backend/app/services/auth/dependencies.py`
- Add `tenant_id: Optional[str] = None` field to `RequestUser` dataclass
- Add `_resolve_tenant_id(payload: dict) -> Optional[str]` helper:
  reads `os.getenv("AUTH_TENANT_ID_CLAIM", "tenant_id")` claim from payload, returns None if missing
- Inject in `get_current_request_user()` and `get_current_ws_user()`

### 6. `backend/app/langgraph_v2/state/sealai_state.py`
Add to `SealAIState`:
```python
# Session context (Sprint 8: tenant isolation)
tenant_id: Optional[str] = None

# v4.4.0 Sprint 8: P5 Procurement
procurement_result: Optional[Dict[str, Any]] = None
rfq_pdf_text: Optional[str] = None
```

### 7. `backend/app/langgraph_v2/phase.py`
Add: `PROCUREMENT = "procurement"`

### 8. `backend/app/langgraph_v2/types.py`
Add `"procurement"` to `PhaseLiteral`.

### 9. `backend/app/langgraph_v2/sealai_graph_v2.py`
- Import `node_p5_procurement` from `app.services.rag.nodes.p5_procurement`
- Register: `builder.add_node("node_p5_procurement", node_p5_procurement)`
- Change: `"rfq_trigger": "response_node"` → `"rfq_trigger": "node_p5_procurement"`
- Add: `builder.add_edge("node_p5_procurement", "response_node")`

### 10. `backend/app/api/v1/endpoints/langgraph_v2.py`
In `_run_graph_to_state()`: add `tenant_id: str | None = None` param, inject into SealAIState and user_context.
In SSE handler (main stream endpoint): extract `tenant_id = current_user.tenant_id`, inject into initial SealAIState and user_context.

---

## Design Principles Maintained
- R1: No LLM in P5 (pure deterministic matching)
- R2: Jinja2 StrictUndefined for RFQ PDF
- Fallback: neutral PDF when no MUST criteria met — no invented data
- Watermark: hardcoded template block, not LLM-generated
