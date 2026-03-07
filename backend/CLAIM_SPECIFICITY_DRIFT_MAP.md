# Claim & Specificity Drift Map — Blueprint v1.2 vs Implementation

**Date:** 2026-03-07
**Scope:** `candidate_semantics.py`, `CandidateItem`, `SealingRequirementSpec`, `rfq_admissibility.py`, `node_verify_claims.py`
**Decision:** Option C (Drift-Map) + one real patch (`material_specificity_required` derivation)

---

## 1. claim_type — ABSENT (Intentional Deferral)

### Blueprint Spec
`EvidenceClaim` schema with 6 `claim_type` values:
- `fact_observed` — Direct user observation
- `fact_lookup` — Retrieved from authoritative source
- `fact_inferred` — Logically derived
- `heuristic_warning` — Pattern-based, not authoritative
- `expert_pattern` — Domain expert heuristic
- `manufacturer_specific_limit` — Manufacturer-provided constraint

### Current Implementation
No `claim_type` field exists. Governance relies on a different axis:

| Blueprint claim_type | Closest implementation signal | Exact match? |
|---|---|---|
| `fact_observed` | `source_kind="user"` | Partial — no structured observation record |
| `fact_lookup` | `source_kind="retrieval"` | Partial — all RAG hits are "retrieval" regardless of source authority |
| `fact_inferred` | No equivalent | ABSENT |
| `heuristic_warning` | `source_kind="heuristic"` | Partial — no distinction from expert_pattern |
| `expert_pattern` | `source_kind="heuristic"` | Merged with heuristic_warning |
| `manufacturer_specific_limit` | No equivalent | ABSENT |

### Why This Is a Real Semantic Gap (Not Just Naming)
`source_kind` tracks **where** a value came from. `claim_type` tracks **what kind of assertion** the evidence makes. A manufacturer datasheet saying "max 200C for FKM 75" and a Wikipedia paragraph about FKM both get `source_kind="retrieval"` — indistinguishable. The blueprint intended authority-ranked claim types to gate decisions differently.

### Why Deferral Is Correct Now
Implementing `claim_type` properly requires:
1. RAG hits to carry claim classification metadata (embedding pipeline change)
2. A classifier to tag retrieved chunks with claim_type (LLM or heuristic)
3. Authority ranking in `build_candidate_clusters` and `node_verify_claims`

This is a multi-module change with high blast radius. The current governance model (specificity + governed + excluded_by_gate) provides equivalent safety for the implemented use cases: no unconfirmed candidate can reach `rfq_ready` status.

### Operational Risk: LOW-MEDIUM
- No authority ranking means a forum post and a DIN norm carry equal weight as retrieval sources
- Mitigated by: `selected_fact_ids` preferring DIN sources (score-based), deterministic norm SQL path bypassing RAG entirely for normative data

---

## 2. specificity_level — Vocabulary Drift (Functional Equivalence)

### Blueprint Spec
4 values: `family_only`, `subfamily`, `compound_required`, `product_family_required`

### Current Implementation
5 values on `CandidateItem.specificity`:

| Implementation value | Blueprint equivalent | Mapping quality |
|---|---|---|
| `compound_specific` | `compound_required` | EXACT — same semantics, different name |
| `family_level` | `family_only` | EXACT — same semantics, different name |
| `material_class` | No equivalent | ADDITION — below family_level, e.g. "elastomer" |
| `document_hit` | No equivalent | ADDITION — from retrieval, depth unknown |
| `unresolved` | No equivalent | ADDITION — catch-all for unclassifiable |

| Blueprint value | Implementation equivalent | Status |
|---|---|---|
| `family_only` | `family_level` | Covered (name drift only) |
| `subfamily` | No equivalent | NOT IMPLEMENTED — no sub-family granularity |
| `compound_required` | `compound_specific` | Covered (name drift only) |
| `product_family_required` | No equivalent | NOT IMPLEMENTED |

### Governance Decision Points Using specificity

| Decision point | File:Line | Specificity check | Effect |
|---|---|---|---|
| `governed` flag | `candidate_semantics.py:141-144` | `specificity == "compound_specific"` | Only compound_specific + user/asserted + confirmed = governed |
| Cluster routing | `candidate_semantics.py:175` | `governed AND compound_specific` | Routes to plausibly_viable vs viable_only |
| Scope of validity | `node_prepare_contract.py:908` | `!= "compound_specific"` | Adds disclaimer to governance_metadata |
| Manufacturer validation | `node_prepare_contract.py:939` | `!= "compound_specific"` | Adds to unknowns_manufacturer_validation |
| Specificity conflict | `node_verify_claims.py:369-424` | Checks compound indicator in draft vs contract | COMPOUND_SPECIFICITY_CONFLICT with RESOLUTION_REQUIRES_MANUFACTURER_SCOPE |
| SRS material_specificity_required | `node_prepare_contract.py:871-878` | Best from candidate_clusters | Reflects actual evidence depth on SRS |
| RFQ release_status | `rfq_admissibility.py:39-47` | Via governed_ready (compound_specific required) | Gates rfq_ready status |

### Why This Is Naming Drift, Not Semantic Drift
The governance logic is correct: only `compound_specific` (= blueprint's `compound_required`) enables governed status and RFQ release. The three additions (`material_class`, `document_hit`, `unresolved`) provide finer granularity below the governance threshold — they all route to `viable_only_with_manufacturer_validation`, same as blueprint's `family_only` for governance purposes.

### Operational Risk: LOW
- No governance decision is incorrect due to naming differences
- Audit readability slightly reduced (auditor must know the mapping)

---

## 3. material_specificity_required — PATCHED (This Session)

### Before
`SealingRequirementSpec.material_specificity_required` was always `"family_only"` (default). Never set dynamically. Dead field.

### After
Derived from the best specificity in non-excluded candidate clusters:
- `compound_specific` if any plausibly_viable candidate has it
- `family_level` if the best available is family_level
- `family_only` (default) if no candidates exist

### Governance Value
The SRS now accurately describes what level of material commitment the contract carries. An auditor can read `material_specificity_required` on the SRS and know whether the recommendation is compound-sharp or family-level.

---

## 4. source_kind — Functional, Not Formally Enumerated

### Current Values (Implicit)
`user`, `asserted`, `heuristic`, `retrieval`, `unknown`

### Where Defined
Inferred in `annotate_material_choice()` from the `confidence` field:
- `confidence="retrieved"` -> `source_kind="retrieval"`
- `confidence="heuristic"` -> `source_kind="heuristic"`
- `confidence="user"` -> `source_kind="user"`
- `confidence="asserted"` -> `source_kind="asserted"`
- else -> `source_kind="unknown"`

### Governance Impact
Only through the `governed` flag derivation: `source_kind in {"user", "asserted"}` is one of three required conditions. No other governance decision branches on source_kind directly.

### Risk: LOW
The implicit enum works. A formal `Literal[...]` type would add type safety but no governance value.

---

## 5. Residual Gaps — Honest Assessment

| Gap | Blueprint Reference | Severity | Fix Effort | Recommendation |
|---|---|---|---|---|
| No `claim_type` taxonomy | Section 05 (RAG Architecture) | MEDIUM | HIGH (multi-module) | Defer to RAG pipeline refactoring phase |
| No `subfamily` specificity | Section 03 (Governance Enums) | LOW | LOW | Add when sub-family compound data exists in KB |
| No `product_family_required` specificity | Section 03 (Governance Enums) | LOW | LOW | Add when product family KB is available |
| `source_kind` not a formal Literal enum | Implicit in candidate_semantics.py | LOW | TRIVIAL | Can add anytime; no governance change |
| No authority ranking on retrieval sources | Section 05 (EvidenceClaim) | MEDIUM | HIGH | Requires RAG metadata enrichment |
| `lookup_allowed` / `promotion_allowed` flags computed but only enforced at contract stage | Section 03 (Normalized Layer) | MEDIUM | MEDIUM | Pre-RAG identity gate partially addresses this (implemented in p2_rag_lookup.py) |

---

## 6. What Is NOT Drifting (Confirmation)

These governance components are fully blueprint-aligned:

- **release_status** enum: `inadmissible / precheck_only / manufacturer_validation_required / rfq_ready` — exact match
- **rfq_admissibility** enum: `inadmissible / provisional / ready` — exact match
- **conflict_type** enum: 9 types (7 from blueprint + FALSE_CONFLICT + UNKNOWN) — superset, no loss
- **conflict_severity** enum: 6 levels — functionally equivalent (blueprint's SOFT = implementation's WARNING)
- **3-cluster candidate model**: `plausibly_viable / viable_only_with_manufacturer_validation / inadmissible_or_excluded` — exact match
- **identity_class** enum: `confirmed / probable / family_only / unresolved` — exact match (blueprint uses `identity_` prefix, code doesn't — naming only)
- **Deterministic governance**: All specificity, clustering, release_status, and conflict decisions are pure functions with no LLM involvement — matches blueprint intent
