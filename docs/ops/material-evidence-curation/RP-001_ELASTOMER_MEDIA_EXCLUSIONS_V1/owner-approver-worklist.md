# RP-001 owner-approver worklist

Required authenticated roles: `verified_human` and
`material_evidence:approve`.

The owner-approver must be a third authenticated subject, different from both
creator and reviewer. Approval is factual evidence approval only.

## A. Separation and lifecycle

- [ ] Repository metadata proves creator, reviewer, and owner-approver subjects
  are pairwise different.
- [ ] The current projection is exactly `reviewed / not_approved`.
- [ ] No rejection, revocation, or quarantine terminal state exists.
- [ ] Event sequence and hash chain are intact and append-only.
- [ ] No shared account, service principal, agent, model, or header-supplied
  identity fills a human role.

## B. Approval gate

- [ ] Exact MAT-EVID-01A snapshot, content hash, schema, domain pack, ruleset
  snapshot, claims, sources, and bindings revalidate.
- [ ] Exact MAT-EVID-01C snapshot covers every and only every source and claim.
- [ ] Every source identity contains document ID, revision, edition, and exact
  content digest.
- [ ] Every source rights state is `permitted`, `licensed`, or
  `public_domain`; none is `unknown` or `restricted`.
- [ ] Every claim has all declared required source types.
- [ ] Every claim text is at most 512 characters and 1024 UTF-8 bytes.
- [ ] `claim_relations` is empty.
- [ ] Every rule claim is atomic over one material, one approved canonical
  medium, and one condition.
- [ ] The primary claim exactly equals the complete proposed rule statement.
- [ ] The primary claim type matches `unvertraeglich` or opaque `bedingt`.
- [ ] No positive compatibility statement, recommendation, or release wording
  appears.
- [ ] The MED-NORM catalog approval is current and its identity evidence is
  independently approved.

## C. Fail-closed negative checks

- [ ] Replacing any source digest changes `source_ref` and invalidates the
  pinned dossier.
- [ ] Changing claim text or scope changes `claim_ref`.
- [ ] Missing, duplicate, foreign, orphan, or cross-tenant references are
  rejected.
- [ ] Same-ID retargeting, review revocation/quarantine, catalog drift, or
  source/scope drift invalidates the reviewed capability.
- [ ] `vertraeglich`, a mismatched primary claim type, `other_technical` as a
  rule claim, or a non-atomic scope is rejected.

## D. Approval action

- [ ] Authenticate as the owner-approver and use only the append-only
  MAT-EVID-01C approval transition.
- [ ] Record no approval in a spreadsheet, comment, or Git commit as a
  substitute for the repository event.
- [ ] After approval, run the non-production exact capability validation from
  `import-validation-runbook.md`.
- [ ] Leave all material flags false and sampling zero.
- [ ] Do not create an active pointer, deploy, or expose a public result.

Approval result:

```text
FACTUAL_EVIDENCE_APPROVED_NO_RUNTIME_AUTHORITY
```

If any item is not satisfied, do not approve. Return a new immutable evidence
or review snapshot to the creator/reviewer path.
