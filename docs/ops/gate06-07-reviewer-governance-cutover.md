# GATE-06/07 — Reviewer roles, affiliation authority, and COI cutover

Status: **IMPLEMENTED LOCALLY, NOT DEPLOYED, BLOCKED EXTERNAL**. This document
does not authorize a Keycloak or database mutation. No production role,
affiliation, review, feature flag, or container was changed while preparing it.

## Authority boundary

Keycloak proves subject and realm roles. It does not prove employment,
ownership, contracting, advisory, audit, or shared-organization relationships.
Those relationships must come from a named human-controlled authority source:

- an owner-attested identity roster;
- an independent HR register; or
- a contractual affiliation register.

The source owner must provide an immutable, versioned bundle conforming to
`security/affiliation-authority-bundle.schema.json`. Every record binds the
subject, organization, relationship, validity interval, source reference,
source version, separate human recorder, revision, and SHA-256. JWT claims,
review request bodies, e-mail domains, company names, and self-attestations are
not acceptable authority. The bundle contains personal/organizational data and
must never be committed or copied into CI logs or PR evidence.

## Safe local/read-only preparation

The Keycloak governance reconciler is read-only by default and emits counts and
hashes only:

```bash
python3 ops/keycloak_governance_reconcile.py
```

The affiliation importer validates a local authority bundle without opening a
database connection:

```bash
python3 ops/reviewer_governance_cutover.py authority \
  --bundle '<ACCESS-CONTROLLED-AUTHORITY-BUNDLE.json>'
```

After migrations exist on an isolated restore copy, legacy review profiling is
also read-only and returns only candidate counts plus a profile hash:

```bash
SEALAI_V2_DATABASE_URL='<ISOLATED-RESTORE-DSN>' \
python3 ops/reviewer_governance_cutover.py quarantine
```

Both quarantine dry-run and apply require the same access-controlled, stable,
minimum-32-byte `SEALAI_GOVERNANCE_FINGERPRINT_KEY`. It HMACs source identifiers
before they enter a receipt or quarantine row; never place the key in shell
history, a command argument, CI output, or version control.

Neither command activates `knowledge_review_enabled` or
`capability_profiles_enabled`.

## Staged gated cutover

1. **GATE-06 — role census.** Bind the exact
   `security/keycloak-governance-v1.json` hash to a sanitized role/group census.
   Resolve every forbidden direct `admin` assignment and incompatible group
   overlap through the human identity roster. The reconciler never guesses or
   changes user memberships. Apply only the exact managed roles/groups after a
   separate GATE-06 approval, passing both the manifest hash and the dry-run
   `sanitized_state_sha256`; rerun dry-run and require zero drift/overlap.
2. **GATE-07 — additive schema.** On a restore-tested isolated copy, apply
   Alembic `20260715_0014` and `20260715_0015`. The first creates empty
   affiliation, immutable snapshot, append-only decision, and fingerprint-only
   quarantine tables. The second installs PostgreSQL `NOT VALID` checks and
   snapshot foreign keys plus append-only triggers; it does not validate
   historical rows. Neither migration imports data, changes review status, or
   enables a feature.
3. **GATE-07 — human authority import.** Peer-review the access-controlled
   bundle and its dry-run hash. The append-only future command is:

   ```bash
   SEALAI_V2_DATABASE_URL='<APPROVED-TARGET-DSN>' \
   python3 ops/reviewer_governance_cutover.py authority \
     --bundle '<ACCESS-CONTROLLED-AUTHORITY-BUNDLE.json>' \
     --apply \
     --confirm-gate GATE-07 \
     --expected-input-sha256 '<APPROVED-DRY-RUN-HASH>'
   ```

   Existing record IDs must be byte-equivalent; the tool inserts new revisions
   only and never updates/deletes authority history.
4. **GATE-07 — legacy quarantine.** Review the aggregate candidate counts.
   Approved legacy knowledge/capability decisions without server COI snapshots
   must not be grandfathered. Insert only PII-free fingerprints into the
   quarantine queue using the exact dry-run profile hash:

   ```bash
   SEALAI_V2_DATABASE_URL='<APPROVED-TARGET-DSN>' \
   python3 ops/reviewer_governance_cutover.py quarantine \
     --apply \
     --confirm-gate GATE-07 \
     --expected-input-sha256 '<APPROVED-PROFILE-HASH>' \
     --detected-at '<APPROVED-UTC-TIMESTAMP>'
   ```

   This does not alter source rows or infer a reviewer. Re-review from current
   authority is required before release. Constraint validation is a later
   separately reviewed GATE-07 step.
5. **GATE-08 — deploy, keep disabled, verify.** Deploy schema and code together,
   recreate API/worker containers, and keep both review surfaces off. Run
   negative tests for missing authority, shared affiliation, self-review,
   contributor/reviewer/approver/admin/operator overlap, stale authority, and
   connection-pool leakage. Only a later explicit activation decision may turn
   either feature on.

## Stop conditions

- the authority source owner, bundle version, or peer approval is absent;
- raw subjects, organizations, tokens, credentials, or bundle contents appear
  in a receipt/log;
- any legacy `admin` assignment or incompatible group overlap remains;
- bundle/profile hash differs from the approved dry-run receipt;
- an existing authority record differs from the bundle;
- any active reviewer/approver lacks a current human-authoritative affiliation;
- schema head, target DB fingerprint, immutable backup, or isolated restore
  proof is missing;
- a migration attempts a backfill, validation, feature activation, role change,
  update, or delete outside its approved stage.

## Rollback

Keep the review feature flags off and roll application containers back to the
previous compatible image. The additive tables and `NOT VALID` constraints may
remain. Authority revisions, snapshots, decisions, and quarantine receipts are
audit history and must not be deleted or rewritten. A mistaken authority entry
is superseded by a reviewed higher revision; a quarantined resource is released
only through a fresh independent review after the authority source is corrected.

Production closure requires GATE-06 role evidence, GATE-07 database/authority
evidence, and GATE-08 post-deploy tests. Until all three exist, AUTH-003 and
GOV-001 must not be labelled `VERIFIED`.
