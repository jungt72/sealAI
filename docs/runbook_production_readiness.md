# sealingAI Production Readiness Runbook

Canonical production host:

```text
https://sealingai.com
```

Legacy hosts must redirect to the canonical host. Runtime, Auth.js, Keycloak issuer,
sitemaps, robots.txt, and smoke tests must not reintroduce `sealai.net` as the app
origin.

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
