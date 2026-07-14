# sealingAI Production Readiness Runbook

Canonical production host:

```text
https://sealingai.com
```

Legacy hosts must redirect to the canonical host. Runtime, Auth.js, Keycloak issuer,
sitemaps, robots.txt, and smoke tests must not reintroduce `sealai.net` as the app
origin.

The explicit `www` policy is to retain `www.sealingai.com` only as an HTTPS 308
redirect to the canonical apex host. It is not an independent application origin.
The redirect may be activated only when its DNS record, trusted certificate chain,
exact SAN, and Nginx security headers all pass together.

## Daily checks

```bash
cd /home/thorsten/sealai
BASE_URL=https://sealingai.com ./ops/smoke-live-pilot-readiness.sh
./ops/check-domain-readiness.sh
./ops/check-registry-readiness.sh
```

## Full production gate

```bash
cd /home/thorsten/sealai
./ops/production-readiness-gate.sh
```

This gate is expected to fail while either of these external prerequisites is open:

- DNS: `www.sealingai.com` must resolve to `49.13.233.145`.
- Registry: backend image must be reachable from GHCR and pinned by digest.

## DNS prerequisite

Set one of these records at the DNS provider:

```text
CNAME  www  -> sealingai.com
```

or:

```text
A  www  -> 49.13.233.145
```

Then issue the production certificate:

```bash
cd /home/thorsten/sealai
./ops/issue-sealingai-cert.sh
./ops/check-domain-readiness.sh
```

Certificate issuance, DNS changes, and Nginx activation are production mutations.
The commands above are an execution sequence, not current authorization: record the
exact DNS/certificate/rollback plan and obtain `GATE-08` before running it. Until then,
use only the local contract tests. The readiness script validates both hostnames with
the system trust store (or an explicit safe `TLS_CA_FILE`), requires TLS 1.2 or newer,
checks the exact SAN, and rejects missing HSTS, CSP, XCTO, referrer, or permissions
policy. It has no certificate-verification bypass.

The monitoring rollout must preserve that policy as two independent, non-following probes:

- `https://sealingai.com/api/health` must return exactly 200 over a trusted apex TLS connection.
- `https://www.sealingai.com/api/health` must return exactly 308 over a trusted `www` TLS connection
  with `Location: https://sealingai.com/api/health`.

This separation is mandatory: probing `www` with a 2xx module creates a permanent false alarm, while
following its redirect can hide a broken `www` certificate, hostname, or redirect destination.
Production DNS, certificate issuance, Nginx activation, and monitoring deployment remain GATE-08
mutations; the repository contract alone is not runtime evidence.

```bash
python3 -m pytest \
  backend/tests/test_tls_verification_contract.py \
  backend/tests/test_remediation_control.py -q
```

## GHCR prerequisite

The GitHub token on the VPS needs package write permission:

```bash
gh auth refresh -h github.com -s write:packages
```

After granting the scope, promote the currently live local backend image:

```bash
cd /home/thorsten/sealai
./ops/promote-local-backend-image.sh
./ops/check-registry-readiness.sh
```

Successful promotion sets:

```text
BACKEND_IMAGE=<tag>@sha256:<digest>
BACKEND_PULL_POLICY=always
```
