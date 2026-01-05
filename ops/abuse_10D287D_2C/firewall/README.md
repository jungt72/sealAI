## Docker Egress Hardening

### Problem

UFW `DEFAULT deny (outgoing)` and `ufw-user-output` rules apply to the host `OUTPUT` chain. Docker publishes container traffic via NAT and the `FORWARD` chain. As seen in Phase 1/2 (`ops/abuse_10D287D_2C/audit/03_iptables_rules.log`, `ops/abuse_10D287D_2C/audit_phase2/01_iptables_S.log`), Docker inserts `DOCKER-FORWARD` rules that accept bridge egress, so container outbound can bypass UFW host egress policy.

### Fix

Docker evaluates the `DOCKER-USER` chain before its own rules. We enforce a **default-deny** policy for containers there.

- `docker_egress_harden_v4.sh` adds IPv4 rules.
- `docker_egress_harden_v6.sh` adds IPv6 rules (safe even if Docker IPv6 is off).

Allowed container outbound:

- DNS: `53/udp`, `53/tcp`
- Web: `80/tcp`, `443/tcp`
- NTP: `123/udp`

Everything else is dropped. Additionally, IPv4 explicitly drops UDP to `103.227.209.22`.

### Install / Rollback

Install by applying the scripts once and enabling systemd persistence:

```bash
sudo bash ops/abuse_10D287D_2C/firewall/docker_egress_harden_v4.sh
sudo bash ops/abuse_10D287D_2C/firewall/docker_egress_harden_v6.sh
sudo cp ops/abuse_10D287D_2C/firewall/docker-egress-harden.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now docker-egress-harden.service
```

Rollback:

- Disable unit: `systemctl disable --now docker-egress-harden.service`
- Flush chain: `iptables -F DOCKER-USER; ip6tables -F DOCKER-USER`
- Remove unit file if desired.

