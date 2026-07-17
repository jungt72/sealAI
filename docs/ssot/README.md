# sealingAI SSoT

This directory contains the ratified strategic source of truth for sealingAI.

## Canonical source

- Human-reviewed source: `sealingAI_SSoT_v2.0.docx`
- Diffable projection: `sealingAI_SSoT_v2.0.md`
- Source SHA-256: `066dd803b7013fa8b7fdcac4703dee63c3fb183a55d7ef4e2cca76e963802580`
- Status: ratified
- Ratification date: 2026-07-10

The DOCX is the signed-off source artifact. The Markdown file is a mechanical
projection for review, search, and change impact analysis. A change to either
requires an Owner Decision Record and a new version; they must never drift
silently.

## Authority

1. Applicable law, binding regulation, contracts, and licenses.
2. The ratified strategic SSoT in this directory.
3. Ratified invariants, ADRs, security contracts, and the Owner Decision
   Register.
4. Build specifications, data contracts, API/SSE schemas, and eval rubrics.
5. Tests, CI/CD gates, and production runbooks.
6. Implementation.
7. Historical concepts, audits, screenshots, and discussions.

`AGENTS.md` is an operating guide at level 3/4. It may explain how to work in
the repository, but it may not override the SSoT.

## Operational companions

- `ssot-map.json`: machine-readable implementation and gate status.
- `product-maturity.json`: honest maturity for horizons and product modes.
- `INVARIANT_MAPPING.md`: traceability from principles and hard gates to code.
- `OWNER_DECISION_REGISTER.md`: ratified strategic decisions.
- `PAIN_EVIDENCE_LEDGER.md`: evidence and validation status for industry pains.
- `IMPLEMENTATION_AUDIT_2026-07-11.md`: initial repository gap audit.
- `INTEROPERABILITY_CHARTER.md`: lifecycle and external data-contract policy.
- `QUALITY_ASSURANCE_PLAN.md`: review, validation, incident, and CAPA policy.
- `MATERIAL_CONSTRAINT_GOVERNANCE.md`: default-off MAT-GOV package boundaries,
  canonical verdict contract, inert MAT-GOV-03A snapshot foundation, and owner
  activation constraints.

## Change rule

Every strategic change identifies the affected principle, gate, horizon,
data contract, test/eval, public maturity statement, rollback path, and owner.
Unimplemented horizons remain `planned` or `in_build`; they are not inferred
from aspirational text.
