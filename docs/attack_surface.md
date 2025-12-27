# Attack Surface & Hardening Notes

## Publicly reachable ports (after Phase 2)

| Port | Service | Exposure | Notes |
|---|---|---|---|
| 22/tcp | `sshd` | public | Consider disabling password auth; see Phase‑2 recommendations. |
| 80/tcp | `nginx` | public | Redirects to HTTPS, ACME challenge. |
| 443/tcp | `nginx` | public | Main app entry, proxies to internal services. |
| 8443/4443/9090 | none | **blocked** | Denied via UFW (IPv4+IPv6). 9090 is Cockpit TLS on host. |

Internal/localhost‑only publishes (not public):

- `backend` `127.0.0.1:8000`
- `frontend` `127.0.0.1:3000`
- `qdrant` `127.0.0.1:6333-6334`
- `odoo` `127.0.0.1:8069`
- `redis` already `127.0.0.1:6379`
- `keycloak`, `postgres`, `strapi`, `odoo-db` are internal only.

## Outbound policy

Host outbound is default‑deny via UFW (`ops/abuse_10D287D_2C/audit_phase2/06_ufw_status.log`).  
Container outbound is default‑deny via `DOCKER-USER` (`ops/abuse_10D287D_2C/firewall/docker_egress_harden_v4.sh`, `docker_egress_harden_v6.sh`).

Allowed outbound (host + containers):

- DNS: `53/udp`, `53/tcp`
- Web: `80/tcp`, `443/tcp`
- NTP: `123/udp`

## Admin UIs / Sensitive endpoints

- Strapi Admin is reachable under `/admin` on 443 and should be protected by strong admin credentials and optional IP allowlisting.
- Odoo ERP is exposed via Nginx routes; ensure admin accounts are MFA‑protected.
- Keycloak is internal; if later exposed, only via Nginx/443 and with IP allowlisting.

## Secrets & Config

- `.env.dev`, `backend/.env.example`, `.env.keycloak` hold credentials/secrets; ensure production secrets are rotated after any compromise suspicion.
- Key runtime secrets:
  - `OPENAI_API_KEY` (backend LLM access)
  - `NEXTAUTH_SECRET`, `KEYCLOAK_CLIENT_SECRET`
  - `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `QDRANT_API_KEY`

## Firewall Recommendations

- Keep `DOCKER-USER` default‑deny in place to prevent UDP amplification abuse.
- Periodically audit published ports from `docker compose config` and `ss -tulpn`.
- Consider disabling Cockpit if unused: `systemctl disable --now cockpit.socket`.

