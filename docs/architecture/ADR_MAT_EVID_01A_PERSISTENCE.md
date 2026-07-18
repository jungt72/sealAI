# ADR: MAT-EVID-01A immutable evidence manifests

Status: accepted for additive local implementation only; production migration,
runtime evidence binding, review, approval, and activation are not authorized.

Date: 2026-07-18

## Context

MAT-GOV-03A schema v1 deliberately fixes every rule evidence object to
`{"state":"unbound"}`. Reinterpreting that field would destroy historical hash
meaning. MAT-EVID-01A therefore requires a separate, explicitly versioned and
content-addressed aggregate before any evaluator may consume evidence.

## Decision

`MAT-EVID-01A.v1` introduces a closed evidence-manifest payload containing:

- one exact `mss_<hash>` MAT-GOV-03A snapshot and its domain pack;
- sources identified by document ID, document revision, publication edition,
  and SHA-256 content digest;
- atomic claims with exact material, media, and condition scope;
- explicit `rule_ref -> claim_ref` pairs.

`source_ref` hashes the complete source identity. `claim_ref` hashes only the
NFC claim text and exact scope, so an unrelated source revision does not change
the logical claim identity, while any claim-text or scope change does. Sources,
claims, source references, and bindings are unique and canonically ordered.
Dangling and orphan references fail closed. A manifest snapshot additionally
binds the content hash to a stable server-generated manifest family ID.

The manifest has no review, approval, deployment, lifecycle, active-pointer,
authority, or positive-statement field. Technical validation means only that
the closed schema, canonicalization, identities, references, and exact 03A
binding are internally valid. It confers no factual acceptance.

## Persistence and foreign-key boundary

Four initially empty tables store manifest families, immutable snapshots,
technical validation events, and technical audit events. The new manifest
family has an `ON DELETE RESTRICT` foreign key to the exact immutable 03A
snapshot and is unique for that snapshot; manifest versions are snapshots in
that one family. All other foreign keys remain inside the MAT-EVID aggregate.
This is a documented extension of the bounded material-governance FK exception,
not a retrofit of legacy tables.

PostgreSQL and the SQLite test profile install triggers rejecting every
`UPDATE` and `DELETE`. The repository exposes create/read methods only and
revalidates canonical bytes, content hash, snapshot ID, JSON projection,
domain pack, bound 03A snapshot, and every bound rule reference on each load.
Corrections require a new immutable evidence snapshot.

The migration has dialect-specific structural adoption fingerprints. It
creates no row, seed, backfill, matrix import, lifecycle state, public/admin
API, or runtime dependency. Downgrade is allowed only while every new table is
empty. Production execution requires a separate owner decision.

## Canonical identity

All JSON is strict UTF-8/NFC, duplicate-free, float-free, compact and
recursively key-sorted. Typed set-like arrays are unique and sorted by UTF-8
bytes. The domain-separated identities are:

```text
source_ref = "msr_" + SHA-256(
  b"sealai.material-evidence.source.v1\x00" + canonical_source_identity
)

claim_ref = "mec_" + SHA-256(
  b"sealai.material-evidence.claim.v1\x00" + canonical_claim_text_and_scope
)

content_sha256 = SHA-256(
  b"sealai.material-evidence.content.v1\x00" + canonical_manifest_bytes
)

snapshot_id = "mes_" + SHA-256(
  b"sealai.material-evidence.snapshot.v1\x00"
  + ASCII(manifest_id) + b"\x00" + ASCII(content_sha256)
)
```

Golden fixtures freeze source, claim, content, snapshot, validation, and audit
hashes for v1.

## Consequences

- MAT-GOV-03A schema v1 and every existing snapshot remain byte-meaning stable.
- Existing matrix text, legacy `Quelle`, RAG data, URLs, model output, and
  material evidence cards are not imported or trusted automatically.
- A URL cannot be a standalone source record because revision, edition, and
  content digest are mandatory and unknown fields are rejected.
- MAT-EVID-01B must provide the separate fail-closed runtime binding contract.
- MAT-GOV-03C review/approval/deployment axes remain absent and unauthorized.
- Every material feature flag remains false and shadow sampling remains zero.
