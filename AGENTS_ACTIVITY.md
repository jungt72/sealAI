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

2026-07-18 | Claude Code | .env.prod-Verschluesselung (sops+age) | ops/env-prod.sops jetzt
git-getrackt (PR #334): jeder Wert verschluesselt, Keys lesbar fuer git diff. Live-Workflow
unveraendert -- .env.prod selbst bleibt die Klartext-Datei. sops-Binary manuell installiert
(~/bin/sops, per cosign gegen offizielle getsops/sops-Sigstore-Signatur verifiziert), age =
offizielles Ubuntu-Paket. Age-Private-Key liegt nur in ~/.config/sops/age/keys.txt (0600, nie
committed). Zwei Stolpersteine unterwegs gefunden+behoben: (1) urspruenglicher Dateiname
.env.prod.sops wurde von ops/check-secret-hygiene.py's filename.env-Regel abgelehnt (Namens-Regel,
unabhaengig vom Inhalt) -> nach ops/env-prod.sops verschoben; (2) secrets/ ist bereits ein
reserviertes, komplett gitignortes "nie committen"-Verzeichnis in diesem Repo -> nicht verwendet.
Damit sind jetzt alle 3 vom Owner freigegebenen Restpunkte (Branch/Stash-Cleanup, GATE-11-Wiring,
.env.prod-Overhaul) abgeschlossen.

2026-07-18 (Nachtrag) | Claude Code | PR-Aufraeumung + Secret-Scan-Struktur-Fund | 13
remediation-Stack-PRs (#293-#305, #311) geschlossen -- Owner bestaetigte den Stack als tot/
aufgegeben (Basis bereits als #291 gemerged). 5 alte Alt-PRs geschlossen (#5, #6, #89, #120, #127
-- alle inhaltlich superseded/V1-Backend-Ziel/bereits andernorts gelandet, einzeln verifiziert).
3 Dependabot-PRs (#222, #223, #308) geschlossen, NACHDEM ein Branch-Update bei ihnen einen
Struktur-Fund ausgeloest hat: jeder Branch-Update/Merge, der main ueber den 2026-07-14-
Remediation-Commit hinweg einholt, laesst den Range-basierten Secret-Scanner die dort bereits
bekannten, dokumentierten Alt-Funde (certs/tls.key, keycloak/certs/key.pem, ACME-JWK,
docs/debug_internal_error/live/*, siehe docs/security/credential-rotation-runbook.md) erneut als
"neu eingefuehrt" markieren -- kein neuer Leak, aber ein strukturelles Problem: JEDER
Branch-Update ueber diese Grenze hinweg wird das gleiche tun, bis entweder ein separat
freizugebender History-Rewrite passiert oder gewuenschter Inhalt als frischer Commit direkt auf
aktuellem main neu erstellt wird (statt den alten Branch zu aktualisieren). Verifiziert an einem
9 Tage alten Branch (PR #208) -- Alter des Branches ist NICHT der Faktor.
Noch offen, Owner-Entscheidung noetig: #187 (staging deploy script, DIRTY/CONFLICTING, teils schon
anders gelandet), #205 (Phase-3A-Governance-Log-Eintrag, DIRTY/CONFLICTING, Inhalt echt fehlend),
#208 (Phase-3B-Governance-Log-Eintrag, BLOCKED durch obigen Fund, Inhalt echt fehlend). Keine
Werte je angezeigt/kopiert/geloggt -- nur redigierte CI-Ausgabe gelesen, im Einklang mit dem
Runbook.

2026-07-18 (Nachtrag 2) | Claude Code | Governance-Log-Backfill statt Merge | #205/#208 (Phase-3A/
3B-Aktivierungs-Logs) als frische Commits wortgetreu direkt auf main nachgezogen (PR #338,
gemerged) statt die alten Branches zu mergen -- umgeht den Struktur-Fund zum Range-Secret-Scanner
sauber. 4 fehlende ops/deploy-ledger.jsonl-Zeilen an ihrer historisch korrekten chronologischen
Position eingefuegt (nicht ans Ende angehaengt). #205 + #208 geschlossen als superseded durch #338.
#187 (staging deploy script) bleibt bewusst unangetastet -- echte Merge-Konflikte, kein
Empfehlungs-Fall wie bei 205/208, Owner-Entscheidung noetig.

2026-07-21 | Claude Code | GATE-10 OpenAI-Challenger (ops/gate_challenger.py) | Auf Owner-Wunsch
gebaut: ein einzelner gebundener gpt-5.4-mini-Call pro Aufruf, prueft GATE-10-P1-Stand gegen
docs/ops/production-release-freeze.md + den P1-Diff (c32270fd), schreibt nur einen lesbaren Bericht
nach ops/.gate-challenges/ (gitignored) -- ruehrt nie eine Approval-Datei an und importiert nie
backend/sealai_v2/eval/ (den bezahlten Multi-Case-Judge). Live pilotiert (~13k Tokens): bestaetigte
unabhaengig, dass 2/7 Manifest-Hashes gebunden sind und aktuell kein Freigabepfad existiert
(freeze_lift_implemented weiterhin false). backend/tests/test_gate_challenger.py deckt
Kontext-Sammlung, Fail-closed ohne OPENAI_API_KEY, und die exakte Request-Form (ein Call,
max_completion_tokens, kein Approval-Schreibzugriff) ab -- lokal gruen, ruff format/check sauber.
Noch nicht in einen Freigabe-Workflow verdrahtet; reine Lese-/Beratungs-Hilfe.

2026-07-21 (Nachtrag) | Claude Code | GATE-10 P1 Phase 2 (backend_image_digest) | Auf
Owner-Wunsch, schrittweise nach GATE-10-Challenger-Piloten: dritte von sieben
required_manifest_hashes real gebunden. ops/production_release_gate.py::
_verify_backend_image_attestation ruft das bereits existierende
ops/verify-image-attestations.sh (Sigstore/Rekor Build-Provenance + SBOM, dieselbe Pruefung
die ops/release-backend-v2.sh schon vor jeder Image-Promotion faehrt) und lehnt eine
manifest-behauptete Digest ab, die nicht wirklich von build-and-push.yml aus dem
freigegebenen source_git_sha gebaut wurde. Erstes Feld in dieser Datei, das Docker+Netzwerk
braucht -- bewusst, eine Signaturpruefung laesst sich nicht lokal nachrechnen.
frontend_image_digest bleibt bewusst aussen vor: es existiert noch gar keine attestierte
Build-Pipeline fuer das Frontend-Image (build-and-push.yml baut nur backend-v2) -- das ist
ein groesserer, separater Vorlauf (neue CI-Pipeline), keine reine Gate-Verdrahtung wie hier.
GATE10_LIFT_IMPLEMENTED bleibt unveraendert false; es fehlen weiterhin frontend_image_digest,
dashboard_artifact_sha256 (kein Publisher existiert) und rollback_plan_sha256/
evidence_manifest_sha256 (keine Schema-Entscheidung getroffen -- Produktentscheidung, keine
reine Technik).

Beim Verdrahten einen selbst verursachten Bug in derselben Aenderung gefunden und sofort
korrigiert, bevor committed wurde: eine textbasierte Ersetzung hatte den Funktionskoerper von
_verify_source_derived_artifact_hashes versehentlich geloescht (Phase-1-Pruefung waere damit
wirkungslos gewesen). Ursache war ein zu kurzer Match-Anker beim automatisierten Patchen: durch
sorgfaeltigen Diff-Review vor dem Commit gefunden, nicht durch Tests (die haetten es aber auch
gefangen -- siehe unten). Zwei bestehende Tests (test_gate10_artifact_binding.py::
test_unfreeze_accepts_real_source_derived_hashes_up_to_the_lift_flag,
test_production_release_gate.py::test_versioned_two_commit_unfreeze_binds_exact_source_parent)
mussten angepasst werden (Attestation-Registry gemockt), weil sie mit Dummy-Digests bis zum
GATE10_LIFT_IMPLEMENTED-Check durchlaufen sollten und nun vorher am echten
Attestation-Call scheiterten. Neue backend/tests/test_gate_backend_image_attestation.py
(6 Tests) deckt Format-Ablehnung, exakte Skript-Argumente, Fail-closed bei Script-Fehler,
Erfolgspfad, und die Ein-Feld-Grenze der Registry ab. Alle betroffenen Gate-Tests lokal gruen
(104 Tests); ein unabhaengiges, vorbestehendes venv-Problem
(prometheus_fastapi_instrumentator fehlt, auch auf unveraendertem main reproduzierbar)
verhinderte den vollen ops/gate.sh-Lauf lokal, betrifft aber nicht CI (frische Installation).

2026-07-21 (Nachtrag 2) | Claude Code | GATE-10 P1 Phase 2b (frontend_image_digest) |
Vierte von sieben required_manifest_hashes real gebunden. Wichtiger Fund unterwegs:
frontend_image_digest meint das V1-Marketing-Frontend (frontend/, ghcr.io/jungt72/
sealai-frontend, aktuell per lokalem docker build auf dem VPS gebaut ueber
ops/release-frontend.sh -- keine GitHub Actions, keine Signatur) -- NICHT frontend-v2/
das Dashboard, das gar kein Dockerfile hat und weiterhin unter dashboard_artifact_sha256
faellt (separates, noch offenes Feld). Neue .github/workflows/build-and-push-frontend.yml
baut das V1-Frontend jetzt mit derselben Sigstore/Rekor-Provenance+SBOM-Kette wie Backend;
ops/production_release_gate.py::_verify_frontend_image_attestation (Registry-Eintrag,
gemeinsame _verify_image_attestation-Implementierung mit dem Backend-Pfad, kein
Duplicate-Code) verifiziert das. Owner-Aktion noetig, aber unkritisch: die
NEXT_PUBLIC_*/Domain-Config-Werte, die ops/release-frontend.sh bisher aus .env.prod zieht,
sind als GitHub-Actions-Repository-Variablen mit Fallback auf die aktuellen
Produktionswerte hinterlegt -- laeuft ungeaendert auch ohne dass der Owner etwas eintraegt,
kann aber ueber Settings > Actions > Variables ueberschrieben werden. Keiner der 13 Werte
ist ein echtes Secret.

Bewusst NICHT angefasst: ops/release-frontend.sh selbst baut weiterhin nur lokal. Es hat --
anders als ops/release-backend-v2.sh -- kein Release-Stage-Konzept (--candidate/--final/
Approval-Bindung an APPROVED_SOURCE_SHA, Rollback-Hold, Runtime-Profile-Hash); das
Backend-Skript ist erkennbar deutlich ausgereifter. Einen aequivalenten optionalen
Pull-und-Verify-Pfad (FRONTEND_V1_IMAGE, analog BACKEND_V2_IMAGE) nachzuruesten waere ohne
dieselbe Absicherung entweder unvollstaendig oder ein eigenes, groesseres Redesign des
produktiven Frontend-Deploy-Pfads -- daher bewusst als separater, spaeterer Schritt
zurueckgestellt statt hier mit reingezogen.

backend/tests/test_gate_backend_image_attestation.py -> test_gate_image_attestation.py
umbenannt (deckt jetzt beide Felder ab), 2 neue Tests fuer den Frontend-Verifier ergaenzt.
Grenz-Test test_registry_only_covers_backend_for_now angepasst (jetzt beide Felder erwartet
-- dokumentiert die neue, bewusste Grenze statt die alte). 106 betroffene Gate-Tests lokal
gruen. Neues Workflow-YAML manuell gegen build-and-push.yml diff-geprueft (kein actionlint
auf dem VPS verfuegbar); via python yaml.safe_load syntaktisch verifiziert.

2026-07-21 (Nachtrag 3) | Claude Code | GATE-10 P1 Phase 3 (rollback_plan/evidence_manifest) |
Fuenfte und sechste von sieben required_manifest_hashes real gebunden -- 6/7 jetzt erledigt,
nur noch dashboard_artifact_sha256 offen. Owner-Entscheidung vorausgegangen: OpenAI-Challenger
hat auf Basis der echten GATE-11/12-Schemas und eines echten GOVERNANCE_LOG-Rollback-Eintrags
zwei Wege vorgeschlagen (feste eigene Datei pro Feld vs. Governance-Log-verankert); Owner hat
sich fuer feste Dateien entschieden. Neue docs/ops/GATE-10-ROLLBACK-PLAN.md konsolidiert die
echten, bereits existierenden Rollback-Mechanismen aus ops/release-backend-v2.sh (Rollback-Hold/
-Rung-Tags, gedruckter Rollback-Befehl bei rotem Smoke-Test) und ops/release-frontend.sh
(automatisches .env.prod-Snapshot-Restore) an einem Ort -- kein neuer Mechanismus, nur
konsolidierte, hash-gebundene Dokumentation. Neue docs/ops/GATE-10-EVIDENCE-MANIFEST.md
definiert, welche echten Befehle/Ausgaben hinter jedem der vier required_readiness_claims
(P0_SECRETS_CONTAINED/P0_STORAGE_STABLE/P0_REDIS_STABLE/RELEASE_GATE_FAIL_CLOSED) stehen
sollten -- macht noch keinen Code-Unterschied im Gate selbst (das prueft weiterhin nur, dass die
vier Keys "true" sind), aber legt fest, was als Beleg zaehlen soll, statt einer reinen
Selbstauskunft.

Beide Felder nutzen dieselbe Source-Derived-Recipe wie Phase 1 (_git_write_tree, kein
Docker/Netzwerk noetig) -- ROLLBACK_PLAN_PATHSPECS/EVIDENCE_MANIFEST_PATHSPECS binden je eine
einzelne feste Datei, genau wie DATABASE_MIGRATION_PATHSPECS einen festen Pfad bindet.

Beim Testen einen echten git-Mechanismus gelernt, der die urspruengliche Testfixture-Annahme
widerlegt hat: `git add -A -- <nicht-existierender-literaler-Pfad>` schlaegt fehl ("did not
match any files"), staged NICHT stillschweigend nichts -- anders als angenommen. Beide
Synthetic-Repo-Testfixtures (_make_minimal_source_commit in test_gate10_artifact_binding.py,
_make_gate_control_repo in test_production_release_gate.py) mussten deshalb um Stub-Dateien
fuer die zwei neuen Pfade erweitert werden, sonst waeren die bestehenden "up to lift flag"/
"two-commit-binding" Tests mit "cannot stage the real release artifact for hashing"
fehlgeschlagen statt das zu pruefen, was sie eigentlich pruefen sollen. 6 neue Tests
(Perturbation + Neutralitaet + Forgery-Rejection fuer beide Felder), 2 bestehende Grenz-/
Positivpfad-Tests angepasst. Alle betroffenen Gate-Tests lokal gruen.

2026-07-21 (Nachtrag 4) | Claude Code | GATE-10 P1 Phase 4 (dashboard_artifact_sha256) --
alle 7/7 Hashes real | Letztes der sieben required_manifest_hashes gebunden. Bewusst eng
gescoped nach Owner-Vorgabe: NUR Content-Hashing gebaut, NICHT den eigentlichen Live-Promote-
Schritt (Kopieren verifizierter Bytes ins live dist/-Bind-Mount) -- docs/ops/
RUNBOOK_V2_CUTOVER.md nennt das explizit eine "OWNER, low-traffic window"-Aktion, kein
Automatismus, und warnt: "This P1 contract is not implemented yet; a local npm run verify
is evidence for candidate bytes only and cannot make them production-eligible."

Wichtiger Fund unterwegs: /dashboard ist bereits live (nginx bindet snippets/v2_dashboard.conf
schon ein, dist/ hat echten Inhalt vom 14.7.) -- der Cutover geschah ueber einen manuellen,
owner-gesteuerten Prozess, nicht ueber den im Runbook vorgesehenen gated Weg. frontend-v2/
vite.config.ts hatte den candidate-seitigen Teil bereits fertig und gehaertet gebaut (fixer
outDir .build/dashboard-candidate, sealai-deny-live-dashboard-build-Plugin verweigert jeden
anderen outDir, jede Symlink-Komponente, jeden Inode-Alias auf dist/) -- nur das Hashing/
Binden ans Gate fehlte.

Neue _directory_sha256()-Funktion in ops/production_release_gate.py: deterministischer
Hash ueber Pfad+Inhalt jeder Datei (sortiert, Symlinks abgelehnt) -- fundamental anders als
alle bisherigen Felder, weil .build/dashboard-candidate/ NICHT git-getrackt ist (gitignored
Build-Output). Live gegen einen echten npm run build getestet (echte 40+ Dateien, KaTeX-Fonts,
JS-Bundles) -- deterministisch bestaetigt.

backend/tests/test_gate_dashboard_artifact.py (neu, 8 Tests): fail-closed bei fehlendem/leeren
Verzeichnis, Symlink-Ablehnung, Determinismus unabhaengig von Erstellungsreihenfolge,
Hash-Aenderung bei Inhalts- UND Pfaenderung (Rename mit identischen Bytes bewegt den Hash --
bindet den Pfad, nicht nur die Bytes). Beide Synthetic-Repo-Fixtures um einen Stub-
dashboard-candidate erweitert (gleiches Muster wie schon bei rollback_plan/evidence_manifest
noetig). 1 neuer Forgery-Test, 2 Grenz-Tests angepasst. Alle betroffenen Gate-Tests lokal
gruen.

docs/ops/production-release-freeze.md auf 7/7 aktualisiert -- mit explizitem Abschnitt "was
7/7 bedeutet und was nicht": kein Weg, verifizierte Bytes tatsaechlich zu promoten, existiert
noch; GATE10_LIFT_IMPLEMENTED bleibt eine eigene, bewusste Entscheidung, kein Automatismus
beim letzten Hash.
