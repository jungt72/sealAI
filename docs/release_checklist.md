# Release checklist (latest-pin strategy)

1) Regenerate backend lock: `ops/gen_backend_requirements_lock.sh`
2) Run tests in container: `docker run --rm -v "$PWD/backend:/app" -w /app sealai-backend:dev pytest -q -ra`
3) Run dependency audit: `ops/audit_deps_backend.sh`
4) Smoke checks:
   - `/healthz`
   - `/metrics`
   - `/api/v1/langgraph/chat/v2`
