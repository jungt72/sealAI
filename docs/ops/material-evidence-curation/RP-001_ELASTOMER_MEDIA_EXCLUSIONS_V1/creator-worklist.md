# RP-001 creator worklist

Required authenticated roles: `verified_human` and
`material_evidence:create`.

The creator researches and records candidate evidence. The creator cannot
perform the independent review or approval transition.

## A. Identity and scope

- [ ] Authenticate through the normal identity provider; confirm the tenant is
  supplied by `VerifiedIdentity`, not a header or form field.
- [ ] Confirm that reviewer and owner-approver are two other real people with
  different authenticated subjects.
- [ ] Select one material-axis subject and one service/media-axis subject from
  `candidate-register.json`.
- [ ] Explain only why the pair merits research; do not state a verdict before
  sources are examined.
- [ ] Establish the exact material/compound identity. If only a family is
  known, record the limitation and do not claim compound release.

## B. Canonical medium

- [ ] Look for an exact, currently approved MED-NORM catalog entry under the
  same tenant and domain pack.
- [ ] If no entry exists, stop the rule track and open a separate media-identity
  curation track.
- [ ] For that track, collect an atomic `other_technical` identity claim,
  exact canonical name, identity kind, aliases, and the derived identity
  assertion scope.
- [ ] Do not infer identity from `+`, `/`, commas, conjunctions, trade-name
  familiarity, or an LLM suggestion.
- [ ] Do not mix a MED-NORM `other_technical` identity claim into the
  MATERIAL-RULES claim set; its reviewed dossier and catalog entry are a
  separate prerequisite.

## C. Sources and claims

- [ ] Copy `claim-capture-form.md` once per proposed atomic claim.
- [ ] Acquire every exact source revision and complete
  `source-rights-checklist.md`.
- [ ] Compute SHA-256 from retained bytes; do not hash a URL, description, or
  downloaded HTML wrapper instead of the intended document.
- [ ] Formulate one atomic proposition within 512 characters / 1024 UTF-8
  bytes.
- [ ] Use exactly one material, one canonical media ID, and one condition for
  every RP-001 rule claim.
- [ ] Select only `incompatibility` for a proposed `unvertraeglich` primary
  claim or `conditional_compatibility` for opaque `bedingt`.
- [ ] Limit supporting claims to `temperature_limit`, `application_limit`, or
  `regulatory_constraint` and only when the source states the content.
- [ ] Keep `positive_statement_allowed` false.

## D. Technical preparation

- [ ] Request a reserved `rule_ref`, domain pack, tenant, and future ruleset
  family from the authorized operator. Do not invent identifiers.
- [ ] Ensure the proposed rule statement equals exactly one primary claim.
- [ ] Ensure every source supports at least one claim and every claim is bound
  to the intended rule.
- [ ] Ask the authorized tooling to derive `source_ref`, `claim_ref`, media ID,
  content hashes, and snapshot IDs. Do not calculate domain-separated IDs by
  hand.
- [ ] Sort all set-like arrays by UTF-8 bytes and remove duplicates before
  handoff.
- [ ] Submit the completed worksheets and source-access references to the
  independent reviewer.

## Creator stop conditions

Stop and mark the worksheet `RETURNED_BY_REVIEWER` or `REJECTED` when:

- the exact source revision cannot be acquired;
- rights are unknown or restricted;
- source and proposed scope differ;
- the medium has no independently reviewed canonical identity;
- a contradiction or supersession remains;
- the proposition needs more than one material, medium, or condition;
- only a positive compatibility statement could be supported;
- another person cannot independently reproduce the source and hash.

Creator completion marker:

```text
CREATOR_CURATION_COMPLETE_REVIEW_NOT_PERFORMED
```
