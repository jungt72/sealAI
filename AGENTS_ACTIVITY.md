# Agenten-Aktivitäts-Log

Append-only, eine Zeile pro Session, die Infrastruktur/Gates/Prod-Verhalten anfasst. Zweck: sichtbar
machen, wenn mehrere Agenten (Claude Code, Codex, ...) auf demselben Namensraum/Bereich arbeiten,
bevor daraus eine unkoordinierte Kollision wird (siehe GATE-10-Forensik, 2026-07-17/18: Codex und
Claude Code arbeiteten unabhängig im selben `remediation/p0-*`-Namensraum, ohne dass eine Seite die
andere sehen konnte). Kein Ersatz für Commit-Messages/PR-Beschreibungen — nur ein Radar.

Format: `DATUM | AGENT (falls bekannt) | BEREICH | KURZBESCHREIBUNG`

## Log

2026-07-18 | Claude Code | GATE-10 Forensik + Konsolidierung | Disk-Notfall behoben (95%→68%),
disk-guard + public-port-guard repariert/maskiert, Key-Hygiene (SSH authorized_keys), 87 gemergte
Branches gelöscht, 2 redundante Worktrees entfernt, 117 alte .env.prod-Snapshots rotiert, FLAGS.md
angelegt (PR #314). Freeze selbst NICHT angefasst — Owner-Decision zum Notfall-Korridor steht aus.

2026-07-18 | Codex | MATERIAL-RULES-01 (MAT-GOV-03A/B + MAT-EVID-01A/B/C + MED-NORM-01) | Reviewed
Rule-Pack-Boundary + Contract-Hardening gemergt (PR #322, Merge-Commit `b66897e1`). Fail-closed,
disqualify-only Bindung (nur `unvertraeglich`/opakes `bedingt`), laufende Revalidierung von Review/
Binding/Tenant/Snapshot/Medienkatalog. 53 kanonische Evidence-Gaps dokumentiert, keine Fakten/Claims/
Seeds erfunden. Unabhängiger Codex-Review PASS (0 Critical/High/Medium/Low). GATE-10-Freeze griff
korrekt (Exit 20, kein Build/Push/Deploy/SBOM). MAT-GOV-03C bleibt blockiert bis Owner: Primärquellen
kuratieren, MED-NORM-Review, 3 getrennte Subjects (Creator/Reviewer/Approver), min. 1 freigegebener
Rule-Pack.

2026-07-18 | Claude Code | Restarbeiten aus Professionalitaets-Assessment | Docker-Image-Retention
(ops/rotate_docker_images.sh, PR #324, woechentlich So 03:30) + Remediation-PR-Stack-Triage
(docs/ops/remediation-pr-triage-2026-07-18.md, PR #326: 16 offene PRs sind in Wahrheit 1 gestapelte
12er-Kette #293-#305 + 1 Standalone-Draft #311 + 2 Dependabot + 7 Alt-PRs, keine PR angefasst) +
Guard-Health-Check (ops/check_guard_health.sh, PR #327, alle 6h). Beim Bau des Guard-Health-Checks
lebende Luecke gefunden: disk_safeguard.sh (Cron, User thorsten) ist seit einem upstream-Rewrite ein
No-Op-Shim fuer Nicht-Root-Aufrufer; der vorgesehene Ersatz sealai-docker-disk-guard.timer war nie
enabled. Disk-Guard lief seitdem ueber keinen Pfad. Fix braucht einmalig `sudo systemctl enable --now
sealai-docker-disk-guard.timer` vom Owner (keine passwortlose sudo in dieser Session) -- noch offen.

2026-07-18 (Nachtrag) | Claude Code + Owner | Disk-Guard-Luecke geschlossen | Owner hat `sudo
systemctl enable --now sealai-docker-disk-guard.timer` sowie danach `sudo systemctl start
sealai-docker-disk-guard.service` ausgefuehrt (Timer allein reichte nicht: OnBootSec/OnUnitActiveSec
sind monotone Trigger, die ohne echten Reboot bzw. ohne einen frischen Service-Lauf nicht nachtraeglich
feuern). Service lief danach mit status=0/SUCCESS, State-Dir aktualisiert. Redundante
thorsten-Crontab-Zeile fuer das alte disk_safeguard.sh-Shim entfernt -- genau ein Pfad (systemd-Timer)
ist jetzt aktiv. check_guard_health.sh bestaetigt: OK.

2026-07-18 | Claude Code | Gruppe-2-Branch-/Stash-Bereinigung | 8 zuvor zurueckgestellte Branches
geloescht, alle einzeln content-verifiziert als superseded/stale (Funktionalitaet bereits unter
anderem Commit in main vorhanden, oder Zielcode entfernt): codex/architecture-hardening,
codex/architecture-status, codex/durable-worker, docs/ist-audit-0623, feat/hero-top-image,
feat/v1.7-blueprint, feat/v2-phase2d-smalltalk-prompt-wiring, inc-4a-remediation. Alle 5
verbleibenden Stashes ebenso einzeln verifiziert und gedroppt (claude-seo-preserved: identisch
bereits in main; Keycloak-CSS-Stash: Ziel-Datei nur noch leerer Stub, echtes Theme ist Disk-Mount;
cockpit-overview-pre-sync: 472 Dateien/2 Monate alt, laengst divergiert; ptfe-rwdr-ssot-pre-patch:
bewahrte eine als "unrelated" geflaggte, bereits vermiedene Loeschung; frontend-workspace-cleanup:
Ziel war V1-Backend-Code, komplett entfernt seit Retirement). Keine Ueberschneidung mit Codex'
aktiver Arbeit (feature/mat-evid-02) verifiziert vor Ausfuehrung.

2026-07-18 | Claude Code | GATE-11-Wiring in release-backend-v2.sh | --low-risk-emergency als
dritte Release-Stage ergaenzt (PR #332), rein additiv (--candidate/--final/kein-Argument
byte-identisch unveraendert, testverifiziert). Voraussetzung war die Owner-Bestaetigung, dass der
alte remediation/p0-p2-Stack (#293-#305, dieselben Gate-Dateien beruehrend) tot/aufgegeben ist --
damit keine Kollision. GATE-10-Freeze selbst weiterhin unangetastet; nur der additive
Notfall-Korridor ist jetzt tatsaechlich aufrufbar, nicht nur dokumentiert.
