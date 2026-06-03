---
name: v17-audit
description: Deep read-only gap audit of this repository against the V1.7 Universal Sealing Case Platform blueprint. Use when asked to audit the IST state vs V1.7, map the Core/Domain-Pack boundary, or verify tenant isolation and UX wiring. Produces an evidence-based gap report. Never edits files.
---

# V1.7 Gap Audit (strictly read-only)

## Contract
- Analysis only. Never use Edit, Write, or any state-changing tool. Do not run test suites or application code unless the user explicitly approves it in this session.
- Every finding MUST carry evidence as `path:line`. Anything without evidence is labeled `ASSUMPTION`.
- End with the report and STOP. Patches are a separate, explicitly approved phase — never propose inline code changes here.

## Inputs (read these first, in this order)
1. `docs/sealing_intelligence_v1_7_universal_sealing_case_platform_blueprint.md` — binding architecture. Focus: §3 (Core/Pack), §8 (Security/Tenant), §9 (Sequencing), §11 (Acceptance Criteria).
2. `docs/sealing_intelligence_v1_6_mobile_first_complete_architecture_blueprint.md` — operative contracts. Focus: §5 (scenario matrix), §6 (tiers/traces), §7 (mode contracts), §11/§12/§28 (envelopes/schemas), §20 (RFQ readiness).
3. `docs/architecture/SSOT_REGISTRY.md` and `AGENTS.md` — confirm precedence rules are consistent with both blueprints.

## Phase 1 — Parallel exploration (keep main context lean)
Delegate to read-only subagents; collect their reports before synthesizing:
1. `audit-core-pack-cartographer` — Core vs RWDR boundary map (V1.7 §11 criteria 1–4, 9).
2. `audit-tenant-security` — tenant scoping / IDOR on every case, file, evidence, RFQ and stream operation (criterion 6).
3. `audit-ux-wiring` — chat → SSE → cockpit/pocket wiring, mobile first-progress, golden-test coverage (criteria 7–8).
Additionally use the built-in Explore agent for a repo map: top-level modules, entry points, test layout, CI config.

## Phase 2 — Synthesis: gap matrix vs V1.7 §11
Classify each acceptance criterion as ERFÜLLT / TEILWEISE / FEHLT / NICHT PRÜFBAR, with evidence and severity:
1. Core and RWDR Domain Pack visibly separated; no RWDR specifics in generic plumbing.
2. DomainPack interface (or equivalent) exists; a second seal type would be addable without core rework.
3. Classification stage (SealTypeImpactAgent or equivalent) selects the pack.
4. required_fields / Mindestkern declared domain-specifically (RWDR = first implementation).
5. Cross-cutting knowledge (material/medium/norm) organized separately from domain knowledge.
6. Tenant scoping enforced on ALL case/file/evidence/RFQ operations; no cross-tenant access.
7. RWDR killer flow wired end-to-end (Chat → Cockpit → Pocket Cockpit → State Gate → RFQ One-Pager).
8. Photo + "sifft" yields <1 s visible mobile progress; bad photos trigger measurement/photo guidance.
9. No speculative universal abstraction built beyond RWDR.
10. Manufacturer feedback structurally captured as a knowledge source.

Also spot-check V1.6 operations: tier latency budgets + trace fields (§6), mode coverage vs scenario matrix (§5), State Gate as single writer, RFQ readiness logic (§20).

## Phase 3 — Report (exact output format)
1. **IST-Zustand** in max. 10 sentences.
2. **Gap-Matrix**: `# | V1.7 criterion | status | evidence (path:line) | severity | target phase (P0–P3)`.
3. **Top-5 risks** with blast radius.
4. **Recommended patch sequence** — P0 first (tenant/IDOR, then wiring); each patch small and independently testable.
5. **Open questions / assumptions.**

Then STOP. After user approval only: save the report to `docs/audits/<YYYY-MM-DD>_v17_gap_audit.md`.
