# RP-001 import and validation runbook

This runbook describes a future, separately authorized non-production import.
It does not authorize an import now. There is no public or mutating admin API
for these contracts; an authorized operator must use the canonical domain and
repository methods in a controlled environment.

## 0. Entry gate

Stop before any database write unless all of the following are true:

- the package fingerprint and 53-gap source hash match `package-manifest.json`;
- one creator worksheet is complete for every claim;
- creator, reviewer, and owner-approver are assigned to three pairwise distinct
  real verified subjects;
- the target is an explicitly authorized non-production database;
- the exact tenant and domain pack come from approved configuration and
  `VerifiedIdentity`, not from the worksheet or request headers;
- the selected medium has an exact, approved, current MED-NORM catalog entry;
- the future 03A ruleset creation and non-production migrations have separate
  owner authorization;
- all material flags are false and sampling is zero.

If the canonical medium entry is missing, stop the rule import. Complete the
separate MED-NORM identity-evidence workflow first. A MED-NORM
`other_technical` identity claim is not a MATERIAL-RULES supporting claim and
must not be mixed into the rule claim set.

Before importing that identity claim, resolve one owner decision explicitly:
MAT-EVID-01A requires non-empty `scope.materials`, but MED-NORM defines no
neutral material-scope value for a media-identity claim. The operator must not
invent a placeholder. Until an owner-approved, contract-consistent scope policy
exists, source curation may continue but the catalog identity import is
`BLOCKED_BY_OWNER_SCOPE_POLICY`.

## 1. Deterministic source preparation

For each retained source:

1. Normalize only the metadata strings to required NFC; never rewrite source
   content or claim meaning.
2. Calculate SHA-256 over exact source bytes.
3. Call `derive_source_ref` with exact document ID, revision, publication
   edition, and digest.
4. Compare the derived reference with the creator and reviewer worksheets.
5. Reject a URL-only, missing-revision, missing-edition, non-NFC, duplicate, or
   unknown-field record.

No source file is copied into this Git package.

## 2. Ruleset prerequisite

Under separate authorization, create one immutable MAT-GOV-03A.v1 snapshot:

- each `rule_ref` is unique and reserved;
- each RP-001 rule has exactly one material, one canonical media ID, and one
  non-empty condition in both the direct fields and `scope`;
- verdict is exactly `unvertraeglich` or opaque `bedingt`;
- `statement` equals exactly one intended primary claim;
- `evidence_binding` remains exactly `{"state":"unbound"}`;
- `positive_statement_allowed` remains false;
- domain pack is exact and owner-supplied.

Do not create this snapshot from the candidate register. The creator's
evidence-backed proposal and separate authorization are prerequisites.

## 3. MAT-EVID-01A manifest

For each claim:

1. Construct `EvidenceClaimScopeV1` with sorted, unique NFC arrays.
2. Call `derive_claim_ref` with exact claim text and scope.
3. Build `AtomicEvidenceClaimV1` with non-empty sorted source refs.
4. Build exact `RuleClaimBindingV1` entries.
5. Ensure every source supports a claim, every claim binds to a rule, and no
   reference is foreign, dangling, duplicated, or orphaned.
6. Build `EvidenceManifestPayloadV1` against the exact 03A snapshot and domain
   pack.
7. Serialize canonical JSON and parse it again with
   `EvidenceManifestSnapshotV1.from_json`.
8. Create the manifest family and store the snapshot through
   `MaterialEvidenceRepository`; never write tables directly.

Technical validity remains factually unreviewed.

## 4. MAT-EVID-01C dossier

The verified-human creator performs the authenticated create path:

1. Create a review family for the exact evidence snapshot.
2. Copy every and only every 01A source identity and claim scope.
3. Add exact bounded document metadata, locator, rights state/basis, optional
   excerpt, closed claim type, and non-empty required source types.
4. Set final conflict/supersession relations. Approval requires an empty array;
   any relation requires a corrected immutable evidence snapshot.
5. Parse and validate the complete dossier against the exact 01A snapshot.
6. Store it through `MaterialEvidenceReviewRepository.store_snapshot` using the
   creator's authenticated `VerifiedIdentity`.

The creator cannot call the review or approval transition.

## 5. Independent review and approval

1. The independent reviewer repeats source, hash, rights, factual, scope,
   source-type, conflict, and MED-NORM checks.
2. Using a different verified subject with `material_evidence:review`, call
   `record_review` or `record_rejection`.
3. The owner-approver repeats all approval gates.
4. Using a third verified subject with `material_evidence:approve`, call
   `record_approval` only from `reviewed / not_approved`.
5. Reload snapshot and projection from PostgreSQL and confirm exact
   `reviewed / approved` state and hash chain.

No worksheet checkbox substitutes for these append-only events.

## 6. MED-NORM validation

Reload the exact catalog through `MediumCatalogRepository` using the same
tenant identity and verify:

- media ID is derived from canonical name plus closed identity kind;
- aliases are exact, unique, sorted, and exclude canonical name;
- the entry binds an exact approved review snapshot/hash;
- each identity claim is `other_technical`, scoped only to the media ID, with
  the exact `med-norm-identity-sha256:*` condition;
- the mandatory 01A material scope follows a separately owner-approved policy
  and was not invented by the operator;
- current approval revalidates before and after use;
- catalog authority remains `NORMALIZATION_ONLY` and positive statements stay
  false.

## 7. MAT-EVID-01B technical binding

Under separate non-production authorization:

1. Create an exact `bound_unreviewed` companion for the 03A and 01A snapshots.
2. Validate complete `rule_ref -> claim_ref` coverage, identical scope, tenant,
   domain pack, versions, hashes, evaluator/kernel/build identities, and pins.
3. Reject missing, duplicate, foreign, cross-rule-reused, retargeted, or
   scope-drifted claims.
4. Keep the canonical material match evidence state unchanged and unbound.
5. Do not activate shadow sampling or a pointer.

## 8. MATERIAL-RULES-01 final validation

Load the repository-issued capability in the controlled environment and
confirm for every rule:

- the exact current 01B binding, 03A ruleset, 01A manifest, approved 01C
  projection, and MED-NORM catalog all revalidate;
- primary statement claim is unique and byte-identical to rule statement;
- primary type is `incompatibility` for `unvertraeglich` or
  `conditional_compatibility` for `bedingt`;
- supporting types are only temperature, application, or regulatory;
- scope is one material, one media ID, and one condition;
- references are complete, sorted, tenant-bound, and source-bound;
- authority equals `FACTUAL_REVIEWED_DISQUALIFY_ONLY`;
- `positive_statement_allowed` is false;
- serialization of the live capability is rejected.

Repeat negative checks by altering one copy at a time: hash, tenant, scope,
claim type, statement, approval state, catalog entry, and binding target. Every
alteration must fail closed.

## 9. Receipt and stop

Produce a non-production validation receipt containing only IDs, hashes,
versions, timestamps, test results, and authenticated subject references. Do
not include source text, tokens, or licensed content.

Final acceptable receipt state:

```text
RP001_REVIEWED_RULE_PACK_TECHNICALLY_VALIDATED_INERT
```

Then stop. Do not create an active pointer, public API output, frontend
projection, migration on production, sampling, deployment, or material release.
