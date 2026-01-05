# SealAI Codebase Overview

This repo contains a Docker‑Compose based application stack with a FastAPI/LangGraph backend, Next.js frontend, Keycloak SSO, Strapi CMS, Qdrant vector DB, Redis, Postgres and Nginx as reverse proxy.

## Runtime Architecture (Docker)

- Compose entrypoint: `docker-compose.yml`.
- Public edge: `nginx` service publishes `80/443` and proxies to internal containers via Docker DNS (`resolver 127.0.0.11`) configured in `nginx/default.conf`.
- Data stores:
  - Postgres: `postgres` service (`postgres:15`), persistent volume `pgdata`.
  - Redis: `redis` service (`redis/redis-stack-server:7.4.0-v6`), passworded via `REDIS_PASSWORD` in `.env.dev` / `backend/.env.example`.
  - Qdrant: `qdrant` service (`qdrant/qdrant:v1.15.0`), storage in `qdrant_storage`.
  - Strapi uploads: `strapi_uploads` volume.
  - Odoo + separate Postgres (`odoo`, `odoo-db`).

## Request Flow

1. Client hits `https://sealai.net` → Nginx (`nginx/default.conf`).
2. Nginx routes:
   - Frontend (catch‑all + `/api/auth/*`) → `frontend:3000`.
   - Backend API `/api/v1/*` and LangGraph SSE v2 endpoint `/api/v1/langgraph/chat/v2` → `backend:8000`.
   - Strapi Admin `/admin/*` and Strapi APIs `/api`, `/graphql`, etc. → `strapi:1337`.
   - Odoo ERP paths `/erp`, `/web`, and other Odoo endpoints → `odoo:8069`.

## Backend (FastAPI + LangGraph)

- App entry: `backend/app/main.py` creates the FastAPI `app`, mounts routers under `/api/v1`, enables CORS/GZip, and configures health checks.
- Settings/env: `backend/app/core/config.py` defines required env vars such as:
  - DB: `postgres_*`, `database_url`, `POSTGRES_SYNC_URL`
  - Redis: `redis_url`, `REDIS_URL`, `REDIS_PASSWORD`
  - Qdrant: `qdrant_url`, `qdrant_collection`, `qdrant_api_key`
  - Auth: `nextauth_url`, `nextauth_secret`, `keycloak_issuer`, `keycloak_jwks_url`, `keycloak_client_id/secret`, `keycloak_expected_azp`
  - LLM: `openai_api_key`, `openai_model`, `llm_small`
- Auth/JWT verification:
  - HTTP/WS dependencies and JWKS caching live in `backend/app/api/v1/dependencies/auth.py` and `backend/app/services/auth/token.py`.
  - WebSockets accept JWTs via header or subprotocol (`extract_jwt_from_websocket`).
- LangGraph:
  - Main graph compilation: `backend/app/langgraph/compile.py` with state in `backend/app/langgraph/state.py`.
  - Node implementations under `backend/app/langgraph/nodes/`.
  - Streaming/WS orchestration in `backend/app/services/chat/ws_streaming.py`.
  - Existing internal audits: `backend/docs/audit_langgraph_stack.md`, `backend/docs/audit_langgraph_flow_rwd.md`.

## Frontend (Next.js + NextAuth)

- Next.js app under `frontend/src/app`.
- NextAuth Keycloak provider at `frontend/src/app/api/auth/[...nextauth]/route.ts`.
  - Uses env vars `NEXTAUTH_URL`, `KEYCLOAK_ISSUER`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET`.
  - Stores Keycloak tokens in JWT session callbacks.
- UI uses backend under `/api/v1` via Nginx proxy.

## Keycloak

- Built from `keycloak/Dockerfile`.
- Realm/config in `keycloak-realm-backup/` and `.env.keycloak`.
- Not publicly exposed; used internally by NextAuth and backend JWT validation.

