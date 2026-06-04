# Personas und Swimlanes

Diese Swimlanes definieren, wer in SeaLAI welche Schritte ausloesen darf, welche Daten sichtbar sind und wo Consent- oder Sicherheitsgrenzen liegen.

## User / Buyer

| Aspekt | Definition |
|---|---|
| Rolle | Beschreibt Dichtungsfall, RFQ-Bedarf, Matching-Wunsch, Supportfrage oder Dokumente. |
| Erlaubte Aktionen | Nachricht senden, Angaben bestaetigen/korrigieren, Dokumente hochladen, RFQ-Preview erzeugen, Consent fuer Export geben. |
| Verbotene Aktionen | Engineering Truth direkt setzen, fremde Tenant-Daten lesen, Hersteller automatisch kontaktieren, Compliance-Freigaben erzeugen. |
| Darf sehen | Eigene Cases, eigene Dokumente, Open Points, RFQ-Preview, Consent-Status, sichtbare Partnernetzwerk-Offenlegung. |
| Darf nicht sehen | Daten anderer Tenants, interne Partnerkonditionen, fremde Dokumente, Secrets, interne Pfade. |
| Consent/Security | RFQ Export nur nach `RFQConsentGranted`; Dokumentfreigabe nur fuer explizit enthaltene Dokumente. |
| Beispiel-Trigger | "Wir brauchen eine neue Dichtung", "Ist FKM fuer diese Oelwerte kritisch?", "Die Dichtung leckt wieder." |

## Maintenance / Instandhaltung

| Aspekt | Definition |
|---|---|
| Rolle | Meldet Ausfall, Leckage, Stillstand, Ersatzteil- oder Reorder-Bedarf. |
| Erlaubte Aktionen | Schaden beschreiben, Fotos/Dokumente hochladen, Dringlichkeit setzen, bekannte Betriebsdaten angeben. |
| Verbotene Aktionen | Finale Ursache festlegen, Haftung anerkennen, fremde Cases lesen, automatische Notfallbestellung ausloesen. |
| Darf sehen | Eigene technische Intake-Views, Emergency Triage, Failure Intake, offene Fragen. |
| Darf nicht sehen | Herstellerinterne Bewertungen, Partnerpreise, andere Organisationen. |
| Consent/Security | Uploads bleiben Evidence/Kandidaten; kein Dispatch an Hersteller ohne expliziten Export-Flow. |
| Beispiel-Trigger | "Anlage steht", "WDR undicht nach 300 Stunden", "Wir haben nur ein altes Teil." |

## Engineering / Anwendungstechnik

| Aspekt | Definition |
|---|---|
| Rolle | Prueft technische Angaben, bestaetigt Felder, erstellt Antwortentwuerfe und interne Notizen. |
| Erlaubte Aktionen | `ConfirmCaseField`, Evidence bewerten, Artefakte erzeugen, offene Punkte priorisieren. |
| Verbotene Aktionen | Compliance ohne Nachweis freigeben, finale Root Cause behaupten, LLM-Fallback als Wahrheit bestaetigen. |
| Darf sehen | Tenant-eigene Case Fields, Evidence, Audit Timeline, Drafts, Decision Understanding. |
| Darf nicht sehen | Fremde Tenants, unfreigegebene Herstellerdaten, Secrets. |
| Consent/Security | Herstellerpruefung und Quelle muessen sichtbar bleiben; Drafts duerfen keine Haftungszusage enthalten. |
| Beispiel-Trigger | "Bitte Antwortentwurf fuer Kundenanfrage", "Bitte RFQ-Preview aus aktuellem Case." |

## Manufacturer Partner

| Aspekt | Definition |
|---|---|
| Rolle | Potentieller Partner im SeaLAI-Partnernetzwerk; liefert Capability-Daten oder erhaelt spaeter explizit freigegebene RFQ-Artefakte. |
| Erlaubte Aktionen | Eigene Capabilities pflegen, eigene Sicht auf freigegebene Artefakte sehen, technische Rueckfragen stellen, wenn ein Sharing-Flow implementiert ist. |
| Verbotene Aktionen | Cases ohne Consent sehen, technische Fit Scores durch Zahlung verbessern, fremde Partnerdaten sehen. |
| Darf sehen | Nur freigegebene, recipient-spezifische Artefakte und eigene Capability-Daten. |
| Darf nicht sehen | Nicht freigegebene Dokumente, andere Partnerbewertungen, andere Tenants. |
| Consent/Security | `DocumentVisibilityApproved` und RFQ/Export-Consent sind Pflicht vor Sichtbarkeit. |
| Beispiel-Trigger | Partnerdaten aktualisiert, Fit-Matrix angefragt, freigegebenes Exportpaket verfuegbar. |

## Distributor

| Aspekt | Definition |
|---|---|
| Rolle | Kann Ersatzteil-, Legacy-Part- oder Reorder-Kontext liefern, ohne automatisch Herstellerfreigabe zu sein. |
| Erlaubte Aktionen | Artikelnummern, Zeichnungen, Lieferkontext, bekannte Herstellerreferenzen beisteuern. |
| Verbotene Aktionen | Herstellerfreigabe vortaeuschen, Preisgueltigkeit bestaetigen, fremde Kundenfaelle sehen. |
| Darf sehen | Freigegebene, tenant- und fallbezogene Informationen. |
| Darf nicht sehen | Nicht freigegebene RFQs, interne Engineering Notes anderer Parteien. |
| Consent/Security | Identitaet alter Teile bleibt unsicher, bis Evidence und Bestaetigung vorliegen. |
| Beispiel-Trigger | "Alte Artikelnummer gefunden", "Kunde braucht Ersatz fuer unbekanntes Profil." |

## SeaLAI Admin

| Aspekt | Definition |
|---|---|
| Rolle | Verwaltet Mandanten, Feature Flags, Partnerstatus, Audit- und Betriebssicht. |
| Erlaubte Aktionen | Partner `active_paid` verwalten, Tenant-Policy setzen, Audit Events pruefen. |
| Verbotene Aktionen | Secrets ausgeben, technische Wahrheit manuell manipulieren, Consent umgehen, Produktionsdaten unkontrolliert aendern. |
| Darf sehen | Betriebs- und Auditdaten nach Rollenberechtigung, keine Secrets im Klartext. |
| Darf nicht sehen | Unnoetige Kunden-IP, Dokumentinhalte ausserhalb definierter Admin-Policy. |
| Consent/Security | Admin-Aktionen muessen auditierbar sein; Tenant-Isolation bleibt Pflicht. |
| Beispiel-Trigger | Partner aktiviert/deaktiviert, LLM-Verarbeitung fuer Tenant erlaubt, Audit Review. |

## System Automation

| Aspekt | Definition |
|---|---|
| Rolle | Beobachtet Todo Views und fuehrt klar begrenzte Commands aus. |
| Erlaubte Aktionen | Dokumentextraktion, Stale-Check, RAG-Lookup, Fit-Matrix-Berechnung, Exportgenerierung nach Gate. |
| Verbotene Aktionen | Business-Regeln verstecken, Consent ueberspringen, externe Dispatches starten, finale Claims erzeugen. |
| Darf sehen | Nur fuer den Job noetige tenant-scoped Daten. |
| Darf nicht sehen | Fremde Tenants, Secrets, nicht freigegebene externe Ziele. |
| Consent/Security | Jeder Worker braucht explizite Triggerbedingungen und Failure Events. |
| Beispiel-Trigger | `EvidenceUploaded`, `CaseRevisionChanged`, `RFQConsentGranted`. |

## RAG / Knowledge System

| Aspekt | Definition |
|---|---|
| Rolle | Liefert bevorzugt kuratierte oder tenant-scoped Wissensantworten. |
| Erlaubte Aktionen | `RunRAGLookup`, Quellenstatus zuordnen, RAG-Miss melden. |
| Verbotene Aktionen | Fehlende Quelle durch Sicherheitssprache ueberdecken, fremde Tenant-Dokumente durchsuchen. |
| Darf sehen | Zugelassene Wissensbasis und tenant-erlaubte Dokumente. |
| Darf nicht sehen | Nicht berechtigte Dokumente, Secrets, interne Pfade in User Views. |
| Consent/Security | RAG-Hit braucht sichtbare Quelle und `validation_status`; RAG-Miss muss als Miss sichtbar bleiben. |
| Beispiel-Trigger | Allgemeine Dichtungsfrage, Kompatibilitaetsfrage, Supportentwurf mit Wissensbedarf. |

## LLM Research Fallback

| Aspekt | Definition |
|---|---|
| Rolle | Liefert allgemeine Orientierung, wenn RAG unzureichend ist und Fallback erlaubt ist. |
| Erlaubte Aktionen | `RunLLMResearchFallback`, Antwort als nicht validiert labeln, Kandidaten vorschlagen. |
| Verbotene Aktionen | CaseField bestaetigen, Compliance beweisen, finale Kompatibilitaet behaupten, Upload-Instruktionen ausfuehren. |
| Darf sehen | Nur policy-erlaubte, minimale Eingaben; keine nicht freigegebenen Dokumente. |
| Darf nicht sehen | Secrets, fremde Tenants, verbotene Dokumentinhalte. |
| Consent/Security | Sichtbares Label: Quelle LLM Research Fallback, `validation_status=unvalidated`, nur Orientierung. |
| Beispiel-Trigger | `KnowledgeRAGAnswerMissing` plus Fallback-Policy erlaubt. |

## Explizite Grenzen

- Dokument-Sichtbarkeit: Dokumente bleiben tenant-scoped und werden nur als Evidence/Kandidaten genutzt.
- RFQ Export: nur nach Consent, no-final-release, open-points acknowledgement und export intent.
- Manufacturer Matching: nur aktive zahlende SeaLAI-Partner; technische Bewertung ohne Zahlungseinfluss.
- Partnernetzwerk-Offenlegung: jede Fit-Matrix braucht `PartnerNetworkDisclosureAttached`.
- LLM-Fallback: sichtbar nicht validiert, nie Engineering Truth.
- Tenant-Isolation: jede dauerhafte Case-, Artifact-, Upload- und RFQ-Sicht prueft Tenant.
- Support/Complaint Drafts: keine Haftungszusage, keine finale Root Cause.
- Kein externer Dispatch: `ExternalDispatchBlocked` ist Default, bis ein gesonderter consent-gated Flow gebaut wird.
