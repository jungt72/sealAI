# RWDR Shadow Review Protocol

Status: `implemented_default_off`
Pack: `rwdr.v1@1.0.0`
Updated: 2026-07-14

This protocol governs evidence collection before any visible RWDR chat
cutover. It does not authorize deployment, technical suitability, or product
activation.

## Runtime posture

The controlled shadow posture is:

```text
SEALAI_V2_ADAPTIVE_INTERVIEW_PACK_RWDR_ENABLED=true
SEALAI_V2_ADAPTIVE_INTERVIEW_SHADOW_ENABLED=true
SEALAI_V2_ADAPTIVE_INTERVIEW_SHADOW_REPORTING_ENABLED=true
SEALAI_V2_ADAPTIVE_INTERVIEW_ENABLED=false
```

Migration `20260713_0009` must be applied before those flags are enabled. The
backend must be recreated through the sanctioned release process; a restart
does not apply compose allow-list changes.

## Aggregate review surface

An authenticated tenant admin may read:

```text
GET /api/v2/admin/adaptive-interview/shadow-summary
```

Optional UTC `since` and `until` parameters bound the sample. The response is
version-homogeneous for the current pack and policy. It exposes aggregate
counts only. HMAC case references, fingerprints, turns, documents, question
wording, and individual decisions are never returned.

`observations_total` may exceed `observations_analyzed` when the requested limit
is reached. A truncated result is not valid as a complete review population.
The aggregate keeps only the newest observation for each case revision;
`duplicate_observations_discarded` makes replay deduplication explicit.
`reviewable_divergences` applies the definition below directly and is a sample
counter, never an activation decision.

## Evidence threshold

Before preparing a chat cutover, collect at least 30 reviewable divergence
cases across representative RWDR scenarios. Reviewable divergence means one
of:

- `different_need`
- `legacy_question_only`
- `controller_question_only`
- `controller_escalates`

`legacy_unstructured` measures mapping coverage and does not count as a
blinded A/B comparison until the legacy question can be mapped without
guessing. Repeated observations of the same case revision must not be treated
as independent engineering cases.

## Human adjudication

The aggregate endpoint deliberately cannot decide which question is better.
For the 30-case review set, the owner prepares an A/B worksheet from
owner-controlled test cases, randomizes which wording is A or B, and records:

- preferred next action: A, B, or tie;
- relevance to the documented CaseState;
- whether a critical conflict or scope gate was skipped;
- whether the question asks for already documented information;
- whether the question is answerable, or correctly allows unknown/unobtainable;
- concise human rationale.

Production shadow telemetry is not expanded with raw case context merely to
make this review convenient. The worksheet uses controlled test cases or a
separately approved data-handling process.

## Controlled review workflow

The repository provides a cost-free controlled review path for the first
human comparison. It executes the production `rwdr.v1` policy against 30
versioned CaseState variants, compares the resulting question with a mapped
legacy question, and makes no LLM, retrieval, network, or production-database
call:

```text
PYTHONPATH=backend python -m sealai_v2.eval.interview_shadow_review export \
  --output-dir .runtime/rwdr-shadow-review/v1
```

The export contains:

- `worksheet.csv`: balanced, source-blinded A/B questions with empty human
  rating fields;
- `blinding_key.json`: source mapping, need IDs, divergence type, and rule
  references; the reviewer must not open it before completing the worksheet;
- `review_attestation.json`: reviewer identity, timestamp, and blinded-review
  attestation template;
- `manifest.json`: corpus, pack, worksheet, key, and attestation hashes plus the
  explicit zero-call and no-auto-activation posture.

The reviewer completes every worksheet row using only the allowed values:

```text
preferred_next_action: A | B | tie
relevant_to_case: A | B | both | neither
critical_gate_skipped: A | B | both | none
asks_documented_information: A | B | both | none
answerable_or_handles_unknown: A | B | both | neither
rationale: non-empty human explanation
```

After the worksheet and attestation are complete, the result can be validated
and unblinded without an LLM call:

```text
PYTHONPATH=backend python -m sealai_v2.eval.interview_shadow_review adjudicate \
  --review-dir .runtime/rwdr-shadow-review/v1
```

The command rejects changed case context, questions, row IDs, source mapping,
corpus, or domain pack. Its `adjudication.json` reports human preference and
quality counts, but always carries `automatic_activation_authorized=false`.
It does not issue a PASS/FAIL verdict and cannot replace the owner's cutover
decision.

Controlled cases are review evidence for question-selection quality, not
production incidence evidence. Before a visible cutover, the release owner
must explicitly record whether the controlled sample is sufficient or whether
a separately approved production-derived review population is also required.

## Cutover gate

No code or metric self-authorizes activation. A later chat-cutover change
requires all of:

- owner-signed blinded review worksheet;
- at least 30 reviewable divergence cases;
- zero observed skipped scope or critical-conflict gates;
- `additional_llm_calls_by_controller = 0`;
- complete, non-truncated report for the approved review window;
- green property, contract, migration, tenant-isolation, and golden tests;
- explicit owner decision recorded in the current SSoT decision register.

Until then, `FIELD_PRIORITY`, visible chat behavior, and legacy
`missing_information` remain authoritative.
