# GATE-07 — Datenautorität, Ownership, Constraints und RLS

Status: **VORBEREITET, NICHT AUSGEFÜHRT, BLOCKIERT**. Dieses Runbook autorisiert keine
Produktionsänderung. Migration 0012/0013 ist additiv; Profiling, Quarantäne-Markierung, Backfill,
Constraint-Validierung, Rollenwechsel und RLS/FORCE RLS sind getrennte Freigabeschritte.

```yaml
gate_id: GATE-07 DATABASE_MIGRATION
objective: >-
  Postgres als alleinige Daten- und Wissensautorität etablieren, mehrdeutige Legacy-Ownership
  quarantänisieren, referenzielle Grenzen validieren und Tenant-/Owner-Isolation mit getrennten
  nicht-bypassenden Datenbankrollen sowie FORCE RLS beweisen.
current_state: >-
  Code und additive Migrationen sind vorbereitet. Produktionsprofil, Backup, Mapping,
  Constraint-Validierung, Runtime-GUC/Role-Adapter, echte PostgreSQL-Rollentests und produktive
  Rollenbelegung sind nicht belegt. GATE-07 bleibt geschlossen.
exact_actions:
  - 0012/0013 in einer isolierten, produktionsähnlichen PostgreSQL-Kopie migrieren
  - ausschließlich aggregiertes Profiling erzeugen und peer-reviewen
  - unveränderliches, restore-getestetes PostgreSQL-Backup erstellen
  - mehrdeutige Legacy-Zeilen ohne Owner-Zuweisung oder Löschung quarantänisieren
  - ausschließlich menschlich geprüfte, eindeutige Ownership-Zuordnungen backfillen
  - Shadow-Constraints einzeln validieren
  - getrennte Login-/NOLOGIN-Rollen und transaction-scoped Tenant/Subject-Kontext verifizieren
  - RLS zuerst in ephemerer DB, dann im Wartungsfenster aktivieren und FORCE setzen
  - API-, Worker-, Tenant-Admin-, Platform-Owner- und Negativtests ausführen
exact_commands_sanitized:
  - "psql '<TEST_DSN>' -v ON_ERROR_STOP=1 -f ops/postgres/gate07-data-authority-profile.sql"
  - "SEALAI_TEST_POSTGRES_DSN='<EPHEMERAL_TEST_DSN>' SEALAI_TEST_POSTGRES_CONFIRM=EPHEMERAL_ONLY pytest -q backend/sealai_v2/tests/test_postgres_gate07_integration.py"
  - "pg_dump '<PRODUCTION_DSN>' --format=custom --file='<IMMUTABLE_BACKUP_PATH>'"
  - "psql '<PRODUCTION_DSN>' -v gate07_approved=true -v target_database='<EXPECTED_DB>' -f ops/postgres/gate07-quarantine-ambiguous.sql"
  - "psql '<PRODUCTION_DSN>' -v ON_ERROR_STOP=1 -c 'ALTER TABLE <TABLE> VALIDATE CONSTRAINT <REVIEWED_CONSTRAINT>'"
  - "psql '<PRODUCTION_DSN>' -v gate07_approved=true -v runtime_scope_adapter_verified=true -v target_database='<EXPECTED_DB>' -f ops/postgres/gate07-rls-cutover.sql"
affected_services:
  - sealai-v2-api
  - memory-outbox-worker
  - knowledge-outbox-worker
  - postgres
  - keycloak-role-mapping
expected_downtime: "Wartungsfenster erforderlich; Dauer erst nach Staging-Lockmessung festlegen"
data_risk: high
security_risk: high
preconditions:
  - separate schriftliche GATE-07-Freigabe mit Zeitfenster und Befehlsumfang
  - GATE-06-Freigabe für produktive Auth-/Realm-Rollenänderungen
  - exakter Produktionsfingerprint erneut read-only verifiziert
  - 0012/0013 erfolgreich in Restore-Kopie getestet
  - aggregiertes Profil ohne ungelöste Verletzung für den jeweiligen Schritt
  - immutable Backup vorhanden und Restore in isolierter DB erfolgreich
  - Legacy-Mapping von zwei Menschen geprüft; keine automatische Zuweisung
  - transaction-scoped DB-Rollen-/GUC-Adapter implementiert und ephemer getestet
  - API/Worker verwenden nicht die Tabellen-Ownerrolle und besitzen kein BYPASSRLS
  - Platform-Owner-Zugriff auf Leads datenschutzrechtlich bestätigt
backup_status: "NICHT BELEGT; Produktionsbackup/Restore ist Pflicht vor Mutation"
verification:
  - Profiling erneut ausführen; nur aggregierte Zähler speichern
  - pg_constraint.convalidated für alle neun Constraints prüfen
  - pg_class.relrowsecurity und relforcerowsecurity für alle acht Tabellen prüfen
  - pg_roles auf NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOBYPASSRLS prüfen
  - Cross-Tenant-, Cross-Owner-, stale-case- und quarantined-row-Negativtests
  - API-, Memory-Worker- und Knowledge-Worker-Smokes mit getrennten Rollen
  - Briefing/RFQ mit zwei Cases, alter Revision, Parallelrequest, IDOR und gelöschtem Case
rollback:
  - vor COMMIT immer ROLLBACK und Deploy unverändert lassen
  - nach Schema-Migration App auf vorherigen kompatiblen Commit zurückrollen; additive Spalten belassen
  - bei RLS-Störung im freigegebenen Wartungsfenster FORCE/RLS nur mit separatem Rollback-Befehl deaktivieren und vorherige Owner/Grants aus dem gesicherten Manifest wiederherstellen
  - Quarantäne niemals automatisch aufheben; nur geprüfte Zuordnungen dürfen wieder freigegeben werden
  - Restore aus immutable Backup, falls Datenintegrität nicht anderweitig beweisbar ist
stop_conditions:
  - Datenbankname/Fingerprint weicht ab
  - Backup oder Restore-Beleg fehlt
  - Rohdaten erscheinen in Profil-/Testausgabe
  - irgendein Constraint-Verletzungszähler ist ungleich null
  - uneindeutige Ownership-Zuordnung oder ungeprüftes Backfill
  - API/Worker teilt Tabellenowner- oder BYPASSRLS-Rolle
  - transaction-scoped Tenant/Subject-Kontext fehlt oder kann über Connection-Pooling leaken
  - Lock-Timeout, unerwartete Rowcount-Abweichung oder Service-Smoke schlägt fehl
```

## Stufen und Beleggrenzen

1. **Additive Schema-Stufe:** `20260715_0012` ergänzt nullable Ownership-/Case-Grenzen,
   Authority-Epoch und die fingerprint-basierte Quarantänetabelle. `20260715_0013` installiert nur
   PostgreSQL-`NOT VALID`-Constraints. Keine Migration validiert Constraints oder aktiviert RLS.
2. **Profiling:**
   [gate07-data-authority-profile.sql](../../ops/postgres/gate07-data-authority-profile.sql) läuft
   `READ ONLY` und gibt ausschließlich Zähler aus. Ausgaben bleiben trotzdem zugriffsbeschränkte
   Betriebsevidenz.
3. **Quarantäne:**
   [gate07-quarantine-ambiguous.sql](../../ops/postgres/gate07-quarantine-ambiguous.sql) benötigt
   Ziel-DB-Abgleich, explizite Gate-Variable und interaktiv eingegebenen HMAC-Pepper. Es setzt nur
   `ownership_state='quarantined'` und speichert HMAC-Fingerprints; es weist keinen Owner zu und
   löscht keine Zeile.
4. **Backfill:** Ein Mapping darf nur aus beweisbarer Identität/Provenienz stammen. Zwei Reviewer
   signieren Record-Fingerprint, Ziel-Subject, Quelle, Ablauf und Change-Ticket. Mehrdeutige Zeilen
   bleiben quarantänisiert. Ein heuristischer Tenant- oder „erster Nutzer“-Backfill ist verboten.
5. **Validierung:** Jeder der neun Constraints wird separat mit `VALIDATE CONSTRAINT` ausgeführt.
   Nach jedem Befehl folgen Profil und Service-Smoke; der nächste Befehl benötigt einen sauberen
   Beleg. Diese Befehle stehen absichtlich nicht in Alembic.
6. **Rollen/RLS:**
   [gate07-rls-cutover.sql](../../ops/postgres/gate07-rls-cutover.sql) bleibt unerreichbar, bis der
   Runtime-Adapter pro Transaktion eine verifizierte Rolle sowie `app.tenant_id`/`app.subject_id`
   setzt und Connection-Pool-Resettests bestanden hat. FORCE RLS verhindert den Tabellenowner-
   Bypass; API und Worker dürfen niemals Tabellenowner sein.

## Derzeitige harte Blocker

- Kein aktuelles aggregiertes Produktionsprofil und kein Restore-getestetes immutable Backup.
- Kein menschlich doppelt geprüftes Legacy-Ownership-Mapping.
- Der transaction-scoped PostgreSQL-Rollen-/GUC-Adapter ist noch nicht implementiert; eine
  RLS-Aktivierung würde die laufenden Repository-Pfade blockieren oder zu unsicherem Shared-Role-
  Betrieb führen.
- Der opt-in echte PostgreSQL-Test ist vorbereitet, aber in diesem Arbeitslauf nicht ausgeführt.
- Produktive Keycloak-/DB-Rollenbelegung und Platform-Owner-Datenschutzzweck sind nicht freigegeben.
- Service- und beide Outbox-Worker sind noch nicht mit getrennten produktionsgleichen DB-Rollen
  gegen FORCE RLS verifiziert.

Deshalb lautet der zulässige DATA-001-Status: **IN_PROGRESS / GATE-07 BLOCKED**, nicht
`IMPLEMENTED_NOT_DEPLOYED` oder `VERIFIED`. Die lokalen Fail-closed-Anwendungspfade und
Cutover-Artefakte ersetzen weder den noch fehlenden Runtime-Adapter noch einen RLS-Nachweis.
