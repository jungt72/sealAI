# sealingAI V2.1 — Produkt-Konzept

**Status:** Entwurf zur Weiterentwicklung
**Verhältnis zu V2:** Evolution, kein Neubau. V2.1 baut auf der bestehenden Trust-Spine (L1–L4), der dünnen linearen Pipeline, dem deterministischen Rechenkern, der Verträglichkeitsmatrix und den Fachkarten auf. Was 2.1 hinzufügt, sind neue *Eingänge*, neue *Operationen* und neue *Wissens-Dimensionen* — auf demselben Fundament.
**Zweck:** Das gemeinsame, geerdete Produktverständnis festhalten — präzise genug, um die nächste Bauphase zu treiben, und doktrinär genug, dass das Produkt kohärent bleibt, während es wächst.

---

## 0. Was dieses Dokument ist

Dieses Konzept beschreibt **was** sealingAI V2.1 für den Anwender sein soll und **wie** es architektonisch zusammenhängt — nicht die Implementierungsdetails (die entstehen im doktrin-gegateten Bau mit Claude Code, Gap für Gap, gegen die `build_spec`).

Es löst eine konkrete Gefahr: dass das Produkt zu einem **starren Empfehlungs-Trichter** verkommt, der jeden Anwender durch „nenn mir deine Anwendung" presst — oder umgekehrt zu einem **Werkzeugkasten** loser Features ohne gemeinsame Mitte. V2.1 ist keins von beidem. Es ist **ein Dichtungsexperte mit einem geerdeten Wissensschatz und einer Trust-Spine**, den man über verschiedene Eingänge erreicht und der verschiedene Operationen anbietet.

---

## 1. Leitbild — das Produkt in einem Satz

> **sealingAI ist ein Dichtungsexperte, mit dem man redet, wie man gerade muss — er versteht die Anwendung besser, als der Anwender sie beschreiben kann, empfiehlt mit geerdeter Sicherheit das richtige Material und die richtige Bauform, und legt seine Begründung offen, damit Vertrauen *informiert* ist, nicht blind.**

Drei Versprechen stecken darin:

1. **Verstehen über die Beschreibung hinaus.** Der Wert ist nicht „bereite eine qualifizierte Anfrage vor" (das ist Hersteller-Wert in Verkleidung). Der Wert ist, die *nicht-offensichtlichen* Faktoren aufzudecken, von denen der Anwender nicht wusste, dass sie zählen.
2. **Geerdete, selbstbewusste Empfehlung.** Der Anwender erwartet das *korrekte* Material. Das *ist* das Produkt.
3. **Offengelegte Begründung → informiertes Vertrauen.** Die Trust-Spine, die Provenienz und die Ehrlichkeit sind das Gegengift gegen „blindes Vertrauen" — und das, was V2 zu einem *glaubwürdigen* Experten macht.

---

## 2. Der Anwender und sein Schmerz

**Der typische Anwender ist kein Dichtungsexperte.** Er ist z. B. ein Getriebe-Konstrukteur, der über die Dichtung als *peripheres Sub-Bauteil* „gestolpert" ist — ein Teil, das normalerweise ausgelagert oder blind übernommen wird.

**Der heutige Prozess ist verlustbehaftet:**

```
flache Parameter rein → flache Hersteller-Einschätzung → blindes Vertrauen → Feldtest-Validierung
                                                                              (Ausfallkosten bei der am wenigsten gerüsteten Partei)
```

Er weiß nicht, was er nicht weiß. Das Ergebnis ist eine Entscheidung, die auf zu wenig Verständnis beruht und deren Korrektheit sich erst (teuer) im Feld zeigt.

**Was V2 dem entgegensetzt — der „Aha"-/Love-Moment:** Das System hebt die blinden Flecken, die der Anwender nicht gesehen hat, gibt eine geerdete Empfehlung *und* zeigt das Warum. Der Anwender geht mit *informiertem* Vertrauen heraus — er versteht, *warum* NBR und nicht EPDM, und kann die Entscheidung mit offenen Augen tragen.

**Akuter Schmerz als stärkste Adoptions-Magnete:** Nicht jeder Anwender startet neu und hat Zeit. Viele haben ein *Jetzt-Problem* — „mein Dichtring leckt, warum?" oder „schlüssel mir diese kryptische Bezeichnung auf und finde was Vergleichbares". Diese akuten Eingänge (siehe §5) sind potenziell die *stärkeren* Magnete als der Empfehlungs-Flow.

---

## 3. Leitprinzipien — die Kalibrierungs-Doktrin

Diese Prinzipien *erweitern* die bestehende V2-Doktrin („das Backend besitzt die Fakten und Zahlen; das LLM erzählt nur"). Sie sind die Seele des Produkts.

### 3.1 Selbstbewusst-korrekt ist der Default
Der Anwender kommt mit *einer* Erwartung: sag mir das korrekte Material. Ein System, das ständig hedged und auf den Hersteller verweist, hat genau diese Aufgabe verfehlt. Der **Default ist die selbstbewusste, korrekte Empfehlung** — nicht der Hedge. Und das ist erreichbar, weil die allermeisten realen Fälle *gut verstandenes Terrain* sind.

### 3.2 So assertiv wie die Erdung
- Auf einem **geerdeten Fakt** (Matrix: Aceton greift NBR an) → flach prescriptive, kein Zögern.
- Auf einer **Rechengrenze** (Kern: 12 m/s über der Linie) → prescriptive.
- Auf etwas **Nicht-Geerdetem** (eine Lebensdauer-Vorhersage, ein Fall außerhalb des geprüften Wissens) → *nicht* assertiv, sondern ehrlich über die Grenze.

Der Trust-Spine kodiert diese Unterscheidung bereits (geerdet → selbstbewusst, ungeerdet → Hedge). Die Härte reitet auf der Architektur, die schon steht.

### 3.3 Der Hedge ist die seltene, markierte Kante — nicht der Rückfall
Ehrlichkeit über Unsicherheit ist *nicht* das häufige Verhalten, sondern die seltene Ausnahme: echte, nicht im Wissen abgedeckte Chemie. Und selbst dort heißt sie nicht „weiß ich nicht" — sondern eine *begründete* Empfehlung aus den Grundprinzipien, ehrlich markiert als außerhalb der geprüften Daten. **Der Anwender kriegt immer ein Material.**

### 3.4 Die Ehrlichkeit *verdient* und *schützt* die Assertivität
Ein System, das „das weiß ich nicht sicher" sagt, *wenn* es unsicher ist, wird *geglaubt*, wenn es sagt „nimm NBR". Ein System, das *immer* assertiv ist — auch wo es nicht sollte —, wird einmal beim selbstbewussten Irren ertappt und verliert *alles* Vertrauen.

Die brutale Asymmetrie, die das nötig macht: assertiv-*und-richtig* rettet den Anwender vor dem Feldausfall (er liebt es); assertiv-*und-falsch* heißt, er folgt *direkt in den Ausfall* — und weil er gefolgt ist, ist das Vertrauen weg und es gibt realen Schaden. **Die Anwender folgen den Empfehlungen — deshalb schießt die Korrektheits-Latte nach oben.**

### 3.5 Assertiv ≠ autoritär
V2 hält seinen Boden, wenn es geerdet ist („EPDM quillt in deinem Mineralöl — Fakt, hier die Quelle"), aber der Anwender behält die **finale Entscheidung (L4)** und kann mit offenen Augen übergehen. Er kann widersprechen, aber nicht sagen, er sei nicht gewarnt worden.

### 3.6 Auf sicherheitskritisch/unsicher kippt Härte in „Stopp, bestätigen"
Wo Blind-Folgen gefährlich wäre, *verlangt* V2 die Hersteller-Bestätigung, statt durchzuwinken — kein selbstbewusstes grünes Licht. Auch das ist hart: hart auf der Verifikation bestehen. (Entspricht dem SAFETY-Instinkt der bestehenden Fallen: die Sicherheits-Klausel wird nie weggegated.)

### 3.7 Der Trust-Spine dient der selbstbewussten Korrektheit — nicht dem Absichern
Die Verifikation ist *nicht* da, um V2 hedgen zu lassen. Sie ist da, damit die selbstbewussten Empfehlungen *stimmen*. Wenn V2 „nimm NBR" sagt, soll es recht haben — und genau das stellt L3 sicher.

### 3.8 Bau-Priorität: den geerdet-korrekten Bereich vergrößern
Nicht elegantere Hedge-Mechanik, sondern mehr geerdetes Wissen (Fachkarten, Matrix, Versagensmodi, Rechengrenzen, Archetypen) — damit V2 auf *immer mehr* realen Fällen einfach das richtige Material nennt und recht hat. Das Ziel ist, die Kante zu *verkleinern*.

### 3.9 Neutralität ist heilig — kein pay-to-rank
Hersteller-Auswahl und -Alternativen *ausschließlich* nach **Fähigkeit**, nie nach Bezahlung. Der gesamte Produktwert ruht auf dem Vertrauen des Anwenders; pay-to-rank würde es zerstören. Nicht verhandelbar.

### 3.10 Normen sind geerdet — nie rezitiert
Normen sind eine *primäre Autoritäts-Quelle* hinter dem „geerdet" (§9.3) — und zugleich genau das, was ein LLM mit *falscher* Autorität halluziniert (falsche Nummern, Maße, Revisionen). Regel: V2 referenziert eine Norm nur, wenn die Referenz geerdet ist (owner-reviewt, echte Norm + Revision), und ist ehrlich, wo es die aktuelle Revision nicht sicher kennt. Die Kehrseite *stärkt* die Doktrin: eine Norm ist *keine Meinung* — „ISO 3601, 3,53 mm, ID 50" ist maximal geerdet *und* maximal assertiv. Normen sind eine Quelle genau der Erdung, die die Härte (§3.1–3.2) verdient.

---

## 4. Architektur-Kern: ein Fall, viele Eingänge und Operationen

Das ist die organisierende Idee von V2.1 — und das, was das Produkt kohärent hält, während es wächst.

Im Zentrum steht **ein strukturierter, geerdeter Fall**:

> **Fall** = Archetyp (Maschinen-Art) + Betriebsbedingungen (Drehzahl/Geschwindigkeit, Temperatur, Druck) + Medium + Geometrie (Welle Ø, Bauraum) + *ggf.* die Dichtungs-Spezifikation (Werkstoff, Typ, Bauform).

Der Fall ist die Verallgemeinerung des `case_context`, den V2 heute schon im Empfehlungs-Flow aufbaut. Die Modi sind nur verschiedene **Eingänge** in diesen Fall und verschiedene **Operationen** darauf.

### Eingänge — wie der Fall entsteht
| Eingang | Was er füllt |
|---|---|
| Anwendung beschreiben | Fall (Bedingungen, Medium, Geometrie) |
| Bezeichnung aufschlüsseln (Decode) | die Dichtungs-Spezifikation |
| Versagendes Teil schildern | Fall + Symptome |
| Bestehende Lösung nennen | Fall + aktuelle Dichtung |

### Operationen — was V2 mit dem Fall tut
| Operation | Eingabe → Ausgabe |
|---|---|
| **Empfehlen** | Fall (ohne Dichtung) → optimale Dichtung |
| **Diagnostizieren** | Fall + Dichtung + Symptome → Ursache → (oft) Fix |
| **Gegenchecken** | Fall + aktuelle Dichtung → passt sie? (ja / nein→warum→Fix) |
| **Alternativen/Hersteller finden** | Dichtungs-Spezifikation → vergleichbare Dichtungen / fähige Hersteller |
| **Erklären** | Konzept/Werkstoff → Lehr-Antwort (braucht keinen vollen Fall) |

**Die Pointe:** Decode → dann gegenchecken *oder* Alternativen finden *oder* drumherum empfehlen — *derselbe* Fall, *dasselbe* geerdete Wissen, *dieselbe* Trust-Spine, nur ein anderer Weg rein und etwas anderes getan. Ein Experte, kein Werkzeugkasten.

### Sitz auf der bestehenden Pipeline
Das passt ohne Bruch auf V2:
- Das `verstehen` ist bereits ein **weicher Intent-Read**, der *annotiert* statt zu routen — er kann den gewünschten Modus erkennen, ohne in einen Funnel zu zwingen.
- L1 antwortet bereits **fragetyp-abhängig in der Tiefe** — eine Wissensfrage kriegt eine Wissensantwort, ein Anwendungsfall kriegt Anwendungs-Reasoning.
- Die „eine diskriminierende Rückfrage nur bei echtem Bedarf"-Disziplin verhindert die Über-Befragung.

V2.1 macht diese Fähigkeit *explizit* und *vollständig* — der Fall wird zum benannten gemeinsamen Objekt, die Operationen werden ausgebaut.

---

## 5. Die Modi

Sieben Modi, die **fließend** ineinander übergehen — das System muss die Übergänge natürlich nehmen, nicht modal-springend.

### A — Wissen / Erklären
„Was kann PTFE?", „Wie funktioniert ein RWDR?", „Unterschied FKM/EPDM?"
→ Klare Ingenieur-Antwort, geerdet (Fachkarte), mit Quelle. *Keine* Anwendungs-Befragung. Direkter Wert.

### B — Maschine / Anwendung besprechen
„Lass mich mein Rührwerk durchgehen.", „Worauf muss ich bei der Getriebe-Dichtung achten?"
→ Offen, explorativ: Verständnis der Maschine und ihrer dichtungsrelevanten Besonderheiten aufbauen. Archetyp-geführt (§8). Mündet oft in eine Empfehlung, muss aber nicht.

### C — Empfehlen *(das Herz — siehe §6)*
„Empfiehl mir eine Dichtung für mein Getriebe: Welle 40, Mineralöl, 100 °C."
→ Der Verstehen→Challengen→Empfehlen→Hersteller→Anfrage-Flow.

### D — Diagnostizieren *(akut, wichtig)*
„Mein Dichtring leckt nach 3 Wochen — warum?"
→ Symptom → Ursache → Fix. Nutzt die **Versagensmodi**-Dimension. Mündet oft in Empfehlen (den Fix). Akuter Schmerz, starker Magnet.

### E — Bestehende Lösung gegenchecken *(sehr wichtig)*
„Wir verwenden X — ist das richtig?"
→ Im Kern Operation C im *Bewertungs*-Modus: passt die aktuelle Dichtung zum Fall? Ergebnis „ja, passt" oder „nein → warum → Fix". Anxiety-Relief / Zweitmeinung.

### F — Alternativen / Hersteller finden
„Wer kann das noch?", „Gibt es eine Alternative zu diesem Teil?"
→ Die „Hersteller wählen"-Operation eigenständig: nach **Fähigkeit**, neutral, kein pay-to-rank. Nutzt die **Hersteller-Fähigkeiten**-Dimension.

### G — Bezeichnung aufschlüsseln + vergleichbar machen *(akut, sehr konkret)*
„Schlüssel mir `BAUMSL 40-62-10 FKM` auf und finde Vergleichbares."
→ Bezeichnung parsen → strukturierte Spezifikation (Maße, Werkstoff, Typ, Merkmale) → Quervergleich über Hersteller. Nutzt die **Bezeichnungs-Schemata + Quervergleich**-Dimension. Eine tägliche, nervige, mit Google nicht lösbare Aufgabe — potenziell der stärkste Einzel-Magnet. **Mit der schärfsten Haftungs-Kante (§9.2).**

**Übergänge sind die Regel:** „Wie funktioniert ein RWDR" (A) → „eigentlich hab ich da eine Anwendung" (C). Decode (G) → gegenchecken (E) → Alternativen (F). Diagnose (D) → Empfehlung des Fixes (C).

---

## 6. Der Empfehlungs-Flow (das Herz)

Mit der „selbstbewusst-korrekt per Default"-Kalibrierung aus §3.

**0. Intent-Read (weich).** Wissen / besprechen / empfehlen? Bei Empfehlungs-Absicht (explizit oder emergent) → in den Flow; sonst den passenden Modus bedienen (und übergehen, wenn eine Anwendung auftaucht).

**1. Verstehen — archetyp-geführt.** Maschinen-Art erkennen → Archetyp-Profil laden → durch *dessen* Linse befragen:
- Getriebe → Öl-Additive / Drehzahl→Umfangsgeschwindigkeit / Wellenoberfläche / Rundlauf
- Rührwerk → Prozessmedium / Druck-Vakuum / Hygiene / Trockenlauf
Die archetyp-spezifischen **blinden Flecken** hochholen. Nicht weiter befragen als für *diese* Empfehlung nötig.

**2. Challengen — geerdet, assertiv.** Die genannten Annahmen gegen die geerdeten Fakten stress-testen (Matrix / Kern / Fachkarte / Archetyp). Die echten Risiken *für diese Maschine* aufwerfen — hart, wo geerdet („EPDM ist hier falsch, weil…"), ehrlich, wo echt unsicher. Selektiv, lehrreich, konvergent. Funde werden mitgenommen.

**3. Empfehlen — selbstbewusst, korrekt, per Default.** Das optimale Material + Typ/Bauform, prescriptive, mit offengelegtem **Warum** (Quelle, Begründung). Die seltene echte Kante kriegt den „außerhalb geprüfter Daten, bestätigen"-Vermerk. Die Challenge-Restrisiken fließen als *transparente Bedingungen* ein („konservativ X, weil Wellenoberfläche unbestätigt — vor Freigabe prüfen"). **L4 bleibt:** Orientierung; die finale Freigabe liegt beim Hersteller / Anwender.

**4. Hersteller wählen** — nach **Fähigkeit** (neutral, kein pay-to-rank).

**5. Anfrage** — die präzise, detaillierte Anfrage aus dem voll-verstandenen Fall + der Empfehlung, an den gewählten Hersteller versendbar.

---

## 7. Die Wissens-Dimensionen

V2.1 erdet das gesamte Können in **sieben** owner-reviewten Wissens-Dimensionen — alle als **Daten** (kein Code), **owner-kuratiert** (nie modell-generiert), **erweiterbar**.

| # | Dimension | Hält | Speist | Status |
|---|---|---|---|---|
| 1 | **Fachkarten** | Werkstoff-Eigenschaften | Erklären, Grounding (L2) | steht (V2) |
| 2 | **Verträglichkeitsmatrix** | Medium × Werkstoff | Empfehlen, Challenge, L3 | steht (V2, 27 Zellen) |
| 3 | **Rechenkern** | Umfangsgeschwindigkeit, PV, Verpressung | Empfehlen, Challenge | steht (V2) |
| 4 | **Anwendungs-Archetypen** | Maschinen-Profile (§8) | Verstehen, Challenge, Empfehlen | **neu** (heute wohl implizit im LLM → erden) |
| 5 | **Versagensmodi** | Symptom → Ursache → Fix | **Diagnose** + schärft den **Challenge** | **neu** |
| 6 | **Hersteller-Fähigkeiten** | Wer macht was (Werkstoffe/Bauformen/Größen/Zertifikate) | **Alternativen-Suche** + „Hersteller wählen" | **neu** |
| 7 | **Bezeichnungs-Schemata + Quervergleich** | Hersteller-Codierungen + Äquivalenz | **Decode + vergleichbar machen** | **neu**, spezialisiert |

**Geteilte Assets (kein Silo):**
- **Versagensmodi** trägt die Diagnose *und* ist die Quelle der Challenge-Risiken (die typischen Versagensmodi eines Archetyps *sind* die Risiken, die im Empfehlen aufzuwerfen sind).
- **Hersteller-Fähigkeiten** trägt die Alternativen-Suche *und* den „Hersteller wählen"-Schritt des Herz-Flows.

**Erdungs-/Quellen-Anforderung:** Jede neue Dimension wird wie Matrix und Fachkarten behandelt — owner-reviewt, mit nachvollziehbarer Quelle, niemals vom Modell erfunden. Die Bestätigung des exakten Ist-Stands (was steckt heute schon implizit im L1-Prompt vs. ist wirklich neu) gehört in die Bau-Planung mit Claude Code.

**Quer-Schicht: Normen & Regularien (kein achtes Silo — ein Faden durch Dim. 1/4/7).** Normen sind im Dichtungswesen kein Thema neben den anderen; sie greifen auf drei Ebenen:
- **Provenienz/Autorität** → durch **Fachkarten + Matrix**: die Eigenschafts- und Verträglichkeitswerte zitieren ihre Norm-/Datenblatt-Basis; selbst die Werkstoffnamen sind genormt (ISO 1629 / ASTM D1418).
- **Geometrische Korrektheit** → durch **Decode (Dim. 7) + Bauform**: DIN 3760/3761 (RWDR), ISO 3601 (O-Ring), ISO-Einbauraum-Normen (Hydraulik). Eine deterministische, norm-definierte Korrektheitsschicht — wie der Rechenkern, nur für Geometrie. „Vergleichbar" und „beschaffbar" setzen Norm-Konformität voraus.
- **Harte Anwendungs-/Compliance-Randbedingung** → durch **Archetypen (Dim. 4)**: Lebensmittel (FDA, EU 1935/2004, 3-A), Trinkwasser (KTW, WRAS, NSF/ANSI 61), ATEX, Pharma (USP Class VI) und — aktuell brisant für FKM/PTFE/FFKM — PFAS/REACH. Ein hartes Gate, das technisch passende Werkstoffe *eliminieren* kann; Constraint-Filter auf der Empfehlung. (Seed: die bestehende Regulatory-Vorlage REACH/SVHC, PFAS, RoHS, Food, FDA.)

Behandlung wie alles Wissen: geerdet, owner-reviewt, nie rezitiert (§3.10). Grenze (L4): V2 *orientiert* auf die anwendbare Norm und sagt, *was* sie bedeutet; die *Zertifizierung* der konkreten Mischung bleibt beim Hersteller.

---

## 8. Anwendungs-Archetypen

**Eine eigene Wissens-Dimension.** Die Fachkarten kennen *Werkstoffe*, die Matrix *Verträglichkeit*, der Kern *Formeln* — aber „**was eine Maschinen-Art an die Dichtung stellt**" ist etwas anderes. Ein Getriebe (horizontale Welle, Öl-geschmiert, mittlere/hohe Drehzahl, Medium = Schmiermittel) bringt andere Sorgen als ein Rührwerk (oft vertikale Welle, langsam, Prozessmedium berührt die Dichtung, evtl. Druck/Vakuum, Hygiene, Wellenauslenkung, Trockenlauf beim Anfahren).

Der Archetyp **treibt** drei Dinge: das **Interview** (was zu fragen ist), den **Challenge** (welche Risiken für diese Maschine), die **Empfehlung** (was passt). Und er ist ein Riesen-Teil des „das versteht meine Welt"-Moments: sagt der Anwender „Rührwerk" und V2 spricht sofort über Prozessmedium, Trockenlauf, Hygiene — *da* fühlt er sich verstanden.

### Profil-Schema (Skizze)
Jedes Archetyp-Profil hält:
- **Typische Konstellation** (Wellenlage, Geschwindigkeitsbereich, Druck/Vakuum, Schmierung, Medium-Charakter)
- **Dichtungsrelevante Besonderheiten** (z. B. Trockenlauf, Hygiene, Wellenauslenkung)
- **Typische Versagensmodi** (Verweis in Dim. 5) → die Challenge-Risiken
- **Typische Werkstoff-/Typ-Eignungen** → die Empfehlungs-Kandidaten
- **Anwendbare Regime** (z. B. Lebensmittel/Trinkwasser/ATEX, falls archetyp-typisch) → Compliance-Constraints (§7-Quer-Schicht)
- **Interview-Fragen** (was diese Maschine zu klären zwingt)
- **Blinde Flecken** (was der Anwender hier typischerweise übersieht)

### Vorgeschlagener Starter-Satz
*(Vorschlag von Claude; Thorsten hat die Markt-Wahrheit — frei umsortieren, die Daten-Struktur macht das billig. Geordnet nach Häufigkeit × Prelon-Fokus (RWDR/PTFE/Hydraulik) × Eigenheit des Profils.)*

1. **Getriebe** — häufigster RWDR-Fall; horizontal, Öl, Drehzahl
2. **Elektromotor** — sehr häufig; hohe Drehzahl, oft Schutz-gegen-Eintrag statt Rückhalt
3. **Pumpe** — rotierend, aggressives Medium = Förderfluid, Druck
4. **Rührwerk / Mischer** — vertikal, langsam, Prozessmedium, Hygiene, Trockenlauf
5. **Hydraulikzylinder** — linear, Hochdruck, Stangen/Kolben, Extrusion
6. **Pneumatikzylinder** — linear, Niederdruck, trocken/leicht geschmiert, Geschwindigkeit

**Nächste Welle (Kandidaten):** Radlager/Achse, Flansch/statisch, Drehdurchführung.

**Struktur:** als Daten (owner-reviewte Profile, wie die Fachkarten), im Nachgang optimier- und erweiterbar. Klein anfangen (die häufigsten zuerst), wachsen lassen.

---

## 9. Die Trust-Spine über alle Modi

### 9.1 Uniforme Anwendung
Die bestehende vierschichtige Trust-Spine gilt für **jede** Operation gleich:
- **L1** generiert (erzählt), **L2** erdet (Fachkarten + Matrix), **L3** verifiziert (gegen Fallen-Katalog + Matrix, topik-skopierte Korrekturen), **L4** ist die menschliche Hersteller-Freigabe.

Eine **Diagnose**, eine **Äquivalenz**, ein **Gegencheck-Urteil** ist genauso eine geerdete, verifizierte, mit-Quelle-belegte **Behauptung** wie eine Empfehlung. Das Hinzufügen von Modi vervielfacht das Trust-Risiko *nicht* beliebig — es ist dieselbe Disziplin, auf den Output jeder Operation angewandt. Die Verifikation dient der *selbstbewussten Korrektheit* (§3.7), nicht dem Absichern.

### 9.2 Scharfe Warnung: Quervergleich / Äquivalenz (Modus G, F)
**„Teil X = Teil Y" ist die gefährlichste Behauptung im ganzen System.** Falsch heißt: der Anwender kauft das falsche Teil → direkter Ausfall. Zwei Dichtungen mit *nominell* gleicher Spezifikation können sich im Compound, im Design, in Toleranzen, in der Performance unterscheiden.

Also „so assertiv wie geerdet" in seiner schärfsten Form:
- V2 darf Äquivalenz **nicht lässig behaupten** — nur geerdet.
- **Ehrlich über die Grenze:** „gleich in Nennmaßen + Werkstoffklasse; Compound und Eignung beim Hersteller bestätigen."
- Der **L4-Riegel trägt hier echtes Gewicht** — Äquivalenz ist Orientierung, nicht Freigabe.

### 9.3 Normen-Behauptungen: geerdet oder gar nicht
Eine Norm-Referenz ist eine *Behauptung mit Autorität* — und damit eine, die L3 prüfen können muss. „Laut DIN 3760 ist das Maß X" mit falschem X ist das schlimmste selbstbewusst-Falsch, weil es in falscher Autorität steckt. V2 zitiert eine Norm (Nummer, Revision, Inhalt) nur aus geerdeter Quelle, nie aus dem Modell-Gedächtnis (§3.10). Wo die aktuelle Revision unsicher ist → ehrlich markieren.

---

## 10. Was steht (V2) vs. was V2.1 neu baut

*(Macht das Konzept baubar: was wird wiederverwendet/verdrahtet vs. neu erstellt. Exakter Ist-Stand pro Punkt in der Bau-Planung mit Claude Code bestätigen.)*

### Wiederverwenden / verdrahten (steht in V2)
- Die dünne lineare Pipeline (verstehen→grounden→rechnen→antworten→verifizieren→zitieren→erinnern), weicher Intent-Read, Tiefe-nach-Fragetyp
- Trust-Spine L1–L4 inkl. topik-skopierter L3-Korrekturen
- Deterministischer Rechenkern (Umfangsgeschwindigkeit, PV, Verpressung)
- Verträglichkeitsmatrix (27 geprüfte Zellen), Fachkarten, Fallen-Katalog
- Postgres-Persistenz (tenant-scoped, restart-survival), P0-Tenant-Isolation, Injection-/Exfil-Abwehr
- Eval-Lineal (25 Fälle, 10 Klassen, Edge/Injection/Multiturn, 8 harte Schranken, Human-Oracle-Adjudikation)

### Neu bauen (V2.1)
- **Wissen:** Archetyp-Profile (Dim. 4, implizit → geerdet), Versagensmodi (Dim. 5), Hersteller-Fähigkeiten (Dim. 6), Bezeichnungs-Schemata + Quervergleich (Dim. 7)
- **Normen-Quer-Schicht:** Norm-/Datenblatt-Basis an Fachkarten + Matrix, Geometrie-Normen für Decode/Bauform, Compliance-Regime an den Archetypen (§7) — alles geerdet, nie rezitiert
- **Operationen:** Diagnostizieren (D), Gegenchecken (E), Alternativen/Hersteller finden (F, ggf. Ausbau des Hersteller-Schritts), Decode + vergleichbar machen (G)
- **Eingänge:** Decode-Eingang, Versagendes-Teil-Eingang, Bestehende-Lösung-Eingang
- **Framing:** der explizite gemeinsame *Fall* + die Eingänge/Operationen-Struktur; das archetyp-geführte Verstehen; die Multi-Modus-Oberfläche mit fließenden Übergängen
- **Eval:** neue Schranken/Fälle pro neuer Operation (eine Diagnose/Äquivalenz/ein Gegencheck wird genauso gemessen wie eine Empfehlung)

---

## 11. Vorgeschlagene Bau-Reihenfolge

*(Vorschlag; Thorsten setzt die Priorität. Jeder Wissens-Erdungs-Schritt ist owner-reviewt — Doktrin-Gate. Jede neue Operation kommt mit ihren Eval-Schranken.)*

Zwei strategische Leitplanken: **(I)** den geerdet-korrekten Bereich vergrößern ist der Kern-Wert-Treiber; **(II)** akute-Schmerz-Wedges (Decode, Diagnose) treiben die Adoption.

1. **Kern festigen:** Archetyp-Profile erden (Starter-Satz) + das archetyp-geführte Verstehen + der Empfehlungs-Flow auf der Kalibrierung. *Das ist die Mitte, auf der alles andere ruht.*
2. **Ein akuter Wedge zuerst:** Modus **G (Decode + Quervergleich)** *oder* **D (Diagnose)** — als früher Adoptions-Magnet. (G braucht Dim. 7 + die scharfe Äquivalenz-Disziplin; D braucht Dim. 5, das ohnehin den Challenge schärft — D ist daher synergetisch mit Schritt 1.)
3. **Gegencheck (E)** — günstig, sobald der Empfehlungs-Engine steht (E ist C im Bewertungs-Modus).
4. **Alternativen/Hersteller (F)** — sobald Dim. 6 (Hersteller-Fähigkeiten) geerdet ist.
5. **Wissens-Tiefe wachsen lassen** — weitere Archetypen, Matrix-Zellen, Versagensmodi, Rechengrenzen. Kontinuierlich, owner-reviewt. *Das ist die Dauer-Arbeit, die den Wert über die Zeit baut.*

---

## 12. Grenzen und bewusst Ausgeklammertes

- **L4 ist eine echte Grenze:** V2 gibt *Orientierung*, ersetzt nicht die Hersteller-Freigabe. Auf sicherheitskritisch/unsicher → „Stopp, bestätigen".
- **Kein pay-to-rank** — heilig (§3.9).
- **Äquivalenz ist begrenzt** — nie über Nennmaße + Werkstoffklasse hinaus ohne Hersteller-Bestätigung (§9.2).
- **Normen: orientieren, nicht zertifizieren** — V2 nennt die anwendbare Norm und was sie bedeutet; die Zertifizierung der konkreten Mischung bleibt beim Hersteller. Nie aus dem Gedächtnis zitiert (§3.10/§9.3).
- **Wissen ist owner-kuratiert** — wächst über die Zeit, startet klein, nie modell-generiert.
- **Deferred-by-design aus V2 bleiben deferred** (Token-Streaming, RFQ-Artefakt, Vektor-Retrieval/Qdrant, Redis-Working-Memory, Postgres-kanonisches Wissen) — Swap auf Skalierungs-Trigger, nicht jetzt.
- **Konzept-vollständig ≠ Pilot-bereit.** Die Ops-Schicht (Anwalt-Claim-Grenze, Keycloak-Secret-Rotation, Per-Turn-Provenienz, CSP/Token-Beweis, LangSmith-Privacy) ist ein *eigener* Pfad, außerhalb dieses Konzepts.

---

## Anhang A — Eingänge × Operationen (Übersicht)

```
                         OPERATIONEN
                 Empfehlen Diagnose Gegencheck Alternativen Erklären
EINGÄNGE
  Beschreiben       ●         ○          ○           ·          ●
  Decode            ○         ·          ●           ●          ○
  Versagendes Teil  ○         ●          ○           ·          ○
  Bestehende Lösung ○         ○          ●           ●          ○
  (reine Frage)     ·         ·          ·           ·          ●

  ● Kern-Kombination   ○ häufiger Übergang   · selten/n.a.
```

## Anhang B — Archetyp-Profil-Schema (zur Erdung)

```yaml
archetyp: Rührwerk
typische_konstellation:
  wellenlage: vertikal (häufig)
  geschwindigkeit: niedrig
  druck_vakuum: möglich (Reaktor)
  schmierung: keine / Prozessmedium
  medium_charakter: variabel, oft aggressiv/abrasiv
dichtungsrelevante_besonderheiten:
  - Prozessmedium berührt die Dichtung
  - Trockenlauf beim Anfahren
  - Hygiene-/Reinigungsanforderung (CIP/SIP)
  - Wellenauslenkung
typische_versagensmodi: [verweis: Dim.5]
typische_eignungen:
  werkstoffe: [...]
  bauformen: [...]
anwendbare_regime: [z. B. EU 1935/2004 + FDA + 3-A bei Lebensmittel-Reaktor]
interview_fragen:
  - "Welches Prozessmedium, in welcher Konzentration/Temperatur?"
  - "Druck oder Vakuum im Behälter?"
  - "Hygiene-/Reinigungsregime?"
  - "Anfahren trocken?"
blinde_flecken:
  - "Medium oft unterschätzt vs. reine Schmierung"
  - "Trockenlauf beim Start nicht bedacht"
quelle: [owner-review-ref]
```

---

*Ende V2.1 Produkt-Konzept. Die Implementierung folgt dem etablierten doktrin-gegateten Relay (Claude = Reviewer/Gatekeeper, Claude Code = autonome Umsetzung, alle produktiv-mutierenden Schritte owner-freigegeben), gemessen gegen die `build_spec` und das Eval-Lineal.*
