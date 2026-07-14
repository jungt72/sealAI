# GATE-05: Netzwerksegmentierung, Listener-Allowlist und Firewall-Cutover

Status: `PREPARED_NOT_ACTIVATED`
Findings: `NET-001`, `NET-002`, `CONT-001`

Dieser Stand ist ausschließlich eine lokale, prüfbare Vorbereitung. Er erzeugt
keine Docker-Netze, startet oder recreatet keinen Container, ändert weder
Firewall noch systemd und rotiert keine Zugangsdaten. Solche Schritte bleiben
unter Production Freeze verboten, bis die jeweils genannten Gates einzeln
freigegeben und protokolliert wurden.

## Ziel und Vertrauensgrenzen

Der Produktions-Compose verwendet keinen impliziten `default`-Bus mehr. Jede
Verbindung hat einen benannten Zweck; serviceinterne Netze sind
`internal: true`. Egress erfolgt über separate Netze. Nur Nginx veröffentlicht
Ports auf allen Host-Adressen.

| Quelle | Erlaubtes Ziel | Netz / Zweck | Verbotene Beispiele |
|---|---|---|---|
| Internet | Nginx `80/443` | `edge_network` | Backend, Keycloak, Postgres, Qdrant, Redis |
| Nginx | Frontend `3000` | `frontend_network` | alle Datendienste |
| Nginx | Backend V2 `8001` | `backend_network` | alle Datendienste |
| Nginx | Keycloak `8080` | `keycloak_edge_network` | Postgres direkt |
| Backend V2 | Keycloak JWKS `8080` | `backend_identity_network` | Redis |
| Backend V2 / Worker | V2-Postgres `5432` | `postgres_backend_network` | Keycloak-Netz |
| Backend V2 / Worker | Qdrant `6333` mit API-Key | `qdrant_backend_network` | Redis, Frontend, Nginx |
| Keycloak | Keycloak-Postgres `5432` | `postgres_keycloak_network` | Backend/Qdrant |
| Prometheus | Backend-Metrik `8001` | `backend_metrics_network` | Datendienste |
| Grafana | Prometheus `9090` | `observability_network` | Backend/Datendienste |
| Strapi (separates Projekt) | Postgres `5432` | einziges externes, scoped und mit Docker `--internal` erzeugtes `strapi_postgres_network` | jedes App-/Edge-Netz |
| Paperless/Gotenberg/Tika | nur eigenes Projekt | `paperless_internal` | jedes sealingAI-Produktionsnetz |

`backend-v2` und `backend-v2-worker` teilen Qdrant/Postgres/Egress, weil sie
dasselbe Trust-Domain-Image und denselben Outbox-Vertrag besitzen. Das
Keycloak-JWKS-Netz ist technisch bidirektional; der Backend-HTTP-Auth-Vertrag
bleibt deshalb zusätzlich erforderlich. Docker-Bridge-Netze sind keine
unidirektionale Firewall.

Die isolierte RC-/Staging-Topologie wird im vorgelagerten Release-Integrity-
Stack geliefert. Sie darf niemals wieder `sealai_default`, Produktions-Secrets
oder Produktionsdatenbanken einbinden.

## Lokale, read-only Verifikation

Der Compose-Guard verarbeitet ausschließlich bereits gerendertes JSON und gibt
keine Environment-Werte aus:

```bash
docker compose --env-file /PFAD/ZU/REDACTED-CONTRACT-ENV \
  -f docker-compose.yml -f docker-compose.deploy.yml \
  --profile v2 --profile frontend-container --profile observability \
  config --format json \
  | python3 -I ops/compose_security_guard.py \
      --policy ops/network_topology_policy.json
```

Er blockiert unbekannte Services, zusätzliche Netzpfade, mutable Images,
ungeplante Host-Ports, fehlende Runtime-Härtung und eine fehlende oder
abweichende Qdrant-Credential-Bindung.

Der Listener-Guard kennt absichtlich nur `observe`; ein Apply-Modus existiert
nicht:

```bash
python3 -I ops/network_listener_guard.py \
  --mode observe --policy ops/listener_allowlist.json --timeout-seconds 5
```

Exit `0` bedeutet Policy-Match, `2` unerwartete Listener und `3` eine nicht
vertrauenswürdige/fehlgeschlagene Beobachtung. Der Aufruf nutzt
`ss -H -lntu` ohne Prozessargumente. Die versionierten systemd Units sind nur
Installationsartefakte; ihr Kopieren/Aktivieren ist eine GATE-05-Mutation. Dabei
werden Skript und Policy objektweise root-owned nach
`/usr/local/libexec/sealai/network-listener-guard.py` (0755) und
`/etc/sealai/listener-allowlist.json` (0644) installiert. Der Dienst liest
niemals aus `/home/thorsten`; eine spätere Home-Berechtigungshärtung kann den
Observer daher nicht unbemerkt deaktivieren. Vor Aktivierung müssen Quell- und
Zieldigest identisch sein; `systemctl daemon-reload` und `enable --now` bleiben
Teil der einzeln freizugebenden GATE-05-Ausführung.

## Harte Vorbedingungen

Vor jedem Produktionsschritt müssen alle Punkte erfüllt sein:

1. **GATE-10:** Freeze ist für den exakt gehashten Release explizit aufgehoben.
2. **GATE-02:** neue, unterschiedliche Keycloak-, V2-DB- und Qdrant-Credentials
   liegen im autorisierten Secret Store; keine Werte stehen in Ticket, Shell-
   History, Git oder Evidence.
3. **GATE-07:** dedizierte DB-Rollen und Datenbanken sind per geprüfter,
   rollback-fähiger Migration angelegt. Die alte Shared-Rolle bleibt nur für
   das befristete Rollback aktiv.
4. **GATE-05:** privilegierter Ist-Export von `nftables`/UFW, Docker-Netzen,
   Routing und Listenern ist geprüft. Eine Out-of-band-Konsole und zwei
   unabhängige SSH-Sitzungen sind verfügbar.
5. **GATE-08:** alle Ziel-Images sind per Digest attestiert; UID/GID,
   Writable-Path-Inventar und Limits wurden gegen genau diese Digests in der
   isolierten RC-Umgebung validiert.
6. Verifizierte Postgres- und Qdrant-Backups, Restore-Probe und ausreichend
   Speicherreserve sind aktuell.
7. Ein externer Probe-Host prüft IPv4 und IPv6 unabhängig vom VPS.

Fehlt eine Vorbedingung, lautet der Status `BLOCKED_EXTERNAL`; es gibt keinen
Teil-Cutover.

## Sequenz mit Stop-Bedingungen

Jede Phase erhält ein eigenes Evidence-Zeitfenster. Nie mehrere Services
gleichzeitig recreaten.

### 0. Ist-Zustand und Rollback einfrieren (read-only, danach GATE-05)

- Exakte Container-IDs, Image-Digests, Netzwerk-Attachments und Health werden
  erfasst, ohne Environment-Inhalte auszulesen.
- Der privilegierte Firewall-Regelsatz wird in einer root-only Datei gesichert
  und zusätzlich gehasht. `nft -c` validiert sowohl Backup als auch Kandidat.
- Die alten Netzwerk-Attachments werden pro Service als exakte Rollback-
  Zuordnung dokumentiert; keine pauschale Rückkehr zu `sealai_default`.
- Das projektübergreifende Strapi-Netz muss bei der einmaligen Erstellung
  `Internal=true` erhalten. Compose kann diese Eigenschaft bei einem
  `external`-Netz nicht setzen; `docker network inspect` muss sie vor jedem
  Attach beweisen. Andernfalls hätte Postgres unbeabsichtigten Egress.

**STOP:** Dirty Worktree, paralleler Deploy, ungesunder Core-Service,
abweichende Runtime-Digests, fehlendes OOB oder unvollständiger Firewall-Export.

### 1. Credentials und Datenrollen (GATE-02 + GATE-07)

- Keycloak und V2 erhalten getrennte Postgres-Rollen; Strapi erhält nur seine
  eigene DB/Schema-Berechtigung.
- Qdrant-Key wird mit sicherem Zeichensatz und mindestens 32 Zeichen erzeugt.
- Backend/Worker und Qdrant erhalten denselben Key erst im geplanten
  Recreate-Fenster. `backup_qdrant.sh` überträgt den Header über stdin, nicht
  über argv oder Logs.

**STOP:** Rollen können außerhalb ihres Schemas lesen/schreiben, alter und neuer
Credential-Satz sind nicht separat testbar, oder Qdrant-Backup/Restore ist rot.

### 2. Netze serviceweise umstellen (GATE-05 + GATE-08)

Empfohlene Reihenfolge: interne Netze anlegen, Postgres, Keycloak, Qdrant,
Worker, Backend, Frontend, Nginx; anschließend Biz/Paperless. Nach jedem
Recreate folgen Health, erlaubte Verbindung und sämtliche negativen Matrix-
Probes. Erst dann wird der nächste Service berührt.

**STOP:** unerwartete Namensauflösung, Datendienst aus Edge/Frontend erreichbar,
Health nicht stabil, Fehler-/Latenzbudget überschritten, Schreibpfad durch
`read_only`/`tmpfs` blockiert oder OOM/PID-Limit ausgelöst.

Rollback erfolgt nur für den zuletzt veränderten Service: alter Digest,
alte Credential-Version und die vorher attestierte Netzwerkzuordnung. Bereits
grüne, unabhängige Zonen bleiben gehärtet. Ein Rollback darf Qdrant-Auth nicht
deaktivieren, wenn der alte Client den neuen Key bereits unterstützt; sonst
wird das vollständige vorherige Credential-Paar atomar wiederhergestellt.

### 3. Firewall mit automatischem Timeout-Rollback (GATE-05)

Die konkrete Regeldatei wird erst aus dem privilegierten Ist-Export erstellt.
Keine Regel aus diesem Dokument darf blind ausgeführt werden.

1. Kandidat mit `nft -c -f <candidate>` syntaktisch prüfen.
2. Root-only Backup mit `nft -c -f <backup>` rückprüfen.
3. Über einen transienten, eindeutig benannten systemd Timer einen
   **automatischen Restore des Backups in fünf Minuten** armieren. Timerstatus
   und exakte Kommandozeile werden vor Apply geprüft.
4. Kandidat anwenden; die armierte Rückkehr bleibt aktiv.
5. Aus bestehender und neuer SSH-Sitzung sowie vom externen Probe-Host testen:
   SSH, HTTP/HTTPS, IPv4/IPv6, alle negativen Ports und Produkt-Smokes.
6. Nur wenn alle Tests grün und der Listener-Guard sauber sind, den Timer
   gezielt stoppen, entfernen und dessen Entfernung verifizieren.

**STOP/automatischer Rollback:** Verlust einer SSH-Sitzung, OOB nicht erreichbar,
HTTP/TLS rot, ein verbotener Port erreichbar, IPv4/IPv6-Divergenz, Timer nicht
nachweisbar aktiv oder unbekannte nft/UFW/Docker-Regelinteraktion.

Der bestehende blocklist-orientierte Listener-Mechanismus ist keine
Freigabeevidenz. Der neue Allowlist-Guard startet zunächst ausschließlich im
Beobachtungsmodus; Firewall-Enforcement folgt niemals automatisch aus einem
Guard-Fund.

## Container-Härtung: Kompatibilitätsvertrag

Für alle Produktionsservices sind `no-new-privileges`, `cap_drop: ALL`, ein
read-only Root-FS, explizite tmpfs-/Volume-Schreibpfade, PID/CPU/RAM-Limits,
`unless-stopped` und begrenzte lokale Logs vorbereitet. Nur nachweisbar
notwendige Start-Capabilities bleiben bei Nginx, Postgres und Redis erhalten.
Explizite non-root UIDs werden nur für die im eigenen Dockerfile belegten
Frontend-/Backend-Images erzwungen.

Die Werte `*_MEMORY_LIMIT`, `*_CPU_LIMIT` und `*_PIDS_LIMIT` besitzen bewusst
keine Defaults. GATE-08 setzt sie aus p95/p99-Lastmessung plus dokumentierter
Reserve. Ein geratenes Limit wäre kein Sicherheitsgewinn.

Pro Digest sind in der RC-Umgebung nachzuweisen:

- Start, Health, kontrollierter Neustart und erwartete Grace-Period;
- positiver Schreibtest ausschließlich in gelisteten Volumes/tmpfs;
- negativer Schreibtest auf Root-FS und nicht freigegebenen Pfaden;
- effektiver User, Capabilities, `NoNewPrivs`, PID-/CPU-/RAM-Limit;
- bounded load ohne OOM/Throttling-bedingte fachliche Fehler;
- Logrotation ohne sensitive Payloads;
- Backup, Restore und Rollback mit denselben Controls.

Image-eigene Healthchecks von Gotenberg/Tika und konkrete UID-/Writable-Path-
Eigenschaften fremder Images müssen am gewählten Digest runtime-verifiziert
werden. Bis dahin bleibt CONT-001 `IMPLEMENTED_NOT_DEPLOYED`, nicht `CLOSED`.

## Restrestrisiken

- Eine gemeinsame Postgres-Instanz bleibt ein Blast-Radius; getrennte Netze und
  Rollen ersetzen keine physische Datenbanktrennung.
- Das JWKS-Netz ist bidirektional; Service-Auth und Backend-Rate-Limits bleiben
  Defense-in-depth.
- Das scoped Strapi-Netz erlaubt Zugriff auf den Postgres-Endpunkt. `pg_hba`,
  Rollen- und Schema-Isolation müssen GATE-07 beweisen.
- Docker-Netze kontrollieren keine ausgehenden Ziele im Internet. Host-
  Firewall/DOCKER-USER-Egress bleibt eine eigene, privilegiert zu prüfende
  Grenze.
- Die lokalen Änderungen beweisen keine VPS-Firewall, keinen externen Reachability-
  Zustand und keine Image-Kompatibilität; diese Evidenz ist `BLOCKED_EXTERNAL`.
