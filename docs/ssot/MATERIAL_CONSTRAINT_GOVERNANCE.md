# Material-Constraint Governance

Status: MAT-GOV-01 implemented as a default-off contract; no material-rule
activation. Owner decisions ratified 2026-07-16.

This companion specification applies the ratified SSoT principles P1-P5 and
P12 to material constraints. It does not add material facts, media classes,
evidence, formulas, coefficients, or a release authority.

## Canonical contract

The only material-compatibility verdict values are the existing matrix values:

```text
vertraeglich
unvertraeglich
bedingt
```

`MaterialConstraintResult` is the canonical typed result. Material and medium
each carry an independent `known | missing | unknown | ambiguous` resolution
state. `MediumCardinality` separately records only the structurally established
count `none | single | multiple | unknown`; it performs no lexical or technical
medium normalization. Their relation is separately `undetermined | resolved |
unresolved | not_applicable`, and evaluation is `evaluated | blocked |
no_rule_data`. A verdict exists only for `evaluated`; its absence is never an
executable wildcard. `unobtainable` remains exclusively an adaptive-interview
`NeedStatus`.

The cross-field contract is closed: missing media are `none + undetermined`,
unknown or ambiguous media are `unknown + undetermined`, one known medium is
`single + not_applicable`, and multiple known media are either `multiple +
unresolved` or `multiple + resolved`. MAT-GOV-01 evaluates only the
single/not-applicable form. Every multiple cardinality is blocked, including a
relation marked resolved: that relation state alone does not prove that a
structured, separately evaluable list of contact media exists. No punctuation
or conjunction in free text is used to infer cardinality. MED-NORM-01 must
establish the structured media representation before any multiple-media
evaluation can become eligible.

`bedingt` is opaque and cannot collapse into `vertraeglich`. Every applicable
conditional rule remains attached through its stable matrix-cell reference,
including when an incompatible rule wins the legacy precedence. The existing
Gegencheck response remains a backward-compatible projection and continues to
show only the strongest member of the winning category.

All matches are canonically ordered by verdict precedence, stable rule
reference, statement, and neutral source reference. Duplicate rule references
are invalid. Therefore `matches`, `conditions`, `decisive_ref`, and serialized
JSON do not depend on seed, input, or database order. The canonical evaluator
is complete and unbounded: every applicable match and condition is retained.
The historical six-hit bound exists only inside the Legacy-Gegencheck
projection, after the canonical verdict and decisive reference have been
computed from the complete result; projection cannot mutate that result.

The canonical `source_ref` is exactly `matrix-cell:<rule_ref>` and construction
rejects every other value.
`evidence_binding_state` is fixed to `unbound` until MAT-EVID-01 establishes a
claim/evidence/review binding. Legacy `Quelle` labels do not confer evidence or
review status on this contract.

`vertraeglich` and the legacy `matrix_compatible` projection mean only:

```text
keine dokumentierte Unverträglichkeit
```

They never authorize a positive compatibility statement, material selection,
component release, or `COVERED_RECOMMENDATION` on their own. The canonical
contract enforces `positive_statement_allowed=false` for every result.

## Work-package boundaries

| Package | Binding scope |
| --- | --- |
| MAT-GOV-01 | Canonical typed result, unchanged verdict values, stable conditional references, legacy Gegencheck adapter, default-off additive serialization |
| MAT-GOV-02 | Scope, null, unknown, unresolved-relation, hard-gate, conflict, `unobtainable`, and precedence invariants |
| MAT-GOV-03 | Ruleset persistence, review/activation, rollback, and immutable decision-snapshot pinning |

MAT-GOV-01 contains no database migration, ruleset lifecycle, new material
rule, medium catalog, evidence migration, thermal model, or frontend
recommendation. `material_constraints_enabled` defaults to false. While false,
the historical Gegencheck code path and API payload remain unchanged and contain
no `material_constraints` key. Enabling the contract requires the separately
default-off compatibility matrix setting; an invalid flag combination is
rejected during settings validation.

## Ratified owner decisions

1. Every multiple-media input fails closed in MAT-GOV-01. An unresolved
   relationship remains `unresolved`; `resolved` is a reserved fachlicher state
   but does not itself prove an evaluable structured media list. Activation of
   multiple-media evaluation belongs to MED-NORM-01 and MAT-GOV-02.
2. Internally attested matrix cells may block, caution, or remain conditional,
   but cannot create a positive compatibility statement.
3. `matrix_compatible` cannot alone create `COVERED_RECOMMENDATION`.
4. Existing Produktspec rules remain default-off and are not migrated
   automatically.
5. Unreviewed LLM material tendencies cannot create a canonical or positive
   material statement.
6. Conflicts and hard gates always precede `unobtainable`.
7. Executable RWDR thermal calculation remains NO-GO until separately sourced,
   reviewed, tested, and owner-activated.

Items 1, 2, 3, and 6 require the MAT-GOV-02 implementation before activation.
Ruleset lifecycle and snapshot binding require MAT-GOV-03. Until both packages
are complete and independently gated, the new contract remains an audit-only,
default-off surface.
