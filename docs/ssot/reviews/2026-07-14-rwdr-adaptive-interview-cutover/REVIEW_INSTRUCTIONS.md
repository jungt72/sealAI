# RWDR A/B Review

Review `worksheet.csv` before opening `blinding_key.json`.

The case context contains only documented CaseState fields. It does not name
the omitted field or the internal scenario group. Do not edit the case context,
questions, row order, case IDs, or `review_unit_hash`.

Complete all six rating columns for every row:

- `preferred_next_action`: `A`, `B`, or `tie`.
- `relevant_to_case`: which question is relevant: `A`, `B`, `both`, or `neither`.
- `critical_gate_skipped`: which question skips a critical gate: `A`, `B`,
  `both`, or `none`.
- `asks_documented_information`: which question asks for information already
  present in the CaseState: `A`, `B`, `both`, or `none`.
- `answerable_or_handles_unknown`: which question is answerable or correctly
  permits unknown/unobtainable: `A`, `B`, `both`, or `neither`.
- `rationale`: a concise human explanation. It must not be empty.

Boolean values such as `true` and `false` are invalid because the affected A/B
side would be lost during unblinding.

After completing the worksheet, fill `review_attestation.json` truthfully. The
adjudicator validates and aggregates the review but never authorizes cutover.
