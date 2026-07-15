# Secret and Env Hygiene

sealingAI injects credentials at runtime. A credential value never belongs in
Git, an image layer, a diagnostic capture, a ticket, a PR, an audit report, or
an agent transcript. The safe schema-only example is
[`examples/runtime-secret-injection.example.yaml`](examples/runtime-secret-injection.example.yaml).

## Required gate

`ops/check-secret-hygiene.py` uses only the Python standard library. It detects
secret-bearing filenames and content classes including private PEM material,
private JWK fields, JWTs, Bearer headers, provider/API tokens, sensitive
assignments, credentialed connection strings, env files, and database/cache
dumps.

Contiguous ASCII secret signatures are scanned directly in raw bytes before
and independently of text decoding. This covers private-key markers, JWTs,
Bearer and provider tokens, credentialed connection strings, sensitive
assignments and JSON fields, and database-dump magic even when invalid bytes
surround otherwise intact signatures. Recognizable sensitive markers with a
damaged value produce a redacted `content.unscannable-sensitive-data` finding.

Structured text scanning additionally uses strict UTF-8/UTF-8-BOM decoding plus
BOM-bound or structure-confirmed UTF-16LE/BE decoding. Clearly text-like
ambiguous NUL-wide content receives a bounded byte-normalized view. Genuine
binary files without a supported secret signature remain clean rather than
being rejected solely for being binary. Assignment and JSON keys share one
plural-aware classifier with narrow exclusions for technical token counters.
Encrypted or compressed secrets cannot be detected without decryption or
unpacking and remain outside this repository scanner's contract.

The scanner has two output invariants:

1. It reports only a rule ID, file path, optional line number, and scan source.
2. Every detected value is rendered as `[REDACTED]`; subprocess output that
   could contain file content is suppressed on errors.

Exit codes are fail-closed: `0` means clean, `1` means a finding, and `2` means
the requested scope could not be scanned completely.

```bash
# Tracked plus non-ignored candidate files; ignored runtime files are not opened.
python3 ops/check-secret-hygiene.py --worktree

# Exact staged blobs, suitable for pre-commit.
python3 ops/check-secret-hygiene.py --staged

# An immutable tree and all commit trees introduced by a change.
python3 ops/check-secret-hygiene.py --tree HEAD
python3 ops/check-secret-hygiene.py --range <base-sha>..<head-sha>
```

CI runs the immutable-tree and introduced-commit scans with full Git history.
`ops/resolve-secret-scan-range.py` is the shared fail-closed range resolver for
CI and pre-push: fast-forwards use the exact remote range, new or force-rebased
feature branches use the authoritative default-branch merge base, and a
non-fast-forward default-branch push is rejected.
It does not exempt Markdown, examples, diagnostics, or generated-looking files.
Placeholder examples are allowed by value, not by a broad path exclusion.

## Local hooks

The versioned `.githooks/pre-commit` scans the index. The pre-push hook scans
each pushed tip and every commit tree introduced relative to the remote base;
an unavailable base or merge-base blocks the push.

Before enabling the hooks, check whether the clone already has an intentional
hooks path. Do not overwrite an existing integration without owner approval.

```bash
git config --local --get core.hooksPath
git config --local core.hooksPath .githooks
```

Hook activation is a per-clone operator action. CI remains the authoritative
repository gate even when a developer has not enabled local hooks.

## Repository policy

- Real `.env*`, overrides, rollbacks, auth captures, private keys, ACME account
  material, and database/cache payloads stay untracked.
- Example files contain only approved placeholders such as
  `SET_IN_SECRET_STORE` or `INJECT_AT_RUNTIME`; they are still content-scanned.
- Public certificates may be tracked. Their private keys may not.
- Keycloak exports are allowed only when every credential field is a
  placeholder and the scanner passes.
- Do not add broad scanner exclusions to make a finding green. A false positive
  needs a synthetic reproduction and a narrowly reviewed detector correction.
- A finding is evidence of possible exposure, not permission to inspect or
  print the value.

## Incident path

1. Stop promotion of the affected tree.
2. Record credential class, owning system, exposure location, and status only.
3. Follow [`credential-rotation-runbook.md`](credential-rotation-runbook.md).
4. Correct host permissions with
   [`credential-permissions-runbook.md`](credential-permissions-runbook.md).
5. After rotation/revocation, obtain explicit approval for
   [`git-history-remediation-runbook.md`](git-history-remediation-runbook.md).
6. Re-run tree, range, and CI gates. Never restore removed credential material
   as part of a rollback.
