# Konzeptpapier v2 — Kandidaten-Spezifikation (Bauform · Werkstoff · Lippen · DIN) + Hersteller-Datenblatt-Ingestion mit struktureller Neutralitäts-Firewall

**Status:** Entwurf v2, überarbeitet nach adversarialer Review (GPT 5.5). · **Datum:** 2026-06-27 · **System:** sealingAI V2.1
**v1→v2:** „Produktempfehlung/korrekter Produkttyp" → **Kandidaten-Spezifikation**; Completeness-Gate; STRUKTURELLE Firewall
(zwei Stores + Import-Boundary-Enforcement + Hash-Invarianz-Test); Maß-Epistemik; Wissensreifegrad-Leiter mit
Experten-Freigabe; konservative DIN-Lizenz-Governance; Kritikalität/Eskalation/Haftung; Constraint-Resolution statt
Ranking; Family-Kernel-Contract; 12 Eval-Schranken als Gates; explizite Go/No-Go-Gates.

---

## 0. Leitsatz (ersetzt „wir empfehlen den richtigen Dichtring")
> sealingAI erzeugt eine **nachvollziehbare, normverankerte Kandidaten-Spezifikation mit offengelegten Annahmen,
> Grenzen und Prüfpunkten** — damit Hersteller und Anwender schneller zur richtigen Lösung kommen. Es ersetzt **keine**
> technische Auslegung/Freigabe.

## 1. Zweck & Ziel
Zwischen Situationsanalyse und Hersteller-Gespräch fehlt die **Kandidaten-Spezifikation** (Bauform + Werkstoff +
Lippenzahl + Maße + DIN-Bezug). Ziel: Der User **versteht seine Dichtungssituation** und erhält eine **DIN-verankerte,
nachvollziehbar begründete Kandidaten-Spezifikation als Gesprächs-/Anfragebasis**, die **vor Einsatz durch
Hersteller/Fachverantwortliche final zu prüfen** ist.
**Nicht-Ziele:** keine Freigabe/Eignung/Compliance; kein Ersatz der Hersteller-Auslegung; keine DIN-Reproduktion; keine
Typ-/Maß-Erfindung außerhalb kuratierten, fachlich freigegebenen Wissens.
**Verbotene Sprache (Schranke, §10):** „korrekt", „geeignet", „freigegeben", „DIN-konform bestätigt", „Bestellspezifikation".

## 2. Die zwei Leitplanken — verschärft
- **G1 — Grounding + Completeness.** Jede fachliche Aussage stammt nur aus reviewten, fachlich freigegebenen Fachkarten
  oder dem Rechenkern. **NEU: Grounding ≠ Korrektheit.** Wahre Einzelregeln können zu falscher Komposition führen, wenn
  Kontext fehlt. Deshalb ein **Completeness-Gate je Familie**: ohne die Pflicht-Mindest-Inputs **keine** konkrete
  Bauform-/Werkstoff-/Maß-Kombination — nur Teil-Screening + explizite Defer.
- **G2 — §3.9 Neutralität, STRUKTURELL.** Prozessuale Trennung reicht nicht. Die neutrale Spezifikation und die
  Hersteller-Capability liegen in **zwei getrennten Stores**; der Spec-Service hat **keinen Lese-/Importpfad** auf den
  Capability-Store (erzwungen durch den bestehenden Import-Boundary-Enforcer — wie der §3.9-Strukturguard heute). Ein
  **CI-Hash-Invarianz-Test** beweist: derselbe Fall → derselbe Spec-Output, egal welche Datenblätter eingespielt sind.

## 3. Systemkontext + welche bestehenden Mechanismen die neuen Forderungen erzwingen
Fachkarten = reviewte JSON-SSoT; Trust-Spine L1→L2-Grounding→L3-Verifier→L4; §4-Verträglichkeitsmatrix; Versagensmodi;
Trap-Katalog; Gegencheck/Modus E (disqualify-only); Case-State + Rechenkern; Partner-Pool + Capability-Matching (§3.9
durch Trennung); Geltungsrahmen; Review-/Challenge-Ingestion.
**Bestehende Keystones, die v2 wiederverwendet:** (a) **Import-Boundary-Enforcer** → erzwingt die Zwei-Store-Trennung
strukturell; (b) **§3.9-Strukturguard** (lehnt `rank/paid/tier`-Felder ab) → erweitert um `source_type`/`vendor_claim_not_allowed`;
(c) **GroundingFact nur in Grounding-Lanes konstruierbar** → Analogon „Spec-Service kann keine Capability lesen"; (d)
**review_state/provenance + Promote-Pipeline** → die Reifegrad-Leiter; (e) **deterministische Eval-Schranken** → die 12 neuen Tests.

## 4. Die Kandidaten-Spezifikations-Stage
Position: nach der Situationsanalyse, vor dem Matching. Ablauf:
1. **Criticality-Classifier** (§10) klassifiziert den Fall: `normal | caution | high-risk | out-of-scope`.
2. **Completeness-Gate:** prüft die familienspezifischen Pflicht-Inputs. Fehlen kritische (Medium/Temp/Druck/Geometrie …)
   → kein konkreter Spec, nur Teil-Screening + benannte Lücken.
3. **Constraint-Resolution** (kein Ranking, §9): disqualify > safety/defer > Muss-Kriterien (Kandidatenraum) >
   Kann-Kriterien (Varianten) > explizite Konflikt-Anzeige.
4. **Output:** Kandidaten-Spec mit **Maß-Epistemik** (§5), Begründungskette (`source_id`/`rule_id`/`version`),
   Normbezug, offenen Punkten, Defer-Gründen, Geltungsrahmen. Bei `high-risk`/`out-of-scope` → Eskalation statt Spec.
**Negative Knowledge** wird explizit genutzt: „wann ausdrücklich KEINE AS", „wann Standard-RWDR verlassen", „wann keine
Materialaussage möglich".

## 5. Epistemik — Input-Confidence, Maß-Typisierung, Negative Knowledge
- **Input-Confidence je Userangabe:** `vom_typenschild | gemessen | aus_altdichtung | geschätzt | unbekannt`. Schwache
  Inputs senken die Spec-Konkretheit + erzwingen Defer.
- **Maß-Typisierung (ersetzt das flache `masse`):**
  | Typ | Bedeutung |
  |---|---|
  | `observed_size` | vom User / Altdichtung / Zeichnung übernommen |
  | `candidate_size` | aus dem Fall abgeleitet |
  | `verified_norm_size` | gegen lizenzierte/geprüfte Norm-/Herstellerquelle verifiziert |
  | `unknown_or_unverified` | bewusst offen |
  - **Pflichtregel:** Maße nur vom User → Ausgabe NIE „DIN-konform"; höchstens „vom User angegeben; DIN-/Einbauraum-Abgleich offen".

## 6. DIN-Abgleich + Lizenz-Governance (konservativ, rechtlich abgesichert)
- **Erlaubt:** Normnummern, öffentlich etablierte Kurzbezeichnungen (A/AS/B/C …), selbst entwickelte Entscheidungslogik.
- **NICHT ohne explizite Lizenz:** Normtexte, Tabellen, **systematische Maßreihen** oder daraus rekonstruierbare Inhalte
  werden **nicht gespeichert, reproduziert oder durchsuchbar gemacht**. („Weit publizierte Maßreihen" aus v1 ist KEIN
  sauberer Schutzbegriff und wird gestrichen.)
- **Gate:** vor produktiver Nutzung normbasierter Regelkarten **Lizenz-/Rechtsprüfung je Normquelle**; DIN-Media-AI-Lizenz
  prüfen. Rechtsgrundlage u. a. § 5 Abs. 3 UrhG (private Normwerke bleiben geschützt) + DIN-Media-Repro-/AI-Lizenzhinweise.
- „Abgleich gegen die DIN" = die KI liefert die DIN-verankerte Hypothese + Normbezug; User/Hersteller gleichen gegen die
  echte (lizenzierte) Norm ab.

## 7. Neutralitäts-Firewall — STRUKTURELL (Risiko-Herzstück)
Indirekte Angriffe (aus der Review) und die Gegenmaßnahmen:
- **Kurator-Kontamination** → **getrennte Reviewer-Rollen:** Capability-Reviewer ≠ Neutral-Knowledge-Reviewer.
- **Coverage-/Maßreihen-/Feedback-Bias** → neutrale Regeln dürfen NUR promoted werden mit `source_type ∈ {standard,
  textbook, expert_signed, multi_vendor_common}`; `vendor_claim` ist **nicht erlaubt** als neutrale Quelle.
- **Innovation-Laundering** → eigene Reviewklasse **`vendor_originated_generic_claim`**: ein Hersteller-Design wird nur
  neutrales Wissen nach expliziter Abstraktion + Fachfreigabe, mit nachvollziehbarer Herkunftskennzeichnung.
- **Struktur:** `neutral_knowledge_store` und `capability_store` sind getrennt; der **Spec-Service importiert/liest den
  Capability-Store nicht** (Import-Boundary-Enforcer). **CI-Test:** Spec-Output-Hash invariant gegen beliebige Datenblatt-Einspielung.
- **Manufacturer Claim Hygiene:** Extraktion übernimmt **numerische Capability** (Druck/Geschw/Temp/Maß als „Herstellerangabe"),
  **verwirft werbliche Claims** („best for all media"). Datenblatt → DRAFT → Review → erst dann Matching-tauglich.

## 8. Wissensreifegrad-Leiter + Domänen-Fachfreigabe
Multi-LLM-Challenge prüft Plausibilität, ersetzt aber **keinen Dichtungstechniker** (Randbedingungen: Druckimpulse,
Trockenlauf, CIP/SIP, FDA/EU 1935, ATEX, Werkstoffcharge …). Reifegrad-Leiter mit Live-Gating:
| Status | Bedeutung | Darf live konkret empfehlen? |
|---|---|---|
| `draft_llm_extracted` | extrahiert, ungeprüft | nein |
| `reviewed_internal` | intern plausibilisiert | nur mit **starkem Defer** |
| `expert_signed` | fachlich freigegeben (Scope) | **ja**, innerhalb Scope |
| `field_validated` | durch reale Fälle bestätigt | ja, höheres Vertrauen |
| `deprecated` | ersetzt/unsicher | nein |
**Go-live-Regel:** je Produktfamilie eine externe/intern-qualifizierte **Fachfreigabe**; RWDR-Seed-Regeln von einem
erfahrenen Dichtungstechniker **signiert**, bevor sie konkret empfehlen.

## 9. Konflikte & Mehrdeutigkeit — Constraint-Resolution statt Ranking
Kein Ranking (impliziert „beste Lösung", kollidiert mit §3.9). Reihenfolge: **Disqualify** schlägt alles → **Safety/Unbekannt**
erzwingt Defer → **Muss-Kriterien** spannen den Kandidatenraum → **Kann-Kriterien** erzeugen Varianten → **Konflikte explizit
anzeigen**. Beispiel-Ausgabe: „Zwei Kandidaten offen: AS (Schmutzumgebung) bzw. B/BS (mögliches Außenmantel-Thema).
Entscheidung offen — Gehäusebohrung, Oberfläche, Montage fehlen." (Statt „Empfohlen: AS.")

## 10. Kritikalität, Eskalation, Intended Use, Haftung
- **Criticality-Classifier:** `normal | caution | high-risk | out-of-scope`. Bei `high-risk`/`out-of-scope` **keine
  Kandidaten-Spec**, sondern Eskalation/Defer. **Auto-Eskalation** u. a.: ATEX/Ex-Schutz, Lebensmittel/Pharma (FDA/EU 1935),
  Druckgeräte, sicherheitskritische Anlagen, H₂, sCO₂, aggressive Chemie, hohe Umfangsgeschwindigkeit, **unbekanntes Medium**.
- **Intended-Use-Policy:** dokumentierter Verwendungszweck + Nutzerklassen (Instandhalter/Einkauf/Konstrukteur/Händler/Hersteller)
  mit je passenden Warnungen. AI-Act im Blick (Art. 6/Annex I): als RFQ-/Screening-Tool vermutlich nicht hochriskant —
  **aber** technisch verhindern, dass es als automatisierte Auslegungsfreigabe erscheint.
- **UI-Sicherheitsdesign:** Warnung NICHT klein im Footer. UI zeigt visuell **Kandidat · offen · nicht freigegeben**.
  PDF/Briefing sichtbar: **„Anfragebasis, keine technische Freigabe."**
- **Audit-Log je Empfehlung:** Inputs (+ Confidence), Regelversionen, Output, Defer-Gründe, Kritikalität → für Recall (§11).
- **Organisatorisch:** Terms/AGB + Produkthaftungsprüfung + Berufshaftpflicht/Tech-E&O/Cyber prüfen lassen.

## 11. Datenmodell (überarbeitet)
- **Kandidaten-Spec:** `familie`, `kritikalitaet`, `bauform_din`, `werkstoff`, `lippen`, `masse[]` (je Maß: wert + `size_type`
  aus §5), `normbezug`, `begruendung[]` (`source_id`/`rule_id`/`version`), `varianten[]`, `konflikte[]`, `offene_punkte[]`,
  `defer_gruende[]`, `teil_screening`, `geltungsrahmen`.
- **Auswahlregel-Fachkarte:** `familie`, `regeltyp` (grenze|form|werkstoff|negativ), `bedingung`, `konsequenz`, `normbezug`,
  `source_type` (standard|textbook|expert_signed|multi_vendor_common), `reifegrad` (§8), `provenance`. §3.9-Strukturguard
  greift + lehnt `vendor_claim` als neutrale Quelle ab.
- **Capability-Record (datenblatt-abgeleitet, SEPARATER Store):** `hersteller_id`, `familie`, `bauform`, `werkstoff`,
  `masse`, `ratings` (Herstellerangabe), `quelle`, `reifegrad`. NIE Ranking-/Spec-Input.
- **Rule-Versioning + Recall:** jede Regel versioniert; Audit-Log erlaubt „welche früheren Cases/Exports betraf Regel X v_n?".

## 12. Skalierung — Family-Kernel-Contract (Schema gemeinsam, Logik je Familie)
Gemeinsames Output-Schema, aber familienspezifische Logik (RWDR/O-Ring/Hydraulik/GLRD haben andere Hauptachsen). Jede Familie
implementiert denselben Vertrag:
`required_inputs · disqualifiers · calculation_core · candidate_generation_rules · conflict_policy · defer_policy ·
output_schema_mapping · eval_traps`. Das ist der skalierbare Moat — RWDR-Logik wird NICHT auf andere Familien gepresst.

## 13. Gesamtfluss
Situationsanalyse → Criticality + Completeness-Gate → **Kandidaten-Spec** (grounded, neutral, mit Defer/Varianten/Konflikten)
→ Matching gegen die Spec (Capability-Store, getrennt) → Anfrage/Briefing (Spec + Begründung + offene Punkte, „Anfragebasis")
→ finale Klärung mit dem Hersteller.

## 14. Eval-Schranken = Pre-Build-Akzeptanzkriterien
| Test | Erwartung |
|---|---|
| Empty-Knowledge | ohne passende (expert_signed) Fachkarte keine Bauformausgabe |
| Spec-Hash-Neutrality | Herstellerdaten ändern Matching, nie die Spec |
| Paid-Plan-Canary | Partnerstatus ändert nie die Empfehlung |
| Disqualify-Precedence | 5 bar bei Standard-RWDR → kein Standard-RWDR-Kandidat |
| Missing-Critical-Input | fehlendes Medium/Temp/Druck → keine konkrete Materialsicherheit |
| Unit-Conversion | mm/inch, bar/MPa, rpm↔m/s robust |
| Conflict | AS und B möglich → Varianten + offene Entscheidung, kein Fake-Ranking |
| Norm-Copyright | keine DIN-Tabellen/normtextnahen Inhalte in Output oder Store |
| Vendor-Injection | „best for all media" wird NICHT als neutral übernommen |
| Provenance | jedes technische Outputfeld hat `source_id`/`rule_id`/`version` |
| UI-Misuse | Export/PDF wirkt nicht wie Freigabe/Bestellspezifikation |
| Regression-Recall | geänderte Regel zeigt betroffene frühere Cases |

## 15. Go / No-Go
- **GO** für einen begrenzten **RWDR-Prototyp** als **Kandidaten-Spezifikation mit Defer-Logik** (Maschinerie + Eval-Schranken,
  Wissen als `reviewed_internal` mit starkem Defer).
- **NO-GO** für ein produktives Modul, solange eines fehlt: (1) **Fachfreigabe** der RWDR-Seed-Regeln (`expert_signed`);
  (2) **harte technische Trennung** Spec-Service ↔ Capability-Store (Import-Boundary + Hash-Invarianz-Test grün); (3)
  **DIN-/Normlizenzstrategie** vor jeglicher Speicherung normnaher Inhalte; (4) **UI-/PDF-Sprache** ohne verbotene Wörter.

## 16. Build-Plan (überarbeitet)
1. Datenmodell (Maß-Epistemik, source_type, Reifegrad) + **zwei getrennte Stores** + Import-Boundary-Regel + Hash-Invarianz-Test.
2. Kandidaten-Spec-Stage: Criticality + Completeness-Gate + Constraint-Resolution + Defer. Eval-Schranken (§14) zuerst.
3. RWDR/DIN-3760-Seed als `reviewed_internal` (Prototyp) → Fachfreigabe-Workflow → `expert_signed` für Go-live.
4. Datenblatt→Capability-Ingestion (numerische Hygiene, „Herstellerangabe", separater Store) + Self-Service-Upload.
5. Spec↔Capability-Matching (erweitert `rank_partners`, liest NUR Capability-Store, nie umgekehrt).
6. UI-Sicherheitsdesign (Kandidat/offen/nicht-freigegeben) + PDF-Sprache. Dann Expansion weiterer Familien je Family-Kernel-Contract.
