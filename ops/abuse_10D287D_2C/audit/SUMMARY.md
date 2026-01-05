## Phase 1 Summary (Audit/Diagnose)

**Zeitpunkt Audit:** 2025-12-12 (siehe `00_system_basics.log`).

### Aktueller Zustand

- **Live‑Capture:** `tcpdump` auf `udp and host 103.227.209.22` für 15s zeigt **keine Pakete** (siehe `15_tcpdump_udp_103.227.209.22.log`). Der gemeldete UDP‑Traffic läuft **aktuell nicht sichtbar**.
- **Host‑UDP‑Sockets:** Nur systemnahe UDP‑Sockets (`systemd-resolved` auf 53/udp, `chronyd` auf 323/udp, DHCP client auf 68/udp). **Kein Prozess** mit UDP‑Bindung/Send zu Port `3449` erkennbar (siehe `04_ss_tulpn.log`, `05_ss_uapn_head200.log`, `06_lsof_udp_head200.log`).
- **UFW/iptables:** UFW aktiv mit Default `deny (incoming), deny (outgoing)` und Outbound nur `53/udp+tcp`, `80/tcp`, `443/tcp`, `123/udp` erlaubt (siehe `02_ufw_status_verbose.log`). iptables OUTPUT Policy `DROP` bestätigt das (siehe `03_iptables_S.log`).
- **Docker‑Stack:** Mehrere Container laufen (SealAI + Odoo). Docker erstellt eigene FORWARD‑Ketten und akzeptiert Forwarding vom Bridge‑Interface (`DOCKER-FORWARD` akzeptiert `br-*`), wodurch **Container‑Egress UFW‑OUTPUT umgehen kann** (siehe `03_iptables_S.log`, `11_docker_ps_all.log`).
- **Container‑Logs (21:30–jetzt):** Keine eindeutigen Hinweise auf UDP‑Flooder in den letzten Logs (siehe `docker_logs_*.log`).

### Diagnosehypothese

Der von Hetzner gemeldete UDP‑DDoS ist **aktuell gestoppt** bzw. nicht reproduzierbar. Da Host‑Egress per UFW/iptables hart auf `DROP` steht, ist ein **Container als Quelle wahrscheinlicher** (Docker‑FORWARD akzeptiert Container‑Outbound auch bei UFW‑Outgoing‑Deny). Ein konkreter Schuldiger (Container/Prozess) konnte ohne Live‑Traffic **nicht eindeutig identifiziert** werden.

### Nächste Schritte in Phase 2

- Docker‑Egress explizit über `DOCKER-USER`/UFW‑route policy begrenzen oder Container isolieren.
- Optional längere/gezielte Capture‑Fenster mit `tcpdump`/UFW logging, um Quelle bei Wiederauftreten zuzuordnen.

