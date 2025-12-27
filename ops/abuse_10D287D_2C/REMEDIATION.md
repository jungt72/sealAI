# Remediation – Abuse 10D287D_2C

## Ausgangslage

Hetzner meldete ausgehenden UDP‑Flood von `49.13.233.145` zu `103.227.209.22` (UDP, src‑port 3449). Phase 1 zeigte keinen Live‑Traffic, aber Docker kann Host‑Egress‑Policies via `FORWARD`/NAT umgehen.

## Änderungen (Phase 2)

### 1) Container‑Egress default‑deny über `DOCKER-USER`

- Neue idempotente Scripts:
  - `ops/abuse_10D287D_2C/firewall/docker_egress_harden_v4.sh`
  - `ops/abuse_10D287D_2C/firewall/docker_egress_harden_v6.sh`
- Regeln werden in `DOCKER-USER` eingefügt (vor Docker‑FORWARD), Reihenfolge:
  1. `ESTABLISHED,RELATED` → `RETURN`
  2. Allow DNS `53/udp+tcp` → `RETURN`
  3. Allow Web `80/tcp`, `443/tcp` → `RETURN`
  4. Allow NTP `123/udp` → `RETURN`
  5. Explizit block IPv4 UDP nach `103.227.209.22` → `DROP`
  6. Default‑deny für sonstigen Container‑Egress → `DROP`
- Persistenz via systemd:
  - Unit: `ops/abuse_10D287D_2C/firewall/docker-egress-harden.service`
  - Installiert nach `/etc/systemd/system/docker-egress-harden.service` und aktiviert.

**Verifikation:** `ops/abuse_10D287D_2C/audit_phase2/20_verify_iptables_DOCKER-USER_v4.log`, `21_verify_ip6tables_DOCKER-USER_v6.log`.

### 2) Öffentliche Ports reduziert

- `docker-compose.yml` Host‑Publishes auf localhost beschränkt:
  - `backend` `8000/tcp` → `127.0.0.1:8000:8000`
  - `frontend` `3000/tcp` → `127.0.0.1:3000:3000`
  - `qdrant` `6333-6334/tcp` → `127.0.0.1:*`
  - `odoo` `8069/tcp` → `127.0.0.1:8069:8069`
  - `keycloak` Port‑Publishing entfernt (`ports: []`); Zugriff nur intern über Docker‑Netz.
  - Public Access läuft ausschließlich über `nginx` auf `80/443` (siehe `nginx/default.conf`).
- UFW Inbound Admin‑Ports geschlossen:
  - `8443/tcp`, `4443/tcp`, `9090/tcp` auf IPv4+IPv6 `DENY IN`.

**Verifikation:** `ops/abuse_10D287D_2C/audit_phase2/22_verify_ufw_verbose.log`, `23_verify_ss_tulpn.log`.

## Rollback

1. Docker‑Egress:
   - `systemctl disable --now docker-egress-harden.service`
   - `iptables -F DOCKER-USER; ip6tables -F DOCKER-USER`
2. Compose‑Ports:
   - Revert `docker-compose.yml` Änderungen und `docker compose up -d`
3. UFW:
   - `ufw delete deny in 8443/tcp` (analog 4443/9090) falls wieder nötig.

## Reproduzierbare Anwendung

```bash
sudo bash ops/abuse_10D287D_2C/firewall/docker_egress_harden_v4.sh
sudo bash ops/abuse_10D287D_2C/firewall/docker_egress_harden_v6.sh
sudo cp ops/abuse_10D287D_2C/firewall/docker-egress-harden.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now docker-egress-harden.service
docker compose up -d
```

