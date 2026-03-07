# SealAI v1.2 Remediation — Closeout Review

**Date:** 2026-03-07
**Reviewer:** Claude (automated, evidence-based)
**Scope:** All remediation patches from HITL-Bridge through Claim/Specificity Drift-Map
**Standard:** Blueprint v1.2 as normative reference

---

## Phase A — Reconciled Findings Table

### Finding 1: RFQ Path Blueprint-Konform

**Status: SUBSTANTIALLY REDUCED**

| Aspect | Before Remediation | After Remediation | Evidence |
|---|---|---|---|
| RFQDraft model | Declared in state, never instantiated | Produced by `node_finalize` | `node_finalize.py:374-391` (`_build_rfq_draft`) |
| RFQDraft in state | Never written | Written to `system.rfq_draft` | `node_finalize.py:494` |
| SRS embedded in RFQ | N/A | SRS flows into RFQDraft | `node_finalize.py:376-388` |
| RFQ admissibility | Already functional | Unchanged (was already strong) | `rfq_admissibility.py:21-47` |
| rfq_confirmation HITL | Not wired | Checkpoint fires when RFQ+admissibility exist | `subgraph_builder.py:360-369` |
| RFQ to manufacturer | No send path | Still no send path | No downstream consumer of rfq_draft beyond state |

**What's really better:** RFQDraft is now a real runtime artifact with SRS, governance metadata, and manufacturer questions. rfq_confirmation checkpoint gates release. The rfq_admissibility → release_status chain is unbroken.

**What still lacks:** No actual manufacturer send mechanism. RFQDraft is produced and gated but has no downstream consumer that transmits it externally. This is a feature gap, not a governance gap.

**Pilot-blocking?** No. RFQ production and governance gating work. External transmission is a product feature, not a safety concern.

---

### Finding 2: HITL Checkpoints

**Status: SUBSTANTIALLY REDUCED**

| Aspect | Before Remediation | After Remediation | Evidence |
|---|---|---|---|
| snapshot_confirmation | Not wired | Fires when SRS spec_id changes, blocked by confirmed_spec_id | `subgraph_builder.py:334-344` |
| rfq_confirmation | Not wired | Fires when RFQ+admissibility present and not confirmed | `subgraph_builder.py:360-369` |
| draft_conflict_resolution | Not wired | Fires only when OPEN conflicts exist | `subgraph_builder.py:376-386` |
| LangGraph interrupt_before | Missing | Still missing — uses internal checkpoint pattern instead | Zero `interrupt_before` calls in codebase |
| Resume API → state | Not connected | confirm_decision injected via aupdate_state | `langgraph_v2.py:3055-3067` |
| SSE checkpoint events | Not emitted | `checkpoint_required` event emitted | `langgraph_v2.py:2544-2558` |
| _clear_checkpoint | Deep-merge bug (stale keys survived) | Fixed with `and value` guard | `subgraph_builder.py:253` |

**What's really better:** All 3 HITL checkpoints fire at correct points with correct gating logic. The resume round-trip (API → state → subgraph re-entry) works. _clear_checkpoint no longer leaks stale data.

**What still lacks:** No native LangGraph `interrupt_before` — the subgraph uses its own checkpoint-and-resume pattern. This works but means HITL state is internal to the subgraph, not visible to LangGraph's built-in interrupt/resume tooling. Also: draft_conflict_resolution fires but does NOT transition conflicts to RESOLVED — after user approval, conflicts remain OPEN. On next verification cycle they would re-trigger.

**Pilot-blocking?** Partially. The checkpoint-resume loop works for snapshot and RFQ confirmation. But draft_conflict_resolution has a re-trigger problem: approving conflicts doesn't mark them RESOLVED, so they'd fire again. This needs a small fix before pilot if conflict resolution is user-facing.

---

### Finding 3: Observed → Normalized → Asserted Pipeline

**Status: PARTIALLY REDUCED**

| Aspect | Before Remediation | After Remediation | Evidence |
|---|---|---|---|
| observed_inputs field | Declared, empty forever | Populated on all 3 extraction paths | `langgraph_v2.py:832`, `nodes_frontdoor.py:801`, `p1_context.py:566` |
| Append-only semantics | N/A | Enforced — existing entries never overwritten | `parameter_patch.py:270` (`if key in observed: continue`) |
| identity_class_at_capture | N/A | Recorded per field | `parameter_patch.py:280` |
| Downstream consumption | N/A | **ZERO downstream readers** | Grep: no code reads `state.reasoning.observed_inputs` for decisions |
| Normalized layer | identity_class computed | Unchanged (was already functional) | `parameter_patch.py` identity classification |
| Asserted layer | Flat fields on WorkingProfile | Unchanged — no typed MediumProfile/MachineProfile/InstallationProfile | Still flat |

**What's really better:** observed_inputs is now a real audit trail of raw user inputs with source and identity classification. The write infrastructure is correct and append-only.

**What still lacks:** observed_inputs is **write-only dead data**. No governance decision, no output formatting, no audit report, and no verification check reads it. The blueprint intended observed_inputs to enable "was hat der Nutzer wirklich gesagt vs. was hat das System daraus gemacht" — that comparison never happens. Also: no typed asserted profiles exist (MediumProfile etc.).

**Pilot-blocking?** No. observed_inputs is an audit/debugging infrastructure investment. Its absence from runtime decisions doesn't affect safety — identity_class gating works independently.

---

### Finding 4: SealingRequirementSpec as Real Object

**Status: CLOSED**

| Aspect | Before Remediation | After Remediation | Evidence |
|---|---|---|---|
| SRS model | Declared, never instantiated | Produced by `_build_sealing_requirement_spec` | `node_prepare_contract.py:850-895` |
| spec_id | Never set | `"srs-c{cycle}-r{revision}"` | `node_prepare_contract.py:880` |
| operating_envelope | N/A | Populated from WorkingProfile | `node_prepare_contract.py:868` |
| dimensional_requirements | N/A | Populated (shaft_diameter) | `node_prepare_contract.py:869-873` |
| normative_references | N/A | Extracted from RAG chunks | `node_prepare_contract.py:883` |
| material_family_candidates | N/A | Built from candidate_clusters | `node_prepare_contract.py:884` |
| material_specificity_required | Always "family_only" | Derived from best candidate specificity | `node_prepare_contract.py:869-878` |
| manufacturer_validation_scope | N/A | From governance_metadata | `node_prepare_contract.py:886` |
| Cycle invalidation | N/A | SRS set to None when cycle advances | `assertion_cycle.py:97` |
| Consumed downstream | N/A | Used by node_finalize to build RFQDraft | `node_finalize.py:376-388` |

**What's really better:** SRS is a fully populated, cycle-bound, downstream-consumed governance artifact. All blueprint fields are populated from real data sources. material_specificity_required reflects actual candidate evidence depth.

**What still lacks:** Nothing material. The SRS is complete for pilot purposes.

---

### Finding 5: EvidenceClaim / claim_type Governance

**Status: STILL OPEN (Documented Deferral)**

| Aspect | Before Remediation | After Remediation | Evidence |
|---|---|---|---|
| claim_type enum | Absent | Still absent | Zero matches in codebase |
| EvidenceClaim schema | Absent | Still absent | Zero matches in codebase |
| Source authority ranking | All RAG hits equal | All RAG hits still equal | `source_kind` only tracks origin, not claim authority |
| Drift documentation | None | Comprehensive drift map | `CLAIM_SPECIFICITY_DRIFT_MAP.md` |

**What's really better:** The gap is now precisely documented with exact mapping of what blueprint concepts map to which implementation constructs, and where real semantic gaps remain vs. naming drift.

**What still lacks:** No claim_type taxonomy. A DIN norm hit and a forum post carry equal weight as `source_kind="retrieval"`. No authority-ranked evidence hierarchy. This is a real governance gap, but one that requires RAG pipeline changes (embedding metadata, classification) to fix properly.

**Pilot-blocking?** No. The deterministic norm SQL path (`query_deterministic_norms`) bypasses RAG entirely for normative data, which is where authority matters most. Semantic RAG results go through the verify_claims conflict checker which catches specificity mismatches. The risk of a forum post overriding a DIN norm is mitigated by the deterministic path, not eliminated.

---

### Finding 6: Installation-Evidence Gap

**Status: STILL OPEN**

| Aspect | Before Remediation | After Remediation | Evidence |
|---|---|---|---|
| 3-agent parallel fan-out | 2 branches (material+mechanical) | Unchanged | `sealai_graph_v2.py` topology |
| MediumProfile | Absent | Still absent | No typed medium profile |
| MachineProfile | Absent | Still absent | No typed machine profile |
| InstallationProfile | Absent | Still absent | No typed installation profile |
| Installation evidence agent | Absent | Still absent | No installation-specific evidence node |

**What's really better:** Nothing changed in this area. Not a remediation target.

**What still lacks:** Blueprint specifies 3 evidence agents (medium/machine/installation). Implementation has 2 analysis branches (material/mechanical). Installation-specific reasoning (mounting context, housing geometry, shaft surface) is not a distinct evidence path.

**Pilot-blocking?** No. The 2-branch model covers the critical safety paths (chemical resistance, mechanical limits). Installation context is captured through flat WorkingProfile fields (dynamic_type, shaft_diameter, shaft_runout) which flow into calculations. The gap is architectural decomposition, not missing safety coverage.

---

### Finding 7: Specificity Drift / Enum Drift

**Status: SUBSTANTIALLY REDUCED**

| Aspect | Before Remediation | After Remediation | Evidence |
|---|---|---|---|
| specificity vocabulary | 5 impl values vs 4 blueprint values | Same — but drift map documents exact mapping | `CLAIM_SPECIFICITY_DRIFT_MAP.md` Section 2 |
| material_specificity_required | Dead field (always "family_only") | Dynamically derived from candidates | `node_prepare_contract.py:869-878` |
| Governance chain | Already functional | Verified unbroken: specificity → governed → clusters → metadata → release_status | Full chain confirmed by code inspection |
| identity_class naming | `confirmed` vs blueprint `identity_confirmed` | Unchanged — naming prefix difference only | `ParameterIdentityRecord:420` |

**What's really better:** material_specificity_required is now a live governance signal instead of a dead default. The drift between implementation vocabulary and blueprint vocabulary is documented with explicit mapping and risk assessment. The governance chain from specificity through release_status is verified unbroken.

**What still lacks:** `subfamily` and `product_family_required` specificity values from blueprint are not implemented. No formal Literal type for `source_kind`. These are low-severity gaps that don't affect governance correctness.

**Pilot-blocking?** No.

---

## Phase B — Closeout Memo

### Build-Closeout-Ready

The following are fully functional at runtime with correct governance semantics:

1. **SealingRequirementSpec** — full producer, cycle-bound, consumed by RFQDraft builder
2. **RFQDraft** — produced in node_finalize, carries SRS, gated by rfq_confirmation
3. **RFQ admissibility chain** — specificity → governed → clusters → metadata → release_status: unbroken
4. **Identity gates** — pre-RAG (p2_rag_lookup) and contract-level (node_prepare_contract): both runtime active
5. **Candidate semantics** — deterministic, governance-driving, correctly routing clusters
6. **snapshot_confirmation** — fires on spec_id change, prevented from re-firing by confirmed_spec_id
7. **rfq_confirmation** — fires when RFQ+admissibility exist and not yet confirmed
8. **Assertion cycle invalidation** — SRS, RFQDraft, and AnswerContract correctly invalidated on cycle advance
9. **material_specificity_required** — derived from live candidate data
10. **_clear_checkpoint / _deep_merge_patch** — empty-dict replacement bug fixed

### Not v1.2-Rein But Documented and Tragbar

1. **claim_type taxonomy absent** — documented in drift map; mitigated by deterministic norm SQL path
2. **specificity vocabulary drift** — 5 impl values vs 4 blueprint values; exact mapping documented; governance logic correct
3. **source_kind not a formal enum** — implicit, functional, low risk
4. **No native interrupt_before** — checkpoint pattern works but is subgraph-internal
5. **observed_inputs write-only** — audit infrastructure exists but is not consumed
6. **No typed asserted profiles** — flat WorkingProfile instead of MediumProfile/MachineProfile/InstallationProfile
7. **2-branch vs 3-agent** — material+mechanical vs medium/machine/installation decomposition

### Remaining Critical Items Before Pilot

1. **draft_conflict_resolution re-trigger bug** — approving conflicts via HITL doesn't mark them RESOLVED; they remain OPEN and would re-fire on next verification cycle. Requires small fix: set `resolution_status="RESOLVED"` after user approval in `_consume_decision` path for draft_conflict_resolution.

---

## Phase C — Priority Decision

### P0 Remaining (Fix Before Pilot)

| Item | Effort | Why P0 |
|---|---|---|
| draft_conflict_resolution must set RESOLVED on approval | ~10 lines | Without this, user-approved conflicts re-trigger infinitely |

### P1 Remaining (Fix Before Production)

| Item | Effort | Why P1 |
|---|---|---|
| observed_inputs first downstream consumer | ~30 lines | Write-only data has zero governance value; needs at least one reader (e.g., in verify_claims or governance_metadata) |
| source_kind formal Literal type on CandidateItem | ~5 lines | Type safety, no governance change |
| Conflict RESOLVED status lifecycle documentation | Docs only | Currently RESOLVED is dead code in the Literal type |

### P2 (Document-Only / Future Phase)

| Item | Effort | Why P2 |
|---|---|---|
| EvidenceClaim / claim_type taxonomy | HIGH (multi-module) | Requires RAG pipeline metadata enrichment |
| subfamily / product_family_required specificity values | LOW | Depends on KB data availability |
| Typed asserted profiles (MediumProfile etc.) | MEDIUM | Architectural refactoring, no safety impact |
| 3-agent evidence fan-out | HIGH | Architectural refactoring of graph topology |
| Native LangGraph interrupt_before | MEDIUM | Current checkpoint pattern works; interrupt_before would improve visibility |
| RFQ external transmission | Feature work | Not a governance/safety item |

---

## Phase D — Recommendation

**FREEZE AND REVIEW.**

Rationale:
- The remediation has closed or substantially reduced 5 of 7 original findings
- Only 1 P0 item remains (draft_conflict_resolution re-trigger) — this is a ~10-line fix
- The governance chain (identity → specificity → clusters → admissibility → release_status) is verified unbroken
- All remaining gaps are either documented deferrals or infrastructure investments, not safety holes
- Continued patching has diminishing returns — the next real governance improvements (claim_type, installation agent) require architectural changes, not patches

**Recommended next step:** Fix the single P0 (conflict RESOLVED status on approval), then freeze the remediation branch and move to integration testing against real user flows.
