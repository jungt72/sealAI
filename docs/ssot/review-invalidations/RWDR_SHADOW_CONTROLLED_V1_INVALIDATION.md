# RWDR Controlled Shadow Review v1 - Invalidated

Status: `invalidated_no_adjudication`
Review set: `rwdr-shadow-controlled-v1`
Source merge: `992d573868b5da49c301347c1ee2ee4715b7958d`
Invalidated: 2026-07-14

The v1 controlled worksheet must not be used as ground truth, activation
evidence, or a controller-quality result. No `adjudication.json` was accepted.

## Findings

1. The visible profile label disclosed the omitted application goal in all
   five `application_goal_missing` rows. For example, a context labelled as a
   new-design scenario simultaneously declared the application goal missing.
2. The application-goal question and its machine-readable enum covered new
   design, replacement, and failure analysis, while the corpus also contained
   retrofit and optimization cases.
3. The externally completed worksheet used Boolean values for side-specific
   metrics. The adjudication schema requires `A`, `B`, `both`, `neither`, or
   `none`, because a Boolean cannot identify which blinded question it rates.
4. No completed owner attestation was present. The strict adjudicator therefore
   could not and did not accept or unblind the submitted file.

## Corrective action

- Review set v2 removes `scenario_group`, profile labels, and explicit missing
  field labels from the blinded worksheet. Only documented CaseState fields are
  displayed.
- Pack `rwdr.v1@1.0.1` and question catalog `rwdr.questions.1.0.1` add retrofit
  and optimization to both canonical wording and answer schema.
- Every export includes `REVIEW_INSTRUCTIONS.md` with exact side-specific token
  semantics and an explicit warning that `true`/`false` are invalid.
- Regression tests enforce all three corrections before export.

The v1 corpus hash recorded by its manifest was
`0ed092cd8a46a5ebaa2f0612baf0fac020575829137379c4383298478ed504bb`.
Its history remains recoverable from the source merge above; it is superseded
by `rwdr-shadow-controlled-v2` and must not be revived.
