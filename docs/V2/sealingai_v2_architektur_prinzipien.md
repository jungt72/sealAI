# sealingAI V2.0 — Architektur-Prinzipien
### LLM-first, halluzinations-kontrolliert · *supersedes V1.8*

> Status: **supersede + delta**. Dieses Dokument ersetzt die orchestrierungs-zentrierten
> Teile von V1.8. Es ist ein Prinzipien-Dokument (tragende Entscheidungen), kein
> Implementierungs-Blueprint. Gegen *dieses* Dokument und gegen das Eval-Seed-Set wird
> auditiert — nicht mehr gegen den V1.8-Zustandsgraphen.
>
> Vorrang: **V2.0 > V1.8 > V1.7.**

---

## §0 — Delta gegenüber V1.8 (die Überlebenskarte)

**Invertiert / rausgeschrieben** (war spröder Steuer-Determinismus):
- §1.6 „Workflow, nicht Agent" → **LLM-first mit gezielten Leitplanken**
- §7.3 Turn-DAG (route→gate→scheduler…) → **dünne Pipeline** (§3)
- §7.4 Module/Proposals/Gate-als-Schreiber → **LLM komponiert direkt, geerdet**
- §7.5 Dirty Scheduler → entfällt
- §5.3 Mode-Taxonomie + Elicitation-Zwang → **weiche, LLM-geführte Intents**
- §6 Field-Envelope-Zustandsmaschine + Slot-Binding → **leichter, LLM-gepflegter Kontext**

**Bleibt unverändert:** Security/Tenant (P0); die kuratierte Wissensschicht (wird *zentral*);
die Produktidentität.

**Bleibt, aber umgerahmt:** RAG (von „darf keine Wahrheit schreiben" → **Grounding-Substrat**,
§2-L2); Safety-Formel „Erklärung ≠ Freigabe" (von Maschine → **Ehrlichkeits-Norm + Verifikation**,
§2-L3/L4); Jinja2 (Chat → LLM; **RFQ-Rendering bleibt deterministisch**, §4); Observability/Evals
(→ **Halluzinations-/Korrektheits-Evals**, §7).

**Neu (fehlte V1.8 komplett):** die **Vertrauens-Architektur** als Kernkapitel (§2).

**Operative Konsequenz:** Die in Arbeit befindliche **G1-Refaktorierung ist hiermit beendet** —
der Graph, den sie umbaut, wird entfernt. Den bereits committeten, isoliert mergebaren Teil als
Hygiene behandeln; den Graph-Umbau *nicht* fortsetzen (siehe §9).

---

## §1 — Das Leitprinzip

> **Ein starkes LLM antwortet und denkt frei auf Ingenieur-Niveau. Eine dünne Grounding- und
> Verifikations-Schicht beschränkt nur das, was nicht halluziniert werden darf — Zahlen, Normen,
> Verträglichkeits-Spezifika, verbindliche Auswahl. Und das System ist ehrlich über die Grenze
> zwischen robustem Wissen und Zu-Verifizierendem.**

Drei Determinismen, bewusst getrennt:
- **Steuer-Determinismus** (Routing/Intake/Slot-Binding) → **abgeschafft**. War die Quelle der Live-Fehler.
- **Fakten-Grounding** (kuratierte Kompatibilitäts-/Norm-/Werkstoffdaten) → **behalten, ausgebaut**. Quelle der Wahrheit.
- **Mess-Determinismus** (das Eval als stabiles Lineal) → **neu, orthogonal** zur Generativität des Produkts.

Reifegrad-Ziel: **reaktive** Intelligenz jetzt (über das Eval messbar); **prädiktive/lernende**
Intelligenz später (longitudinales Eval auf der Outcome-Schleife, §8).

---

## §2 — Die Vertrauens-Architektur (die Wirbelsäule)

Halluzinationsarmut entsteht **nicht** durch Determinismus, sondern durch vier Schichten, die
zusammen tragen. Keine Schicht beansprucht Vollständigkeit — das ist Design, nicht Mangel.

**L1 · Generator** — starkes LLM + System-Prompt mit *Ingenieur-Register* und *Ehrlichkeits-Normen*.
- Aufgabe: deckt den **unendlichen Antwortraum** ab; integriertes Schließen (§5); das „Warum".
- Darf nicht: präzise Zahlen/Normen erfinden; einen Default unhinterfragt bestätigen.

**L2 · Grounding** — RAG über die kuratierte Wissensschicht für **Spezifika** (Zahlen, Normen,
Verträglichkeit), mit Provenienz/Zitaten.
- Aufgabe: quantitative/normative Aussagen belegen oder als „typisch, verifizieren" markieren.
- Darf nicht: zur impliziten Steuerlogik werden; das Schließen ersetzen.

**L3 · Verifikation** — Kritiker-Pass gegen die **Domänen-Fallenliste** (der Katalog aus dem Eval:
FKM/Dampf, EPDM/Mineralöl, NBR/Ozon, PTFE-Kaltfluss, FKM/Amin, „food-grade"×Fett …) + kalibrierte
Abstention + Bereiche statt Falsch-Präzision.
- Aufgabe: bekannte selbstbewusst-falsche Muster abfangen, bevor die Antwort rausgeht.
- Darf nicht: korrekte Antworten glattbügeln; eine eigene Wahrheitsquelle erfinden.

**L4 · Mensch/Hersteller** — die Grenze „Orientierung ≠ verbindliche Spezifikation"; finale
Validierung und Freigabe.
- Aufgabe: am realen, kritischen Fall entscheiden; Haftung trägt der Hersteller/Händler.
- Architektonisch sichtbar: jede Empfehlung trägt die Orientierungs-Markierung (kein versteckter Disclaimer).

**Das Eval** ist die **Messung** dieses Stacks (Mess-Determinismus, §7) — **keine** Laufzeit-Schicht.

---

## §3 — Die Antwort-Pipeline (dünn)

Ersetzt den 5-Schichten-Router + die Field-Envelope-Intake-Maschine vollständig:

**verstehen → grounden → antworten (mit Konfidenz) → verifizieren → zitieren**

- **verstehen:** das LLM erfasst Frage *und* Kontext; **minimales** Routing — höchstens eine weiche
  Unterscheidung „Wissensfrage" vs. „Fall durcharbeiten", vom LLM gehandhabt, kein deterministisches Gate.
- **grounden:** Retrieval der einschlägigen Spezifika (L2), bevor/während geantwortet wird.
- **antworten:** frei auf Ingenieur-Niveau, mit markierter Konfidenz; eine Rückfrage **nur bei echtem
  Bedarf** und dann *die eine diskriminierende* (nicht als Eingangs-Gate, nicht als Fragenkatalog).
- **verifizieren:** Kritiker-Pass (L3) gegen die Fallenliste.
- **zitieren:** Provenienz — belegt vs. Allgemeinwissen-verifizieren.

Direkte Fehlerbehebung: die dokumentierten Live-Fehler (Wasserdampf-Rückfrage, Salzsäure-Misroute,
Plauder-Geschwafel) sind in dieser Pipeline strukturell ausgeschlossen — keine Demotion-Schicht,
kein Slot-Zwang, kein generischer Opener.

---

## §4 — Deterministisch vs. generativ (die Grenze, explizit)

**Deterministisch / Code (der *gute* Determinismus):**
- **Berechnungen** — Umfangsgeschwindigkeit, PV, Nut-/Spaltauslegung, Dichtungskennwerte; mit
  *zitierten Formeln/Normen*; nie LLM-geraten. Ehrlich über Input-Unsicherheit (Ergebnis ist nur so gut wie die Eingabe).
- **Geerdete KB-Fakten** — Quelle der Wahrheit für Zahlen/Normen/Verträglichkeit.
- **Security/Tenant**, **RFQ-/Briefing-Rendering** (stabiler Artefakt aus geerdeten Fakten),
  **das Eval** (das Lineal).

**Generativ / LLM:**
- das Schließen, die Gesprächsantworten, das **integrierte Reasoning** (§5), die nächstbeste Frage,
  die Warum-Erklärungen.

**Regel:** Zahlen und Normen werden *geerdet*; Schlussfolgern wird *generiert*; die Grenze ist für den
Nutzer **sichtbar** (Provenienz). **Lebensdauer** wird *nicht* als präzise Zahl vorhergesagt — Faktoren
und Auslegungsgrenzen, keine erfundene L10.

### §4.1 — Jinja2: die Implementierung des guten Determinismus

Jinja2 ist das Werkzeug der deterministischen Seite. Drei Rollen, alle sinnvoll:
1. **Prompt-Assembly** — System-/Verifizierer-Prompts aus versionierten Templates + dynamischem Kontext
   (Grounding-Fakten, Fallkontext, Norm-Blöcke); versioniert, diff-bar, testbar, mit konditionalen Blöcken.
2. **Artefakt-Rendering** — Briefing/RFQ, Berechnungs-Report, Compliance-Tabelle: feste Struktur aus
   geerdeten Fakten, jedes Mal gleich, halluzinationsfrei.
3. **Provenienz-/Zitat-Formatierung** — das *Wie* der Quellendarstellung (das *Was* entscheiden LLM + Grounding).

**Nicht** für die **konversationelle Chat-Antwort** — die generiert das LLM. Die Antwort-*Struktur* gehört
als weiche Norm in den Prompt, **nicht** als hartes Post-Template (sonst kehrt die V1.8-Rigidität zurück,
die die Live-Fehler erzeugte).

**Grenzregel:** *Jinja2 baut Prompts und rendert Artefakte; das LLM entscheidet Inhalt.* Niemals Antwort-
oder Domänenlogik in Jinja-Konditionale legen — ein Slot-getriebener if/else-Baum über den fachlichen
Inhalt wäre Steuer-Determinismus durch die Hintertür.

---

## §5 — Die vier Intelligenzen als EIN Reasoning

Medium, Material, Typ, Anwendung sind **kein** Silo-Quartett, sondern **eine bedingungsbewusste Kette**:

`Medium × Anwendung × Bedingungen → Material → Typ → Berechnung → Briefing`

Architektonisch: **ein** Reasoning-Kontext, über den das LLM arbeitet, geerdet an den Stellen, an denen
Spezifika behauptet werden. Der Tiefen-Moat liegt in den **Wechselwirkungen** (FKM passt zum Medium,
versagt an der Temperaturspitze; der Typ muss beim Rührwerk wegen Außermittigkeit anders ausgelegt
werden) — nicht in vier Nachschlagewerken.

---

## §6 — Was aus V1.8 überlebt (carried over)

- **Security/Tenant P0** — unverändert.
- **Kuratierte Wissensschicht** — wird *zentral* (L2-Substrat).
- **Produktoberfläche** — Lebenszyklus/Solution Companion, Briefing, Matching bleiben als *Produkt*;
  ihre deterministische Intake-Implementierung ist weg, das Konzept bleibt.
- **Observability/Tracing** — umgewidmet zum **Eval-Stack** (Halluzination/Korrektheit/Ehrlichkeit).
- **Operating-Window-Vergleich** — bleibt deterministischer Code (§4), der gespeiste Zustand wird LLM-gepflegt.

---

## §7 — Der Bau- und Mess-Loop

`Pipeline bauen → Eval laufen lassen → Glaubwürdigkeits-Quote + Schranken-Quote messen → iterieren.`

- Das **Eval-Seed-Set** ist das **Bauziel** *und* der **Regressionswächter** jeder Änderung.
- **Harte Schranke:** kein „fertig" ohne **100 % Schranken-Quote** (keine betretene Falle, keine
  selbstbewusst-falsche Aussage, keine erfundene Präzision).
- **Red-Team:** jeder schlechte (Live- oder Kollegen-)Treffer wird ein neuer Fall.
- **Generalisierung statt Memorieren:** eine **verdeckte/rotierende Teilmenge** zurückhalten.
- Das Eval misst den Generator, es enumeriert den Antwortraum nicht — die Stichprobe testet das
  *Schließen*, das Schließen generalisiert.

---

## §8 — Offene strategische Entscheidungen (Parkplatz)

Nicht Prinzip-Ebene, aber von der Architektur künftig zu tragen:
- **Nachfrage-Persona:** *entschieden* — der Nicht-Spezialist mit nicht-trivialem Dichtungsproblem
  (Konstrukteur + Reliability-Ingenieur), Tiefe-zuerst.
- **Angebotsseite:** Hersteller *oder* Hersteller + technische Händler — **offen**.
- **Hersteller-Fähigkeitsregister + neutrales Matching** — *harte Regel:* **kein Pay-to-Rank, kein
  bezahlter Einfluss auf die Beratung**; Zahlung kauft Eligibilität im fähigkeitsgematchten Pool.
- **Evidence-Intake** (Foto / Altteil / Datenblatt / Typenschild) — der Nutzer kennt seine Parameter oft nicht.
- **Compliance-Intelligenz** (Lebensmittel/FDA/EG 1935, Wasser/KTW, ATEX, Pharma/USP VI) — Wissens- *und* Matching-Dimension.
- **Prädiktive/lernende Schleife** — das longitudinale Eval auf Outcome-Daten; die „Decke" der Intelligenz; später.
- **Kaltstart** — Wissensschicht seeden (Normen/Handbücher/Datenblätter) + erste Angebotsseite gewinnen.

---

## §9 — Geltung & Vorrang

- **V2.0 > V1.8 > V1.7.**
- Die deterministische Orchestrierungs-Spec (V1.8 §1.5/§1.6/§5.3/§6/§7) ist **pensioniert** — *nicht*
  mehr Audit-Maßstab.
- Die **G1-Arbeit ist abgeschlossen**: vor weiteren Commits stoppen; den isoliert mergebaren Teil als
  Hygiene behandeln, den Graph-Umbau nicht fortsetzen.
- Audit-Maßstab ab jetzt: **dieses Dokument + das Eval-Seed-Set.**
