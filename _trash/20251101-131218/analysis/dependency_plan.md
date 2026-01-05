# Dependency remediation plan

## Python (backend)
- FastAPI 0.119.1 → 0.120.0 (minor release). Requires Starlette 0.38+; verify current pin 0.48.0 compatible.
- Redis client 6.4.0 → 7.0.0 (major). Review breaking changes: `retry_on_timeout` default change, TLS handling.
- Uvicorn 0.37.0 → 0.38.0 (minor). Ensure CLI invocation in Dockerfile still valid.
- pytest 8.3.3 → 8.4.2 and align pytest-asyncio to 0.24.0 per release notes.
- Ruff 0.6.9 → 0.14.2; prefer using pyproject tool settings.
- Black 24.8.0 → 25.9.0; confirm python 3.12 support.
- Introduce isort 7.0 (if needed) but prefer Ruff format to avoid extra tool.
- Replace duplicated requirements files (`requirements-dev.txt` vs `requirements.dev.txt`).
- Drop unused packages flagged by deptry/vulture (langgraph duplicates once migration done, SSE-specific code removal etc.).
- Add `pip-audit` run in CI.

## Node/Frontend
- Align to Node 20.19.5 LTS; update `.nvmrc` once created.
- Next.js 15.x currently; plan upgrade to Next 16 after backend compatibility testing; keep React 19 accordingly.
- TypeScript 5.4.0 → 5.9.3; update `tsconfig.json` to JSON-compliant or rename to `.jsonc`.
- Add eslint 9.38 + prettier 3.6, configure consistent scripts.
- Remove unused deps per depcheck/knip (e.g., `@react-three/drei`, `react-icons`, `rehype-highlight`) once corresponding code removed.
- Introduce security scan via `npm audit --production` in CI.

## Docker/Compose
- Pin base images with explicit digests or tags.
- Add healthcheck for backend & frontend services.
- Remove unused services discovered during cleanup.
