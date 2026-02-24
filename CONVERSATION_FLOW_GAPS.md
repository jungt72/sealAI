# Missing Capabilities for Real-World Conversations

**Date:** 2026-02-24
**Based on:** LangGraph V2 Conversation-Flow Audit (see CONVERSATION_FLOW_AUDIT_REPORT.md)

---

## ROOT CAUSE: Dual-Path Architectural Disconnect

The entire gap list below stems from one root architectural issue:

**The graph has two disconnected flows. For any first-turn user query, ALL traffic goes
through the P1→P4 pipeline (node_router → node_p1_context → P2/P3/P4...). The
frontdoor_discovery_node — which performs LLM intent classification and gates all
pattern-specific routing — is ONLY reachable from the HITL resume path.**

```
NEW QUERY:    START → profile_loader → node_router → node_p1_context → P2/P3/P4 → END
HITL RESUME:  START → profile_loader → node_router → resume_router → frontdoor → KB/supervisor
```

Fixing this architectural disconnect (GAP-1 below) resolves Patterns 1, 2, 3, 5, and 7
simultaneously.

---

## CRITICAL — Blocks Conversation Patterns

### [ ] GAP-1: frontdoor_discovery_node unreachable on fresh queries
- **Affects Patterns:** 1 (Info-Abfrage), 2 (Material-Screening), 3 (Troubleshooting), 5 (Vergleich), 7 (Smalltalk)
- **Symptom:** All first-turn queries go through P1→P4 pipeline regardless of intent
- **Expected:** Intent classification (smalltalk/troubleshooting/comparison) should run on every query
- **Code:** `sealai_graph_v2.py:738-752` — `node_router` only dispatches to frontdoor via resume path
- **Fix:** Insert `frontdoor_discovery_node` (or equivalent intent classifier) in the new_case path, before or as part of P1 fan-out
- **Effort:** Medium (graph rewiring + state merge logic)

### [ ] GAP-2: Troubleshooting wizard completely absent for fresh queries
- **Affects Pattern:** 3 (Leckage-Troubleshooting)
- **Symptom:** "Wir haben Leckage" → generic discovery answer, no systematic diagnosis
- **Existing code:** `leakage_troubleshooting_node` + `troubleshooting_pattern_node` + `troubleshooting_explainer_node` exist at `nodes_flows.py:730-835` but unreachable
- **Missing:** Multi-turn HITL wizard with systematic question sequence (location? frequency? conditions? material? age?)
- **Fix:** (a) Wire troubleshooting intent to reach `leakage_troubleshooting_node` on first turn; (b) Implement question-loop HITL for symptom gathering
- **Effort:** High (new HITL flow + question nodes)

### [ ] GAP-3: Pattern 3 multi-turn HITL wizard not implemented
- **Affects Pattern:** 3 (Leckage-Troubleshooting)
- **Symptom:** No systematic 5-8 question sequence to gather leakage diagnostics
- **Expected:** Wizard asks: leakage location → rate → conditions → seal age → assembly date
- **Missing nodes:** `wizard_question_node`, `wizard_answer_collector_node`, symptom accumulator
- **Fix:** Implement new nodes for structured diagnostic collection
- **Effort:** High (new nodes + state fields + HITL interrupts)

### [ ] GAP-4: Quality gate provides no alternatives on CRITICAL blocks
- **Affects Pattern:** 2 (Material-Screening), 4 (Design-Beratung)
- **Symptom:** "BLOCKER: Medium 'HF' nicht verträglich" — no guidance what to use instead
- **Code:** `p4_5_quality_gate.py:230-236` — `QGateCheck.message` contains only diagnosis, no `suggestions` field
- **Fix:** Add `suggestions: List[str]` field to `QGateCheck`; populate in `_check_medium_compatibility()` with compatible PTFE/FFKM alternatives for HF, chromic acid, etc.
- **Effort:** Low-Medium (extend data model + add material lookup)

### [ ] GAP-5: KB compound filter not wired into new_case path
- **Affects Pattern:** 2 (Material-Screening)
- **Symptom:** "Material für 150°C, HF-Säure" → compound filter not screened, no hard-block on first turn
- **Existing code:** `node_compound_filter_parallel` (`compound_filter.py`) implemented but only in frontdoor parallel path
- **Fix:** Part of GAP-1 fix — when frontdoor_discovery_node runs on new_case, compound filter will execute
- **Effort:** Resolved by GAP-1 fix

---

## HIGH — Degrades User Experience

### [ ] GAP-6: RFQ keyword detection too narrow
- **Affects Pattern:** 6 (RFQ-Anfrage)
- **Symptom:** "Angebot für 100 Dichtungen, 50×70×10, FFKM" — does NOT trigger `_RFQ_PATTERNS`
- **Code:** `node_router.py:30-41` — patterns require compound phrases ("angebot einholen", "rfq senden") not standalone "Angebot für..."
- **Missing patterns:**
  ```python
  r"angebot\s+für\b"
  r"preisanfrage"
  r"ich\s+brauche\s+ein\s+angebot"
  r"quote\s+for"
  r"bitte\s+um\s+ein\s+angebot"
  ```
- **Fix:** Extend `_RFQ_PATTERNS` regex; add LLM fallback for ambiguous cases
- **Effort:** Low

### [ ] GAP-7: No fast path for smalltalk/educational on first turn
- **Affects Pattern:** 7 (Smalltalk/Educational)
- **Symptom:** "Was ist der Unterschied zwischen FKM und FFKM?" → 3-5s P1-P4 pipeline
- **Expected:** <500ms via `smalltalk_node` (nano model) or `material_comparison_node`
- **Code:** `sealai_graph_v2.py:547-558` — `smalltalk_node` only reached from `clarification` or frontdoor resume
- **Fix:** Part of GAP-1 fix — frontdoor classification sets social_opening=True → fast path
- **Effort:** Resolved by GAP-1 fix (plus ensure `smalltalk_node` has sufficient max_tokens for educational answers — currently 120 tokens, too short)

### [ ] GAP-8: Smalltalk node max_tokens too low for educational content
- **Affects Pattern:** 7 (Smalltalk/Educational)
- **Symptom:** Even if `smalltalk_node` is reached, 120 tokens is insufficient for "FKM vs FFKM" explanation
- **Code:** `nodes_error.py:27` — `max_tokens=120`
- **Fix:** Either increase max_tokens for educational queries, or use a separate `educational_node` with mini model (max_tokens=400)
- **Effort:** Low

### [ ] GAP-9: material_comparison_node unreachable for fresh queries
- **Affects Pattern:** 5 (Material-Vergleich)
- **Symptom:** "PTFE vs FFKM" comparison goes through P4 pipeline with generic DISCOVERY_TEMPLATE
- **Existing code:** `material_comparison_node` at `nodes_flows.py:620` — renders `material_comparison.j2`, async mini model
- **Fix:** Part of GAP-1 fix — when `intent.goal == "explanation_or_comparison"`, supervisor routes here
- **Effort:** Resolved by GAP-1 fix

### [ ] GAP-10: No alternatives suggested when compound filter blocks
- **Affects Pattern:** 2 (Material-Screening)
- **Symptom:** KB gate blocks material but doesn't tell user what IS compatible
- **Code:** `factcard_lookup.py:115-122` — `hard_blocks` only generates blocking message, no alternatives
- **Fix:** When blocking, query `CompoundDecisionMatrix` for alternative conditions or materials
- **Effort:** Low-Medium

### [ ] GAP-11: P5 RFQ cold-start: no spec collection before PDF generation
- **Affects Pattern:** 6 (RFQ-Anfrage)
- **Symptom:** RFQ trigger with no prior working_profile generates near-empty RFQ PDF
- **Code:** `p5_procurement.py:355-358` — skips silently when no profile
- **Fix:** Add HITL loop to collect: Bauform, DN, PN, medium, pressure, quantity before matching
- **Effort:** Medium (new HITL flow)

---

## MEDIUM — Nice-to-Have / Future Sprints

### [ ] GAP-12: No TCO calculator for material comparison
- **Affects Pattern:** 5 (Material-Vergleich)
- **Symptom:** "PTFE vs FFKM für 150°C" — no lifecycle cost comparison available
- **Search result:** 0 files in codebase contain "tco" or "total_cost" logic
- **Required inputs:** material cost/kg, seal lifetime (hours), replacement cost, downtime cost
- **Fix:** Implement `TcoCalculator` service with configurable cost parameters per compound
- **Effort:** Medium-High (new service + data model)

### [ ] GAP-13: No CRM integration in procurement
- **Affects Pattern:** 6 (RFQ-Anfrage)
- **Symptom:** RFQ PDF generated internally but not sent to partner CRM
- **Code:** `p5_procurement.py` — 5 hardcoded partners, no external API calls
- **Fix:** Add webhook/API client to push RFQ to HubSpot/Salesforce/custom CRM
- **Effort:** Medium

### [ ] GAP-14: Static partner registry
- **Affects Pattern:** 6 (RFQ-Anfrage)
- **Symptom:** `_PARTNER_REGISTRY` is hardcoded list of 5 test partners (`p5_procurement.py:62-113`)
- **Fix:** Move to Postgres `partners` table or external partner API
- **Effort:** Medium

### [ ] GAP-15: EXPLANATION_TEMPLATE never selected for new_case queries
- **Affects Pattern:** 7 (Smalltalk/Educational)
- **Symptom:** Educational queries use generic DISCOVERY_TEMPLATE since `intent.goal` is None on first turn
- **Code:** `sealai_graph_v2.py:127-134` — `_select_final_answer_template()` defaults to DISCOVERY_TEMPLATE when goal=None
- **Fix:** Part of GAP-1 fix — frontdoor sets intent.goal = "explanation_or_comparison" for educational queries
- **Effort:** Resolved by GAP-1 fix

### [ ] GAP-16: `print()` debug statement in final answer pipeline
- **Affects:** ALL patterns (observability noise)
- **Symptom:** `print(f"!!! FINAL LLM CONTEXT PAYLOAD: ...")` at `sealai_graph_v2.py:266`
- **Fix:** Replace with `logger.debug()`
- **Effort:** Trivial

### [ ] GAP-17: `print()` debug statement in material_agent_node
- **Affects:** All RAG paths
- **Symptom:** `print(f"DEBUG RAG: Searching Qdrant...")` at `nodes_flows.py:202`
- **Fix:** Replace with `logger.debug()`
- **Effort:** Trivial

---

## Implementation Priority Order

| Priority | Gap | Description | Effort | Impact |
|----------|-----|-------------|--------|--------|
| 1 | GAP-1 | Wire frontdoor into new_case path | Medium | Fixes 5 patterns |
| 2 | GAP-4 | Quality gate alternatives | Low-Med | Fixes UX for P2, P4 blockers |
| 3 | GAP-2/3 | Troubleshooting wizard | High | Completes Pattern 3 |
| 4 | GAP-6 | Expand RFQ keywords | Low | Fixes Pattern 6 routing |
| 5 | GAP-8 | Increase smalltalk max_tokens | Low | Improves Pattern 7 quality |
| 6 | GAP-11 | P5 spec collection HITL | Medium | Fixes Pattern 6 cold-start |
| 7 | GAP-12 | TCO calculator | High | Completes Pattern 5 |
| 8 | GAP-13/14 | CRM + partner DB | Medium | Productionizes Pattern 6 |
| 9 | GAP-16/17 | Remove debug prints | Trivial | Code quality |

---

## Quick Win Summary (< 1 day each)

1. **GAP-6**: Extend `_RFQ_PATTERNS` in `node_router.py:30-41` with 5 new patterns
2. **GAP-8**: Change `max_tokens=120` to `max_tokens=400` in `nodes_error.py:27`
3. **GAP-16**: `sealai_graph_v2.py:266` — `print(...)` → `logger.debug(...)`
4. **GAP-17**: `nodes_flows.py:202` — `print(...)` → `logger.debug(...)`
5. **GAP-4**: Add `suggestions: List[str] = []` to `QGateCheck` in `p4_5_quality_gate.py:51`

---

## Patterns That ARE Working

- **Pattern 4 (Design-Beratung):** The P1→P4 pipeline is exactly right for this. Full 8-check
  quality gate, gasket calculation, safety factor, number verification — all functional.
- **Pattern 6 (RFQ):** Routing works when keywords match; 4-stage partner matching is solid;
  Jinja2 PDF render with critical-application watermark is implemented.
- **Answer Subgraph (V3):** `final_answer_node` runs a contract-first subgraph
  (`prepare_contract → draft_answer → verify_claims → targeted_patch → finalize`) which adds
  hallucination-resistant claim verification — this is a strong foundation for all patterns.
