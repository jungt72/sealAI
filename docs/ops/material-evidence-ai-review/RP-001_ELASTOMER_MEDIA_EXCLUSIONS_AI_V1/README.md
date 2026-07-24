# RP-001 AI cross-review package

Package: `RP-001_ELASTOMER_MEDIA_EXCLUSIONS_AI_V1`

```text
REVIEW_INCOMPLETE
NO CROSS-REVIEWED CLAIMS
MERGE_NO_GO
```

Status: deterministic `ai_draft`; both separately authorized Claude transports
ended `REVIEW_INCOMPLETE` before a result envelope. No challenge or adjudication
was persisted. The authorized retry is exhausted; a future attempt must be a
new identical review job with a new transport identity. It has no human review,
factual approval, MED-NORM catalog authority, active
pointer, sampling, public API/frontend surface, production migration or
deployment authority.

The subsequently authorized third formal job produced a valid redacted Claude
transport envelope for exact `claude-sonnet-5` with ten turns, zero web use and
zero permission denials. Its inner report contained no JSON object and was
rejected by the strict parser as `INVALID_REPORT_NO_VERDICT`. No challenge or
adjudication row was created. A fourth formal attempt is prohibited, so the
package remains `REVIEW_INCOMPLETE`, `NO CROSS-REVIEWED CLAIMS`, and
`MERGE_NO_GO`.

`generated/review-job-planned-after-transport-02.json` binds that next job to
the same immutable review snapshot and both unchanged audit-input hashes. It is
planning evidence only, carries `automatic_execution_authority=false`, and is
not a challenge, verdict, approval or permission to retry.

The completed transport diagnosis is registered in
`generated/transport-diagnostic-20260719.json`; the exact supported CLI option
inventory is `generated/claude-cli-options-2.1.205.json`. Raw canary stdout,
stderr and authentication material remain private outside the repository. No
email address, organization identifier, session identifier, UUID, token or
credential is persisted here.

## Selected evidence gaps

The package selects six explicit material/service pairs from the immutable
53-gap register. A gap is only a selection boundary; the two source documents,
their exact digests, locators and permitted short excerpts provide the claim
content.

| Rule | Material gap | Service gap | Effect |
|---|---|---|---|
| `MR-RP001-AI-ACM-GLYCOL-BRAKE-FLUID` | `material:acm` | `service:glycol-brake-fluid` | `unvertraeglich` |
| `MR-RP001-AI-ACM-STEAM-GT150C` | `material:acm` | `service:steam` | `unvertraeglich`, only above 150 °C |
| `MR-RP001-AI-NBR-GLYCOL-BRAKE-FLUID` | `material:nbr` | `service:glycol-brake-fluid` | `unvertraeglich` |
| `MR-RP001-AI-NBR-STEAM-GT150C` | `material:nbr` | `service:steam` | `unvertraeglich`, only above 150 °C |
| `MR-RP001-AI-VMQ-DIESEL-FUEL` | `material:vmq` | `service:fuels` | `unvertraeglich`, diesel only |
| `MR-RP001-AI-VMQ-STEAM-GT150C` | `material:vmq` | `service:steam` | `unvertraeglich`, only above 150 °C |

General EPDM and FKM statements are deliberately excluded: the registered
gaps require crosslink- or subtype-specific evidence that these sources do not
provide. No source text or existing matrix cell was imported automatically.

## Sources and rights boundary

The source PDFs are not committed. The builder requires their exact local
bytes and verifies:

- `Parker-ORD-5700.pdf` — SHA-256
  `9572aeef454600cb788d5385ae0666405012bd49a03aa14116b5ad56e839582c`;
- `Trelleborg-Chemical-Compatibility-Guide.pdf` — SHA-256
  `d29a89d3188e520d232235c1a3de5f783317f3a557d269669ff1be572d74a52b`.

Only the bounded, attributed excerpts in `creator-input.json` enter the frozen
Claude corpus. `rights_state=permitted` is limited to that short quotation for
source-critical technical review under UrhG section 51; it grants no right to
reproduce or redistribute either source document.

## Deterministic draft build

From the repository root:

```bash
PYTHONPATH=backend python -m sealai_v2.material_evidence_ai_review.rp001_pack \
  --creator-input docs/ops/material-evidence-ai-review/RP-001_ELASTOMER_MEDIA_EXCLUSIONS_AI_V1/creator-input.json \
  --creator-prompt docs/ops/material-evidence-ai-review/RP-001_ELASTOMER_MEDIA_EXCLUSIONS_AI_V1/creator-prompt.txt \
  --candidate-register docs/ops/material-evidence-curation/RP-001_ELASTOMER_MEDIA_EXCLUSIONS_V1/candidate-register.json \
  --source-directory /tmp/sealingai-rp001-sources \
  --output /tmp/sealingai-rp001-ai-pack-draft
```

The output directory must not exist. The builder validates the candidate
register digest and its complete 53-gap/zero-pair boundary, exact source-file
digests, two-source family coverage, typed media identities, atomic rules,
Evidence-v2 bindings, immutable snapshot IDs/hashes and the outbound corpus
safety receipt. It emits only `ai_draft` artifacts. Claude challenge,
adjudication and persistence are separate one-shot steps under
`docs/ops/material-evidence-ai-review.md`.

The complete one-shot executor is `ops/execute-rp001-ai-pack.py`. It reads the
isolated local database URL only from the named environment variable (default
`SEALAI_V2_RP001_DATABASE_URL`) so that the credential is never placed on the
command line or written to an artifact.
It refuses a non-local PostgreSQL host, a database outside the
`sealai_rp001_ai_pack_…` namespace, a non-empty database, repository-local
output, missing source bytes or an existing output directory. It then performs
the additive migration, exact snapshot persistence, one Claude challenge,
closed Codex adjudication and lifecycle replay. Any factual or scope finding is
quarantined; the executor never edits a claim automatically.

The future user notice remains:

> KI-gestützte, quellenbasierte Ausschlussprüfung – keine individuelle
> technische Freigabe.
