# Core ↔ Domain-Pack boundary (Blueprint §3.3, §3.5, §10.1)

Short, binding map of where the governed **core** ends and a **seal-domain pack**
begins. Established by P1-1 (2026-06-04). RWDR is the **only** pack today; this
boundary exists so the *next* seal type lands as a pack, never as another core
`if seal_type == …` branch.

## Core (domain-agnostic — must NOT branch on seal type)

The governed runtime: state gate / reducers, turn boundary, dashboard & pocket
projections, streaming, output guards, RFQ-readiness machinery, calculation
ledger projection, risk/readiness scoring. The core **asks a pack**; it never
hardcodes per-type field lists, calc ids, or `engineering_path == "rwdr"`.

**Enforced (P1-4):** `backend/tests/architecture/test_core_seal_type_branching.py`
fails CI on any seal-type string-branching (`== "rwdr"`, membership in a seal-type
collection literal, or a per-type field-list dict) in the core modules outside a
versioned, documented allowlist. `…/test_single_writer_invariant.py` fails on any
governed-layer state produced outside the reducer chain (direct constructor or
`.governance/.decision/.normalized/.asserted.model_copy`).

## Pack (one seal domain — owns its specifics)

A `DomainPack` (`app/domain/domain_pack.py`) declares, for one domain:
`pack_id`, `classification_signals()`, `required_fields()`, `calculations()`,
`owns_calc_id()`, `rfq_template_id`. RWDR's implementation is `RwdrPack`
(`app/domain/seal_packs.py`); its *depth* lives in the existing pack modules
(`app/agent/domain/rwdr_calc.py`, `app/services/rwdr_mvp_brief.py`) — those are
**not moved**, the pack only declares/owns.

Deliberately **omitted** from the protocol (no clean pack-level impl today; add
when one exists): `failure_modes` (lives on `ApplicationPattern`), `risk_flags`
(computed per case in `rwdr_mvp_brief`).

## The seam

`app/domain/seal_packs.py` — a **one-entry** `_PACKS` tuple (no registry class;
Rule of Three §3.5) + thin selectors:
- `pack_for(seal_type, seal_family)` — classification → pack.
- `required_fields_for(...)` — pack first, else explicit O-Ring/Hydraulic
  **shallow stubs**, else default.
- `state_gate_type_sensitive_fields_for(sealing_type)` — the state-gate
  type-sensitive required fields (RWDR via the pack, others shallow stubs);
  returns `None` for an unknown type (P1-4 PR1).
- `pack_for_calc_id` / `is_pack_calculation` / `pack_for_engineering_path` —
  calc/risk routing by pack membership.
- `pack_for_calc_type(calc_type)` — EXACT pack-id match for the coarse
  `calc_type` label (mirrors `calc_type == "rwdr"`; unlike `pack_for_calc_id` it
  does NOT match the `rwdr.<id>` namespace, P1-4).

O-Ring / Hydraulic are **shallow stubs** (data tuples behind the seam, no pack).
O-Ring screening geometry depth lives in `app/agent/domain/oring_calc.py` (P1-4
PR4 / C9 — relocated out of the v92 core orchestrator; the core injects its calc
primitives), parallel to RWDR's depth in `app/agent/domain/rwdr_calc.py`.

## How pack #2 (e.g. O-Ring) joins

1. Implement `class OringPack` against the `DomainPack` protocol (its
   `classification_signals`, `required_fields`, `calculations`, …).
2. Add it to `_PACKS` — the selectors fan out automatically; promote the O-Ring
   shallow stub into the pack's `required_fields()`.
3. **Only now** extract a real registry if `_PACKS` has outgrown a tuple
   (Rule of Three §3.5). Not before.
4. No core edits: the core already routes through the seam.

⛔ **Stop sign:** a new seal type is added as a pack (one `_PACKS` entry), never
as another core branch or another hardcoded tuple.

## Core seal-type branching — closed across the whole core (P1-4, 2026-06-04)

> **Correction of an earlier over-claim.** P1-3 routed only the two
> `risk_readiness.py` risk branches and this file briefly read as if the core was
> fully resolved. The V1.7 re-run audit (`docs/audits/2026-06-04_v17_gap_audit_rerun.md`,
> C1 → TEILWEISE/HIGH) showed the seam existed but was **not enforced across the
> core**: live `== "rwdr"` branching remained in the **state-gate reducer**, the
> **challenge engine**, and the **cockpit/workspace projection** (none touched by
> P1-1/P1-3), plus a few more the inventory surfaced. P1-4 closes all of it and
> installs the enforcer so it cannot recur.

**Routed through the seam (behaviour-neutral, frozen 1:1):**
- `reducers.py` — per-type required-field dict → `state_gate_type_sensitive_fields_for` (PR1).
- `challenge_engine.py` (4 sites) — `engineering_path == "rwdr"` → `pack_for_engineering_path` (PR2).
- `case_workspace.py` (3 sites) — path/calc-type branches → `pack_for_engineering_path` / `pack_for_calc_type` (PR3).
- `checks_registry.py` / `output_contract_assembly.py` / `calculation_projection.py` —
  the remaining clean core branches the inventory surfaced beyond the three audited
  surfaces (owner decision A: route them too, so the enforcer guards the whole core
  with no allowlist inflation) (PR3.5).

**Allowlist (deliberate documented CORE checks — the genuine exceptions):**
- `risk_readiness.py` `if path in {"static", "hyd_pneu"}` / `if path == "ms_pump"` /
  `engineering_path in {rwdr, ms_pump, unclear_rotary}` — **heterogeneous sets with no
  1:1 pack equivalence**; only `rwdr` is a pack, so routing would silently drop the
  other paths. An honest core check beats a contorted pack abstraction (Rule of Three;
  owner decision 2026-06-04). This is the canonical example of the boundary staying in
  the core by design.
- `orchestrator.py::normalize_seal_type` — the **classification stage** (C3) that maps
  raw input → canonical `SealType`; it *produces* the label the rest of the core asks
  the pack about. Allowed, not plumbing-branching.

Each allowlist entry carries a documented owner decision in
`test_core_seal_type_branching.py`; a stale-entry guard removes any entry that no
longer matches a real flagged line.

## C9 — O-Ring calc depth (closed, P1-4 PR4)

`_oring_calculations` (a real 5-calc O-Ring geometry) lived in the generic v92 core
orchestrator and was unconditionally called by `build_calculation_state` — the §3.3
flip-side of C1. Relocated **verbatim** to `app/agent/domain/oring_calc.py` (the core
injects its generic calc primitives; no `OringPack` — O-Ring stays a shallow stub).

## S3 — state-gate single-writer (closed, P1-4 PR5b)

`GovernanceState`/`DecisionState`/`NormalizedState` are produced **only** by the
reducer chain. Three deterministic `model_copy` content-syncs that previously
produced governed-layer instances outside the chain (`api/utils.py`,
`output_contract_assembly.py`, `persistence.py`, plus `sheet_events.py`) now route
through `reducers.produce_governance / produce_decision / produce_normalized`.
Enforced by `test_single_writer_invariant.py`.
