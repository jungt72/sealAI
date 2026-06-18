# sealingAI V2.0 — Green-Field Build-Spec (Arbeitsauftrag für Claude Code)

> **Forward (V2.1):** the next-phase WHAT/HOW live in `sealingai_v2_1_produkt_konzept.md` +
> `sealingai_v2_1_implementierungs_konzept_cc.md` — an evolution of this spec. This build-spec stays
> the executable V2.0 plan; the V2.1 docs are the forward SoT for the increment build.

> **Was das ist:** ein **ausführbarer Bauplan** für einen Neuaufbau auf der grünen Wiese.
> CC baut dagegen, der Owner gatet an HALT-Punkten. Kein 800-Zeilen-Blueprint — Verträge,
> Sequenz, Abnahme, Grenzen.
>
> **Normative Anhänge (gelten verbindlich, hier nicht dupliziert):**
> - `sealingai_v2_architektur_prinzipien.md` — die tragenden Prinzipien (das *Warum*)
> - `sealingai_eval_seed_set_v0.md` — das **Abnahme-Lineal**
> - `sealingai_system_prompt_l1.jinja` — der **validierte L1-Generator-Seed**
>
> **Vorrang:** diese Spec + die Anhänge **>** V1.8 **>** V1.7.
> **Audit-Maßstab ab jetzt:** diese Spec + das Eval. Die alte deterministische Orchestrierung
> (V1.8 §1.5/§1.6/§5.3/§6/§7) und die G1-Refaktorierung sind **pensioniert** (§11).

---

## 1 — Das Produkt (Nordstern, ein Absatz)

sealingAI ist eine **Dichtungstechnik-Intelligenz**: Sie beantwortet *jede* Frage zur
Dichtungstechnik auf **Ingenieur-Niveau, in der Tiefe, ohne Halluzinationen**, hilft dem
Nutzer, seine konkrete Dichtungssituation durchzuarbeiten, erzeugt ein **herstellerfertiges
Briefing**, und zeigt — **neutral** — passende Hersteller/Händler. Entwickelt wird sie
**Tiefe-zuerst**: das vertrauensbildende Herz ist die Antwortqualität, alles andere hängt sich
daran. Die finale Freigabe liegt immer beim Hersteller/Händler (Haftungsausschluss sealingAI).

---

## 2 — Architektur-Überblick

**Vier-Schichten-Vertrauensmodell** (Details: Prinzipien §2):
- **L1 Generator** — starkes LLM + L1-System-Prompt; deckt den unendlichen Antwortraum ab.
- **L2 Grounding** — Fachkarten + Verträglichkeitsmatrix (RAG); erdet Spezifika, liefert Provenienz.
- **L3 Verifizierer** — Kritiker-Pass gegen Fallen-Katalog + Matrix; fängt selbstbewusst-Falsches ab.
- **L4 Mensch/Hersteller** — Orientierung ≠ Freigabe; finale Validierung.

**Dünne Pipeline** (eine gerichtete Kette, kein Routing-Geflecht):
`verstehen → grounden → antworten (mit Konfidenz) → verifizieren → zitieren`

**Grenze deterministisch/generativ** (Prinzipien §4): Berechnungen + geerdete Fakten + Artefakt-
Rendering = Code (Jinja2); Schließen + Gesprächsantwort = LLM. Provenienz sichtbar.

---

## 3 — Tech-Stack & Repo-Struktur

**Stack-Entscheidungen** (CC darf im Detail anpassen, nicht im Kern):
- **Python + FastAPI** Backend (konsistent mit Bestand).
- **LLM-Zugriff** per API; **Tiering**: starkes Frontier-Modell für L1 (Generator) und L3
  (Verifizierer); günstigeres Modell nur für Hilfsaufgaben. Modellwahl ist Config (§9-Abnahme
  entscheidet, ob günstiger reicht) — nicht hartkodieren.
- **Jinja2** für Prompt-Assembly *und* Artefakt-Rendering (Prinzipien §4.1).
- **Postgres** = dauerhafter System-of-Record (Unterhaltungen, Nachrichten, Fallzustand-Snapshots,
  Nutzer-Gedächtnisprofil, **Fachkarten kanonisch** mit Provenienz + Review-State, Matrix).
- **Redis** = heißes Arbeitsgedächtnis (aktives Gesprächsfenster + Live-Fallzustand).
- **Qdrant** = Vektor-Retrieval (Fachkarten/Matrix + Gedächtnis-Fakten + Vergangenheits-Chats).
- **Security/Tenant ab Tag 1** (P0, aus V1.8 übernommen): server-seitige Tenant-Filter,
  Pipeline für unvertraute Inhalte, keine Secrets in Logs.

**Vorgeschlagene Repo-Struktur** (CC darf justieren):
```
sealingai/
  core/         # reine Domänenlogik + Berechnungen (zitierte Formeln), keine I/O
  pipeline/     # die 5 Stufen: understand, ground, answer, verify, cite
  prompts/      # jinja2: system_l1.jinja (Seed vorhanden), verifier_l3.jinja, ...
  knowledge/    # Fachkarten-Schema + Loader, Verträglichkeitsmatrix, Retrieval
  memory/       # 4 Schichten: working(redis), durable(postgres), retrieval(qdrant)
  render/       # jinja2-Artefakt-Rendering: briefing/rfq, calc-report
  eval/         # Seed-Set-Fälle + Harness + Scorer + Schranken-Gate
  api/          # FastAPI: chat, conversations, briefing
  security/     # Tenant-Scoping, unvertraute Inhalte, Injection-Guards
  config/       # Modell-Tiers, Flags
```
**Disziplin:** dünne Adapter, reine `core/`-Funktionen (die gute Lektion aus dem Alten, ohne die
alte Orchestrierung).

---

## 4 — Komponenten-Verträge

Je Komponente: *Verantwortung · Eingang → Ausgang · darf NICHT*.

**L1 Generator** — Seed: `system_prompt_l1.jinja` (bereits validiert).
- Eingang: Nutzerfrage + `grounding_facts` + `case_context` + Flags (`compliance_hint`, `safety_critical`, `anrede=du`).
- Ausgang: Antwort auf Ingenieur-Niveau, **Tiefe nach Frage-Typ** (Wissensfrage → ausführlich; Fallarbeit → Orientierung + die *eine* Frage; Faktfrage → kurz), mit markierter Konfidenz + Provenienz.
- Darf nicht: präzise Zahlen/Normen erfinden; Defaults unhinterfragt bestätigen; Bekanntes erneut fragen; inhaltsleer aufblähen.

**L2 Grounding** — Fachkarten + Matrix über Qdrant.
- Eingang: Anfrage/Kontext → Ausgang: relevante Fachkarten + Matrix-Zeilen **mit Provenienz** (in `grounding_facts`).
- **Fachkarte (Schema):** Identität · Familie · Eigenschaften (Bereiche + Bedingungen) · Mechanismen · Verträglichkeit · Versagensmodi/Grenzen · typische Bauformen · Trade-offs · Zulassungen · **Provenienz je Aussage** · **Review-State** (`draft`/`reviewed`) · Querverweise.
- **Verträglichkeitsmatrix:** relational, abfragbar — Medium × Werkstoff × Bedingung → Bewertung + Quelle. Speist **L2 und L3**.
- Darf nicht: vorgeschriebene Prosa-Antworten enthalten (Karten = geerdete *Substanz*, keine Antworten); ungeprüfte Karten als voll-autoritativ ausgeben (→ L1 markiert „vorläufig").

**L3 Verifizierer** — eigener Pass (Jinja2-Prompt, noch zu entwerfen).
- Eingang: Entwurfsantwort + ihre Aussagen → Ausgang: Prüfung gegen **Fallen-Katalog + Matrix**; markiert/korrigiert; Schranken-Verstöße (betretene Falle, erfundene Präzision, selbstbewusst-falsch) blocken.
- **Fallen-Katalog** = aus dem Eval-Set + der Matrix abgeleitet, gepflegt.
- Darf nicht: korrekte Antworten glattbügeln; eine eigene Wahrheitsquelle erfinden.

**Deterministische Schicht** — `core/` + `render/`.
- Berechnungen als **Code** mit zitierten Formeln (Umfangsgeschwindigkeit, PV, Nut-/Verpressungs-auslegung); ehrlich über Input-Unsicherheit; **keine** Lebensdauer-Punktzahl.
- **Artefakt-Rendering (Jinja2):** Briefing/RFQ + Berechnungs-Report aus geerdeten Fakten — stabil, jedes Mal gleich.

**Gedächtnis** — siehe §7.

**Eval-Harness** — `eval/`.
- Führt die Seed-Fälle gegen die Pipeline, bewertet gegen die Rubrik (7 Achsen), erzwingt die **Schranken-Quote** und liefert die Glaubwürdigkeits-Kennzahl.

---

## 5 — Die Pipeline im Detail (Stufen-I/O)

1. **verstehen** — LLM erfasst Frage + Kontext; **weiche** Unterscheidung „Wissensfrage" vs.
   „Fall durcharbeiten" (kein deterministisches Gate). Konversations-Oberfläche (§6) hier.
2. **grounden** — L2-Retrieval: relevante Fachkarten + Matrix-Zeilen → `grounding_facts`.
3. **antworten** — L1 komponiert die Antwort (Tiefe nach Typ), geerdet, mit Konfidenz; eine
   diskriminierende Rückfrage **nur bei echtem Bedarf**, nie Bekanntes erneut.
4. **verifizieren** — L3 prüft gegen Fallen-Katalog + Matrix; markiert/korrigiert/blockt.
5. **zitieren** — Provenienz: belegt vs. „Allgemeinwissen — verifizieren".

---

## 6 — Konversations-Oberfläche

(LLM-Verhalten + Leitplanken, **kein** deterministischer Modus — schließt den alten Begrüßungs-Bug aus.)
- **Begrüßung/Smalltalk:** kurz, freundlich, in der Rolle, zur Dichtungssituation überleiten — kein kanned-Text.
- **Register:** empathischer Ingenieur; Tiefe nach Frage-Typ; Wärme über *Nützlichkeit*, nicht Floskeln (Detail im L1-Prompt).
- **Off-Topic:** freundliche Grenze + Rückführung, keine Konfabulation.
- **Unsinn/Trolling/adversarial:** in der Rolle bleiben, nicht entgleisen.
- **Prompt-Injection-Resistenz** — besonders für unvertraute Uploads (Datenblätter, Altteil-Beschreibungen); hängt an `security/`.
- **Eval:** eine **Konversations-Rand-Klasse** ist nachzurüsten (Begrüßung, Smalltalk-Rückführung, Unsinn, Injection).

---

## 7 — Gedächtnis (4 Schichten)

1. **Gesprächskontext (Redis)** — aktuelles Chatfenster; lange Chats: jüngste Turns verbatim + rollende Zusammenfassung.
2. **Strukturierter Fallzustand (Redis live, Postgres-Snapshot)** — destillierte Fakten (Medium/Temp/Anwendung/Empfehlung); speist `case_context`. **Prinzip: strukturierter Zustand überlebt Summarisierung** — die Fakten, die nie verloren gehen dürfen, liegen *strukturiert*, nicht nur im Transkript (das war der Re-Ask-Bug).
3. **Historische Chats (Postgres)** — persistieren, auflisten, wieder aufrufen.
4. **Cross-Session-Gedächtnis (Postgres-Profil + Qdrant-Retrieval)** — extrahierte **dauerhafte Fakten** (nicht Transkripte), bei Relevanz eingespielt.

**Disziplinen (verbindlich):** kuratiert merken (nicht alles); relevanz-basiert einspielen (nicht jeden Turn alles); **Nutzerkontrolle** (ansehen/bearbeiten/löschen); **strikte Pro-Nutzer/Tenant-Trennung** (Leck = schwerer Fehler, P0); Veralten → bei Konsequenz rückfragen; **Ehrlichkeit gilt auch hier** (erinnerter Fakt ≠ Evangelium).

---

## 8 — Fachkarten-Lebenszyklus (Wissensschicht)

Deep-Research (großes LLM) ist **Entwurfs-/Quellen-Beschleuniger**, **nicht** die Wahrheitsquelle.
Zwingender Ablauf, sonst Zirkularität (LLM erdet LLM):
1. **Entwurf** — Deep Research erstellt die strukturierte Karte und **zitiert Primärquellen je Aussage** (Normen/Datenblätter/Literatur); Unbelegtes wird markiert, nicht akzeptiert.
2. **Quelle** — Karte ruht auf den zitierten Primärquellen, nicht auf dem Modell.
3. **Review (Owner/Experte)** — prüft, setzt State auf `reviewed`; das ist Sicherheits-Gate **und Moat** (deine Expertise an den umstrittenen Zellen; reine Deep-Research-Ausgabe ist Commodity).
4. **Matrix besonders:** Einträge über **mehrere Quellen** gegenprüfen — Übereinstimmung stark, Widerspruch = „verifizieren"-Zelle.
5. **Nachpflege/Versionierung:** jedes Update = neuer Entwurf → erneute Prüfung; Quellendaten mitführen; L3-/Outcome-Widerspruch → Neuprüfung.
**Bau-relevant:** L1 antwortet auch **vor** voller Kartenbibliothek tief (parametrisch) — die Karten *heben* die Tiefe auf „geerdet/zitiert". Die Karten blockieren den Start nicht (Content-Track läuft parallel, §10).

---

## 9 — Abnahme (Acceptance)

- **Das Eval-Seed-Set ist das Abnahme-Lineal.** Ein Meilenstein gilt als erreicht, wenn die
  einschlägigen Fälle bestehen.
- **Harte Schranke:** **100 % Schranken-Quote** (keine betretene Falle, keine selbstbewusst-
  falsche Aussage, keine erfundene Präzision) — kein „fertig" ohne das.
- **Glaubwürdigkeits-Kennzahl** über die 7 Achsen, je Meilenstein verfolgt.
- **Generalisierung:** verdeckte/rotierende Teilmenge zurückhalten (kein teaching-to-the-test).
- **Eval nachrüsten:** Wissens-Tiefe-Klasse (belohnt Tiefe, bestraft Unter-Tiefe *und* Aufblähen) + Konversations-Rand-Klasse.

---

## 10 — Bau-Sequenz & Meilensteine (mit HALT)

Reihenfolge: erst messen, dann weiterbauen. Nach **jedem** Meilenstein Eval-REPLAY + Owner-Gate.

- **M1 — Skelett + L1 + Eval-Harness.** Repo-Gerüst, L1-Generator (Seed-Prompt), minimale Pipeline (verstehen→antworten), Eval-Harness. → **erste echte Messung** von L1-allein. *HALT.*
- **M2 — L3 Verifizierer + Fallen-Katalog.** → Fallen-Vermeidung sollte springen. *HALT.*
- **M3 — L2 Grounding.** Fachkarten-Schema + Matrix + Retrieval, mit Seed-Karten. → Spezifika geerdet/zitiert. *HALT.*
- **M4 — Deterministische Schicht.** Berechnungen (Code, zitiert) + Artefakt-Rendering (Briefing/RFQ). *HALT.*
- **M5 — Gedächtnis.** Gesprächskontext + Fallzustand + Persistenz; dann Cross-Session. *HALT.*
- **M6 — Konversations-Oberfläche + Security/Injection härten.** *HALT.*

**Parallel (Content-Track, blockiert Code nicht):** Fachkarten-Kuration (Deep-Research → Quelle → Review) füllt L2 fortlaufend.

---

## 11 — Grüne-Wiese-Grenze

**Übernehmen:** Security/Tenant-Muster (P0); vorhandene kuratierte Wissens-Inhalte (falls da); das Eval; Tracing-Konzepte; den L1-Prompt.
**NICHT übernehmen:** die alte Orchestrierung (Turn-DAG, Pre-Gate/Router, Slot-Binder, Field-Envelope-Zustandsmaschine), die G1-Refaktorierung. Neuer, sauberer Modul-Satz.
**G1 ist beendet** — kein weiterer Aufwand in den toten Graphen; isoliert Mergebares nur als Hygiene.

---

## 12 — Leitplanken für CC

- **Dünne Adapter, reine `core/`-Logik.** Jinja2 baut Prompts + rendert Artefakte, **entscheidet nie fachlichen Inhalt** (keine Domänenlogik in Jinja-Konditionalen).
- **Gegen das Eval bauen**, nicht gegen ein Bauchgefühl.
- **HALT an jedem Meilenstein**, Owner gatet (Relay-Muster wie gehabt).
- **Baubar, kein Korsett:** diese Spec gibt Verträge + Abnahme + Seeds; Implementierung im Detail frei.
- **Nicht verhandelbar:** die Ehrlichkeits-/Grounding-/Verifikations-Wirbelsäule und Tenant-Scoping (P0).
- **Überspezifikation vermeiden** — sie würde die alte Rigidität zurückbringen.

---

## 13 — Anhänge (normativ, referenziert)

- `sealingai_v2_architektur_prinzipien.md`
- `sealingai_eval_seed_set_v0.md`
- `sealingai_system_prompt_l1.jinja`
