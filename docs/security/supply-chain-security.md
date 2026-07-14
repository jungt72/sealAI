# Supply-chain security

Dependency and artifact evidence are release controls, not informational
reports. The authoritative policy is `security/supply-chain-policy.json`. The
exception registry is `security/supply-chain-exceptions.json`; the required
GitHub checks and the current external-enforcement receipt are recorded in
`.github/required-security-checks.json`.

## Enforced repository controls

- Backend runtime, CI, and security-control environments use complete,
  transitive, hash-locked Python requirement files. Policy binds every reviewed
  input and generated lock by SHA-256. Recursive includes are accepted only
  when the included input is itself in that inventory.
- `ops/update-python-locks.sh` downloads the official `uv 0.11.28` archive for
  the current supported OS/architecture, verifies its policy-pinned SHA-256,
  and runs only that isolated binary. It generates Python 3.12,
  `x86_64-manylinux_2_28`, wheels-only locks.
- Every tracked Node project must have package-lock v3, an exact manifest/lock
  root match, and a complete external-package inventory. External entries must
  resolve to an HTTPS `registry.npmjs.org` tarball and carry a valid SHA-512
  integrity value. Bundled and linked entries have separate structural checks;
  a missing source or integrity field is not silently accepted.
- All tracked Dockerfiles are inventoried. External base images require a
  SHA-256 digest. Network downloads require HTTPS plus an in-instruction
  SHA-256 verification. Debian/Ubuntu package installation requires a dated
  snapshot source; Alpine packages are version-pinned.
- Every tracked Compose manifest is classified as production, staging,
  development, or `blocked_external`. Production image references must be
  digest-pinned. `ops/check-env-drift.sh` materializes the production Compose
  graph and verifies both the exact repository set and immutable references.
  The retired business manifest is intentionally inert.
- The existing history/tree secret scanner remains a non-waivable required
  gate. Findings are redacted.

## Audit and build evidence

- `pip-audit` receives each exact transitive lock with `--no-deps`,
  `--disable-pip`, and `--strict`. The gate requires the report's normalized
  name/version inventory to equal the lock; truncated output fails.
- `npm audit` runs for all five Node projects after a lifecycle-script-free
  `npm ci --ignore-scripts`. High and critical advisories block. Separate,
  credential-free jobs perform the application lifecycle installs and execute
  the frontend lint/tests/build, dashboard verification, and Strapi build.
- Trivy uses the immutable `0.69.3` scanner pin and `security/trivy.yaml`.
  Image high/critical vulnerabilities and unknown/high/critical license
  findings block. Full license scanning and confidence level `0.9` are bound in
  policy and scan predicates. Repository JSON reports and SPDX SBOMs are kept
  as CI artifacts for 90 days.
- Backend-v2 and Keycloak workflows build unprivileged OCI archives from the
  exact checked-out commit and clean Git tree. Their scan predicate binds the
  artifact repository/digest/type, source commit/tree, scanner configuration,
  report hash, policy hash, and exception-registry hash. The OCI archive,
  predicate, report, and SBOM are retained together.

No current workflow publishes an image, creates a registry attestation, or
deploys production. Those actions are deliberately `BLOCKED_EXTERNAL` until an
independently enforced protected-main/ruleset and publisher approval boundary
can be proven. `.github/workflows/deploy.yml`, the frontend publisher, and the
Keycloak promotion preflight fail before any external mutation. Do not infer a
registry or production claim from a successful local/CI archive build.

## Local verification and updates

Run the deterministic repository contract and focused tests:

```bash
python3 -I ops/supply_chain_gate.py verify
python3 -m pytest \
  backend/tests/test_supply_chain_gate.py \
  backend/tests/test_image_attestation_payload.py \
  --noconftest -q
python3 ops/check-secret-hygiene.py --worktree
```

Regenerate all governed Python locks only through the verified generator:

```bash
ops/update-python-locks.sh
```

Review the input, complete transitive lock, and policy digest changes together.
Never hand-edit a generated Python lock. The update workflow also reruns the
repository gate.

## Exceptions and external governance

The exception schema is deliberately fail-closed. A request must bind an exact
control, scope, advisory, package, version, personal GitHub principal, review
URL, review commit, and canonical exception hash, and may last at most 30 days.
However, independent principal/approval verification is currently
`BLOCKED_EXTERNAL`; consequently any non-empty exception registry fails. There
is no active waiver path. Secrets, missing locks, dependency drift, base-image
digest violations, and missing evidence are non-waivable in every case.

`.github/CODEOWNERS` names the supply-chain control surfaces and
`.github/required-security-checks.json` enumerates every required matrix check.
Repository content cannot prove that GitHub actually enforces either control.
The canonical H6 receipt therefore contains `BLOCKED_EXTERNAL` and null
ruleset/reviewer/evidence fields. Closing H6 requires an independent reviewer to
configure or inspect the GitHub ruleset, require code-owner approval, verify the
exact check list and strict up-to-date semantics, and replace the negative
receipt with a separately reviewed evidence schema. A self-authored repository
claim is not sufficient.

## Inventory boundary

The governed deployable target is backend-v2 plus all five tracked Node
projects. The repository-root `requirements.txt` is a historical host snapshot;
`backend/requirements.txt` and `backend/requirements-dev.txt` belong to the
retired V1/development environment and are not installed by backend-v2 or its
CI. `seo/pyproject.toml` declares no dependencies. Re-activating any excluded
environment requires adding its generated lock and audit scope before use.

Container/registry evidence still requires the relevant external CI or runtime.
Local work must not claim those executions as complete. Publication and deploy
remain disabled until their independent controls exist.
