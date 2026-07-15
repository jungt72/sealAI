# AUTH-001 / AUTH-002 / AUTH-004 — Betriebs- und Sicherheitsvertrag

Stand: 2026-07-14. Dieses Dokument beschreibt den lokal implementierten Kandidaten. Es dokumentiert
keine Produktionsfreigabe und keine ausgeführte Änderung an Keycloak, Datenbank, Provider oder VPS.

## Sicherer Kandidatenzustand

- Realm-Seed und Reconciler setzen `registrationAllowed=false`; `verifyEmail=true` gilt im
  Produktionsprofil. Ohne SMTP bleibt Password-Recovery aus. Bereits nicht verifizierte Konten
  erhalten keinen Providerzugriff.
- `chat`, `chat/stream`, `briefing`, `anfrage` und der LLM-Anteil des internen Paperless-RAG-Ingests
  hängen an derselben Admission-Autorität. Sie prüft
  Kill-Switch, verifizierte E-Mail, Nutzer-/Tenant-Raten und -Quoten, Parallelität sowie globale
  Tages-/Monatsbudgets, bevor die Pipeline Providerarbeit beginnen darf.
- Die Memory- und Knowledge-Outbox, ihre direkten CLIs und die Release-Ingestion verwenden für
  `embed_provider=openai` dieselbe Postgres-Autorität. Der Kill-Switch wird vor dem Aufbau des
  Remote-Arbeitspfads geprüft. Gate, API-Embedder und Collection-Warmup sind lazy: Leere Queues und
  Delete-only-Pässe können lokale Qdrant-Arbeit ausführen, ohne den bezahlten Pfad zu öffnen. Erst
  ein tatsächlich geclaimter Upsert wird lokal gegen die kompletten Byte-/Batchgrenzen geprüft;
  danach erhält der Warmup eine eigene Admission. `fastembed` löst ebenfalls keine Admission aus.
- Produktion hat keinen In-Memory-Fallback. Fehlen Postgres, Migration oder Counter-Autorität,
  antwortet die Grenze fail-closed. Admission-Leases sind crash-tolerant; Kostenreservierungen
  werden bei Fehler/Abbruch nicht erstattet. Auditzeilen und Logs enthalten nur gehashte Scopes.
  Outbox-`last_error` speichert ausschließlich begrenzte Control-/Validierungs-/Exception-Typcodes,
  niemals rohe Provider-/Qdrant-Meldungen, URLs, Payloads oder Tracebacks.
- Ein Remote-Embedding-Aufruf ist hart auf 50 Texte, 24.000 UTF-8-Bytes je Text und 1.200.000 Bytes
  je Batch begrenzt. Memory bündelt die geclaimten Upserts in genau einen Aufruf; Knowledge tat dies
  bereits. SDK-interne Retries sind für Outbox-Embedder `0`; höchstens fünf Worker-Versuche sind
  erlaubt und jeder spätere Versuch benötigt eine neue Admission. Die Direkt-CLIs verwenden
  Batchgröße 50; geclaimte, aber nicht synchronisierte Memory-Arbeit beendet die CLI ungleich null.
  Bei hybridem Knowledge-Index wird der lokale Sparse-Batch vollständig vor Warmup und bezahltem
  Dense-Aufruf berechnet und geprüft; ein lokaler Sparse-Fehler verbraucht daher keine Admission.
  Diese Grenzen sind Beweisparameter, noch keine freigegebene Preisberechnung.
- `GET /api/v2/admin/provider-costs` zeigt nur Aggregate und Limits und ist serverseitig admin-gated.
- Request-Bodies sind bei 128 KiB begrenzt; produktive Prompts bei 8.000 Zeichen. Sensitive
  Query-Namen werden am ASGI-Rand verworfen. Case-Selektion nutzt Header bzw. Request-Body und
  browserseitig `history.state`/tab-scoped Storage, nie neue Query-Strings.
- OIDC verwendet eine tabgebundene, fünf Minuten gültige One-Time-Transaktion mit State, Nonce und
  PKCE-Verifier. Sie wird vor Netzwerk-I/O verbraucht. Callback-Parameter werden synchron aus der
  History entfernt; doppelte Parameter, Replay, falscher Response-Issuer und falsche ID-Token-
  Claims werden verworfen. Logout enthält kein `id_token_hint`.
- Der Nginx-Zugriffslog verwendet `$uri` statt `$request_uri`/`$args`, lässt Referrer weg und
  unterdrückt Callback-, OIDC- sowie Case-Record-Pfade vollständig.
- JWKS hat eine maximale Cache-SLA von 600 Sekunden, Cache-Control kann sie nur verkürzen.
  Single-flight, globales Unknown-KID-Backoff und ein begrenzter Negative-Cache verhindern Fetch-
  Verstärkung. Abgelaufener Cache plus Keycloak-Ausfall lehnt Tokens ab; entfernte Keys werden nach
  der TTL nicht mehr akzeptiert. Access Tokens sind lokal zusätzlich auf 300 Sekunden Alter plus
  höchstens 30 Sekunden Clock-Skew begrenzt.

## Mechanisch geschlossene Provideraktivierung

`SEALAI_V2_PROVIDER_REQUESTS_ENABLED=false` ist der Default in Settings, Compose, Staging und beiden
Env-Beispielen. Selbst `true` plus ein syntaktisch gültiger Digest startet den Dienst derzeit nicht:
`PROVIDER_BUDGET_ACTIVATION_IMPLEMENTED=false` blockiert die Aktivierung, bis
[provider-budget-contract.yaml](../security/provider-budget-contract.yaml) mit realen, zeitgebundenen
Preisen und mechanisch bewiesenen Call-/Token-/Retry-Grenzen unabhängig freigegeben wurde. Die
Beispielwerte `250000/10000000/100000000` sind konservative Test-/Konfigurationsdefaults, keine
genehmigte Preisberechnung.

## Externe Blocker

| Blocker | Status | Sichere Wirkung bis zur Auflösung |
|---|---|---|
| SMTP, Zustellbarkeit, Bounce-/Recovery-Prozess | `BLOCKED_EXTERNAL` | Registrierung geschlossen; Recovery aus; keine Umgehung von `email_verified` |
| Captcha/Bot-Provider samt Datenschutzfreigabe | `BLOCKED_EXTERNAL` | Nicht erforderlich, solange Self-Registration geschlossen bleibt; keine Öffnung |
| OTP-Rollout und Recovery für alle Zielrollen | `BLOCKED_EXTERNAL` | Privilegierter Owner-Flow bleibt separat gatepflichtig; keine erzwungene Massenmutation |
| Keycloak-Introspection/Admin-Event-Integration für sofortige Einzel-Session-Revocation | `BLOCKED_EXTERNAL` | Stateless SLA maximal Tokenalter 300 s + Skew; globale Keyrevocation maximal JWKS-TTL 600 s |
| Anbieterpreise, Modellgrenzen, maximaler Call-/Retry-Graph, native Provider-Hardcap | `BLOCKED_EXTERNAL` | Provider-Kill-Switch kann nicht aktiviert werden |
| Externer Alarmempfänger für Budget-/Abuse-Ereignisse | `BLOCKED_EXTERNAL` | Lokales Audit + Adminaggregate vorhanden; kein behauptetes Paging |

## Verifikation nach genehmigter Bereitstellung

1. Ohne Browser-/Nutzer-/Providerdaten Realm-Booleans und exakte Redirects zurücklesen.
2. Registrierungsseite muss fehlen; ein anonymer Registrierungsversuch darf kein Konto erzeugen.
3. Verifizierter Testnutzer: State/Nonce/PKCE-Login erfolgreich, Callback-History ohne Query.
4. Falscher, fehlender und wiederholter State: kein Tokenrequest; falscher Issuer/Audience/Nonce:
   kein veröffentlichter Access Token.
5. Unverifizierter Staging-Nutzer: Providerroute 403, aber nur in einem isolierten Build, dessen
   Testpolicy die Produktions-Aktivierungssperre nicht abschwächt.
6. Fake-Provider: Rate/Quota/Concurrency 429, Budget 402, Store-/Keycloak-Ausfall 503. Zusätzlich
   Outbox-Warmup und -Batch mit je genau einer Admission, kein SDK-Retry, kein Aufruf bei leerer bzw.
   Delete-only Queue und kein Admission-Zugriff bei `fastembed`. Leere/zu große Payloads müssen vor
   Factory, Warmup und Admission abgewiesen werden. Keine kostenpflichtige Anfrage für diese Tests.
7. Keyrotation: alter Key nach SLA abgelehnt; parallele Fake-KIDs und IdP-Ausfall erzeugen höchstens
   einen Refresh je Backoff-Fenster.
8. Nginx-Testfixture: kein Code, Token, State, `id_token_hint` oder Case-Identifier in Accesslogs.

## Rollback-Invarianten

Registrierung wird nicht wieder geöffnet, Query-/Log-Redaction nicht entfernt und Providerbudget
nicht gelockert. Bei Loginproblemen wird ausschließlich die exakte Client-/Redirectänderung auf den
gesicherten Vorzustand zurückgenommen oder ein kompatibler Fix vorgerollt. Bei JWKS-Problemen darf
auf eine kürzere TTL zurückgegangen werden, nie auf unbegrenztes Stale-Caching. Beim App-Rollback
bleibt `SEALAI_V2_PROVIDER_REQUESTS_ENABLED=false`; Migration 0011 bleibt zunächst additiv liegen,
weil ein Downgrade Audit-/Budgetdaten löschen würde.
