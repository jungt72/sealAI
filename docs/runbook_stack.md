# SealAI Stack Runbook

## Boot persistence
- `sealai-stack.service` is a oneshot unit that waits for `network-online.target`, `docker.service` and `ufw.service`, then runs `docker compose -f /root/sealai/docker-compose.yml -f /root/sealai/docker-compose.deploy.yml up -d --remove-orphans backend frontend`. The unit stays marked as active so the stack relaunches automatically after reboots.
- Install it with `sudo ./ops/install_sealai_stack_service.sh`; the script copies the service file into `/etc/systemd/system`, runs `systemctl daemon-reload`, and enables the unit `--now`.
- If you ever need to stop automatic restarts (for example during maintenance), run `sudo systemctl disable --now sealai-stack.service` and then manually bring the stack up with the compose commands below.

## Stack restart and recovery
- The canonical restart command is `docker compose -f /root/sealai/docker-compose.yml -f /root/sealai/docker-compose.deploy.yml up -d --remove-orphans backend frontend`. This mirrors the systemd unit and keeps the published ports (8000, 3000) and compose healthchecks intact.
- After any manual restart you can refresh the service definition with `sudo systemctl restart sealai-stack.service` to let systemd track the new state.

## Smoke tests
- Run `./ops/stack_smoke.sh` to confirm the backend/frontend pair is running, listening on ports 8000/3000, and returning healthy responses. The script exits with diagnostics plus the last 200 log lines on failure.
- `ops/docker_firewall_fix.sh --test` now wraps `ops/stack_smoke.sh` and classifies failures as “services not running”, “listeners missing”, or “curl blocked/timeouts” so firewall fixes only trigger when the network stack is actually blocking traffic.

## Rollback steps
1. Disable the systemd unit: `sudo systemctl disable --now sealai-stack.service`.
2. Take down the containers to avoid stray listeners: `docker compose -f /root/sealai/docker-compose.yml down --remove-orphans`.
3. Reapply the firewall baseline (if needed) by rerunning `sudo ops/docker_firewall_fix.sh --mode relaxed` or your preferred mode so the DOCKER-USER drop rule plus bridge return rules stay intact.

Keep UFW in default deny (incoming/outgoing/routed) and leave the final DROP in DOCKER-USER; the stack still relies on the return rules and `sealai-stack.service` to keep the two public ports accessible without exposing anything else.
