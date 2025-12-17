# Docker Firewall Hardening

## Why OUTPUT DROP blocks Docker bridge traffic
UFW defaults to `deny (outgoing)`, so the host’s `OUTPUT` chain drops every packet except the ones explicitly allowed (currently `lo` and a handful of remote addresses). Docker creates bridge networks (e.g. `172.18.0.0/16`, `172.19.0.0/16`, `172.20.0.0/16`) and advertises container services there, yet packets from host processes toward those bridge IPs hit the default `DROP` before they ever reach the bridge. Container-internal tools like `wget` succeed because they operate inside the bridge, but host requests stall because `OUTPUT` never permits the bridge subnet.

## How the helper adjusts iptables
The helper now:
1. Detects every Docker bridge interface (`br-*` plus `docker0`) and derives the actual IPv4 network (`172.18.0.0/16` instead of the interface IP, e.g. `172.18.0.1/16`).
2. Ensures `DOCKER-USER` continues to `RETURN` traffic for each subnet (`-s` and `-d`), letting Docker’s own rules take over while the chain stays default-deny.
3. Inserts `OUTPUT -d <bridge-subnet> -j ACCEPT` at the top of the host’s `OUTPUT` chain so host processes can reach containers regardless of the broader `DROP`.
4. Removes the redundant TCP port and `lo` accept rules that previously lived in `DOCKER-USER`, keeping the chain predictable and focused on subnet permissions.
5. Reports every planned `iptables` command when invoked with `--dry-run`, and skips execution in that mode.

All commands are logged as `[docker-firewall] …`, and the helper exits if any required binary (`ip`, `iptables`, or `python3`) is missing.

## Rules that stay and what is added
- `DOCKER-USER -s <bridge-cidr> -j RETURN` (ensures traffic from Docker bridges is evaluated by Docker)
- `DOCKER-USER -d <bridge-cidr> -j RETURN` (ensures traffic to Docker bridges is evaluated by Docker)
- `OUTPUT -d <bridge-cidr> -j ACCEPT` (allows host outgoing connections toward container IPs despite the default drop)
- Redundant `-p tcp --dport 3000/8000` and `-i lo -p tcp --dport 3000/8000` rules are removed to avoid stale port-specific overrides; only the subnet safeguards remain.

## Validation and verification
1. Dry-run the helper first:
   ```bash
   sudo /usr/local/bin/docker_firewall_fix.sh --dry-run
   ```
2. Apply the rules:
   ```bash
   sudo /usr/local/bin/docker_firewall_fix.sh
   ```
3. Inspect the chains:
   ```bash
   sudo iptables -L OUTPUT -n -v --line-numbers | sed -n '1,80p'
   sudo iptables -L DOCKER-USER -n -v --line-numbers | sed -n '1,80p'
   ```
4. Exercise the services:
   ```bash
   curl -v --max-time 5 http://127.0.0.1:3000/ -o /dev/null
   curl -v --max-time 5 http://127.0.0.1:8000/api/v1/ping -o /dev/null || true
   curl -v --max-time 5 http://172.18.0.10:3000/ -o /dev/null || true
   ```
5. If connections still hang, capture packet detail:
   ```bash
   sudo tcpdump -ni any 'tcp port 3000 or tcp port 8000' -c 50
   ```

## Runbook

### Diagnosis
- `sudo iptables -S INPUT; sudo iptables -S OUTPUT; sudo iptables -S FORWARD` (verify default DROP posture and observe inserted rules)
- `sudo iptables -S DOCKER-USER` (confirm `RETURN` rules precede the final `DROP`)
- `sudo iptables -t nat -S | rg -n '3000|8000|DNAT|REDIRECT|DOCKER'` (ensure Docker’s NAT rules are intact)
- `sudo ufw status verbose` (check UFW profile/state)
- `sysctl net.ipv4.ip_forward` and `ip addr show | rg -n 'br-|docker0|inet '` (bridge status)
- `docker ps` / `docker compose ps` (ensure containers expected to publish 3000/8000 are up)
- `curl -v --max-time 5 http://127.0.0.1:3000/` (host connectivity test)

### Rollback
1. Undo the service if necessary:
   ```bash
   sudo systemctl disable --now docker-firewall.service
   ```
2. Remove any helper-inserted iptables entries for the bridge subnets:
   ```bash
   sudo iptables -D OUTPUT -d 172.18.0.0/16 -j ACCEPT
   sudo iptables -D DOCKER-USER -s 172.18.0.0/16 -j RETURN
   sudo iptables -D DOCKER-USER -d 172.18.0.0/16 -j RETURN
   ```
3. Repeat step 2 for other bridge subnets or run `sudo iptables -nL DOCKER-USER` to confirm the cleanup.

## Persistence via systemd
The tracked unit (`ops/docker-firewall.service`) mirrors `/etc/systemd/system/docker-firewall.service`. The service waits until `network-online.target`, `docker.service`, and `ufw.service` are active, then runs the helper once with `RemainAfterExit=yes`. Logs end up in the journal (`StandardOutput=journal+console`), and `Restart=on-failure` ensures that transient failures are visible immediately.

Refresh the unit after edits:
```bash
sudo systemctl daemon-reload
sudo systemctl restart docker-firewall.service
sudo systemctl status docker-firewall.service
```
