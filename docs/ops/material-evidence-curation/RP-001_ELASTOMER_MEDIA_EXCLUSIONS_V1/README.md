# RP-001 human evidence curation package

Package ID: `RP-001_ELASTOMER_MEDIA_EXCLUSIONS_V1`

Status: `HUMAN_CURATION_ONLY`

Authority: `NONE`

This package prepares human work for a first evidence-bound, disqualify-only
material rule pack. It contains no claim, material fact, media classification,
rule, approval, activation, or recommendation. Nothing in this directory is a
MAT-EVID manifest, MAT-EVID review dossier, MED-NORM catalog snapshot, or
MAT-GOV ruleset snapshot.

## Non-negotiable boundary

- Do not import legacy matrix cells, legacy `Quelle` values, RAG text, model
  output, or undocumented expert memory.
- Do not infer a canonical medium from punctuation, a trade name, an LLM, or
  an unreviewed free-text label.
- Do not treat a URL as a source identity. Document ID, revision, publication
  edition, and SHA-256 content digest are all required.
- Do not create a positive compatibility statement. RP-001 permits only a
  human-proposed `unvertraeglich` or opaque `bedingt` candidate for later
  validation.
- Do not let one person act as creator, reviewer, and owner-approver. The three
  authenticated subjects must be pairwise different.
- Do not place tokens, session IDs, credentials, licensed full texts, customer
  data, or application prompts in this package.
- Do not run a production migration, activate a pointer, raise sampling above
  zero, deploy, or publish a result.

## What the package contains

| Artifact | Human use |
|---|---|
| `package-manifest.json` | Frozen package identity, source contracts, and non-authority declaration. |
| `candidate-register.json` | All 53 canonical gaps separated into material and service/media triage axes; it proposes no pairing. |
| `claim-capture-form.md` | Copy once per atomic claim and complete by hand. |
| `source-rights-checklist.md` | Source identity, access, licensing, excerpt, and rights gate. |
| `creator-worklist.md` | Tasks reserved for the verified-human creator. |
| `reviewer-worklist.md` | Independent factual and scope review. |
| `owner-approver-worklist.md` | Final factual approval checks by a third subject. |
| `import-validation-runbook.md` | Fail-closed conversion into the existing contracts after separate execution authorization. |
| `acceptance-criteria.md` | Exact acceptance and rejection criteria for the first rule pack. |

## How three people use it

1. The creator copies `claim-capture-form.md` for every proposed atomic claim,
   records sources, and prepares a candidate pairing from the two axes in
   `candidate-register.json`. The creator does not review or approve it.
2. The reviewer obtains the source independently, repeats identity, rights,
   text, scope, and conflict checks, and either returns the form with findings
   or records a review decision through the authenticated MAT-EVID-01C path.
3. The owner-approver repeats the approval gates and may approve only through
   an authenticated, append-only MAT-EVID-01C transition. They do not edit the
   creator's evidence snapshot.

The operator may follow `import-validation-runbook.md` only after all human
fields are complete and a separate owner authorization permits the relevant
non-production import. Approval is factual-evidence approval only; it is not
deployment or material-release authority.

## Current hard stop

`candidate-register.json` intentionally contains no proposed material/media
pair. A verified-human creator must select and justify each pair from the
canonical gaps. If the selected medium has no current, approved MED-NORM entry,
media-identity curation and independent review must complete first. Until then,
the rule candidate is not import-eligible.

Owner decision `RP001-OD-01` closes the additional scope-policy question: a
media-identity claim must never receive a material placeholder. It requires a
new typed Evidence scope `media_identity` with no `materials` field and exactly
one `media_ref`. MAT-EVID-01A.v1 remains immutable and cannot represent that
scope. The three humans may curate the source and identity record now, but the
validated Evidence Manifest v2 contract is now available end to end. The
identity claim nevertheless remains non-importable until real verified-human
creation, review, and owner approval satisfy every package criterion.
