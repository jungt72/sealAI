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
- `pack_for_calc_id` / `is_pack_calculation` / `pack_for_engineering_path` —
  calc/risk routing by pack membership.

O-Ring / Hydraulic are **shallow stubs** (data tuples behind the seam, no pack).

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

## Known residual (P1-1 follow-up, surfaced not actioned)

`app/agent/domain/risk_readiness.py:498` (`engineering_path in
{"rwdr","ms_pump","unclear_rotary"}` — a heterogeneous set, not a 1:1 pack
equivalence), `:527`, `:555` (`== "rwdr"`) still string-branch on rwdr. Candidates
for a later pack-membership pass; out of P1-1's named scope.
