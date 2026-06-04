# SeaLAI v0.8.3 — Event-Modeled Codex Implementation Concept

**Dokumenttyp:** Umsetzungs- und Produktkonzept für Codex App / Codex Cloud / Codex CLI  
**Version:** v0.8.3  
**Datum:** 2026-04-29  
**Ziel:** SeaLAI vom RFQ-only Copilot zu einer event-modelled Multi-Szenario-Klärungsplattform für Dichtungstechnik weiterentwickeln.  
**Arbeitsmodus:** Schrittweise, PR-basiert, testgetrieben. Nicht als Big-Bang-Aufgabe ausführen.  
**Wichtige Basis:** Bestehendes Pilot-Readiness-Konzept v1.0 und v0.8.2 bleiben fachlich gültig; v0.8.3 ergänzt das Event-Modeling-Overlay als verbindliche Umsetzungsmethode.

---

## 0. Kurzfassung für Codex

SeaLAI soll in v0.8 nicht nur RFQs vorbereiten, sondern den gesamten technischen Klärungsprozess rund um Dichtungsfälle strukturieren.

Der neue Kernflow lautet:

```text
Dichtungsfall verstehen
→ Szenario erkennen
→ technische Angaben strukturieren
→ RAG / Wissensbasis prüfen
→ falls keine Information vorhanden: LLM-Recherche-Fallback erzeugen
→ Information klar nach Validierungsstatus kennzeichnen
→ passende Artefakte erzeugen
→ optional passenden Hersteller im zahlenden SeaLAI-Partnernetzwerk matchen
→ Export / Antwortentwurf / interne Notiz mit Consent und Governance
```

SeaLAI v0.8.3 soll folgende Kernfähigkeiten erhalten:

1. **Understanding Layer**: Nutzer versteht seine Dichtungssituation besser.
2. **RFQ Readiness**: Unklare Fälle werden herstellerprüfbar.
3. **Manufacturer Fit**: Matching mit zahlenden Partnerherstellern auf Basis technischer Fähigkeiten.
4. **Technical Support & Complaint Qualification**: Herstelleranfragen, Reklamationen, Kompatibilitätsfragen strukturieren.
5. **RAG + LLM Research Fallback**: Wenn RAG nichts liefert, wird eine LLM-Recherche erstellt und als nicht validiert gekennzeichnet.
6. **Uncertainty Governance**: SeaLAI macht bekannt, unklar, unvalidiert, dokumentiert und herstellerseitig zu prüfen sichtbar.
7. **Empathic Intake & Next Best Question**: SeaLAI führt Nutzer präzise und menschlich durch Bedarfs- und Ist-Analyse.
8. **Time-to-Clarity**: SeaLAI verkürzt die Zeit von „wir haben ein Problem“ zu „wir wissen, was bekannt, was offen und wer geeignet ist“.
9. **Event-Modeled Implementation**: Jede relevante Funktion wird als Slice aus Trigger, Command, Event, View und Given-When-Then-Test spezifiziert.

---

## 1. Codex-Ausführungsregel

Dieses Dokument ist **nicht** als Prompt „baue alles sofort“ gedacht.

Codex muss v0.8.3 in einzelnen Event-Modeling-Slices und PRs umsetzen.

Jede Codex-Aufgabe muss so formuliert werden:

```text
Lies AGENTS.md und konzept/SEALAI_V08_3_EVENT_MODELED_CODEX_IMPLEMENTATION_CONCEPT.md.
Setze ausschließlich PR <NUMMER> um.
Arbeite minimalinvasiv.
Keine anderen Features bauen.
Keine produktiven Migrationen ausführen.
Keine Secrets ausgeben.
Führe die genannten Tests aus.
Gib geänderte Dateien, Tests, Risiken und offene Punkte aus.
```

Codex darf:

- Dateien lesen und ändern
- Tests, Lint und Typechecks ausführen
- neue Tests ergänzen
- Migrationen vorbereiten, aber nicht produktiv ausführen
- Feature-Flags ergänzen
- interne Dokumentation ergänzen

Codex darf nicht:

- produktive Services neu starten
- produktive Migrationen ausführen
- echte Secrets anzeigen
- echte Herstelleranfragen versenden
- Dispatch oder E-Mail-Versand aktivieren
- rechtliche / technische Freigaben behaupten
- Rankingplatzierung durch Zahlung beeinflussen
- RAG-Miss-Informationen als validierte Wahrheit persistieren

---

## 2. Aktueller Stack — Annahmen aus dem bestehenden Konzept

Codex muss diese Annahmen zunächst durch Repository-Inspektion prüfen. Falls Dateinamen abweichen, muss Codex die tatsächlichen Pfade finden und dokumentieren.

Bekannte bzw. wahrscheinliche Bestandteile:

```text
backend/
  FastAPI / Python
  app/core/config.py
  app/main.py
  app/services/rfq_preview_service.py
  app/services/rag/rag_ingest.py
  app/api/v1/endpoints/rfq.py
  app/api/v1/endpoints/rag.py
  app/agent/tests/...
  app/api/tests/...

frontend/
  React / TypeScript
  src/components/dashboard/CaseScreen.tsx
  src/components/dashboard/RfqPane.tsx
  src/lib/bff/...
  src/app/api/bff/...

knowledge / storage:
  RAG
  Qdrant wahrscheinlich vorhanden
  Uploads / attachments
  CaseField / FieldStatus / EngineeringValue
  RFQ Preview / Consent
```

Vor jedem PR muss Codex ausführen:

```bash
pwd
git status --short
git branch --show-current
rg -n "CaseField|FieldStatus|EngineeringValue|rfq|RFQ|consent|case_revision|RAG|rag|qdrant|tenant_id|organization|org_id|dispatch_enabled|attachment|upload|CaseScreen|RfqPane|settings\." backend frontend --glob '!node_modules' --glob '!dist' --glob '!build'
```

Wenn das Repo vom erwarteten Stack abweicht, muss Codex **nicht abbrechen**, sondern:

1. tatsächliche Struktur dokumentieren,
2. passenden Implementierungspfad ableiten,
3. nur den jeweiligen PR-Scope umsetzen,
4. keine neue Parallelarchitektur ohne Not erzeugen.

---

## 3. Zusammenfassung aller herausgearbeiteten USPs

### 3.1 Haupt-USP

> **SeaLAI macht industrielle Dichtungsfälle verständlich, strukturiert, herstellerprüfbar und matchbar.**

SeaLAI ist keine simple Chat-App und kein finaler Dichtungsausleger, sondern eine technische Klärungsschicht zwischen Nutzer, Einkauf, Instandhaltung, Engineering, Hersteller und Händler.

---

### 3.2 USP 1 — Dichtungssituation verstehen

SeaLAI hilft dem Nutzer, seine eigene Dichtungssituation besser zu verstehen.

SeaLAI erklärt:

- warum Medium relevant ist,
- warum Temperaturspitzen relevant sind,
- warum Druck, Bewegung und Einbauraum wichtig sind,
- warum statisch / dynamisch entscheidend ist,
- warum Materialnamen wie FKM, EPDM, NBR, PTFE oder FFKM allein nicht reichen,
- warum FDA / Food / Pharma / ATEX / Trinkwasser nicht aus Materialnamen abgeleitet werden dürfen,
- warum Wasser, Natrium, Kalium, Reinigungsmedien, Additive oder Ölalterung prüfungsrelevant sein können,
- welche Angaben dem Hersteller fehlen.

Positionierung:

```text
SeaLAI macht Dichtungsfälle verständlich — nicht nur ausfüllbar.
```

---

### 3.3 USP 2 — RFQ Readiness

SeaLAI erzeugt aus chaotischen Dichtungsfragen eine strukturierte Anfragebasis.

Output:

- bestätigte Angaben,
- unbestätigte Angaben,
- dokumentierte Angaben,
- abgeleitete Angaben,
- berechnete Angaben,
- fehlende Angaben,
- Konflikte,
- offene Punkte,
- Risiken,
- Herstellerprüfbedarf,
- Quellen / Evidence,
- Consent vor Export.

Positionierung:

```text
Von unklarer Dichtungsfrage zu prüfbarer RFQ.
```

---

### 3.4 USP 3 — Manufacturer Fit im SeaLAI Partnernetzwerk

SeaLAI hilft dem Nutzer, passende Hersteller für seine Dichtungslösung zu finden.

Wichtig:

- Es werden nur **zahlende aktive SeaLAI-Partnerhersteller** in die Empfehlungsmatrix aufgenommen.
- Der Nutzer muss das klar sehen.
- Zahlung erlaubt Aufnahme ins Netzwerk, aber darf den technischen Fit Score nicht verbessern.
- Wenn kein Partner passt, muss SeaLAI „kein geeigneter Partner im Netzwerk“ ausgeben können.

Positionierung:

```text
SeaLAI übersetzt Dichtungsfälle in Hersteller-Fit innerhalb des geprüften Partnernetzwerks.
```

Nicht sagen:

```text
SeaLAI findet den objektiv besten Hersteller weltweit.
```

Sagen:

```text
SeaLAI zeigt passende Hersteller aus dem SeaLAI-Partnernetzwerk auf Basis technischer Fit-Kriterien.
```

---

### 3.5 USP 4 — Hersteller-Dschungel entwirren

Die Dichtungstechnik ist geprägt von:

- proprietären Materialbezeichnungen,
- Compound-Codes,
- herstellerspezifischen Produktfamilien,
- uneinheitlichen Codierungen,
- nicht direkt vergleichbaren Datenblättern,
- uneinheitlichen Zertifikatslogiken.

SeaLAI soll diese Welt in eine neutrale technische Sprache übersetzen.

Beispiel:

```text
Hersteller-Code / Produktname
→ generische Materialklasse
→ mögliche technische Bedeutung
→ Quelle
→ Validierungsstatus
→ Austauschbarkeitsrisiko
→ Herstellerprüfung erforderlich
```

Positionierung:

```text
SeaLAI entwirrt proprietäre Herstellerlogiken und macht Dichtungsanforderungen vergleichbar.
```

---

### 3.6 USP 5 — Technical Support & Complaint Qualification

SeaLAI soll nicht nur neue RFQs bearbeiten, sondern auch reale Anfragen, die bei Herstellern landen.

Beispiel:

```text
In einem unserer produzierten Schneckengetriebe verwenden wir Ihre Wellendichtringe
AS 75x95x10 DIN 3760 - FKM - FDA.
Im Rahmen einer Kundenreklamation haben wir das verwendete Getriebeöl extern analysieren lassen.
Darin sind erhöhte Wasser-, Natrium- und Kaliumwerte zu sehen.
Welche Stoffe sind für die Wellendichtringe nicht empfehlenswert?
Sind die gemessenen Werte grenzwertig?
```

SeaLAI muss daraus machen:

- Case-Type: compatibility_inquiry + complaint_case,
- Produkt: Wellendichtring AS 75x95x10 DIN 3760,
- Material: FKM,
- regulatorischer Marker: FDA,
- Anwendung: Schneckengetriebe,
- Medium: Getriebeöl,
- Evidence: externer Analysebericht,
- Finding: erhöhte Wasser-, Natrium-, Kaliumwerte,
- offene Punkte: genaue Werte, Einheiten, Öltyp, Temperatur, Laufzeit, Schadensbild, chemische Form, Dichtungslos,
- sicherer Antwortentwurf,
- interne Engineering-Notiz,
- keine finale Grenzwert- oder Materialfreigabe.

Positionierung:

```text
SeaLAI hilft Herstellern, technische Anfragen und Reklamationen schneller, sicherer und nachvollziehbarer zu qualifizieren.
```

---

### 3.7 USP 6 — Uncertainty Governance

SeaLAI ist besonders vertrauenswürdig, weil es Unsicherheit nicht versteckt.

SeaLAI unterscheidet:

```text
confirmed
user_stated
documented
partner_verified
rag_verified
llm_research_unvalidated
inferred
calculated
conflicting
missing
needs_confirmation
manufacturer_review_required
```

Positionierung:

```text
SeaLAI dokumentiert, was bekannt ist — und was nicht.
```

---

### 3.8 USP 7 — Time-to-Clarity

SeaLAI reduziert die Zeit von:

```text
Wir haben ein Dichtungsproblem.
```

zu:

```text
Wir wissen, was bekannt ist, was fehlt, was kritisch ist, welche Informationen nicht validiert sind und welche Hersteller passen könnten.
```

Positionierung:

```text
SeaLAI reduziert Time-to-Clarity bei Dichtungsfällen.
```

---

### 3.9 USP 8 — Wiederverwendbares Dichtungswissen

Langfristig soll SeaLAI aus jedem Fall wiederverwendbares Wissen erzeugen:

- Anwendung,
- Medium,
- Dichtungstyp,
- Material,
- Hersteller,
- Zertifikate,
- RFQ,
- Antwort,
- Entscheidung,
- Reklamation,
- Ausfallhistorie,
- späterer Reorder.

Positionierung:

```text
SeaLAI verhindert, dass Dichtungswissen nach jeder Anfrage wieder verloren geht.
```

---

## 4. Nicht verhandelbare Produktgrenzen

SeaLAI darf nicht behaupten:

```text
Diese Dichtung ist geeignet.
Dieses Material ist freigegeben.
Dieses Material ist FDA-konform.
Dieses Produkt ist ATEX-zertifiziert.
Dieses Material ist Food Contact freigegeben.
Dieses Material ist pharmafreigegeben.
Dieses Material ist für Trinkwasser zugelassen.
Diese Werte sind sicher grenzwertig oder unkritisch.
Diese Schadensursache ist bewiesen.
Dies ist der objektiv beste Hersteller am Markt.
SeaLAI hat die technische Lösung validiert.
```

SeaLAI darf sagen:

```text
prüfungsrelevant
möglicherweise relevant
nicht entscheidbar ohne weitere Angaben
Herstellerprüfung erforderlich
Nachweis erforderlich
Quelle: RAG / Partnerdaten / Fall-Dokument / LLM-Recherche
nicht validierte Rechercheinformation
offener Punkt
keine finale technische Freigabe
Anfragebasis für Herstellerprüfung
passender Partner im SeaLAI-Partnernetzwerk
kein geeigneter Partner im aktuellen SeaLAI-Partnernetzwerk gefunden
```

---

## 5. Szenario-Architektur

SeaLAI v0.8 muss jeden Fall einem oder mehreren Szenarien zuordnen.

### 5.1 Case Types

Codex soll diese Enum ergänzen oder in bestehende CaseType-Strukturen integrieren:

```python
class CaseType(str, Enum):
    NEW_RFQ = "new_rfq"
    MANUFACTURER_MATCHING = "manufacturer_matching"
    COMPATIBILITY_INQUIRY = "compatibility_inquiry"
    COMPLAINT_CASE = "complaint_case"
    FAILURE_ANALYSIS = "failure_analysis"
    REPLACEMENT_REORDER = "replacement_reorder"
    UNKNOWN_LEGACY_PART = "unknown_legacy_part"
    DRAWING_REVIEW = "drawing_review"
    QUOTE_COMPARISON = "quote_comparison"
    COMPLIANCE_CERTIFICATE_REQUEST = "compliance_certificate_request"
    MATERIAL_SUBSTITUTION = "material_substitution"
    EMERGENCY_MRO = "emergency_mro"
    MANUFACTURER_SUPPORT_INTAKE = "manufacturer_support_intake"
```

Ein Case darf mehrere Szenario-Tags haben.

Beispiel:

```json
{
  "primary_case_type": "compatibility_inquiry",
  "secondary_case_types": ["complaint_case", "manufacturer_support_intake"],
  "scenario_confidence": 0.84
}
```

---

### 5.2 Szenario-Tabelle

| Szenario | Typischer Nutzerinput | Hauptartefakt | Wichtigste Grenze |
|---|---|---|---|
| Neuanfrage / RFQ | „Wir brauchen eine Dichtung für Medium X“ | RFQ Preview | keine finale Empfehlung |
| Hersteller-Matching | „Wer kann das liefern / prüfen?“ | Manufacturer Fit Matrix | nur Partnernetzwerk, transparent |
| Kompatibilitätsfrage | „Ist FKM für Wasser/Na/K kritisch?“ | Compatibility Matrix | keine Freigabe ohne Quelle |
| Reklamation | „Dichtung ist ausgefallen“ | Complaint Intake | keine Ursache beweisen |
| Failure Analysis | Fotos / Schadensbild / Leckage | Failure Analysis Intake | Hypothesen, keine finale Diagnose |
| Reorder | „Wir brauchen die gleiche Dichtung wieder“ | Replacement Sheet | Identität nicht vortäuschen |
| Unbekanntes Altteil | „Wir haben nur das Teil“ | Legacy Part Intake | keine sichere Identifikation ohne Evidence |
| Zeichnung prüfen | „Kann das gefertigt werden?“ | Drawing Review | keine finale Herstellbarkeitsfreigabe |
| Angebote vergleichen | „Drei Angebote, welches passt?“ | Quote Comparison | nicht billigstes blind empfehlen |
| Compliance / Zertifikat | „Reicht FDA?“ | Compliance Checklist | keine Compliance-Freigabe |
| Materialsubstitution | „PFAS-freie Alternative?“ | Substitution Risk Brief | keine pauschale Substitution |
| Emergency MRO | „Anlage steht“ | Emergency Triage | minimaler Triage-Modus, keine Überanalyse |
| Hersteller-Intake | unstrukturierte E-Mail an Hersteller | Internal Engineering Note + Reply Draft | keine Haftungszusage |



## 5A. Dichtungstyp-Architektur — Pflicht-Erweiterung für v0.8.1

**Wichtig:** `CaseType` beschreibt das Prozessszenario, nicht den Dichtungstyp.

Beispiele:

```text
compatibility_inquiry + radial_shaft_seal
new_rfq + flat_gasket
failure_analysis + mechanical_seal
replacement_reorder + hydraulic_rod_seal
manufacturer_matching + custom_profile
```

SeaLAI darf daher Dichtungstypen nicht nur als Textfeld oder Hersteller-Capability behandeln. Der Dichtungstyp muss ein eigenes, orthogonales Klassifizierungsmodell sein.

### 5A.1 Warum diese Erweiterung nötig ist

Das bisherige v0.8-Konzept enthält `seal_types` in den Herstellerfähigkeiten und im Matching-Score. Das reicht nicht aus.

Ohne eigene Dichtungstyp-Architektur entstehen diese Probleme:

- SeaLAI fragt bei Flachdichtungen fälschlich Wellendichtring-Daten ab.
- Hydraulikdichtungen werden wie O-Ringe behandelt.
- Gleitringdichtungen werden zu stark vereinfacht.
- Hersteller-Matching wird ungenau, weil `hydraulic_seal`, `flat_gasket` und `radial_shaft_seal` sehr unterschiedliche Capability-Profile brauchen.
- RAG- und LLM-Recherche-Fallbacks liefern zu allgemeine Antworten.
- RFQ-Preview und Support-Antworten verlieren technische Präzision.

Codex muss deshalb `SealType` als First-Class-Dimension implementieren.

---

### 5A.2 SealType Enum

Codex soll diese Enum ergänzen oder in eine bestehende Struktur integrieren. Namen dürfen an bestehende Projektkonventionen angepasst werden, aber die semantische Abdeckung muss erhalten bleiben.

```python
class SealFamily(str, Enum):
    STATIC = "static"
    ROTARY_DYNAMIC = "rotary_dynamic"
    LINEAR_DYNAMIC = "linear_dynamic"
    FLUID_POWER = "fluid_power"
    PROCESS_SEALING = "process_sealing"
    HYGIENIC_SEALING = "hygienic_sealing"
    SPECIAL_ENGINEERED = "special_engineered"
    UNKNOWN = "unknown"

class SealType(str, Enum):
    # Static / quasi-static
    O_RING = "o_ring"
    X_RING = "x_ring"
    BACKUP_RING = "backup_ring"
    FLAT_GASKET = "flat_gasket"
    FLANGE_GASKET = "flange_gasket"
    PROFILE_GASKET = "profile_gasket"
    BONDED_SEAL = "bonded_seal"
    CLAMP_GASKET = "clamp_gasket"

    # Rotary dynamic
    RADIAL_SHAFT_SEAL = "radial_shaft_seal"
    CASSETTE_SEAL = "cassette_seal"
    V_RING = "v_ring"
    ROTARY_SWIVEL_SEAL = "rotary_swivel_seal"
    MECHANICAL_SEAL = "mechanical_seal"

    # Hydraulic / pneumatic / linear dynamic
    HYDRAULIC_ROD_SEAL = "hydraulic_rod_seal"
    HYDRAULIC_PISTON_SEAL = "hydraulic_piston_seal"
    HYDRAULIC_WIPER = "hydraulic_wiper"
    HYDRAULIC_GUIDE_RING = "hydraulic_guide_ring"
    HYDRAULIC_BUFFER_SEAL = "hydraulic_buffer_seal"
    PNEUMATIC_ROD_SEAL = "pneumatic_rod_seal"
    PNEUMATIC_PISTON_SEAL = "pneumatic_piston_seal"
    U_CUP = "u_cup"
    CHEVRON_PACKING = "chevron_packing"

    # Process sealing
    GLAND_PACKING = "gland_packing"
    VALVE_STEM_SEAL = "valve_stem_seal"
    EXPANSION_JOINT_SEAL = "expansion_joint_seal"

    # Special / engineered
    SPRING_ENERGIZED_SEAL = "spring_energized_seal"
    METAL_SEAL = "metal_seal"
    CUSTOM_PROFILE = "custom_profile"
    MOLDED_PART_SEAL = "molded_part_seal"
    FABRIC_REINFORCED_SEAL = "fabric_reinforced_seal"

    UNKNOWN_SEAL = "unknown_seal"
```

Codex darf intern zusätzliche Subtypen ergänzen, wenn sie im bestehenden Stack bereits vorkommen. Es darf aber keine Dichtungstypen löschen, nur weil sie im MVP noch nicht vollständig bedient werden.

---

### 5A.3 Alias- und Normalisierungslogik

SeaLAI muss deutsche, englische und herstellerspezifische Bezeichnungen normalisieren.

Beispiele:

```text
Wellendichtring, Radialwellendichtring, RWDR, WDR, Simmerring, oil seal, rotary lip seal
→ radial_shaft_seal

Flachdichtung, flange gasket, cut gasket, sheet gasket
→ flat_gasket / flange_gasket

O-Ring, ORing, Rundschnurring
→ o_ring

X-Ring, Quad-Ring
→ x_ring

Gleitringdichtung, mechanical seal, face seal
→ mechanical_seal

Stangendichtung, rod seal
→ hydraulic_rod_seal oder pneumatic_rod_seal, abhängig von Medium / System

Kolbendichtung, piston seal
→ hydraulic_piston_seal oder pneumatic_piston_seal

Abstreifer, scraper, wiper
→ hydraulic_wiper

Führungsring, guide ring, wear ring
→ hydraulic_guide_ring

Stopfbuchspackung, gland packing, compression packing
→ gland_packing

Tri-Clamp-Dichtung, clamp gasket, hygienic gasket
→ clamp_gasket
```

Wenn der Dichtungstyp nicht sicher erkannt wird:

```json
{
  "seal_type": "unknown_seal",
  "seal_type_confidence": 0.34,
  "open_points": [
    "Dichtungstyp nicht sicher identifiziert",
    "Foto, Zeichnung oder Einbausituation erforderlich"
  ]
}
```

SeaLAI darf keinen Dichtungstyp vortäuschen, wenn die Evidence schwach ist.

---

### 5A.4 Seal Application Profile

Jeder Case muss zusätzlich zum `CaseType` ein `SealApplicationProfile` besitzen.

```python
class SealApplicationProfile(BaseModel):
    seal_family: SealFamily
    seal_type: SealType
    seal_type_confidence: float
    seal_type_alias_detected: str | None
    motion_type: Literal[
        "static",
        "rotary",
        "reciprocating",
        "oscillating",
        "helical",
        "unknown"
    ]
    application_domain: Literal[
        "general_industry",
        "hydraulics",
        "pneumatics",
        "process_industry",
        "food_beverage",
        "pharma_medical",
        "chemical",
        "automotive",
        "gearbox",
        "pump",
        "valve",
        "unknown"
    ]
    standard_refs: list[str]
    required_fields_missing: list[str]
    type_specific_risk_flags: list[str]
    evidence_refs: list[str]
```

Das Profil wird vom Scenario Router gemeinsam mit dem CaseType erzeugt.

---

### 5A.5 Dichtungstyp-spezifische Pflichtfelder

Codex soll diese Feldprofile als Konfiguration implementieren, nicht hart verstreut im Code.

#### O-Ring / X-Ring

Pflicht / wichtig:

```text
- Innendurchmesser / Schnurstärke oder Normgröße
- Material / Härte
- statisch oder dynamisch
- Nutgeometrie / Einbauraum
- Medium
- Temperaturbereich
- Druck / Druckspitzen
- Kompression / Squeeze / Dehnung
- Backup-Ring erforderlich?
- Zertifikatsanforderungen
```

Risiken:

```text
- falsche Nutgeometrie
- Extrusion bei Druck
- Quellung / Schrumpfung
- falsche Härte
- dynamischer Einsatz ohne Reibungs-/Verschleißbetrachtung
```

---

#### Radialwellendichtring / RWDR / WDR

Pflicht / wichtig:

```text
- Wellendurchmesser
- Gehäusebohrung
- Breite
- Bauform / Norm, z. B. AS / DIN 3760 falls angegeben
- Material Dichtlippe
- Feder / Staublippe / Schutzlippe
- Medium / Schmierstoff
- Drehzahl / Umfangsgeschwindigkeit
- Temperaturbereich
- Druckdifferenz
- Wellenoberfläche / Härte / Rauheit, falls bekannt
- Einbaurichtung
- Umgebung: Staub, Schmutz, Wasser, Chemikalien
```

Risiken:

```text
- Trockenlauf
- Wellenverschleiß
- zu hohe Druckdifferenz
- falsche Drehrichtung bei Rückförderdrall
- Schmutzeintrag
- Schmierstoff-/Additiv-/Kontaminationsproblem
```

---

#### Flachdichtung / Flanschdichtung

Pflicht / wichtig:

```text
- Flanschtyp / Norm / DN / PN oder ASME-Klasse
- Dichtungsabmessung / Lochbild
- Dichtungswerkstoff
- Dicke
- Medium
- Temperaturbereich
- Druck
- Schrauben / Anzug / Flächenpressung, falls bekannt
- Oberflächen / Rauheit
- Innen- und Außendurchmesser
- Zertifikate / TA-Luft / Food / Pharma / Chemie, falls relevant
```

Risiken:

```text
- unzureichende Flächenpressung
- falsches Material für Medium / Temperatur
- Kriechen / Relaxation
- falsche Dicke
- fehlende Kennwerte für Flanschberechnung
- nicht vergleichbare Herstellerangaben
```

---

#### Hydraulikdichtungen

Gilt für Stangendichtungen, Kolbendichtungen, Abstreifer, Führungsringe, Buffer Seals und Dichtsätze.

Pflicht / wichtig:

```text
- Stangen- oder Kolbendurchmesser
- Nutabmessungen
- Druck / Druckspitzen
- Hydraulikfluid
- Temperaturbereich
- Geschwindigkeit / Hub / Bewegungsprofil
- einfachwirkend / doppeltwirkend
- Zylinderumgebung
- Abstreifer / Führung / Backup erforderlich?
- Verschmutzung / Partikel / Wasseranteil
```

Risiken:

```text
- Extrusion
- Stick-slip
- Verschleiß
- falsche Führung
- falscher Abstreifer
- Medium-/Fluidverträglichkeit
- Druckspitzen
```

---

#### Pneumatikdichtungen

Pflicht / wichtig:

```text
- Kolben-/Stangendurchmesser
- Nutabmessungen
- Druckbereich
- Geschwindigkeit / Hub
- Schmierung ja/nein
- Luftqualität / Kondensat / Partikel
- Temperaturbereich
- Reibungsanforderung
```

Risiken:

```text
- Trockenlauf
- zu hohe Reibung
- Verschmutzung
- Kondensat
- falsche Schmierung
```

---

#### Gleitringdichtung / Mechanical Seal

Pflicht / wichtig:

```text
- Pumpen-/Aggregattyp
- Welle / Wellendurchmesser
- Medium
- Temperatur
- Druck
- Drehzahl
- Viskosität / Feststoffe / Kristallisation / Gasanteil
- Werkstoffe der Gleitflächen und Sekundärdichtungen, falls bekannt
- einfach / doppelt / cartridge / balanced / unbalanced, falls bekannt
- Spülung / Barriere / Sperrmedium, falls relevant
- ATEX / Gefahrstoff / Leckageanforderung
```

Risiken:

```text
- Trockenlauf
- Feststoffe
- Kristallisation
- falsche Spülung
- falsche Sekundärdichtung
- Sicherheits-/Explosionsschutzanforderungen
```

---

#### Stopfbuchspackung / Gland Packing

Pflicht / wichtig:

```text
- Welle / Spindel / Armaturentyp
- Stopfbuchsraum / Abmessungen
- Medium
- Temperatur
- Druck
- Geschwindigkeit / Bewegung
- Emissionsanforderung
- Schmierung / Nachstellbarkeit
```

Risiken:

```text
- Leckageanforderung nicht erfüllt
- falsche Packungswerkstoffwahl
- Wellenverschleiß
- falsche Montage / Vorspannung
```

---

#### Custom Profile / Sonderdichtung / Formteil

Pflicht / wichtig:

```text
- Zeichnung / Skizze / Foto
- Funktion der Dichtung
- Einbauraum
- Medium
- Temperatur
- Druck
- Bewegung
- Materialwunsch oder Altmaterial
- Stückzahl / Serie / Prototyp
- Toleranzen
- Zertifikate
```

Risiken:

```text
- Geometrie nicht herstellbar
- Toleranz nicht spezifiziert
- Material nur vermutet
- Werkzeugkosten / Mindestmenge unklar
```

---

### 5A.6 SealType × CaseType Matrix

Codex soll nicht für jeden Dichtungstyp eigene Szenarien erzeugen. Stattdessen gilt diese Matrixlogik:

```text
CaseType = Was passiert im Prozess?
SealType = Um welche Dichtung geht es?
Artifact = Welcher Output wird erzeugt?
```

Beispiele:

| CaseType | SealType | Output |
|---|---|---|
| new_rfq | flat_gasket | RFQ Preview mit Flansch-/Flächenpressungsfragen |
| compatibility_inquiry | radial_shaft_seal | Compatibility Matrix zu Medium, Öl, Kontamination, Lippe |
| complaint_case | hydraulic_rod_seal | Failure Intake mit Druckspitzen, Nut, Verschleiß, Führung |
| replacement_reorder | o_ring | Reorder Sheet mit Normgröße, Material, Härte, Nut |
| drawing_review | custom_profile | Drawing Review + Herstellbarkeitsfragen |
| manufacturer_matching | mechanical_seal | Partner-Fit nach Mechanical-Seal-Kompetenz, Medium, Druck, ATEX |
| emergency_mro | radial_shaft_seal | Emergency Triage mit Mindestmaßen und Express-Partnern |
| compliance_certificate_request | clamp_gasket | Zertifikatscheck für Food/Pharma/Hygienic-Anwendung |

---

### 5A.7 Auswirkungen auf Hersteller-Matching

Manufacturer Matching muss Dichtungstyp-Fit als harte Komponente behandeln.

Minimalregeln:

```text
- Wenn seal_type_confidence < 0.5:
  → keine harte Top-Empfehlung, sondern „Dichtungstyp unklar“ anzeigen.

- Wenn Partner den SealType nicht unterstützt:
  → Partner nur mit niedrigem Score oder gar nicht anzeigen.

- Wenn CaseType = complaint_case oder compatibility_inquiry:
  → Partner muss supports_failure_analysis oder supports_compatibility_review haben.

- Wenn SealType = mechanical_seal:
  → Partner ohne Mechanical-Seal-Kompetenz nicht als High-Fit ausgeben.

- Wenn SealType = flat_gasket/flange_gasket:
  → Partner-Fit muss Flachdichtung/Flanschdichtung, Werkstoff, Norm-/Zertifikatkompetenz berücksichtigen.

- Wenn SealType = hydraulic_*:
  → Partner-Fit muss Fluid-Power-Kompetenz, Druckbereich, Dichtsatz-/Zylinderkompetenz berücksichtigen.
```

Die bestehende Score-Komponente `Dichtungstyp-Fit` bleibt, muss aber gegen die neue `SealApplicationProfile`-Struktur berechnet werden.

---

### 5A.8 Auswirkungen auf RAG + LLM-Recherche-Fallback

RAG-Queries müssen den Dichtungstyp explizit enthalten.

Beispiel:

```json
{
  "case_type": "compatibility_inquiry",
  "seal_type": "radial_shaft_seal",
  "material": "FKM",
  "medium": "gear oil",
  "reported_contaminants": ["water", "sodium", "potassium"]
}
```

Wenn RAG keine ausreichende Information liefert, darf der LLM-Recherche-Fallback ausgeführt werden, aber die Ausgabe muss deutlich gekennzeichnet werden:

```text
Quelle: LLM-Recherche-Fallback
Validierungsstatus: nicht validiert
Nutzung: Orientierung, keine technische Freigabe
```

Dichtungstyp-spezifische Recherche ist Pflicht. Eine allgemeine Recherche wie `FKM Öl Wasser` ist zu unpräzise, wenn bekannt ist, dass es um einen Radialwellendichtring, eine Flachdichtung oder eine Hydraulikdichtung geht.

---

### 5A.9 Frontend-Anforderungen

Im Case Workspace muss der Dichtungstyp sichtbar und korrigierbar sein.

Pflicht-UI:

```text
Dichtungstyp erkannt:
Radialwellendichtring
Confidence: 82 %
Alias erkannt: „Wellendichtring AS 75x95x10 DIN 3760“

[ändern]
[als unbekannt markieren]
```

Wenn der Dichtungstyp unklar ist:

```text
Dichtungstyp unklar.
Bitte Foto, Zeichnung, Normbezeichnung oder Einbausituation ergänzen.
```

Der Tab „Technischer Hintergrund“ muss seine Inhalte nach SealType variieren.

Beispiele:

```text
RWDR → Welle, Gehäusebohrung, Lippe, Drehzahl, Druckdifferenz, Schmierung
Flachdichtung → Flansch, Flächenpressung, Schrauben, Medium, Temperatur
Hydraulikdichtung → Nut, Druck, Hub, Geschwindigkeit, Führung, Abstreifer
Gleitringdichtung → Medium, Druck, Drehzahl, Gleitflächen, Spülung, Trockenlauf
```

---

### 5A.10 Zusätzlicher PR für Codex

Diesen PR in den bestehenden v0.8-Plan einschieben:

```text
PR 2A — SealType Taxonomy + Type-Specific Intake Profiles
```

Scope:

- `SealFamily` und `SealType` Enum ergänzen.
- Alias-Normalisierung implementieren.
- `SealApplicationProfile` Modell ergänzen.
- Dichtungstyp-spezifische Pflichtfelder als Konfiguration anlegen.
- Scenario Router erweitert CaseType-Erkennung um SealType-Erkennung.
- Manufacturer Matching nutzt `SealApplicationProfile`.
- RAG Query Builder enthält SealType.
- Frontend zeigt Dichtungstyp, Confidence und Änderungsmöglichkeit.

Akzeptanzkriterien:

- „Wellendichtring AS 75x95x10 DIN 3760 FKM FDA“ wird als `radial_shaft_seal` erkannt.
- „Flachdichtung DN80 PN16 Graphit“ wird als `flange_gasket` oder `flat_gasket` erkannt.
- „Stangendichtung Hydraulikzylinder“ wird als `hydraulic_rod_seal` erkannt.
- „Kolbendichtung Pneumatik“ wird als `pneumatic_piston_seal` erkannt.
- „Gleitringdichtung Pumpe Chemie“ wird als `mechanical_seal` erkannt.
- Unklare Eingaben werden als `unknown_seal` mit offenen Punkten behandelt.
- RFQ-Preview fragt je Dichtungstyp unterschiedliche Pflichtfelder ab.
- Hersteller-Fit berücksichtigt Dichtungstyp als Score-Komponente.
- RAG- und LLM-Recherche-Fallback enthalten Dichtungstyp im Query-Kontext.

Tests:

```bash
pytest backend/app/api/tests -k "seal_type or scenario_router or manufacturer_fit"
pytest backend/app/agent/tests -k "seal_type or rag_query or fallback"
npm test -- --runInBand seal-type manufacturer-fit
npm run lint
```

---

### 5A.11 Sicherheits- und Trust-Grenzen

SeaLAI darf aus dem Dichtungstyp keine finale Empfehlung ableiten.

Nicht erlaubt:

```text
„Für diesen Flansch ist diese Flachdichtung geeignet.“
„Diese Hydraulikdichtung ersetzt sicher das Altteil.“
„Diese Gleitringdichtung ist freigegeben.“
```

Erlaubt:

```text
„Der Fall sieht nach einer Flansch-/Flachdichtungsanfrage aus. Für eine Herstellerprüfung fehlen Flanschstandard, DN/PN, Medium, Temperatur, Druck und Dichtungswerkstoff.“

„Die Anfrage deutet auf eine Hydraulik-Stangendichtung hin. Für eine prüfbare Anfrage fehlen Nutabmessungen, Druckspitzen, Fluid, Hub/Geschwindigkeit und Schadensbild.“

„Innerhalb des SeaLAI-Partnernetzwerks passen Hersteller mit Mechanical-Seal-Kompetenz, Chemieanwendung und Kompatibilitätsprüfung am besten. Eine technische Freigabe erfolgt nicht durch SeaLAI.“
```

---


## 5B. Conversation Intelligence Layer — Pflicht-Erweiterung für v0.8.2

**Wichtig:** SeaLAI muss nicht nur technische Felder extrahieren. SeaLAI muss eine seriöse, empathische und präzise Bedarfs- bzw. Ist-Analyse der Dichtungssituation führen.

Das ist eine eigene Produktschicht.

Ziel:

```text
Unstrukturierter Nutzerinput
→ Gesprächsintention erkennen
→ Nutzerzustand / Tonlage erkennen
→ Dichtungssituation schrittweise verstehen
→ gezielte nächste Frage stellen
→ technische Vollständigkeit erhöhen
→ passende Erklärung / Artefakt / Hersteller-Matching ableiten
```

SeaLAI soll sich nicht wie ein beliebiger Chatbot verhalten, sondern wie ein ruhiger, fachlich präziser technischer Klärungsassistent.

---

### 5B.1 Warum diese Erweiterung nötig ist

Die bisherigen v0.8/v0.8.1-Konzepte enthalten:

- Understanding Layer,
- offene Punkte,
- FieldStatus,
- RAG-Fallback,
- Scenario Router,
- SealType Taxonomy,
- Hersteller-Matching.

Das reicht technisch, aber noch nicht vollständig für Vertrauen und Seriosität.

Was noch explizit ergänzt werden muss:

- empathische Gesprächsführung,
- kontrollierter Umgang mit Small Talk, Frust, unklarer Sprache und Off-Topic,
- präzise Bedarfsermittlung,
- Ist-Analyse der vorhandenen Dichtungssituation,
- priorisierte Rückfragen,
- schrittweise Frage-Strategie statt langer Formularabfrage,
- allgemeine Dichtungstechnik-Fragen ohne Case-Zwang,
- Übergang von allgemeiner Frage zu konkretem Case.

SeaLAI muss also zwischen „Chat“, „Wissensfrage“, „konkreter Dichtungsfall“ und „Hersteller-/RFQ-Prozess“ unterscheiden.

---

### 5B.2 Conversation Intent Taxonomy

Codex soll zusätzlich zu `CaseType` und `SealType` eine `ConversationIntent`-Klassifikation implementieren.

```python
class ConversationIntent(str, Enum):
    SMALL_TALK = "small_talk"
    OFF_TOPIC = "off_topic"
    USER_FRUSTRATION = "user_frustration"
    GENERAL_SEALING_QUESTION = "general_sealing_question"
    EDUCATIONAL_EXPLANATION = "educational_explanation"
    NEEDS_ANALYSIS_START = "needs_analysis_start"
    CURRENT_STATE_ANALYSIS = "current_state_analysis"
    RFQ_PREPARATION = "rfq_preparation"
    MANUFACTURER_MATCHING_REQUEST = "manufacturer_matching_request"
    COMPATIBILITY_QUESTION = "compatibility_question"
    COMPLAINT_OR_FAILURE = "complaint_or_failure"
    REORDER_OR_LEGACY_PART = "reorder_or_legacy_part"
    DOCUMENT_ANALYSIS_REQUEST = "document_analysis_request"
    QUOTE_COMPARISON_REQUEST = "quote_comparison_request"
    EMERGENCY_HELP = "emergency_help"
    UNKNOWN = "unknown"
```

`ConversationIntent` beschreibt die Absicht im Dialog.  
`CaseType` beschreibt das Prozessszenario.  
`SealType` beschreibt die technische Dichtungsklasse.

Beispiel:

```json
{
  "conversation_intent": "user_frustration",
  "case_type": "complaint_case",
  "seal_type": "radial_shaft_seal"
}
```

Oder:

```json
{
  "conversation_intent": "general_sealing_question",
  "case_type": null,
  "seal_type": "flat_gasket"
}
```

---

### 5B.3 Response Modes

SeaLAI soll je nach Gesprächsintention einen passenden Antwortmodus wählen.

```python
class ResponseMode(str, Enum):
    EMPATHIC_ACKNOWLEDGEMENT = "empathic_acknowledgement"
    CLARIFYING_QUESTION = "clarifying_question"
    TECHNICAL_EXPLANATION = "technical_explanation"
    GUIDED_INTAKE = "guided_intake"
    CASE_SUMMARY = "case_summary"
    NEXT_BEST_QUESTION = "next_best_question"
    RAG_ANSWER = "rag_answer"
    UNVALIDATED_RESEARCH_ANSWER = "unvalidated_research_answer"
    RFQ_ARTIFACT_PREVIEW = "rfq_artifact_preview"
    MANUFACTURER_FIT_PREVIEW = "manufacturer_fit_preview"
    SUPPORT_REPLY_DRAFT = "support_reply_draft"
    REFUSAL_OR_BOUNDARY = "refusal_or_boundary"
```

SeaLAI darf nicht bei jeder Nachricht sofort eine RFQ erzwingen. Ein Nutzer darf auch einfach fragen:

```text
Was ist der Unterschied zwischen FKM und EPDM?
Was ist eine Flachdichtung?
Warum ist Temperatur bei Dichtungen wichtig?
Ich habe keine Ahnung, welche Dichtung das ist.
```

In solchen Fällen soll SeaLAI kurz und hilfreich erklären und erst dann anbieten bzw. logisch überleiten:

```text
Wenn es um einen konkreten Fall geht, sind Medium, Temperatur, Druck und Dichtungstyp die wichtigsten nächsten Angaben.
```

---

### 5B.4 Empathie- und Seriositätsregeln

SeaLAI soll menschlich, aber nicht kumpelhaft auftreten.

Erlaubter Stil:

```text
Ich verstehe den Punkt. Bei Dichtungen ist genau diese Unklarheit häufig kritisch.
Wir gehen das sauber Schritt für Schritt durch.
Auf Basis Ihrer Angaben kann ich noch keine sichere Bewertung ableiten.
Die wichtigste nächste Information ist ...
```

Nicht erlaubter Stil:

```text
Kein Problem, ich weiß die perfekte Dichtung.
Das ist easy.
Nimm einfach FKM.
Der Hersteller X ist der beste.
Alles gut, das ist unkritisch.
```

Bei Frust oder chaotischer Sprache:

```text
„Die Dichtung nervt, alles undicht, keiner weiß was verbaut ist.“
```

SeaLAI soll reagieren:

```text
Das klingt nach einem akuten Klärungsfall. Ich würde zuerst trennen:
1. Welche Dichtung ist verbaut?
2. Wo tritt die Leckage auf?
3. Welche Betriebsbedingungen liegen an?
Die wichtigste erste Frage: Haben Sie ein Foto, eine Bezeichnung oder Maße der ausgebauten Dichtung?
```

Nicht:

```text
Bitte füllen Sie dieses Formular mit 18 Feldern aus.
```

---

### 5B.5 Need Analysis vs. Current State Analysis

SeaLAI muss zwei Analysearten unterscheiden.

#### Bedarfanalyse

Frage:

```text
Was wird gebraucht?
```

Typische Ziele:

- neue Dichtung,
- Ersatzteil,
- Lieferant / Hersteller finden,
- technische Einschätzung,
- Reklamation beantworten,
- Zertifikat beschaffen,
- Ausfallursache eingrenzen,
- Angebot vergleichen.

#### Ist-Analyse

Frage:

```text
Was liegt aktuell tatsächlich vor?
```

Typische Daten:

- aktueller Dichtungstyp,
- vorhandene Bezeichnung,
- Maße,
- Material,
- Medium,
- Temperatur,
- Druck,
- Bewegung,
- Einbauraum,
- Zustand / Schadensbild,
- Dokumente / Fotos / Analyseberichte,
- bisheriger Hersteller,
- Anwendung / Anlage,
- Dringlichkeit.

Codex soll diese getrennt speichern:

```python
class NeedsAnalysis(BaseModel):
    user_goal: str | None
    desired_outcome: list[str]
    urgency: Literal["low", "normal", "high", "emergency", "unknown"]
    decision_needed: list[str]
    stakeholder_role: Literal[
        "maintenance",
        "engineering",
        "procurement",
        "quality",
        "manufacturer_support",
        "distributor",
        "unknown"
    ]
    next_action_requested: str | None

class CurrentStateAnalysis(BaseModel):
    known_facts: list[str]
    missing_facts: list[str]
    conflicts: list[str]
    assumptions: list[str]
    evidence_refs: list[str]
    seal_application_profile: SealApplicationProfile | None
    completeness_score: float
```

---

### 5B.6 Completeness Score

SeaLAI soll einen technischen Vollständigkeitsgrad berechnen.

```python
class CompletenessScore(BaseModel):
    overall: float
    by_category: dict[str, float]
    blocking_missing_fields: list[str]
    recommended_next_questions: list[str]
```

Beispiel:

```json
{
  "overall": 0.42,
  "by_category": {
    "seal_identity": 0.70,
    "medium": 0.40,
    "temperature": 0.00,
    "pressure": 0.00,
    "motion": 0.60,
    "evidence": 0.50
  },
  "blocking_missing_fields": [
    "temperature_range",
    "pressure",
    "exact_medium_or_oil_type"
  ],
  "recommended_next_questions": [
    "Welches Medium bzw. welches Öl steht mit der Dichtung in Kontakt?",
    "Welche Betriebstemperatur und Temperaturspitzen treten auf?",
    "Liegt Druck oder Druckdifferenz an der Dichtung an?"
  ]
}
```

Der Score darf nicht als „Freigabereife“ dargestellt werden. Er ist nur ein Klärungsgrad.

Pflichtlabel:

```text
Klärungsgrad, keine technische Freigabe.
```

---

### 5B.7 Next Best Question Engine

SeaLAI soll nie wahllos viele Fragen stellen. Es soll die jeweils wichtigsten nächsten Fragen priorisieren.

Regeln:

1. Maximal 1–3 Fragen pro Antwort.
2. Emergency-Modus: nur die eine wichtigste nächste Frage.
3. Erst Dichtungstyp und Ziel klären, dann Details.
4. Typ-spezifische Pflichtfelder aus `SealType` berücksichtigen.
5. Bereits bekannte oder aus Evidence dokumentierte Angaben nicht erneut fragen.
6. Bei Konflikten gezielt nach Entscheidung / Bestätigung fragen.
7. Fragen begründen, aber kurz.

Beispiel für RWDR:

```text
Die wichtigste offene Information ist der Druck bzw. die Druckdifferenz am Wellendichtring, weil RWDR je nach Bauform nur begrenzt druckbelastbar sind.
Können Sie sagen, ob im Getriebe ein Überdruck anliegt oder ob es nur um Öl-/Schmutzabdichtung geht?
```

Beispiel für Flachdichtung:

```text
Für eine Flachdichtung ist die Flansch- bzw. Anschlussnorm entscheidend, weil daraus Lochbild, Dichtfläche und Flächenpressung abgeleitet werden.
Ist es ein DN/PN-Flansch, ASME-Flansch oder eine freie Geometrie nach Zeichnung?
```

Beispiel für allgemeine Frage:

```text
Allgemein gesagt: EPDM und FKM unterscheiden sich stark bei Medienbeständigkeit und Temperaturverhalten.
Geht es bei Ihrer Frage um eine konkrete Anwendung oder möchten Sie nur den grundsätzlichen Unterschied verstehen?
```

---

### 5B.8 Intake Conversation State

Codex soll einen speicherbaren Dialogzustand ergänzen.

```python
class IntakeConversationState(BaseModel):
    case_id: UUID | None
    conversation_intent: ConversationIntent
    response_mode: ResponseMode
    needs_analysis: NeedsAnalysis | None
    current_state_analysis: CurrentStateAnalysis | None
    completeness_score: CompletenessScore | None
    asked_questions: list[str]
    answered_questions: list[str]
    avoided_repeated_questions: list[str]
    next_best_questions: list[str]
    user_tone: Literal[
        "neutral",
        "confused",
        "frustrated",
        "urgent",
        "expert",
        "casual",
        "unknown"
    ]
    should_create_case: bool
    should_generate_artifact: bool
```

---

### 5B.9 Allgemeine Fragen zur Dichtungstechnik

SeaLAI muss allgemeine technische Fragen beantworten können, ohne sofort einen Case zu erzwingen.

Beispiele:

```text
Was ist der Unterschied zwischen FKM und EPDM?
Was macht eine Gleitringdichtung?
Was ist eine Flachdichtung?
Warum ist das Medium wichtig?
Was bedeutet DIN 3760?
Was ist ein Radialwellendichtring?
Was sind typische Ausfallursachen bei Hydraulikdichtungen?
```

Antwortlogik:

1. RAG prüfen.
2. Falls RAG keine Information enthält: LLM-Recherche-Fallback.
3. Falls Fallback genutzt wird: klar als nicht validiert kennzeichnen.
4. Keine finale Anwendungsempfehlung geben.
5. Wenn die Frage konkret wirkt, maximal eine Anschlussfrage stellen.

Beispiel:

```text
Ein Radialwellendichtring dichtet typischerweise eine rotierende Welle gegenüber Gehäuse/Umgebung ab. Relevant sind u. a. Wellendurchmesser, Gehäusebohrung, Dichtlippenmaterial, Medium/Schmierstoff, Drehzahl, Temperatur und Druckdifferenz.

Geht es bei Ihnen um einen konkreten Wellendichtring oder möchten Sie nur den Grundaufbau verstehen?
```

---

### 5B.10 Small Talk, Off-Topic und „Shit Chat“

SeaLAI soll einfache Small-Talk- oder unsaubere Eingaben professionell behandeln.

#### Small Talk

Input:

```text
Hallo
Danke
Wer bist du?
Kannst du mir helfen?
```

Antwort:

```text
Ja. Ich kann Ihnen helfen, Dichtungsfälle zu verstehen, fehlende Angaben zu erkennen, RFQs vorzubereiten und passende Hersteller im SeaLAI-Partnernetzwerk zu finden.
Worum geht es gerade: neue Dichtung, Ersatzteil, Reklamation oder allgemeine Frage?
```

#### Off-Topic

Input:

```text
Schreib mir ein Gedicht.
Was ist der beste Fußballverein?
```

Antwort:

```text
Dabei bin ich hier nicht der richtige Assistent. Ich bin auf Dichtungstechnik, RFQ-Klärung, Hersteller-Fit und technische Supportfälle rund um Dichtungen ausgelegt.
```

Optional eine Rückführung:

```text
Wenn es um eine Dichtung geht, beschreiben Sie einfach kurz die Anwendung oder das Problem.
```

#### Frust / vulgäre Sprache / chaotische Eingaben

Input:

```text
Diese scheiß Dichtung leckt schon wieder.
```

Antwort:

```text
Das klingt nach einem wiederkehrenden Ausfall. Ich helfe, das strukturiert einzugrenzen.
Die wichtigste erste Frage: Um welchen Dichtungstyp geht es — z. B. Wellendichtring, O-Ring, Flachdichtung, Hydraulikdichtung — oder haben Sie ein Foto/eine Bezeichnung?
```

SeaLAI soll nicht moralisieren, aber auch nicht den Ton imitieren.

---

### 5B.11 Case Creation Threshold

SeaLAI soll nicht für jede Nachricht automatisch einen Case erzeugen.

```python
class CaseCreationDecision(BaseModel):
    should_create_case: bool
    reason: str
    required_user_confirmation: bool
```

Regeln:

Case erzeugen, wenn:

- konkrete Anwendung,
- konkrete Dichtung,
- RFQ-Wunsch,
- Hersteller-Matching-Wunsch,
- Reklamation,
- Support-/Kompatibilitätsfall,
- Upload / Dokumentanalyse,
- Reorder / Ersatzteil.

Keinen Case erzeugen, wenn:

- Small Talk,
- rein allgemeine Wissensfrage,
- Off-Topic,
- Nutzer fragt nur nach Begriffserklärung.

Grenzfall:

```text
„Was ist FKM und wäre das für Öl geeignet?“
```

SeaLAI antwortet allgemein und fragt:

```text
Geht es um eine konkrete Anwendung mit Öl, Temperatur und Dichtungstyp?
```

Erst danach Case.

---

### 5B.12 Dialogue API Contract

Codex soll vorhandene Chat-/Agentenroute prüfen und, falls nötig, eine kompatible Route ergänzen.

```http
POST /api/v1/dialogue/turn
```

Request:

```json
{
  "case_id": "uuid-or-null",
  "message": "Diese Dichtung leckt schon wieder.",
  "uploaded_evidence_refs": [],
  "allow_case_creation": true,
  "allow_rag": true,
  "allow_fallback_research": true
}
```

Response:

```json
{
  "conversation_intent": "user_frustration",
  "response_mode": "next_best_question",
  "case_creation": {
    "should_create_case": true,
    "reason": "Konkreter Dichtungs-/Ausfallfall",
    "required_user_confirmation": false
  },
  "needs_analysis": {
    "user_goal": "Leckage/Ausfall eingrenzen",
    "desired_outcome": ["failure_analysis_intake"],
    "urgency": "unknown"
  },
  "current_state_analysis": {
    "known_facts": ["Dichtung leckt wiederholt"],
    "missing_facts": ["Dichtungstyp", "Medium", "Temperatur", "Druck", "Schadensbild"],
    "conflicts": [],
    "assumptions": [],
    "evidence_refs": [],
    "completeness_score": 0.12
  },
  "next_best_questions": [
    "Um welchen Dichtungstyp geht es — z. B. Wellendichtring, O-Ring, Flachdichtung oder Hydraulikdichtung?"
  ],
  "answer": "Das klingt nach einem wiederkehrenden Ausfall. Ich helfe, das strukturiert einzugrenzen. Die wichtigste erste Frage: Um welchen Dichtungstyp geht es — z. B. Wellendichtring, O-Ring, Flachdichtung oder Hydraulikdichtung?"
}
```

---

### 5B.13 Frontend-Anforderungen

Im UI soll der Gesprächsmodus sichtbar, aber nicht störend sein.

Pflicht:

```text
- Erkanntes Anliegen
- Klärungsgrad
- Nächste wichtigste Frage
- Was bereits bekannt ist
- Was noch fehlt
```

Beispiel:

```text
Anliegen: Reklamation / Leckage
Dichtungstyp: noch unklar
Klärungsgrad: 12 % — keine technische Freigabe
Nächste Frage: Um welchen Dichtungstyp geht es?
```

Für allgemeine Wissensfragen:

```text
Anliegen: Allgemeine Dichtungstechnik-Frage
Kein Case angelegt
```

---

### 5B.14 Tests für Conversation Intelligence

Pflichttests:

1. `Hallo` → SMALL_TALK, kein Case, kurze hilfreiche Orientierung.
2. `Kannst du mir bei einer Dichtung helfen?` → NEEDS_ANALYSIS_START, fragt nach Ziel.
3. `Was ist ein Wellendichtring?` → GENERAL_SEALING_QUESTION, kein Case, kurze Erklärung.
4. `Was ist FKM und ist das für Öl geeignet?` → GENERAL_SEALING_QUESTION oder COMPATIBILITY_QUESTION, fragt nach konkreter Anwendung.
5. `Diese scheiß Dichtung leckt schon wieder` → USER_FRUSTRATION + COMPLAINT_OR_FAILURE, empathische Antwort, eine nächste Frage.
6. `Wir brauchen eine Dichtung für Medium X` → RFQ_PREPARATION + NEW_RFQ.
7. `Wer kann das herstellen?` → MANUFACTURER_MATCHING_REQUEST.
8. Wiederholte Nachricht darf nicht dieselbe Frage erneut stellen, wenn sie schon beantwortet wurde.
9. Emergency-Hinweis wie `Anlage steht` → EMERGENCY_HELP, maximal eine wichtigste nächste Frage.
10. Off-Topic → Rückführung ohne Case.
11. Allgemeine Frage mit RAG-Miss → LLM-Fallback mit Label `nicht validiert`.
12. Technische konkrete Frage mit RAG-Miss → LLM-Fallback, aber keine Freigabe.

---

### 5B.15 Zusätzlicher PR für Codex

Diesen PR in den bestehenden v0.8-Plan einschieben:

```text
PR 2B — Conversation Intelligence + Empathic Intake
```

Scope:

- `ConversationIntent` und `ResponseMode` ergänzen.
- `NeedsAnalysis`, `CurrentStateAnalysis`, `CompletenessScore`, `IntakeConversationState` implementieren.
- Next-Best-Question Engine implementieren.
- Case-Creation-Threshold implementieren.
- Dialogue API kompatibel ergänzen.
- Small Talk / Off-Topic / Frust / allgemeine Fragen testen.
- Verbindung zu `CaseType`, `SealType`, RAG und LLM-Fallback herstellen.

Akzeptanzkriterien:

- SeaLAI reagiert empathisch und seriös auf chaotische oder frustrierte Eingaben.
- SeaLAI stellt maximal 1–3 gezielte Fragen.
- Allgemeine Dichtungstechnik-Fragen werden beantwortet, ohne automatisch einen Case zu erzeugen.
- Konkrete Dichtungsfälle werden in CaseType + SealType + Needs/Current State Analyse überführt.
- Klärungsgrad und offene Punkte werden sichtbar.
- Bereits beantwortete Fragen werden nicht stumpf wiederholt.
- RAG-Miss führt auch bei allgemeinen Fragen zum sauber gelabelten LLM-Recherche-Fallback.
- Keine finale technische Freigabe.

Tests:

```bash
pytest backend/app/api/tests -k "dialogue or conversation or intake or next_best_question"
pytest backend/app/agent/tests -k "conversation or small_talk or frustration or general_question"
npm test -- --runInBand dialogue intake conversation
npm run lint
```

---

---

## 5C. Event-Modeling-Overlay — Pflicht-Erweiterung für v0.8.3

### 5C.1 Zweck

v0.8.3 professionalisiert das Konzept durch ein verbindliches Event-Modeling-Overlay.

Das Ziel ist nicht, zwingend Event Sourcing einzuführen. Das bestehende Stack-Modell mit FastAPI, SQLAlchemy/Postgres, Redis, Qdrant, LangGraph/LangChain und Next.js bleibt gültig. Event Modeling dient hier als **Umsetzungsmethode**, damit Codex die Produktlogik nicht als lose Module baut, sondern als nachvollziehbare Informationsflüsse.

Für SeaLAI ist dieser Ansatz besonders passend, weil das Produkt von folgenden Fragen lebt:

```text
Was weiß SeaLAI?
Woher weiß SeaLAI es?
Wer hat es gesagt, dokumentiert, berechnet, validiert oder bestätigt?
Welche Unsicherheit bleibt?
Welche View zeigt es?
Welches Artefakt darf daraus entstehen?
Welche Handlung ist jetzt erlaubt?
```

Die v0.8.3-Regel lautet:

> Jede neue produktive Funktion muss als Slice beschrieben werden: Trigger → Command → Event(s) → View → Given-When-Then-Test.

---

### 5C.2 Event Modeling ist Umsetzungsmethode, nicht Stack-Ersatz

Codex darf aus diesem Overlay **keinen großen Architekturwechsel** ableiten.

Zulässig:

```text
- Command-/Event-/View-Begriffe als Domänenverträge nutzen
- bestehende Services nach Slices schneiden
- Events als Audit-/Domain-Events persistieren, falls vorhandene Struktur passt
- traditionelle Tabellen weiterverwenden
- Views als Backend-Projektionen, DTOs oder Read Models bereitstellen
- Automationen als Todo-Views + Worker/Service-Schritte modellieren
```

Nicht zulässig ohne expliziten Auftrag:

```text
- vollständiges Event-Sourcing-System einführen
- bestehende Datenbankstruktur ersetzen
- produktive Migrationen ausführen
- Framework austauschen
- Message-Bus großflächig einführen
- bestehende produktive Services umbauen, nur um Event Modeling „reinzuquetschen“
```

Event Modeling wird hier genutzt, um **rework-arme, testbare, erklärbare Slices** zu bauen.

---

### 5C.3 Verbindliche Begriffe

#### Trigger

Ein Trigger ist der Auslöser eines Use Cases.

Beispiele:

```text
- Nutzer sendet Nachricht
- Nutzer lädt Dokument hoch
- Nutzer klickt „RFQ-Preview erstellen“
- Nutzer bestätigt Consent
- Nutzer fragt nach passendem Hersteller
- System erkennt CaseRevisionChanged
- Parser-Todo wird automatisch verarbeitet
```

#### Command

Ein Command beschreibt die Absicht, den Systemzustand zu verändern oder einen produktiven Verarbeitungsschritt auszuführen.

Commands sind im Imperativ zu benennen.

Beispiele:

```text
ClassifyConversationIntent
CreateOrUpdateSealingCase
NormalizeSealType
ProposeCaseFieldCandidate
ConfirmCaseField
AttachEvidenceDocument
ExtractEvidenceCandidates
AnswerKnowledgeQuestion
GenerateRFQPreview
GrantArtifactConsent
ComputeManufacturerFitMatrix
QualifyCompatibilityInquiry
GenerateCustomerReplyDraft
GenerateInternalEngineeringNote
MarkArtifactStale
```

#### Event

Ein Event beschreibt einen gespeicherten oder auditierbaren Business-Fakt, der passiert ist.

Events sind im Past Tense zu benennen.

Beispiele:

```text
UserMessageReceived
ConversationIntentClassified
ResponseModeSelected
CaseCreated
CaseTypeAssigned
SealTypeCandidateDetected
SealTypeNormalized
CaseFieldCandidateProposed
CaseFieldConfirmed
EvidenceUploaded
DocumentParseAttempted
ExtractionCandidateCreated
KnowledgeRAGLookupRequested
KnowledgeRAGAnswerFound
KnowledgeRAGAnswerMissing
LLMResearchFallbackUsed
KnowledgeAnswerGenerated
RFQPreviewGenerated
RFQPreviewFrozenToCaseRevision
RFQConsentGranted
RFQConsentRejected
ArtifactMarkedStale
ManufacturerFitRequested
PartnerCandidatesFiltered
ManufacturerFitComputed
NoSuitablePartnerFound
PartnerNetworkDisclosureAttached
CompatibilityInquiryCreated
MissingInformationIdentified
CustomerReplyDraftGenerated
InternalEngineeringNoteGenerated
ComplaintIntakeCreated
FailureAnalysisIntakeCreated
```

Wichtig:

```text
Nicht jede UI-Aktion ist ein Event.
„UserViewedPage“ ist in der Regel kein Business-Event.
„RFQPreviewGenerated“ ist ein Business-Event.
```

#### View

Eine View liest vorhandene Fakten, interpretiert sie und macht sie für UI, Export, Report oder Automation nutzbar.

Beispiele:

```text
ConversationFrontdoorView
KnowledgeAnswerView
SourceValidationBadgeView
CaseWorkspaceProjection
DecisionUnderstandingView
OpenPointsView
SealApplicationProfileView
TypeSpecificQuestionView
RFQPreviewView
ConsentRequiredView
ExportReadyView
ManufacturerFitMatrixView
PartnerDisclosureView
CompatibilityMatrixView
CustomerReplyDraftView
InternalEngineeringNoteView
DocumentEvidencePanel
AuditTimelineView
AutomationTodoView
```

---

### 5C.4 Grundregel: Jedes Feld braucht Herkunft und Ziel

Codex darf kein neues produktives Feld einführen, ohne dessen Herkunft und Ziel zu klären.

Für jedes relevante Feld gilt:

```text
Field
→ Origin
→ Command
→ Event
→ State / Table / Projection
→ View / Artifact
→ Test
```

Beispiel:

| Feld | Ursprung | Command | Event | Ziel-View / Artefakt |
|---|---|---|---|---|
| Medium | Nutzer, Upload, Dokument | ProposeCaseFieldCandidate | CaseFieldCandidateProposed | CaseWorkspace, RFQPreview |
| Temperatur | Nutzer, Upload, Berechnung | ConfirmCaseField | CaseFieldConfirmed | RFQPreview, OpenPoints |
| SealType | Nutzertext, Alias, Dokument | NormalizeSealType | SealTypeNormalized | SealApplicationProfile, TypeSpecificQuestionView |
| Wasserwert im Ölbericht | Upload/Laborbericht | ExtractEvidenceCandidates | ExtractionCandidateCreated | CompatibilityMatrix |
| LLM-Fallback-Info | LLM-Recherche bei RAG-Miss | AnswerKnowledgeQuestion | LLMResearchFallbackUsed | KnowledgeAnswerView mit „nicht validiert“ |
| Fit Score | Partnerdaten + CaseProfile | ComputeManufacturerFitMatrix | ManufacturerFitComputed | ManufacturerFitMatrix |
| Consent | Nutzercheckboxen | GrantArtifactConsent | RFQConsentGranted | ExportReadyView |
| Partnernetzwerk-Hinweis | Systemregel | ComputeManufacturerFitMatrix | PartnerNetworkDisclosureAttached | PartnerDisclosureView |

Wenn Codex für ein Feld keinen Ursprung oder kein Ziel findet, darf es nicht als autoritative Wahrheit eingeführt werden.

---

### 5C.5 Personas und Swimlanes

SeaLAI-Slices müssen mindestens diese Swimlanes berücksichtigen:

```text
User / Buyer
Maintenance / Instandhaltung
Engineering / Anwendungstechnik
Manufacturer Partner
Distributor
SeaLAI Admin
System Automation
RAG / Knowledge System
LLM Research Fallback
```

Nicht jeder Slice nutzt alle Rollen. Aber jeder Slice muss klar machen:

```text
Wer löst den Schritt aus?
Wer sieht welche Daten?
Welche Daten überschreiten eine Grenze?
Welche Daten bleiben intern?
Welche Daten dürfen an Partnerhersteller?
Welche Daten stammen aus RAG, Upload oder LLM-Fallback?
```

Diese Swimlanes sind besonders wichtig für:

```text
- Upload-IP-Schutz
- Tenant-Isolation
- Partner-Matching
- RFQ-Export
- Hersteller-Support
- Reklamationsantworten
- LLM-Fallback-Kennzeichnung
```

---

### 5C.6 Command/Event/View-Katalog

#### Conversation Commands

```text
ClassifyConversationIntent
SelectResponseMode
CreateConversationReply
CreateOrUpdateIntakeConversationState
```

Events:

```text
UserMessageReceived
ConversationIntentClassified
ResponseModeSelected
SmallTalkAnswered
GeneralKnowledgeQuestionDetected
GovernedDomainInquiryDetected
IntakeConversationStateUpdated
```

Views:

```text
ConversationFrontdoorView
NextBestQuestionView
KnowledgeQuestionView
```

#### Case Commands

```text
CreateOrUpdateSealingCase
AssignCaseType
NormalizeSealType
UpdateSealApplicationProfile
ProposeCaseFieldCandidate
ConfirmCaseField
RejectCaseFieldCandidate
MarkCaseFieldConflict
RecomputeCaseReadiness
```

Events:

```text
CaseCreated
CaseUpdated
CaseTypeAssigned
SealTypeCandidateDetected
SealTypeNormalized
SealApplicationProfileUpdated
CaseFieldCandidateProposed
CaseFieldConfirmed
CaseFieldCandidateRejected
CaseFieldConflictDetected
CaseReadinessRecomputed
CaseRevisionIncremented
```

Views:

```text
CaseWorkspaceProjection
DecisionUnderstandingView
OpenPointsView
SealApplicationProfileView
TypeSpecificQuestionView
ReadinessView
```

#### Knowledge Commands

```text
AnswerKnowledgeQuestion
RunRAGLookup
RunLLMResearchFallback
GenerateKnowledgeAnswer
```

Events:

```text
KnowledgeQuestionReceived
KnowledgeRAGLookupRequested
KnowledgeRAGAnswerFound
KnowledgeRAGAnswerMissing
LLMResearchFallbackUsed
KnowledgeAnswerGenerated
SourceValidationStatusAssigned
```

Views:

```text
KnowledgeAnswerView
SourceValidationBadgeView
TechnicalBackgroundPanel
```

#### Evidence / Upload Commands

```text
AttachEvidenceDocument
ValidateUpload
ParseEvidenceDocument
ExtractEvidenceCandidates
LinkEvidenceToCaseField
RejectUnsafeUpload
```

Events:

```text
EvidenceUploaded
UploadValidated
UnsafeUploadRejected
DocumentParseAttempted
DocumentParseFailedSafely
ExtractionCandidateCreated
EvidenceLinkedToCaseField
```

Views:

```text
DocumentEvidencePanel
ExtractionCandidateReviewView
OpenPointsView
CompatibilityMatrixView
```

#### Artifact Commands

```text
GenerateArtifact
GenerateRFQPreview
GenerateCompatibilityMatrix
GenerateComplaintIntake
GenerateFailureAnalysisIntake
GenerateCustomerReplyDraft
GenerateInternalEngineeringNote
MarkArtifactStale
```

Events:

```text
ArtifactGenerated
RFQPreviewGenerated
RFQPreviewFrozenToCaseRevision
CompatibilityMatrixGenerated
ComplaintIntakeGenerated
FailureAnalysisIntakeGenerated
CustomerReplyDraftGenerated
InternalEngineeringNoteGenerated
ArtifactMarkedStale
```

Views:

```text
ArtifactWorkspaceView
RFQPreviewView
CompatibilityMatrixView
ComplaintIntakeView
FailureAnalysisIntakeView
CustomerReplyDraftView
InternalEngineeringNoteView
```

#### Consent Commands

```text
GrantArtifactConsent
RejectArtifactConsent
GenerateExport
```

Events:

```text
ArtifactConsentGranted
ArtifactConsentRejected
RFQConsentGranted
RFQConsentRejected
ExportGenerated
ExportBlocked
```

Views:

```text
ConsentRequiredView
ExportReadyView
AuditTimelineView
```

#### Manufacturer Matching Commands

```text
ComputeManufacturerFitMatrix
FilterEligiblePartnerManufacturers
ScoreTechnicalFit
AttachPartnerNetworkDisclosure
```

Events:

```text
ManufacturerFitRequested
PartnerCandidatesFiltered
ManufacturerFitComputed
NoSuitablePartnerFound
PartnerNetworkDisclosureAttached
```

Views:

```text
ManufacturerFitMatrixView
PartnerDisclosureView
NoSuitablePartnerView
```

---

### 5C.7 Event-Modeled Szenario-Slices

Die folgenden Slices sind verbindliche Ziel-Slices für v0.8.3. Codex darf sie einzeln implementieren, testen und reviewbar abschließen.

#### Slice 1 — Small Talk ohne Case-Erzeugung

```text
Persona:
User

Trigger:
User sends greeting or small-talk message.

Command:
ClassifyConversationIntent

Events:
UserMessageReceived
ConversationIntentClassified(intent=small_talk)
ResponseModeSelected(mode=fast_responder)

Views:
ConversationFrontdoorView
```

Given-When-Then:

```text
Given: No active technical case exists
When: User says "Hallo"
Then:
- ConversationIntentClassified has intent=small_talk
- No CaseCreated event exists
- ConversationFrontdoorView offers entry paths: neue Dichtung, Ersatzteil, Ausfall, allgemeine Frage
```

#### Slice 2 — Allgemeine Dichtungstechnik-Frage

```text
Trigger:
User asks "Was ist FKM?" or "Was ist ein Wellendichtring?"

Commands:
ClassifyConversationIntent
AnswerKnowledgeQuestion

Events:
UserMessageReceived
ConversationIntentClassified(intent=general_sealing_question)
KnowledgeRAGLookupRequested
KnowledgeRAGAnswerFound OR KnowledgeRAGAnswerMissing
LLMResearchFallbackUsed if RAG is insufficient and fallback is allowed
KnowledgeAnswerGenerated

Views:
KnowledgeAnswerView
SourceValidationBadgeView
```

Given-When-Then:

```text
Given: No active case exists
When: User asks "Was ist FKM?"
Then:
- No CaseCreated event exists
- KnowledgeAnswerView is returned
- If fallback was used, validation_status=unvalidated is visible
- Answer does not claim case-specific suitability
```

#### Slice 3 — Frust / chaotische Eingabe

```text
Trigger:
User writes "Diese Dichtung leckt schon wieder."

Command:
ClassifyConversationIntent

Events:
UserMessageReceived
ConversationIntentClassified(intent=failure_analysis or complaint_case, confidence=candidate)
ResponseModeSelected(mode=empathic_triage)

Views:
NextBestQuestionView
```

Given-When-Then:

```text
Given: User provides vague frustrated leakage input
When: Intent is classified
Then:
- SeaLAI acknowledges the situation
- No unsafe technical claim is made
- NextBestQuestionView asks first for seal type or available evidence
- No RFQ artifact is generated yet
```

#### Slice 4 — Neuer RFQ-Case

```text
Trigger:
User provides real application data.

Command:
CreateOrUpdateSealingCase

Events:
CaseCreated
CaseTypeAssigned(case_type=new_rfq)
CaseFieldCandidateProposed
CaseRevisionIncremented
CaseReadinessRecomputed

Views:
CaseWorkspaceProjection
DecisionUnderstandingView
OpenPointsView
```

Given-When-Then:

```text
Given: User says "Wir brauchen eine Dichtung für Getriebeöl bei 80 °C"
When: CreateOrUpdateSealingCase runs
Then:
- CaseCreated exists
- medium=Getriebeöl is user_stated candidate or field
- temperature=80 °C is user_stated candidate or field
- OpenPointsView asks for seal type, pressure, motion, dimensions
```

#### Slice 5 — Dichtungstyp-Normalisierung

```text
Trigger:
User mentions "WDR", "RWDR", "Simmerring", or "Wellendichtring".

Command:
NormalizeSealType

Events:
SealTypeCandidateDetected
SealTypeNormalized(seal_type=radial_shaft_seal)
SealApplicationProfileUpdated

Views:
SealApplicationProfileView
TypeSpecificQuestionView
```

Given-When-Then:

```text
Given: User says "Wellendichtring AS 75x95x10 DIN 3760"
When: NormalizeSealType runs
Then:
- seal_type=radial_shaft_seal with confidence note
- standard_refs includes DIN 3760 if detected
- TypeSpecificQuestionView prioritizes pressure differential, speed, medium, temperature, shaft surface
```

#### Slice 6 — Upload als Evidence, nicht Wahrheit

```text
Trigger:
User uploads oil analysis report.

Commands:
AttachEvidenceDocument
ValidateUpload
ParseEvidenceDocument
ExtractEvidenceCandidates

Events:
EvidenceUploaded
UploadValidated
DocumentParseAttempted
ExtractionCandidateCreated
EvidenceLinkedToCaseField if applicable

Views:
DocumentEvidencePanel
ExtractionCandidateReviewView
CompatibilityMatrixView
OpenPointsView
```

Given-When-Then:

```text
Given: An oil report contains water/sodium/potassium values
When: The document is parsed
Then:
- extracted values are candidates
- validation_status=candidate or documented, not confirmed
- no CaseFieldConfirmed event is created automatically
- uploaded document instructions are ignored as instructions
```

#### Slice 7 — RFQ-Preview mit Revision Freeze

```text
Trigger:
User requests RFQ preview.

Command:
GenerateRFQPreview

Events:
RFQPreviewGenerated
RFQPreviewFrozenToCaseRevision
ArtifactGenerated

Views:
RFQPreviewView
ConsentRequiredView
```

Given-When-Then:

```text
Given: Case revision 12 has medium=user_stated, temperature=documented, pressure=missing
When: GenerateRFQPreview runs
Then:
- RFQPreviewGenerated references case_revision=12
- RFQPreviewView separates known, missing, conflicting, inferred, documented, confirmed fields
- ConsentRequiredView requires no-final-release, open-points-understood, export-intent
```

#### Slice 8 — Consent und Export

```text
Trigger:
User ticks required acknowledgements and requests export.

Command:
GrantArtifactConsent

Events:
RFQConsentGranted OR RFQConsentRejected
ExportGenerated OR ExportBlocked

Views:
ExportReadyView
AuditTimelineView
```

Given-When-Then:

```text
Given: RFQ preview is current and all required acknowledgements are true
When: GrantArtifactConsent runs
Then:
- RFQConsentGranted exists
- ExportReadyView is enabled
```

Failure case:

```text
Given: RFQ preview is stale or an acknowledgement is missing
When: GrantArtifactConsent runs
Then:
- RFQConsentRejected or ExportBlocked exists
- ExportReadyView remains disabled
```

#### Slice 9 — Hersteller-Matching im zahlenden Partnernetzwerk

```text
Trigger:
User asks for suitable manufacturer.

Command:
ComputeManufacturerFitMatrix

Events:
ManufacturerFitRequested
PartnerCandidatesFiltered
ManufacturerFitComputed OR NoSuitablePartnerFound
PartnerNetworkDisclosureAttached

Views:
ManufacturerFitMatrixView
PartnerDisclosureView
NoSuitablePartnerView
```

Given-When-Then:

```text
Given:
- one active paid partner matches radial_shaft_seal
- one unpaid partner matches perfectly
- one active paid partner lacks required capability
When: ComputeManufacturerFitMatrix runs
Then:
- only active paid technically relevant partners are considered
- unpaid partner is excluded
- fit reasons and gaps are shown
- disclosure says this is SeaLAI partner network, not full-market ranking
- payment tier does not change technical fit score
```

#### Slice 10 — Kompatibilitätsanfrage / Ölbericht

```text
Trigger:
Manufacturer or user asks whether water/sodium/potassium values are critical for a WDR FKM FDA.

Command:
QualifyCompatibilityInquiry

Events:
CompatibilityInquiryCreated
ProductDesignationExtracted
ExtractionCandidateCreated
MissingInformationIdentified
CompatibilityMatrixGenerated
CustomerReplyDraftGenerated
InternalEngineeringNoteGenerated

Views:
CompatibilityMatrixView
CustomerReplyDraftView
InternalEngineeringNoteView
```

Given-When-Then:

```text
Given: Inquiry mentions WDR AS 75x95x10 DIN 3760 FKM FDA and oil report values
When: QualifyCompatibilityInquiry runs
Then:
- SeaLAI extracts product designation, seal type, material, application context
- exact lab values/units are required if missing
- no final compatibility approval is claimed
- customer reply draft asks for missing data and manufacturer/compound review
- internal note flags evidence and open questions
```

#### Slice 11 — Reklamation / Failure Intake

```text
Trigger:
User reports leakage, swelling, cracking, extrusion, wear, or repeated failure.

Command:
GenerateFailureAnalysisIntake

Events:
ComplaintIntakeCreated
FailureAnalysisIntakeGenerated
MissingInformationIdentified
InternalEngineeringNoteGenerated

Views:
FailureAnalysisIntakeView
OpenPointsView
InternalEngineeringNoteView
```

Given-When-Then:

```text
Given: User reports "Dichtung nach 3 Monaten ausgefallen"
When: GenerateFailureAnalysisIntake runs
Then:
- SeaLAI captures damage pattern and operating context
- asks for photos/evidence if useful
- no final root cause is claimed
- no liability admission is generated
```

---

### 5C.8 Automation- und Todo-Views

Automatische Prozesse dürfen keine versteckte Businesslogik enthalten. Sie beobachten eine View, führen ein Command aus und erzeugen Events.

Muster:

```text
Event(s)
→ TodoView
→ Automated Trigger
→ Command
→ Event(s)
```

Pflicht-Todo-Views:

| Todo View | Beobachtet | Automated Trigger | Command | Ergebnis |
|---|---|---|---|---|
| DocumentExtractionTodoView | EvidenceUploaded | ParserWorker | ExtractEvidenceCandidates | ExtractionCandidateCreated |
| StaleArtifactCheckTodoView | CaseRevisionIncremented | StaleCheckWorker | MarkArtifactStale | ArtifactMarkedStale |
| RAGLookupTodoView | KnowledgeQuestionReceived | KnowledgeWorker | RunRAGLookup | KnowledgeRAGAnswerFound/Missing |
| FallbackResearchTodoView | KnowledgeRAGAnswerMissing + fallback enabled | KnowledgeWorker | RunLLMResearchFallback | LLMResearchFallbackUsed |
| ManufacturerFitTodoView | ManufacturerFitRequested | MatchingService | ScoreTechnicalFit | ManufacturerFitComputed / NoSuitablePartnerFound |
| ExportTodoView | ArtifactConsentGranted | ExportService | GenerateExport | ExportGenerated |

Regel:

```text
Der Worker darf nicht mehr Geschäftslogik enthalten als:
- Todo lesen
- Command ausführen
- Ergebnis speichern
- Todo abhaken
```

---

### 5C.9 Security Boundary Events

SeaLAI arbeitet mit IP-sensiblen Dokumenten, Partnernetzwerk, Tenant-Grenzen und RFQ-Exports. Deshalb müssen sicherheitsrelevante Übergänge sichtbar sein.

Mögliche Audit-/Boundary-Events:

```text
TenantAccessChecked
TenantAccessDenied
DocumentVisibilityApproved
DocumentVisibilityRejected
PartnerNetworkDisclosureAttached
PartnerNetworkDisclosureAcknowledged
RFQConsentGranted
RFQConsentRejected
ExportGenerated
ExportBlocked
ExternalDispatchBlocked
LLMProcessingAllowed
LLMProcessingBlocked
UploadRejected
```

Nicht jeder Event muss ein öffentlicher Domänen-Event sein. Aber sicherheitsrelevante Übergänge müssen testbar und auditierbar sein.

Pflicht:

```text
- Kein Cross-Tenant-Zugriff ohne serverseitige Prüfung
- Kein Dokument an Partner ohne explizite Freigabe
- Kein Export ohne Consent
- Kein Dispatch ohne Empfänger-Consent
- Kein LLM-Fallback ohne Kennzeichnung
- Kein Partner-Matching ohne Partnernetzwerk-Disclosure
```

---

### 5C.10 View-Verantwortung

Jede View muss klar definieren:

```text
Welche Events/Fakten liest sie?
Welche Felder zeigt sie?
Welche Felder zeigt sie ausdrücklich nicht?
Welche Validierungslabels zeigt sie?
Welche Aktionen erlaubt sie?
Welche Aktionen blockiert sie?
```

Beispiel `ManufacturerFitMatrixView`:

```text
Liest:
- CaseProfile
- SealApplicationProfile
- PartnerCapabilities
- active_paid status
- ManufacturerFitComputed / NoSuitablePartnerFound
- PartnerNetworkDisclosureAttached

Zeigt:
- Partnername
- Fit Score / Fit Band
- Fit Reasoning
- Gaps
- Verification Level
- Disclosure

Zeigt nicht:
- nicht zahlende Hersteller
- versteckte Zahlungsrangfolge
- "bester Hersteller im Markt"

Erlaubt:
- RFQ-Export vorbereiten
- Partner auswählen, falls spätere Versandlogik implementiert ist

Blockiert:
- automatischen Versand ohne Consent
```

---

### 5C.11 Slice-Template für Codex

Jeder Implementierungs-PR muss vor der Änderung den Slice so beschreiben:

```text
Slice ID:
Persona:
Trigger:
Preconditions:
Command:
Events:
State/Table writes:
Views/Projection:
Frontend behavior:
Forbidden side effects:
Given-When-Then tests:
Validation commands:
```

Beispiel:

```text
Slice ID:
S-SEALTYPE-001

Persona:
User

Trigger:
User mentions "RWDR" in message.

Command:
NormalizeSealType

Events:
SealTypeCandidateDetected
SealTypeNormalized

State/Table writes:
No authoritative case field confirmation.
Only seal_type candidate/profile update with confidence.

Views/Projection:
SealApplicationProfileView
TypeSpecificQuestionView

Forbidden side effects:
No RFQ generation.
No manufacturer match.
No final technical claim.

Given-When-Then tests:
Given message contains RWDR
When normalization runs
Then seal_type=radial_shaft_seal and confidence is visible
```

---

### 5C.12 PR 1A — Event Model Blueprint

Vor tiefer Implementierung muss Codex einen Blueprint-PR erstellen.

Ziel:

```text
Das bestehende Konzept wird in umsetzbare Event-Modeling-Slices übersetzt.
```

Erlaubte Dateien:

```text
konzept/event_model/00_method.md
konzept/event_model/01_personas_swimlanes.md
konzept/event_model/02_command_event_view_catalog.md
konzept/event_model/03_scenario_slices.md
konzept/event_model/04_field_origin_destination_matrix.md
konzept/event_model/05_automation_todo_views.md
konzept/event_model/06_security_boundary_map.md
konzept/event_model/07_gwt_specs.md
```

Nicht erlaubt in PR 1A:

```text
- Produktcode ändern
- Services umbauen
- Migrationen erstellen
- Frontend ändern
- APIs ändern
```

Akzeptanzkriterien:

```text
- Alle v0.8.3-Kernfähigkeiten haben mindestens einen Slice.
- Jeder Slice hat Trigger, Command, Event(s), View und GWT-Test.
- Kritische Felder haben Herkunft und Ziel.
- LLM-Fallback hat eigene Events und Labels.
- Partner-Matching hat Disclosure- und No-Fit-Slice.
- RFQ/Consent hat Freeze-, Stale- und Export-Slices.
- Upload/Evidence ist als Candidate-/Evidence-Flow modelliert.
```

---

### 5C.13 Umsetzungskonsequenz

Ab v0.8.3 gilt:

> Kein Feature ohne Slice. Kein Slice ohne Test. Kein Feld ohne Herkunft und Ziel. Keine View ohne bekannte Events/Fakten. Keine Automation ohne Todo-View. Keine LLM-Information ohne Validierungsstatus.

Das ist die wichtigste Professionalisierung für Codex.


## 6. Artefakt-Architektur

Nicht jeder Case endet in einer RFQ. SeaLAI muss je Szenario passende Artefakte erzeugen.

### 6.1 Artifact Types

```python
class ArtifactType(str, Enum):
    RFQ_PREVIEW = "rfq_preview"
    MANUFACTURER_FIT_MATRIX = "manufacturer_fit_matrix"
    TECHNICAL_INQUIRY_SUMMARY = "technical_inquiry_summary"
    COMPATIBILITY_MATRIX = "compatibility_matrix"
    COMPLAINT_INTAKE = "complaint_intake"
    FAILURE_ANALYSIS_INTAKE = "failure_analysis_intake"
    REPLACEMENT_SHEET = "replacement_sheet"
    LEGACY_PART_INTAKE = "legacy_part_intake"
    DRAWING_REVIEW = "drawing_review"
    QUOTE_COMPARISON = "quote_comparison"
    COMPLIANCE_CHECKLIST = "compliance_checklist"
    MATERIAL_SUBSTITUTION_BRIEF = "material_substitution_brief"
    EMERGENCY_TRIAGE = "emergency_triage"
    CUSTOMER_REPLY_DRAFT = "customer_reply_draft"
    INTERNAL_ENGINEERING_NOTE = "internal_engineering_note"
    KNOWLEDGE_RESEARCH_NOTE = "knowledge_research_note"
```

---

### 6.2 Artifact Model

Codex soll ein bestehendes Modell erweitern oder ein neues Modell minimalinvasiv ergänzen.

```json
{
  "artifact_id": "uuid",
  "case_id": "uuid",
  "tenant_id": "uuid",
  "artifact_type": "rfq_preview",
  "case_revision": 7,
  "status": "current",
  "title": "RFQ Preview",
  "content": {},
  "source_refs": [],
  "validation_summary": {
    "has_unvalidated_research": false,
    "has_partner_verified_data": false,
    "has_rag_verified_data": true,
    "has_case_evidence": true,
    "has_conflicts": false,
    "requires_manufacturer_review": true
  },
  "exportable": true,
  "consent_required": true,
  "created_at": "datetime",
  "created_by": "system|user|codex_test_fixture"
}
```

---

## 7. Field Status, Provenance und Validierungsstatus

### 7.1 Bestehende FieldStatus erweitern

Falls `FieldStatus` bereits existiert, Codex soll es vorsichtig erweitern.

```python
class FieldStatus(str, Enum):
    MISSING = "missing"
    USER_STATED = "user_stated"
    USER_CONFIRMED = "user_confirmed"
    DOCUMENTED = "documented"
    RAG_VERIFIED = "rag_verified"
    PARTNER_VERIFIED = "partner_verified"
    LLM_RESEARCH_UNVALIDATED = "llm_research_unvalidated"
    INFERRED = "inferred"
    CALCULATED = "calculated"
    CONFLICTING = "conflicting"
    NEEDS_CONFIRMATION = "needs_confirmation"
    MANUFACTURER_REVIEW_REQUIRED = "manufacturer_review_required"
```

### 7.2 SourceType

```python
class SourceType(str, Enum):
    USER_INPUT = "user_input"
    CASE_DOCUMENT = "case_document"
    RAG_KNOWLEDGE = "rag_knowledge"
    PARTNER_DATA = "partner_data"
    LLM_RESEARCH = "llm_research"
    PUBLIC_WEB_RESEARCH = "public_web_research"
    DETERMINISTIC_CALCULATION = "deterministic_calculation"
    HUMAN_REVIEW = "human_review"
```

### 7.3 ValidationStatus

```python
class ValidationStatus(str, Enum):
    VERIFIED = "verified"
    PARTNER_VERIFIED = "partner_verified"
    CASE_EVIDENCE_ONLY = "case_evidence_only"
    USER_STATED_ONLY = "user_stated_only"
    UNVALIDATED_RESEARCH = "unvalidated_research"
    CONFLICTING = "conflicting"
    UNKNOWN = "unknown"
```

### 7.4 Harte Regel

Informationen mit Status `LLM_RESEARCH_UNVALIDATED` oder `UNVALIDATED_RESEARCH` dürfen:

- erklärt werden,
- als Recherchehinweis erscheinen,
- offene Punkte erzeugen,
- Fragen vorschlagen,
- interne Engineering-Notizen ergänzen.

Sie dürfen nicht:

- als bestätigte technische Wahrheit persistiert werden,
- RFQ-kritische Felder automatisch bestätigen,
- Hersteller-Fit endgültig entscheiden,
- Compliance- oder Materialfreigaben begründen,
- in Exporten ohne Warnlabel erscheinen,
- als „SeaLAI-validiert“ dargestellt werden.

---

## 8. RAG + LLM-Recherche-Fallback

Der Nutzer hat explizit gefordert:

> Wenn aus dem RAG keine Information vorhanden ist, soll immer ein LLM eine Recherche durchführen und die gewonnenen Informationen ausgeben. Diese Informationen müssen klar als nicht validiert bzw. als Rechercheinformation gekennzeichnet werden.

Diese Anforderung ist zentral für v0.8.

---

### 8.1 Ziel

SeaLAI soll niemals einfach sagen:

```text
Dazu habe ich keine Information.
```

Stattdessen:

```text
In der validierten SeaLAI-Wissensbasis wurde keine passende Information gefunden.
Ich habe daher eine LLM-Recherche / allgemeine technische Recherche durchgeführt.
Die folgenden Hinweise sind nicht validiert und müssen durch Herstellerdaten, Laborprüfung oder Anwendungstechnik bestätigt werden.
```

---

### 8.2 Knowledge Answer Flow

```text
User question / case context
→ sanitize query
→ search RAG
→ evaluate RAG coverage
→ if sufficient: answer with RAG_VERIFIED / source refs
→ if insufficient: run LLM research fallback
→ label output as LLM_RESEARCH_UNVALIDATED
→ show confidence and validation warning
→ suggest what evidence would validate it
→ optionally create open points
```

---

### 8.3 Privacy / IP Rule für Research Fallback

Wenn externe Recherche oder ein externes LLM verwendet wird, darf SeaLAI keine vertraulichen Kundendaten ungefiltert weitergeben.

Codex muss eine Sanitization-Schicht implementieren:

```text
Nicht in externe Recherchequery übernehmen:
- Kundennamen
- Projektnamen
- Zeichnungsnummern
- vollständige Artikelnummern, falls vertraulich
- interne Anlagenbezeichnungen
- Seriennummern
- Lieferantengeheimnisse
- hochgeladene Dokumentpassagen mit IP-Charakter
- personenbezogene Daten
```

Erlaubt sind generische technische Queries wie:

```text
FKM Beständigkeit Wasser Natrium Kalium Getriebeöl Wellendichtring allgemeine technische Hinweise
```

Nicht erlaubt:

```text
Kunde Müller GmbH Reklamation Getriebe Typ ABC-9000 Ölbericht Labor XYZ Seriennummer 12345 vollständige Messdaten...
```

---

### 8.4 ResearchFallbackPolicy

```python
class ResearchFallbackPolicy(BaseModel):
    enabled: bool = True
    external_research_enabled: bool = False
    sanitize_case_context: bool = True
    allow_case_document_text_in_research: bool = False
    max_query_chars: int = 600
    require_label_unvalidated: bool = True
    allow_unvalidated_in_export: bool = True
    require_export_warning: bool = True
```

Default für Pilot:

```text
enabled=true
external_research_enabled=false, außer explizit tenant-/admin-/policy-aktiviert
sanitize_case_context=true
require_label_unvalidated=true
allow_unvalidated_in_export=true, aber nur mit Warnlabel
```

Wenn externe Web-/Research-Funktion nicht im Stack vorhanden ist:

- Codex soll eine interne LLM-Rechercheantwort aus dem Modell erzeugen lassen,
- diese als `LLM_RESEARCH_UNVALIDATED` kennzeichnen,
- Quellenfeld leer oder `sources=[]` setzen,
- UI-Hinweis anzeigen: „Keine validierten Quellen im SeaLAI-RAG; keine externen Quellen verfügbar.“

---

### 8.5 KnowledgeAnswer Contract

```json
{
  "question": "Sind Wasser, Natrium und Kalium für FKM-Wellendichtringe kritisch?",
  "rag": {
    "searched": true,
    "result_count": 0,
    "coverage": "none",
    "used_sources": []
  },
  "fallback_research": {
    "performed": true,
    "type": "llm_research",
    "external": false,
    "sanitized_query": "FKM Wasser Natrium Kalium Getriebeöl Wellendichtring allgemeine Hinweise",
    "validation_status": "unvalidated_research"
  },
  "answer": {
    "summary": "Allgemeiner Hinweis: Wasser und alkalische Bestandteile können je nach Konzentration, Temperatur und Einwirkdauer prüfungsrelevant sein...",
    "limits": [
      "Keine compoundbezogene Herstellerfreigabe",
      "Keine Grenzwertbewertung ohne exakte Messwerte und Quelle",
      "Keine Schadensursache ableitbar"
    ],
    "open_points": [
      "exakte Messwerte und Einheiten",
      "chemische Form von Natrium/Kalium",
      "Öltyp und Additivpaket",
      "Betriebstemperatur",
      "Schadensbild"
    ]
  },
  "display_label": "LLM-Recherche — nicht validiert",
  "export_warning": "Diese Informationen stammen nicht aus der validierten SeaLAI-Wissensbasis und müssen durch Herstellerdaten oder Anwendungstechnik geprüft werden."
}
```

---

### 8.6 UI-Label für unvalidierte Recherche

Pflichttext im UI:

```text
Quelle: LLM-Recherche — nicht validiert
Diese Information wurde erzeugt, weil in der SeaLAI-Wissensbasis keine ausreichende Information gefunden wurde. Sie ist keine Herstellerfreigabe, keine Materialfreigabe und keine technische Validierung.
```

Kurzlabel:

```text
Nicht validierte Rechercheinformation
```

Exportlabel:

```text
Hinweis: Der folgende Abschnitt enthält nicht validierte LLM-Recherchehinweise. Diese müssen durch Herstellerdaten, Laborprüfung oder Anwendungstechnik bestätigt werden.
```

---

### 8.7 Tests für RAG-Fallback

Pflichttests:

1. RAG hat Treffer → Antwort nutzt RAG, kein Fallback.
2. RAG hat keine Treffer → Fallback wird ausgeführt.
3. Fallback-Antwort hat Status `LLM_RESEARCH_UNVALIDATED`.
4. UI zeigt Warnlabel.
5. Export enthält Warnlabel.
6. Unvalidierte Information setzt kein kritisches CaseField auf `USER_CONFIRMED` oder `RAG_VERIFIED`.
7. Sanitization entfernt Kundennamen und vertrauliche IDs aus Research Query.
8. Prompt Injection aus Upload kann Research-Policy nicht überschreiben.

---

## 9. Hersteller-Matching und Partnernetzwerk

### 9.1 Grundprinzip

SeaLAI v0.8.3 soll Hersteller-Matching abbilden.

Aber:

```text
SeaLAI empfiehlt nicht den objektiv besten Hersteller am Weltmarkt.
SeaLAI zeigt passende Hersteller aus dem aktiven zahlenden SeaLAI-Partnernetzwerk.
```

Pflichttext im UI:

```text
Die Hersteller-Matrix zeigt ausschließlich aktive SeaLAI-Partnerhersteller. Die Reihenfolge basiert auf technischem Fit innerhalb dieses Partnernetzwerks. Nicht teilnehmende Hersteller werden nicht berücksichtigt.
```

---

### 9.2 Harte Matching-Regeln

1. Nur `active_paid = true` darf in der Matrix erscheinen.
2. Der technische Fit Score darf nicht durch Zahlung, Paketstufe oder Sponsoring verändert werden.
3. Sponsoring darf höchstens separat gekennzeichnet werden, niemals als technischer Fit.
4. Wenn kein Partner passt, muss SeaLAI sagen: `no_suitable_partner_found=true`.
5. SeaLAI muss Gründe und Lücken zeigen.
6. Unvalidierte LLM-Recherche darf nicht allein einen Hersteller-Fit begründen.
7. Partnerdaten müssen nach Verifizierungsgrad gekennzeichnet werden:
   - self_declared
   - document_verified
   - sealai_reviewed
   - manufacturer_verified
8. Matching darf keine automatische Anfrage versenden.
9. RFQ-Weitergabe an Partner erfordert Consent.

---

### 9.3 Partner Capability Graph

Codex soll keine simple Herstellerliste bauen, sondern ein Capability-Modell.

```python
class ManufacturerPartner(BaseModel):
    partner_id: UUID
    tenant_id: UUID | None
    name: str
    active_paid: bool
    visibility_status: Literal["active", "paused", "inactive"]
    verification_level: Literal[
        "self_declared",
        "document_verified",
        "sealai_reviewed",
        "manufacturer_verified"
    ]
    capabilities: ManufacturerCapabilities
    commercial: PartnerCommercialStatus
    created_at: datetime
    updated_at: datetime
```

```python
class ManufacturerCapabilities(BaseModel):
    seal_types: list[str]
    materials: list[str]
    compound_families: list[str]
    industries: list[str]
    certifications: list[str]
    services: list[str]
    manufacturing_modes: list[str]
    batch_sizes: list[str]
    regions: list[str]
    languages: list[str]
    response_modes: list[str]
    supports_emergency_mro: bool
    supports_custom_design: bool
    supports_failure_analysis: bool
    supports_compatibility_review: bool
    supports_documents: list[str]
```

Beispiele:

```text
seal_types:
- o_ring
- radial_shaft_seal
- mechanical_seal
- flat_gasket
- hydraulic_seal
- pneumatic_seal
- custom_profile

materials:
- FKM
- FFKM
- EPDM
- NBR
- HNBR
- PTFE
- PU
- VMQ
- ACM

certifications:
- FDA
- EU_1935_2004
- USP_CLASS_VI
- WRAS
- NSF
- KTW_BWGL
- TA_LUFT
- ATEX_RELEVANT_SUPPORT

services:
- application_engineering
- custom_manufacturing
- reverse_engineering
- failure_analysis
- compatibility_review
- emergency_mro
- certificates
- drawing_review
```

---

### 9.4 Manufacturer Fit Score

Der Score soll transparent und testbar sein.

```python
class ManufacturerFitResult(BaseModel):
    partner_id: UUID
    fit_score: float
    fit_band: Literal["high", "medium", "low", "not_suitable"]
    included: bool
    reasons: list[str]
    gaps: list[str]
    risks: list[str]
    verification_notes: list[str]
    partner_network_disclosure_required: bool = True
```

Score-Komponenten:

| Komponente | Gewichtung Startwert |
|---|---:|
| Dichtungstyp-Fit | 25 |
| Material-/Compound-Fit | 20 |
| Medium-/Branchen-Fit | 15 |
| Zertifikats-/Compliance-Fit | 15 |
| Service-Fit | 10 |
| Region / Sprache / Verfügbarkeit | 5 |
| Evidenz- und Verifizierungsgrad | 10 |

Codex soll die Gewichtung als Konfiguration implementieren, nicht hart verstreut im Code.

---

### 9.5 Matching Response Contract

Endpoint:

```http
POST /api/v1/manufacturer-fit
```

Request:

```json
{
  "case_id": "uuid",
  "case_revision": 7,
  "include_unvalidated_research": false,
  "max_results": 5
}
```

Response:

```json
{
  "case_id": "uuid",
  "case_revision": 7,
  "partner_network_only": true,
  "disclosure": "Es werden ausschließlich aktive SeaLAI-Partnerhersteller berücksichtigt.",
  "no_suitable_partner_found": false,
  "results": [
    {
      "partner_id": "uuid",
      "partner_name": "Partner A",
      "fit_score": 0.86,
      "fit_band": "high",
      "reasons": [
        "unterstützt Radialwellendichtringe",
        "FKM-Kompetenz angegeben",
        "Kompatibilitätsprüfung als Service vorhanden"
      ],
      "gaps": [
        "FDA-Compounddaten nicht verifiziert"
      ],
      "risks": [
        "Grenzwertbewertung erfordert Herstellerprüfung"
      ],
      "verification_level": "self_declared"
    }
  ]
}
```

---

## 10. Consent-Modell v0.8

RFQ Export, Partnerweitergabe, Supportantworten und Matching-Ausgabe brauchen klare Consent- und Disclosure-Regeln.

```json
{
  "user_acknowledged_no_final_release": true,
  "user_acknowledged_open_points": true,
  "user_acknowledged_export_intent": true,
  "user_acknowledged_partner_network_only": true,
  "user_acknowledged_unvalidated_research": true,
  "user_acknowledged_no_automatic_dispatch": true
}
```

Regeln:

- RFQ Export ohne finale Freigabe-Hinweis verboten.
- Partner-Matrix ohne Partnernetzwerk-Hinweis verboten.
- Export mit LLM-Recherche ohne Warnlabel verboten.
- Weitergabe an Partner ohne expliziten Consent verboten.
- Dispatch bleibt standardmäßig aus.

---

## 11. API-Kontrakte

Codex soll vorhandene APIs prüfen und diese Kontrakte entweder implementieren oder mit bestehenden Routen kompatibel mappen.

### 11.1 Case Scenario

```http
POST /api/v1/cases/{case_id}/classify-scenario
GET  /api/v1/cases/{case_id}/scenario
```

Response:

```json
{
  "case_id": "uuid",
  "primary_case_type": "compatibility_inquiry",
  "secondary_case_types": ["complaint_case"],
  "scenario_confidence": 0.84,
  "reasons": [
    "Anfrage enthält Reklamationskontext",
    "Anfrage fragt nach Material-/Medienverträglichkeit",
    "Analysebericht wird erwähnt"
  ]
}
```

### 11.2 Artifact Generation

```http
POST /api/v1/cases/{case_id}/artifacts/{artifact_type}/generate
GET  /api/v1/cases/{case_id}/artifacts/latest?type=rfq_preview
GET  /api/v1/artifacts/{artifact_id}
GET  /api/v1/artifacts/{artifact_id}/export
```

### 11.3 Knowledge Answer

```http
POST /api/v1/knowledge/answer
```

Request:

```json
{
  "case_id": "uuid",
  "question": "Welche der genannten Stoffe sind für FKM-Wellendichtringe nicht empfehlenswert?",
  "allow_fallback_research": true,
  "allow_external_research": false,
  "include_case_context": true
}
```

Response:

```json
{
  "answer_id": "uuid",
  "rag_searched": true,
  "rag_result_count": 0,
  "rag_coverage": "none",
  "fallback_research_performed": true,
  "fallback_type": "llm_research",
  "validation_status": "unvalidated_research",
  "display_label": "LLM-Recherche — nicht validiert",
  "summary": "...",
  "open_points": [],
  "limits": [],
  "source_refs": [],
  "export_warning_required": true
}
```

### 11.4 Manufacturer Fit

```http
POST /api/v1/manufacturer-fit
GET  /api/v1/manufacturer-fit/{case_id}/latest
```

### 11.5 Partner Admin

Nur intern/admin:

```http
POST /api/v1/admin/partners
GET  /api/v1/admin/partners
PATCH /api/v1/admin/partners/{partner_id}
POST /api/v1/admin/partners/{partner_id}/capabilities
```

Muss auth-/tenant-/role-gesichert sein.

---

## 12. Frontend-Zielbild

### 12.1 Workspace Layout

SeaLAI braucht einen rechten Arbeitsbereich mit Tabs:

```text
Overview
Angaben
Offene Punkte
Technischer Hintergrund
Wissensbasis / Recherche
RFQ
Hersteller-Fit
Support / Reklamation
Dokumente
Export
```

Nicht jeder Tab muss für jedes Szenario aktiv sein.

### 12.2 Szenario-Banner

Oben im Workspace:

```text
Erkanntes Szenario: Kompatibilitätsanfrage + Reklamationsfall
Konfidenz: 84 %
```

Aktionen:

```text
Szenario bestätigen
Szenario ändern
Zusätzliches Szenario hinzufügen
```

### 12.3 Wissensbasis / Recherche Panel

Muss zeigen:

```text
Validierte SeaLAI-Wissensbasis: keine ausreichenden Treffer
Fallback: LLM-Recherche durchgeführt
Status: nicht validiert
```

Oder:

```text
Validierte SeaLAI-Wissensbasis: 3 Treffer verwendet
Status: RAG-verifiziert
```

### 12.4 Hersteller-Fit Panel

Muss sichtbar machen:

```text
Nur SeaLAI-Partnernetzwerk
Technischer Fit
Gaps
Risiken
Verifizierungsgrad der Partnerdaten
```

Pflichttext:

```text
Nicht teilnehmende Hersteller werden in dieser Matrix nicht berücksichtigt.
```

### 12.5 Support / Reklamation Panel

Für Hersteller- und Reklamationsfälle:

- Technical Inquiry Summary
- Missing Information Checklist
- Compatibility Consideration Matrix
- Customer Reply Draft
- Internal Engineering Note
- Escalation Recommendation

---

## 13. Sicherheits- und IP-Regeln

### 13.1 Tenant Guards

Alle Case-, Artifact-, RAG-, Upload-, RFQ- und Matching-Queries müssen tenant-/user-/org-scoped sein.

Pflichttests:

- User A kann Case B nicht lesen.
- User A kann Artifact B nicht exportieren.
- User A kann keine Partnerdaten administrieren, wenn nicht admin.
- User A kann keine Dokumente fremder Cases für Research nutzen.

### 13.2 Uploads

Uploads sind Evidence, nicht Wahrheit.

Pflicht:

- MIME / Magic Byte Check,
- Parser Limits,
- path redaction,
- keine Stacktraces im Client,
- Prompt Injection Guard,
- LLM-Verarbeitung policy-gated,
- externe Research Queries sanitized.

### 13.3 Secrets

Codex darf keine Secret-Werte ausgeben.

Wenn Codex potenzielle Secrets findet:

```text
Datei: <Pfad>
Key: <KEY_NAME>
Wert: <masked>
Aktion: Rotation / Entfernen / Beispielwert ersetzen
```

---

## 14. Beispiel: Wellendichtring + Ölbericht + Wasser/Natrium/Kalium

Dieser Use Case muss als Fixture in Tests aufgenommen werden.

### 14.1 Input

```text
In einem unserer produzierten Schneckengetriebe verwenden wir Ihre Wellendichtringe
AS 75x95x10 DIN 3760 - FKM - FDA.

Im Rahmen einer Kundenreklamation haben wir das verwendete Getriebeöl extern analysieren lassen.
Darin sind erhöhte Wasser-, Natrium- und Kaliumwerte zu sehen.

Teilen Sie uns bitte mit, welche der genannten Stoffe für die genannten Wellendichtringe nicht empfehlenswert sind.
Sind die gemessenen Werte grenzwertig?
```

### 14.2 Erwartete Klassifikation

```json
{
  "primary_case_type": "compatibility_inquiry",
  "secondary_case_types": ["complaint_case", "manufacturer_support_intake"],
  "scenario_confidence_min": 0.7
}
```

### 14.3 Erwartete Extraktion

```json
{
  "component": "Wellendichtring",
  "designation": "AS 75x95x10 DIN 3760",
  "material": "FKM",
  "regulatory_marker": "FDA",
  "application": "Schneckengetriebe",
  "medium": "Getriebeöl",
  "reported_findings": ["erhöhter Wasserwert", "erhöhter Natriumwert", "erhöhter Kaliumwert"],
  "context": "Kundenreklamation"
}
```

### 14.4 Erwartete offene Punkte

```text
- Exakte Messwerte und Einheiten für Wasser, Natrium und Kalium fehlen.
- Referenzwerte / Laborbewertung fehlen.
- Getriebeöltyp, Hersteller, ISO-VG und Additivpaket fehlen.
- Vergleichswerte des Frischöls fehlen.
- Betriebstemperatur, Temperaturspitzen und Laufzeit fehlen.
- Schadensbild des Wellendichtrings fehlt.
- Chemische Form von Natrium/Kalium ist unklar.
- Mögliche Quellen wie Kühlmittel, Reinigungsmedien, Salze oder alkalische Rückstände sind nicht geklärt.
- Konkreter FKM-FDA-Compound und Herstellerdatenblatt fehlen.
- Dichtungslos / Charge fehlt.
```

### 14.5 Erwartete Antwortgrenze

SeaLAI darf nicht sagen:

```text
Die Werte sind grenzwertig.
FKM ist geeignet.
Wasser/Natrium/Kalium sind unkritisch.
Die Reklamation ist nicht durch den Wellendichtring verursacht.
FDA-FKM ist für diese Anwendung freigegeben.
```

SeaLAI soll sagen:

```text
Die genannten Werte sind prüfungsrelevant.
Eine Grenzwertbewertung ist ohne konkrete Werte, Einheiten, Öltyp, Temperatur, Einwirkdauer und Herstellerdaten nicht belastbar möglich.
Wasser und mögliche salz-/alkalibezogene Verunreinigungen können je nach Konzentration, Temperatur und Einwirkdauer relevant sein.
Eine compoundbezogene Bewertung muss durch Herstellerdaten oder Anwendungstechnik erfolgen.
```

---

## 15. PR-Plan für vollständige v0.8.3-Implementierung

Die Umsetzung erfolgt nicht modulweise, sondern sliceweise.

Jeder PR muss mindestens einen klaren Event-Modeling-Slice bedienen:

```text
Trigger → Command → Event(s) → View → Given-When-Then-Test
```

Do not implement everything at once.

---

### PR 0 — AGENTS.md + v0.8.3-Dokument ins Repo

Ziel:

```text
Codex bekommt verbindliche Arbeitsregeln, aktive Konzeptdatei und Event-Modeling-Pflicht.
```

Aufgaben:

- `AGENTS.md` auf v0.8.3 ausrichten
- dieses Dokument ins Repo legen:
  `konzept/SEALAI_V08_3_EVENT_MODELED_CODEX_IMPLEMENTATION_CONCEPT.md`
- alte Konzepte als Kontext behalten, aber v0.8.3 als aktive Produkt-/Umsetzungsrichtung markieren
- keine Produktlogik ändern

Tests:

```bash
git status --short
```

Akzeptanz:

```text
- AGENTS.md verweist auf v0.8.3
- Codex darf nicht Big-Bang implementieren
- Event-Modeling-Slice-Regel ist sichtbar
```

---

### PR 1 — Stack Discovery + IST-Audit

Ziel:

```text
Tatsächlichen Stack, produktive Seams und Abweichungen vom Konzept erfassen.
```

Aufgaben:

- keine Implementierung
- Audit-Report erzeugen:
  `konzept/SEALAI_V08_3_STACK_AUDIT_IST.md`
- Backend, Frontend, Auth, Tests, RAG, Uploads, RFQ, Consent, Tenant prüfen
- Umsetzungslücken gegen v0.8.3 markieren

Akzeptanz:

```text
- Nur Audit-Datei geändert
- keine Services neu gestartet
- keine Secrets ausgegeben
```

---

### PR 1A — Event Model Blueprint

Ziel:

```text
v0.8.3 in konkrete Event-Modeling-Slices übersetzen.
```

Erlaubte Dateien:

```text
konzept/event_model/00_method.md
konzept/event_model/01_personas_swimlanes.md
konzept/event_model/02_command_event_view_catalog.md
konzept/event_model/03_scenario_slices.md
konzept/event_model/04_field_origin_destination_matrix.md
konzept/event_model/05_automation_todo_views.md
konzept/event_model/06_security_boundary_map.md
konzept/event_model/07_gwt_specs.md
```

Nicht erlaubt:

```text
- Produktcode
- Migrationen
- API-Änderungen
- Frontend-Änderungen
```

Akzeptanz:

```text
- Jeder Kernflow hat Trigger, Command, Events, View und GWT-Test
- RAG-Fallback ist als unvalidierter Flow modelliert
- Manufacturer Matching hat Partnernetzwerk-Disclosure und No-Fit-Slice
- RFQ hat Freeze-, Consent-, Stale- und Export-Slice
```

---

### PR 1B — Event Vocabulary + Lightweight Event Contracts

Ziel:

```text
Falls im bestehenden Stack sinnvoll: Event-/Command-/View-Begriffe als leichte Contracts einführen.
```

Aufgaben:

- vorhandene Event-/Audit-Struktur prüfen
- keine neue Großarchitektur einführen
- minimale Python/TS-Typen oder Schemas nur dort ergänzen, wo produktiv genutzt
- Events im Past Tense
- Commands im Imperativ
- Views als Projektionen/DTOs

Tests:

```text
- Import-/Schema-Tests
- keine produktive Migration
```

---

### PR 2 — Conversation Intelligence als Event-Modeled Slice

Ziel:

```text
Small Talk, allgemeine Fragen und echte Dichtungsfälle sauber unterscheiden.
```

Slices:

```text
Small Talk ohne Case
General Knowledge ohne Case
Frust / Leakage Triage
Governed Domain Inquiry
```

Tests:

```text
- "Hallo" erzeugt keinen Case
- "Was ist FKM?" erzeugt keinen Case
- "Diese Dichtung leckt schon wieder" erzeugt empathische Triage
- echte RFQ-Absicht geht in governed intake
```

---

### PR 3 — CaseType + Scenario Tags

Ziel:

```text
Szenarioachse im Backend sauber abbilden.
```

CaseTypes:

```text
new_rfq
manufacturer_matching
compatibility_inquiry
complaint_case
failure_analysis
replacement_reorder
unknown_legacy_part
drawing_review
quote_comparison
compliance_certificate_request
material_substitution
emergency_mro
manufacturer_support_intake
general_knowledge
```

Tests:

```text
- Klassifikation realer Beispielinputs
- Unclear bleibt candidate/unclear
- Kein ungewollter RFQ-Flow
```

---

### PR 4 — SealFamily / SealType Normalisierung

Ziel:

```text
Dichtungstypen als eigene technische Achse implementieren.
```

Slices:

```text
RWDR/WDR/Simmerring → radial_shaft_seal
Flachdichtung/Flanschdichtung → flat_gasket/flange_gasket
Hydraulik-Stangendichtung → hydraulic_rod_seal
Gleitringdichtung → mechanical_seal
Stopfbuchspackung → gland_packing
Unknown → unknown_seal
```

Tests:

```text
- Alias-Mapping
- Confidence sichtbar
- keine autoritative Bestätigung ohne Nutzer-/Evidence-Basis
- TypeSpecificQuestionView erzeugt passende nächste Fragen
```

---

### PR 5 — Needs Analysis + Current-State Analysis + Next Best Question

Ziel:

```text
SeaLAI fragt nicht formularhaft, sondern präzise und empathisch.
```

Tests:

```text
- maximal 1-3 nächste Fragen
- im Notfall eine wichtigste Frage
- keine Wiederholung bereits beantworteter Fragen
- Frage enthält kurze technische Begründung
```

---

### PR 6 — SourceType / ValidationStatus / Provenance Upgrade

Ziel:

```text
Jede Information hat Quelle und Validierungsstatus.
```

SourceTypes:

```text
rag_verified
partner_verified
manufacturer_documented
uploaded_evidence
user_stated
deterministic_calculation
llm_research_fallback
unknown
```

ValidationStatus:

```text
validated
documented
self_declared
user_stated
candidate
unvalidated
conflicting
rejected
```

Tests:

```text
- LLM fallback kann nicht validated sein
- Upload-Werte bleiben candidate/documented, nicht confirmed
- RAG-Treffer bekommt richtige SourceType
```

---

### PR 7 — Knowledge Answer Service mit RAG-first

Ziel:

```text
Allgemeine Dichtungsfragen werden zuerst aus RAG/kuratierter Knowledge beantwortet.
```

Tests:

```text
- RAG-Hit sichtbar als dokumentiert/validiert
- kein Casezwang
- keine Fallfreigabe
```

---

### PR 8 — LLM Research Fallback bei RAG-Miss

Ziel:

```text
Wenn RAG nichts liefert, darf LLM-Recherche helfen, aber nur klar als nicht validiert.
```

Events:

```text
KnowledgeRAGAnswerMissing
LLMResearchFallbackUsed
KnowledgeAnswerGenerated
SourceValidationStatusAssigned
```

Tests:

```text
- Fallback nur bei RAG-Miss
- Label "nicht validiert"
- nicht als CaseFieldConfirmed nutzbar
- nicht als Compliance-Evidence nutzbar
```

---

### PR 9 — Artifact Model

Ziel:

```text
Artefakte revisioniert und scenario-spezifisch erzeugen.
```

ArtifactTypes:

```text
rfq_preview
manufacturer_fit_matrix
technical_inquiry_summary
compatibility_matrix
complaint_intake
failure_analysis_intake
replacement_sheet
legacy_part_intake
drawing_review
quote_comparison
compliance_checklist
material_substitution_brief
emergency_triage
customer_reply_draft
internal_engineering_note
```

Tests:

```text
- artifact.case_revision gesetzt
- stale möglich
- source/provenance enthalten
```

---

### PR 10 — RFQ Preview v0.8.3 aus Field Envelopes

Ziel:

```text
RFQ-Preview als Event-Modeled Artifact mit Revision Freeze.
```

Tests:

```text
- RFQPreviewGenerated
- RFQPreviewFrozenToCaseRevision
- bestätigte/dokumentierte/user-stated/inferred/missing/conflicting Werte getrennt
- keine final suitability wording
```

---

### PR 11 — Consent v0.8.3

Ziel:

```text
Consent für Export, offene Punkte, keine finale Freigabe und ggf. Partnernetzwerk.
```

Tests:

```text
- no_final_release erforderlich
- open_points_understood erforderlich
- export_intent erforderlich
- partner_network_disclosure erforderlich, wenn Matching enthalten
- stale preview blockiert Export
```

---

### PR 12 — Compatibility Inquiry Artifact

Ziel:

```text
Kompatibilitätsfragen wie WDR + Ölbericht + Wasser/Natrium/Kalium strukturieren.
```

Tests:

```text
- Produktbezeichnung extrahiert
- Labordaten als Candidates
- fehlende Werte/Einheiten werden abgefragt
- keine finale Kompatibilitätsfreigabe
```

---

### PR 13 — Complaint / Failure Intake

Ziel:

```text
Reklamation und Ausfallanalyse als Intake, nicht als finale Ursache.
```

Tests:

```text
- Schadensbild erfasst
- Fotos/Evidence angefragt
- keine RootCauseConfirmed
- keine Haftungsannahme
```

---

### PR 14 — Customer Reply Draft + Internal Engineering Note

Ziel:

```text
Sichere Antwortentwürfe und interne Anwendungstechnik-Notizen.
```

Tests:

```text
- vorsichtige Sprache
- offene Punkte sichtbar
- Herstellerprüfung empfohlen
- kein Liability Admission
```

---

### PR 15 — Partner Model + Capability Graph

Ziel:

```text
Zahlende Partnerhersteller und technische Fähigkeiten modellieren.
```

Felder:

```text
active_paid
capabilities
seal_types
materials
industries
certifications
services
verification_level
```

Tests:

```text
- inactive/unpaid ausgeschlossen
- capabilities source/verification sichtbar
```

---

### PR 16 — Manufacturer Fit Engine

Ziel:

```text
Technischen Fit im SeaLAI-Partnernetzwerk berechnen.
```

Tests:

```text
- nur active_paid
- Fit Score technisch
- Payment tier ändert Score nicht
- NoSuitablePartnerFound möglich
- DisclosureEvent vorhanden
```

---

### PR 17 — Manufacturer Fit API + UI

Ziel:

```text
Fit Matrix transparent anzeigen.
```

Tests:

```text
- PartnerDisclosureView sichtbar
- Fit reasons sichtbar
- Gaps sichtbar
- keine "bester Hersteller im Markt"-Copy
- kein automatischer Versand
```

---

### PR 18 — Replacement / Legacy Part Mode

Ziel:

```text
Altteil-/Reorder-Fälle mit unsicheren Angaben strukturieren.
```

Tests:

```text
- unsichere Identität sichtbar
- benötigte Fotos/Maße angefragt
- keine 1:1-Austauschbarkeit behauptet
```

---

### PR 19 — Drawing Review Mode

Ziel:

```text
Zeichnungen als Evidence strukturieren, nicht als Wahrheit.
```

Tests:

```text
- DrawingReviewArtifact
- fehlende Toleranzen/Oberflächen/Maße markiert
- keine Herstellbarkeitsfreigabe
```

---

### PR 20 — Compliance / Certificate Mode

Ziel:

```text
Zertifikats- und Compliance-Anforderungen sichtbar machen.
```

Tests:

```text
- FDA/EU1935/ATEX/USP etc. als Anforderungen
- keine Compliance-Freigabe ohne Evidence
- Compound vs Materialfamilie getrennt
```

---

### PR 21 — Quote Comparison Mode

Ziel:

```text
Angebote vergleichbar machen.
```

Tests:

```text
- Annahmen, Ausschlüsse, Zertifikate, Lieferzeit, Preis getrennt
- nicht einfach "billigstes Angebot" empfehlen
```

---

### PR 22 — Emergency MRO Mode

Ziel:

```text
Time-to-Clarity bei Stillstand.
```

Tests:

```text
- eine wichtigste Frage
- minimale Pflichtdaten
- Express-Fähigkeit nur bei Partner Capability
```

---

### PR 23 — Multi-Scenario Workspace UI

Ziel:

```text
Workspace rendert Views und Artefakte aus Backend-Projektionen.
```

Tests:

```text
- Tabs für RFQ, Hersteller-Fit, Support/Reklamation, Dokumente, offene Punkte
- Fallback-Labels sichtbar
- keine Frontend-Wahrheit
```

---

### PR 24 — Security, Tenant, Upload/IP Hardening

Ziel:

```text
IP, Tenant, Upload, Prompt-Injection und Path-Redaction absichern.
```

Tests:

```text
- cross-tenant forbidden
- document sharing requires consent
- upload instructions cannot override rules
- parser errors safe
```

---

### PR 25 — Observability + Audit Events

Ziel:

```text
Business-relevante Event-/Audit-Spuren sichtbar machen.
```

Events:

```text
RFQPreviewGenerated
RFQConsentGranted
ExportGenerated
ManufacturerFitComputed
NoSuitablePartnerFound
LLMResearchFallbackUsed
ArtifactMarkedStale
TenantAccessDenied
```

Tests:

```text
- keine Secrets in Logs
- audit entries source/tenant/revision enthalten
```

---

### PR 26 — Guard Tests + Regression Suite

Ziel:

```text
Sicherheits-, Overclaim-, Fallback-, Matching- und Consent-Grenzen regressionsfest machen.
```

Tests:

```text
- prompt injection
- compliance overclaim
- fallback label
- paid ranking prevention
- RFQ consent
- tenant/IDOR
```

---

### PR 27 — Final v0.8.3 Acceptance Pass

Ziel:

```text
End-to-End-Abnahme gegen Konzept.
```

Akzeptanz:

```text
- jeder produktive Kernflow hat Slice
- jeder Slice hat Tests
- jedes kritische Feld hat Origin/Destination
- keine unvalidierte LLM-Info wird Wahrheit
- Partner-Matching ist transparent
- RFQ bleibt nicht-final
- Frontend rendert Views, nicht Wahrheit
```


## 16. Standard-Testbefehle

Codex soll die tatsächlichen Befehle aus `package.json`, `pyproject.toml`, `pytest.ini` und CI prüfen. Falls abweichend, tatsächliche Befehle verwenden und dokumentieren.

Backend:

```bash
python -m pytest backend/app/api/tests -q
python -m pytest backend/app/agent/tests -q
```

Frontend:

```bash
npm --prefix frontend run test:run
npm --prefix frontend run lint
npm --prefix frontend run build
```

Schnelle Smoke Checks:

```bash
python - <<'PY'
import importlib
for mod in [
    'backend.app.core.config',
    'backend.app.main',
]:
    importlib.import_module(mod)
print('import smoke ok')
PY
```

---

## 17. Master Prompt für Codex App / Codex CLI

```text
Read AGENTS.md first.

Then read:
- konzept/SEALAI_V08_3_EVENT_MODELED_CODEX_IMPLEMENTATION_CONCEPT.md
- konzept/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md
- frontend/DESIGN.md if frontend/UI is touched

Implement only PR <PR_NUMBER>: <PR_TITLE>.

This is not a big-bang implementation.

Before coding:
1. Inspect the current stack and relevant tests.
2. Identify the existing productive seam.
3. Write the Event-Modeling slice for this PR:
   - Slice ID
   - Persona
   - Trigger
   - Preconditions
   - Command
   - Events
   - State/Table writes
   - Views/Projection
   - Frontend behavior if any
   - Forbidden side effects
   - Given-When-Then tests
4. Confirm the smallest safe patch.

Rules:
- Do not restart services.
- Do not run production migrations.
- Do not expose secrets.
- Do not deploy.
- Do not send RFQs.
- Do not contact manufacturers.
- Do not implement other PRs.
- Do not introduce Event Sourcing unless explicitly instructed.
- Do not replace the stack.
- Do not let frontend own engineering truth.
- Do not let LLM output become engineering truth.
- Do not present LLM-research fallback as validated.
- Do not rank paid partners by payment tier.
- Do not hide partner-network disclosure.

After coding:
- Add focused Given-When-Then tests.
- Run relevant validation commands.
- Report:
  1. Short diagnosis
  2. Slice implemented
  3. Exact files changed
  4. Why these files
  5. Behavioral delta
  6. Validation commands and results
  7. Risks / limitations
  8. Next productive patch
```

## 18. Definition: v0.8.3 vollständig umgesetzt

v0.8.3 ist vollständig umgesetzt, wenn SeaLAI nicht nur die Funktionen besitzt, sondern diese Funktionen auch event-modeled, testbar und nachvollziehbar sind.

### Produktfähigkeit

```text
- SeaLAI erkennt Small Talk, allgemeine Dichtungsfragen und echte Fälle getrennt.
- SeaLAI führt empathische Bedarfs- und Ist-Analyse durch.
- SeaLAI fragt präzise Next-Best-Questions statt Formularlisten.
- SeaLAI unterstützt mehrere CaseTypes.
- SeaLAI unterstützt unterschiedliche Dichtungstypen als eigene technische Achse.
- SeaLAI nutzt RAG-first.
- SeaLAI nutzt LLM-Recherche-Fallback nur mit klarer Nicht-Validiert-Kennzeichnung.
- SeaLAI erzeugt RFQ-Previews mit Revision Freeze.
- SeaLAI erzwingt Consent.
- SeaLAI matched nur aktive zahlende Partnerhersteller.
- SeaLAI trennt Zahlung von technischem Fit Score.
- SeaLAI unterstützt No-Suitable-Partner.
- SeaLAI unterstützt Support-, Kompatibilitäts-, Reklamations- und Failure-Intake-Artefakte.
```

### Event-Modeling-Fähigkeit

```text
- Jeder Kernflow hat einen dokumentierten Slice.
- Jeder Slice hat Trigger, Command, Events, View und GWT-Test.
- Jedes kritische Feld hat Herkunft und Ziel.
- Automationen laufen über Todo-Views oder gleichwertig klare Verarbeitungsschritte.
- Security-Boundaries sind auditierbar.
- Views lesen vorhandene Fakten und erfinden keine Wahrheit.
- Commands haben klare Preconditions.
- Events sind Past-Tense Business-Facts.
- Kein Feature hängt nur an Prompt-Text.
```

### Trust- und Sicherheitsfähigkeit

```text
- Keine finale technische Freigabe.
- Keine Compliance-Freigabe ohne Evidence.
- Keine unvalidierte LLM-Info als Wahrheit.
- Keine automatische Herstellerkommunikation ohne Consent.
- Keine Cross-Tenant-Leaks.
- Keine Secret-Ausgabe.
- Uploads sind Evidence, nie Instructions.
- Partnernetzwerk ist transparent offengelegt.
```

### Codex-Fähigkeit

```text
- Codex kann jeden nächsten PR aus einem klaren Slice bauen.
- Tests zeigen Verhalten, Grenzen und Failure Cases.
- PRs bleiben klein.
- Keine Big-Bang-Umsetzung.
```


## 19. Go-to-Market-Positionierung v0.8

Kurz:

```text
SeaLAI bringt Klarheit in Dichtungsfälle.
```

Etwas länger:

```text
SeaLAI hilft Unternehmen, Dichtungsfälle zu verstehen, technische Angaben zu qualifizieren, passende Hersteller im SeaLAI-Partnernetzwerk zu finden und Support- oder Reklamationsfälle nachvollziehbar vorzubereiten.
```

Drei-Säulen-Claim:

```text
Verstehen. Qualifizieren. Matchen.
```

Vier-Säulen-Claim:

```text
Understand. Qualify. Match. Support.
```

Für Nutzer:

```text
SeaLAI hilft Ihnen, Ihre Dichtungssituation zu verstehen, fehlende Angaben zu erkennen und eine herstellerprüfbare Anfrage zu erstellen.
```

Für Hersteller:

```text
SeaLAI qualifiziert eingehende Dichtungsanfragen, Reklamationen und Kompatibilitätsfragen vor, damit Anwendungstechnik schneller und sicherer reagieren kann.
```

Für Partnerhersteller:

```text
SeaLAI bringt qualifizierte Dichtungsfälle zu passenden Partnerherstellern — transparent, technisch begründet und mit klaren offenen Punkten.
```

---

## 20. Externe Referenzen für Codex / Review

Diese Links dienen nur als Orientierung für Implementierungsreview und Produktgrenzen. Sie ersetzen keine Rechtsberatung und keine technische Herstellerprüfung.

- OpenAI Codex Web / Cloud: https://developers.openai.com/codex/cloud
- OpenAI AGENTS.md Guide: https://developers.openai.com/codex/guides/agents-md
- OpenAI Codex Best Practices: https://developers.openai.com/codex/learn/best-practices
- OpenAI Codex App Release Notes: https://help.openai.com/en/articles/11391654-chatgpt-business-release-notes
- EU Ranking Transparency / P2B: https://digital-strategy.ec.europa.eu/en/library/ranking-transparency-guidelines-framework-eu-regulation-platform-business-relations-explainer
- EU DSA Platform Transparency: https://digital-strategy.ec.europa.eu/en/policies/dsa-impact-platforms
- Event Modeling — Home: https://eventmodeling.org/
- Event Modeling Cheat Sheet: https://eventmodeling.org/posts/event-modeling-cheatsheet/
- Event Modeling — What is it?: https://eventmodeling.org/posts/what-is-event-modeling/
- Event Modeling Traditional Systems: https://eventmodeling.org/posts/event-modeling-traditional-systems/

---

## 21. Schlussurteil

v0.8.3 professionalisiert SeaLAI sinnvoll und stark:

```text
RFQ-only Copilot
→ Multi-Szenario-Klärungssystem
→ Partner-Matching-System
→ Hersteller-Support-System
→ Dichtungswissen-Plattform
```

Der wichtigste Implementierungsgrundsatz bleibt:

```text
Keine falsche Sicherheit erzeugen.
Alles mit Quelle, Status und Validierungsgrad kennzeichnen.
```

Der größte kommerzielle USP ist das Partner-Matching.
Der größte Vertrauens-USP ist die Uncertainty Governance.
Der größte Nutzer-USP ist besseres Verständnis.
Der größte Hersteller-USP ist qualifizierter technischer Intake.

SeaLAI v0.8.3 soll deshalb nicht als „KI findet die richtige Dichtung“ positioniert werden, sondern als:

```text
Die technische Klärungsschicht für Dichtungsfälle — von Verständnis über RFQ bis Partner-Fit und Support.
```
