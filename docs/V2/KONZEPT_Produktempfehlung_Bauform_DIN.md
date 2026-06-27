# Konzeptpapier — Grounded Produktempfehlung (Bauform · Material · Lippen · DIN) + Hersteller-Datenblatt-Ingestion mit Neutralitäts-Firewall

**Status:** Entwurf zur adversarialen Review (vorgesehen: Challenge durch GPT 5.5)
**Datum:** 2026-06-27 · **System:** sealingAI V2.1 · **Modul:** „Produktempfehlung" (neu)

---

## 0. Wie dieses Papier zu lesen ist
Es beschreibt ein NEUES Modul für ein BESTEHENDES System mit zwei nicht verhandelbaren Leitplanken (§2).
Domänen-Spezifika (konkrete DIN-Schwellen, Formregeln) sind ILLUSTRATIV und ausdrücklich als
„*domänen-zu-validieren*" markiert — die autoritativen Regeln entstehen durch fachlich gereviewtes,
kuratiertes Wissen, NICHT durch dieses Papier. Das Papier befolgt damit selbst die No-Hallucination-
Disziplin, die das Modul durchsetzen soll. Der Reviewer wird gebeten, §10 (Risiken/offene Fragen)
besonders hart zu prüfen.

## 1. Zweck & Ziel
Zwischen „Situationsanalyse" und „mit dem Hersteller sprechen" fehlt heute ein Schritt: die
**Produktspezifikation** (Bauform + Werkstoff + Lippenzahl + Maße + DIN-Bezug).

**Ziel:** Der User soll seine eigene Dichtungssituation *perfekt verstehen* und auf Basis der Bedarfs-/
Situationsanalyse den *korrekten Produkttyp* (Bauform/Werkstoff/Lippen/Maße) als **grounded Screening**
mit **DIN-Verankerung** empfohlen bekommen — als nachvollziehbar begründeten Gesprächsanker, den er dann
mit dem Hersteller bespricht und finalisiert.

### Nicht-Ziele
- Keine Freigabe-/Eignungs-/Compliance-Zusage. Geltungsrahmen: Orientierung/Screening + Hersteller-Prüfgrundlage.
- Kein Ersatz der Hersteller-Auslegung; finale Maß-/Form-/Werkstoff-Freigabe liegt beim Hersteller.
- Keine Reproduktion von DIN-Normtext/-Tabellen (Urheberrecht, Beuth).
- Keine Erfindung von Typen/Maßen außerhalb des kuratierten Wissens.

## 2. Die zwei Leitplanken (jeder Entwurf MUSS sie erfüllen)
- **G1 — No Hallucination / Grounding.** Jede fachliche Aussage (Bauform, Werkstoff, Lippenzahl, Schwelle,
  DIN-Bezug) stammt ausschließlich aus reviewten Fachkarten (der EINEN Wissens-SSoT) oder dem
  deterministischen Rechenkern. Fällt die Situation aus dem kuratierten Wissen → explizit *deferieren*,
  nicht erfinden. (Bestehend: Trust-Spine L1→L2-Grounding→L3-Verifier→L4; „Gegencheck/Modus E" arbeitet
  disqualify-only.)
- **G2 — §3.9 Neutralität.** Die Empfehlung *was der User braucht* ist herstellerblind und rein fachlich.
  Bezahlung und Hersteller-Daten dürfen die Empfehlung NIE beeinflussen — nur das Matching „welcher
  zahlende Partner kann das liefern". (Bestehendes Muster: Trennung Pool-Mitgliedschaft vs. Capability-Ranking.)

## 3. Systemkontext (für die externe Review)
Kompakt, damit der Entwurf gegen die realen Constraints bewertbar ist:
- **Fachkarten** = reviewte JSON-Wissens-SSoT (kein freies RAG). **Trust-Spine** L1 (Generator) → L2
  (Grounding gegen Fachkarten + §4-Matrix) → L3 (Verifier) → L4.
- **§4-Verträglichkeitsmatrix** (Medium × Werkstoff), **Versagensmodi-Store**, **Trap-Katalog** (typische
  Fehlentscheidungen, die deterministisch disqualifiziert werden).
- **Case-State-Destillation** = die laufende Bedarfsanalyse (Medium, Druck, Geschwindigkeit, Temperatur,
  Geometrie, Verschmutzung …) + ein **deterministischer Rechenkern** (z. B. PV-Wert).
- **Partner-Pool** (Modus F) + **Capability-Matching**; §3.9 durch Trennung (Bezahlung = Pool-Mitgliedschaft,
  Auswahl = Fähigkeits-Fit, `plan` nie Ranking-Input).
- **Geltungsrahmen** auf jeder Oberfläche; **Review-/Challenge-Ingestion-Pipeline** (Doc → DRAFT → Review →
  promote in die SSoT).
Das neue Modul SLOTTET in diese Teile, es ersetzt nichts.

## 4. Architektur — die Produktspezifikations-Stage
- **Position:** nach der Situationsanalyse (ausgearbeiteter Case-State), VOR dem Partner-Matching.
- **Input:** Case-State + bereits ermittelte Rechenkern-Werte.
- **Mechanik:** grounded Ableitung über kuratierte **Auswahlregel-Fachkarten** je Dichtungsfamilie, drei
  Regeltypen:
  1. **Familien-/Eignungsgrenzen (disqualify):** z. B. Standard-RWDR nach DIN 3760 bis ~0,5 bar / ~12 m/s
     *[illustrativ, domänen-zu-validieren]* → darüber disqualifiziert → andere Familie nötig. (Reuse:
     Gegencheck/Trap-Logik.)
  2. **Form-Regeln:** Verschmutzung → S-Form mit Staublippe (AS/BS/CS); Medium/raue Bohrung am Außen-Ø →
     Metallmantel (Form B); sauber/Standard → Form A. Lippenzahl folgt aus der Umgebung.
  3. **Werkstoff:** aus der §4-Matrix (Medium × Werkstoff) + Temperaturgrenzen (z. B. FKM statt NBR bei
     150 °C in aggressivem Öl).
- **Output (strukturiert):** die DIN-konforme Bezeichnung als Startpunkt, z. B. `DIN 3760 – AS – Ø50×72×8 – FKM`,
  + Normverweis als Basis + **Begründungskette** (welche Regel/Fachkarte, mit Provenance) + Geltungsrahmen +
  **offene Punkte**, die der User mit Hersteller/DIN klärt.
- **No-Hallucination in der Stage:** keine Regel-Treffer → kein Typ. Teil-Screening + explizite Defer
  („Familie X plausibel; genaue Form/Maß gegen DIN Y + Datenblatt verifizieren").

## 5. DIN-Abgleich & Urheberrecht
- **Encodebar** (reviewte Fachkarten): die ENTSCHEIDUNGSLOGIK, die TYPBEZEICHNUNGEN (A/AS/B/C …), die
  NORMNUMMER, sowie weit publizierte Nenn-Maßreihen (Fakten).
- **Nicht reproduziert:** DIN-Normtext/-Tabellen (Urheberrecht).
- **„Abgleich gegen die DIN"** heißt: die KI liefert die DIN-verankerte Hypothese + den Normbezug; der
  User/Hersteller gleicht gegen die ECHTE DIN + das Datenblatt ab. Die KI ZEIGT auf die Norm, ist sie nicht.

## 6. Hersteller-Datenblatt-Ingestion + Neutralitäts-Firewall (das Risiko-Herzstück)
**Warum Datenblätter:** sie tragen die REALE Produkt-Capability (welche konkreten Produkte die Spec
erfüllen — exakte Druck-/Geschwindigkeits-/Temperatur-Ratings, Werkstoffgüten, Sonderdesigns, Maße). Das
neutrale Wissen sagt, was der User BRAUCHT; das Datenblatt sagt, was ein Hersteller LIEFERN kann.

**Die Firewall (Trennung, identisch zum bezahlten Pool):**
- Datenblatt-Daten füttern AUSSCHLIESSLICH die Capability-/Matching-Schicht (passt Partner X' Produkt zur
  abgeleiteten Spec?), NIE die neutrale Empfehlung.
- **Quarantäne/Review:** Datenblatt → Extraktion → DRAFT-Capability-Record → Owner/Experten-Review → erst
  dann fürs Matching vertrauenswürdig (kein Direkt-Inject; Datenblatt ist interessengeleitet + ungeprüft).
- **Labeling:** Herstellerwerte als „**Herstellerangabe**" markiert, nie als neutrale Ingenieursaussage. Der
  User verifiziert sie mit dem Hersteller (= das erklärte Ziel).
- **Innovation:** ein neuartiges Hersteller-Design darf in die neutrale Empfehlung NUR, nachdem der Owner es
  zu *herstellerblindem* Generikwissen abstrahiert hat (eigene reviewte Fachkarte) — nie als „kauf Produkt X".
- **Upload-Ort:** das bereits gebaute Self-Service-Dashboard — der Hersteller pflegt sein Datenblatt selbst →
  bessere Matchbarkeit, ohne neue Vertrauensfläche.

## 7. Datenmodell (Skizze)
- **Produktspec (Output):** `familie`, `bauform_din` (z. B. „DIN 3760-AS"), `werkstoff`, `lippen`,
  `masse` (Ø×Ø×b), `normbezug`, `begruendung[]` (Regel-/Fachkarten-Provenance), `offene_punkte[]`,
  `teil_screening` (bool), `geltungsrahmen`.
- **Auswahlregel-Fachkarte (kuratiertes Wissen):** `familie`, `regeltyp` (grenze|form|werkstoff),
  `bedingung` (Schwelle/Prädikat über Case-State-Felder), `konsequenz` (Bauform/Werkstoff/Disqualifikation),
  `normbezug`, `review_state`, `provenance`. Strukturell wie bestehende Fachkarten; der §3.9-Strukturguard
  (kein `rank/paid/tier`-Feld) greift weiter.
- **Hersteller-Capability/Produkt-Record (datenblatt-abgeleitet):** `hersteller_id`, `familie`, `bauform`,
  `werkstoff`, `masse`, `ratings` (druck/geschw/temp) als „Herstellerangabe", `quelle` (datenblatt-id),
  `review_state`. NIE Ranking-Input; nur Matching.

## 8. Gesamtfluss
Situationsanalyse → **Produktspec** (grounded, neutral) → **Partner-Matching gegen die Spec** (Capability,
inkl. reviewter Datenblatt-Daten) → Anfrage/Briefing (enthält Spec + Begründung + offene Punkte) →
**finale Klärung mit dem Hersteller**.

## 9. Wissenskuration — der eigentliche Moat
Der Code ist überschaubar; der Wert liegt in den Auswahlregel-Fachkarten je Familie. Kuration über die
bestehende Review-/Challenge-Pipeline (Multi-LLM-Challenge + Owner-Review), da der Owner keine
Domänenexpertise hat. Start: **RWDR / DIN 3760** als Referenzfamilie (häufigster Fall, Schwellen belegbar),
dann O-Ring (ISO 3601), Hydraulik (Stangen/Kolben), Gleitringdichtung (GLRD).

## 10. Risiken, Annahmen & offene Fragen — BITTE BESONDERS CHALLENGEN
1. **Domänen-Korrektheit OHNE Sealing-Engineer:** Owner + LLMs kuratieren. Wie wird die fachliche
   Richtigkeit der Auswahlregeln VALIDIERT, bevor sie live gehen? Reicht Multi-LLM-Challenge + Eval-Traps,
   oder braucht es zwingend mind. eine externe Fachreview je Familie? Haftungsfolgen?
2. **Firewall-Robustheit:** Kann Datenblatt-Information die Empfehlung INDIREKT verzerren (z. B. wenn dieselbe
   Person Fachkarten UND Datenblätter kuratiert, oder über die Maßreihen)? Wie wird die Trennung STRUKTURELL
   (nicht nur prozessual) erzwungen?
3. **Pseudo-Präzision:** Wie verhindern wir, dass die KI eine Genauigkeit suggeriert (exakte Maße), die der
   User für eine fertige Auslegung hält? Genügen Geltungsrahmen + `offene_punkte` + `teil_screening`?
4. **Mehrdeutigkeit/Konflikte:** Wenn Regeln mehrere Bauformen zulassen oder kollidieren — wie wird
   priorisiert + transparent gemacht, ohne zu raten?
5. **Skalierung über RWDR hinaus:** O-Ring/Hydraulik/GLRD haben andere Typsystematiken. Trägt ein gemeinsames
   Schema, oder braucht jede Familie ein eigenes?
6. **DIN-Urheberrecht:** Wo genau verläuft die Grenze „Entscheidungslogik/Maßreihe (Fakt)" vs. „geschützte
   Normtabelle"? Ist der Ansatz konservativ genug?
7. **Haftung:** Reicht „Screening/Orientierung", wenn ein User die Empfehlung dennoch ungeprüft umsetzt?
8. **Eval-Schranken:** Welche deterministischen Schranken testen hier Grounding + Neutralität + Disqualifikation
   konkret (analog zu den bestehenden TRAP-/CALC-Schranken)?

## 11. Build-Plan (Phasen)
1. Datenmodell + Produktspec-Stage (grounded, disqualify-aware) + Eval-Schranken.
2. RWDR/DIN-3760-Referenzregeln (eine kuratierte Auswahlregel-Fachkarten-Familie) als Muster + Seed.
3. Datenblatt→Capability-Ingestion mit Firewall + „Herstellerangabe"-Labeling (Self-Service-Upload).
4. Matching der Spec gegen Capability (erweitert `rank_partners`).
5. Expansion auf weitere Familien.

## 12. Erfolgskriterien
- Jede fachliche Ausgabe hat Fachkarten-Provenance (Grounding messbar).
- Disqualifikations-Traps greifen (z. B. Standard-RWDR bei 5 bar → disqualifiziert, NICHT empfohlen).
- Neutralitäts-Keystone-Test: Datenblatt-Daten ändern das Matching, NIE die Empfehlung.
- Der User erhält eine DIN-verankerte, nachvollziehbar begründete Spec + klare offene Punkte fürs Hersteller-Gespräch.
