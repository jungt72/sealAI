# ADR: MAT-EVID-02 additive typed Evidence scopes

Status: accepted for additive repository implementation only. Production
migration, content import, factual approval, runtime activation, public output,
and deployment are not authorized.

Date: 2026-07-18

## Context

`MAT-EVID-01A.v1` requires every claim to carry non-empty `materials`, `media`,
and `conditions` and every manifest to bind one exact ruleset snapshot. That
contract remains valid for material-relation claims but cannot represent a
media-identity claim without inventing a material placeholder. RP001-OD-01
forbids such a placeholder and requires a new typed scope version.

## Decision

`MAT-EVID-01A.v2` is additive and uses a closed discriminator in both the
manifest target and every claim scope. A manifest is homogeneous:

- `material_relation` targets one exact `ruleset_snapshot_id`; every claim has
  non-empty `materials` and `media`, an exact `conditions` tuple, and an
  explicit `rule_ref -> claim_ref` binding;
- `media_identity` targets one exact scalar `media_ref`; every claim repeats
  that exact scalar plus one
  `med-norm-identity-sha256:<digest>` assertion reference, has no `materials`
  property, and cannot carry a rule binding.

Unknown fields, mixed scope variants, target/scope drift, media arrays,
placeholder materials, missing source or claim coverage, duplicate JSON keys,
floats, non-NFC text, and unsupported versions fail closed. Version 2 has
independent source-, claim-, content-, snapshot-, validation-, and audit-hash
domains and its own frozen golden fixtures. V1 bytes, hashes, snapshots, tables,
and repositories are not modified, converted, copied, or reinterpreted.

`MAT-EVID-01B.v2` accepts only a `material_relation` manifest and binds exact
ruleset/evidence snapshot IDs, hashes, versions, domain pack, rule refs, claim
refs, scopes, and source refs. A `media_identity` manifest is outside the
material-rules evaluator and fails closed. Its authority remains exactly
`TECHNICAL_UNREVIEWED`; positive statements remain impossible.

`MAT-EVID-01C.v2` covers both v2 claim variants object-exactly. A
`media_identity` claim is reviewable only as `other_technical`; a
`material_relation` claim cannot use that identity-only type. The existing
verified-human creator/reviewer/approver separation and append-only lifecycle
are unchanged. Factual review still grants no runtime or positive-material
authority.

MED-NORM accepts either the historical exact v1 identity-evidence shape or the
new exact v2 `media_identity` shape. V2 removes the material placeholder; it
does not create a media identity, catalog row, alias, or normalization fact.

## Persistence

Migration `20260718_0018` adds fourteen initially empty v2 tables for manifest,
runtime companion, and factual-review aggregates. All references use
`ON DELETE RESTRICT`; target uniqueness uses a non-null exact `target_ref`
bound by a cross-field check to the discriminated target column, so nullable
columns cannot weaken the invariant. PostgreSQL and
SQLite triggers reject `UPDATE` and `DELETE`, and downgrade is permitted only
while every v2 table is empty. Structural adoption is protected by exact
dialect-specific fingerprints.

No row is seeded or backfilled. The migration introduces no active pointer,
sampling, API, frontend, runtime resolver, deployment state, or production
execution authority.

## Consequences

- RP001-OD-01 can be represented without a material placeholder.
- Existing v1 histories remain reproducible under the original hash domains.
- Technical binding and factual review remain separate; neither creates a
  positive material statement or activates a ruleset.
- Human-curated sources and claims are still required. This ADR creates none.
- All material feature flags remain false and shadow sampling remains zero.
- Production migration, MAT-GOV-03C, activation, and deployment remain NO-GO.
