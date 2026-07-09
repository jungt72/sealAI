# sealingAI

sealingAI is a manufacturer-neutral pre-assessment workspace for industrial
sealing technology. It explains from reviewed evidence, calculates only through
the deterministic kernel, and keeps final engineering release outside the
system.

## Active Runtime

The active production path is V2:

```text
marketing web (Next.js)     /                    frontend/
workspace web (Vite)        /dashboard/         frontend-v2/
API (FastAPI)               /api/v2/             backend/sealai_v2/
deterministic kernel        domain boundary      backend/sealai_v2/core/calc/
Postgres                    system of record     sealai_v2.db/
Redis                       ephemeral hot state  database 1
Qdrant                      derived retrieval     reviewed Fachkarten index
Keycloak                    OIDC                 keycloak/
Nginx                       TLS and routing       nginx/
```

`backend/app/` and its former LangGraph runtime are retired history. LangGraph
is deliberately not part of the active request path: V2 is a typed,
observable pipeline with a deterministic calculation boundary. A durable
workflow engine becomes relevant only for future multi-day human approvals or
scheduled work, not for the synchronous advisory turn.

The binding architecture and migration plan are in
[`docs/architecture/2026-07-09-production-architecture.md`](docs/architecture/2026-07-09-production-architecture.md).
The product and safety invariants remain in [`AGENTS.md`](AGENTS.md) and
`docs/V2/`.

## Local Verification

Backend offline suite:

```bash
cd backend
python -m pytest sealai_v2/ -q
python -m pytest tests/architecture/test_v2_import_boundary.py --noconftest
```

Dashboard:

```bash
cd frontend-v2
npm ci
npm run verify
```

Marketing:

```bash
cd frontend
npm ci
npm run lint
npm run build
```

## Production Operations

Production application releases are artifact promotions through:

```bash
./ops/release-backend-v2.sh
./ops/release-frontend.sh
```

The backend release requires a clean checkout, an adjudicated eval replay for
the exact served tree and L1 model, health and kernel smokes, restart survival,
and a rollback rung. `ops/up-prod.sh` is host boot/recovery orchestration only;
it never builds or deploys application code.

Never commit `.env*`, credentials, tokens, or user data. Production image refs
must be immutable `tag@sha256:digest` references.
