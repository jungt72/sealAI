| Service | Published ports | Zweck |
|---|---|---|
| backend | mode: ingress | API (FastAPI/Uvicorn) |
| frontend | mode: ingress | web UI (Next.js) |
| keycloak | mode: ingress | auth/SSO (Keycloak) |
| nginx | mode: ingress, mode: ingress | reverse proxy / TLS terminator |
| odoo | mode: ingress | ERP |
| qdrant | mode: ingress, mode: ingress | vector DB |
| redis | mode: ingress | cache / queue |
