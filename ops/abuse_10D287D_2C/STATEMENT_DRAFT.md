# Draft Statement to Hetzner Abuse Team

We received your notification about outbound UDP traffic from `49.13.233.145` targeting `103.227.209.22` (UDP, src‑port 3449).

**Current status**

- During immediate investigation (Phase 1) no live UDP traffic to the target was observed.
- Host egress was already set to default‑deny via UFW/iptables.

**Actions taken**

1. **Container egress hardened (default‑deny):**  
   Docker containers can bypass host UFW egress through the `FORWARD` chain. We therefore enforced a default‑deny policy in Docker’s `DOCKER-USER` chain for IPv4 and IPv6. Containers may now only send outbound DNS (`53/udp+tcp`), HTTP/HTTPS (`80/443 tcp`) and optional NTP (`123/udp`). All other container egress is dropped. Additionally, IPv4 UDP traffic to `103.227.209.22` is explicitly blocked.
2. **Public attack surface reduced:**  
   Public host port publishing for application services was removed or restricted to localhost. External access is now limited to SSH `22/tcp` and web via Nginx `80/443`. Previously open admin ports `8443/4443/9090` were closed at the firewall (IPv4+IPv6).
3. **Ongoing monitoring:**  
   We continue monitoring egress logs and container behavior. If any recurrence is detected, the responsible container will be isolated and rebuilt, including secrets rotation.

**Conclusion**

Outbound abuse traffic is currently blocked at both host and container levels. Long‑term egress controls and reduced public exposure have been put in place.

