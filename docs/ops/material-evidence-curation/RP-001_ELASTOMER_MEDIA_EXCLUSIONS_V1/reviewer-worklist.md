# RP-001 independent reviewer worklist

Required authenticated roles: `verified_human` and
`material_evidence:review`.

The reviewer must be a different authenticated subject from the creator. The
reviewer does not repair the creator's immutable snapshot. A factual or scope
error is returned for a new creator snapshot.

## A. Independence

- [ ] Confirm through repository metadata that reviewer subject differs from
  creator subject.
- [ ] Obtain each source independently from the recorded authorized location.
- [ ] Recompute every source digest from exact bytes.
- [ ] Confirm no source is a legacy matrix cell, model output, unreviewed RAG
  passage, URL-only identity, or undocumented recollection.

## B. Source and rights review

- [ ] Repeat every item in `source-rights-checklist.md`.
- [ ] Verify title, publisher, document type, revision, edition, locator,
  rights state, and rights basis against the source.
- [ ] Confirm excerpts are unnecessary or rights-permitted and within 280
  characters / 1024 bytes.
- [ ] Confirm every free metadata field and claim text is within the
  MAT-EVID-01C character and UTF-8 byte ceilings.
- [ ] Confirm the declared required source types are present for each claim.

## C. Factual and scope review

- [ ] Compare the complete claim text to the cited source location.
- [ ] Verify exact applicability to the stated material, canonical media ID,
  and condition.
- [ ] Verify the proposition is atomic and does not silently combine
  alternatives, mixtures, sequential exposure, or multiple conditions.
- [ ] Verify a family-level source is not used as compound/component release.
- [ ] Verify the proposed rule statement is byte-identical to exactly one
  primary claim after canonical NFC handling.
- [ ] Verify primary type mapping:
  `unvertraeglich -> incompatibility` or
  `bedingt -> conditional_compatibility`.
- [ ] Verify supporting claim types are limited to temperature, application,
  or regulatory constraints.
- [ ] Search for contrary or superseding evidence and record every result.
- [ ] Confirm final `claim_relations` is empty; otherwise reject the snapshot
  and require correction rather than waiving the conflict.

## D. MED-NORM review

- [ ] Confirm the media ID is present in an exact, tenant-bound, currently
  approved MED-NORM snapshot.
- [ ] Verify its identity claim is `other_technical`, scoped exactly to that
  media ID and the full identity assertion reference.
- [ ] Verify canonical name, identity kind, and every alias are covered by the
  reviewed identity assertion.
- [ ] Confirm no heuristic or LLM classification created the identity.

## E. Review event

- [ ] Confirm the complete MAT-EVID-01C dossier covers every and only every
  MAT-EVID-01A source and claim.
- [ ] Confirm exact evidence snapshot ID, content hash, schema version, and
  contract version.
- [ ] Authenticate and call only the append-only review or rejection path.
- [ ] Never use the creator's account and never record an approval event.

Select exactly one repository action:

```text
REVIEWED_BY_INDEPENDENT_VERIFIED_HUMAN
REJECTED_BY_INDEPENDENT_VERIFIED_HUMAN
```

Review means the evidence dossier passed factual review. It grants no runtime,
deployment, public, recommendation, or material-release authority.
