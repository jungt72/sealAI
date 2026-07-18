# RP-001 source and rights checklist

Complete once per source. Any unchecked blocking item returns the claim to the
creator. The checklist records human work only; MAT-EVID-01C remains the
canonical technical and lifecycle contract.

## Source identity

- [ ] The exact source bytes were obtained independently of legacy matrix or
  LLM output.
- [ ] `document_id` identifies the document, not merely a website.
- [ ] `document_revision` is exact and non-empty.
- [ ] `publication_edition` is exact and non-empty.
- [ ] SHA-256 was calculated over the exact retained bytes.
- [ ] A second calculation produced the same lowercase digest.
- [ ] `source_ref` will be derived by canonical code from all four identity
  fields; it was not typed by hand.
- [ ] The reviewer can access the same exact revision without using a secret in
  this repository.

## Document metadata

- [ ] Title and publisher match the source.
- [ ] Document type uses the closed MAT-EVID-01C enum.
- [ ] Locator identifies an exact section/page/table, or has an explicit
  `unavailable` reason.
- [ ] Metadata is NFC and inside the documented character and byte limits.
- [ ] No field contains an entire document, standard, or long copyrighted
  passage.

## Rights

- [ ] Rights status is explicitly `permitted`, `licensed`, `public_domain`,
  `unknown`, or `restricted`.
- [ ] The rights basis is specific and verifiable.
- [ ] Approval is blocked if rights are `unknown` or `restricted`.
- [ ] If an excerpt is unnecessary, it is omitted.
- [ ] If an excerpt is included, the rights state permits it, its independent
  rights basis is recorded, and it is at most 280 Unicode characters and 1024
  UTF-8 bytes.
- [ ] Licensed source files remain in the authorized document system, not in
  Git, a claim field, logs, or review comments.

## Claim support

- [ ] The cited location supports the exact proposition, not a broader or
  narrower paraphrase.
- [ ] Applicability to the exact material, canonical medium, and condition is
  established by the source rather than assumed from family knowledge.
- [ ] The chosen `required_source_types` are documented; no default sufficiency
  policy was invented by the operator or agent.
- [ ] All contrary, superseding, or scope-limiting sources discovered during
  review are recorded.
- [ ] A material-family source is not presented as compound or component
  release evidence.

## Rights gate result

- [ ] `SOURCE_RIGHTS_READY_FOR_INDEPENDENT_REVIEW`
- [ ] `SOURCE_RIGHTS_BLOCKED`

Select exactly one. A blocked source cannot be hidden, omitted after use, or
overridden by a model-generated summary.
