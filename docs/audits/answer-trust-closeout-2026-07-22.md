# sealingAI answer-trust closeout — 2026-07-22

## Decision

The routing, intent, case-context, evidence-bound answer, calculation and solution-development
changes are implemented and verified. The exact executable source used by the final replays was
captured from temporary Git tree
`0d02d277ad695a7a4ab11862a1d0a102671573ac` before these audit-document updates.

The engineering result is a **reviewable release candidate**. It is not production-approved:
factual correctness and the human-final hard gates still require owner adjudication, the prior
GATE-12 approval is expired and bound to older SHAs, and the production Qdrant retrieval path was
not exercised by this isolated replay.

## Measured improvement

The original full answer replay reported 0.685 credibility and 0.300 solution development. The
final exact-source replay reports:

| Measure | Original | Final |
|---|---:|---:|
| Credibility, rubric axes 2–7 | 0.685 | **0.861** |
| Solution development | 0.300 | **1.000** |
| Consulting UX | 0.583 | **1.000** |
| Provisional hard-gate quota | 0.700 | **1.000** |
| Primary answer status | 8 pass / 8 partial / 9 fail | **15 pass / 9 partial / 1 fail** |
| Memory fabrication | 1.000 | **1.000** |
| Case carry / no re-ask | 1.000 / 1.000 | **1.000 / 1.000** |
| Parametric computation | incomplete | **1.000** |
| Deterministic computation | incomplete | **1.000** |
| Injection / exfiltration | 1.000 / 1.000 | **1.000 / 1.000** |

`LIMIT-02`, including the German verb-final form “welchen Elektromotor ich … nehmen soll”, now
passes the domain-boundary rubric and never invokes helper, standard or frontier generation.

The remaining automated primary fail is `UNCERT-01`: the judge expected an explicit uncertainty
range plus a verification hint, while the answer selected the reviewed steam-policy boundary. It
is a rubric-depth finding, not a hard-gate breach. The independent judge is non-deterministic:
unchanged outputs received different partial/pass scores across control runs. Its score is an
evaluation signal, not a factual oracle and not a substitute for the human worksheet.

## Routing real-world result

The final routing suite contains 127 cases and 197 live attempts, including 35 repeated cases,
multi-turn carry, ambiguous language, German anaphora, domain boundaries, mixed requests and
prompt-injection attempts.

| Gate | Result |
|---|---:|
| Route case accuracy | **1.000** |
| Deterministic preflight, 114 cases | **1.000** |
| Stability | **1.000** |
| Critical safety | **1.000** |
| Communication contract | **1.000** |
| Pipeline errors | **0** |
| Failed case IDs | **none** |
| Latency p50 / p95 / max | **1.039 s / 24.125 s / 42.068 s** |

The routing gate is **GO**. This is not a latency or production-release approval.

## Implemented trust spine

- High-precision deterministic routing handles technical signals, case intake, calculation,
  diagnosis, comparison, RFQ, off-domain requests and controlled social navigation.
- Semantic routing may resolve residual language but cannot override deterministic safety or
  domain boundaries.
- Motor and drive sizing is explicitly outside sealing competence. Mixed drive-and-seal turns are
  decomposed: the drive part is refused while the sealing part advances with one governed question.
- Same-gender German anaphora between drive and sealing objects is never guessed. It receives one
  deterministic reference clarification and makes zero model calls.
- Short material-family definitions are recognized only by an exact reviewed alias in a complete,
  narrow utterance. Manufacturer identifiers, grades, numbers and extra case context fail closed to
  engineering instead of exploiting prefix matching.
- Case state, typed conversation carry and the communication plan govern answer-first behavior,
  depth, one discriminating question and no re-asking of known facts.
- Retrieval queries include the current user goal and typed case context instead of relying on the
  last sentence alone.
- Reviewed policy facts preempt free expansion for sharp material traps and compliance boundaries.
- Structured answers receive one bounded repair. If claims still exceed evidence, the response
  fails closed to exact reviewed evidence.
- Mandatory calculations are rendered from deterministic kernels; missing inputs fail closed and
  computed values cannot be silently replaced by model arithmetic.
- Solution turns must acknowledge known facts, expose assumptions, develop a candidate space,
  perform counterchecks and end with one highest-value next step.

## Verification

- Full `backend/sealai_v2` suite: pass, with expected skips and two dependency deprecation warnings.
- Full `backend/tests/architecture --noconftest`: pass.
- Ruff format and check across backend and architecture tests: pass.
- No-v1-import / no-LangGraph guard: pass.
- `git diff --check`: pass.
- Claude Code hostile review: repeated BLOCK findings were reproduced and converted into
  principle-level regressions; the final architecture received **APPROVE**.
- Answer artifact: `/tmp/sealai-answer-full-final-0d02d277-local/`.
- Human worksheet:
  `/tmp/sealai-answer-full-final-0d02d277-local/human_review_worksheet.md`.
- Routing artifact: `/tmp/sealai-routing-final-0d02d277-local/`.

## Source identity

| Source | SHA-256 |
|---|---|
| Pipeline | `fb99bbede567fcf33c2ef50c84e3b12d760e235f5e4dc0652e887fe4fc68aa40` |
| Routing | `2da1aaba589e30197ecd7fbfec5b4f4c14198332aa5804babb2e4024ad9334a2` |
| Semantic router | `60e96430ad94a43749c3d42a9e73b199194d55dbd9b6dffd2f9db2caf3905377` |
| Communication plan | `a867b7fc0b411999d6f103de493545a6d5409194cd1a8af2073ab76e79e71983` |
| Routing runner | `8d8c86aae8252845105eae335e50a2763e78876b0362e90f728bbd05438b6277` |
| Routing suite | `c10d6b516bd699d86fe7bc0196caa97610ba09f30152d245d95ef823b483769f` |

The replay used `retriever_backend=in_process` in an isolated staging-container overlay. The
routing artifact records the container base Git identity separately because the evaluated tree was
mounted without its `.git` directory; the executable critical sources are bound by the checksums
above. The replay did not write production tenant data and does not constitute a production Qdrant
recall or isolation test.

## Remaining release authority

Before production promotion, the owner must:

1. adjudicate factual correctness, walked-into-trap, invented-precision and confident-wrong fields
   in the exact human worksheet;
2. run a production-like Qdrant retrieval evaluation with recall/facet coverage and tenant isolation;
3. accept or close the observed long-tail generation/repair latency (routing p95 24.125 s and max
   42.068 s; separate answer paths exceeded 100 s);
4. issue a fresh approval bound to the final committed source/tree and reviewed diff.

Until those actions are complete, the correct status is **release candidate, not
production-approved and not production-deployed**.
