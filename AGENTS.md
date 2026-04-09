- nur lesen, prüfen, dokumentieren

### Erwartete Audit-Qualität
- Ist-Zustand, nicht Wunschdenken
- produktiv vs. Legacy sauber trennen
- konkrete Pfade nennen
- technisches Delta gegen Zielarchitektur benennen
- offene Fragen nur benennen, wenn unbelegt

### Reports
Wenn ein Report verlangt ist, standardmäßig unter:
- `konzept/audit/`

---

## 13. Codebase-Orientierung

### Produktive Zielarchitektur
```text
backend/app/agent/
Legacy / Altbestand
backend/app/langgraph_v2/   # read-only
backend/app/_legacy_v2/     # nicht ausbauen
Wichtige Bereiche in backend/app/agent/
api/            # FastAPI-Handler, outward contracts, SSE
prompts/        # PromptRegistry + Jinja2-Templates
runtime/        # Gate, Session, leichte Pfade, Renderer
graph/          # Governed Flows / Topology / Nodes
state/          # Modelle, Reducer, Persistenz, Projektionen
evidence/       # Query-Objekte, Retrieval, Evidence
domain/         # deterministische Fachlogik
sts/            # STS-Lader und Lookups
manufacturers/  # Capability- und Matching-Logik
documents/      # PDF / Dokumentpfade
rag/            # Ingest / Collections / RAG-Setup
data/           # Seed-Daten
Besondere Vorsicht
selection.py nicht funktional aufblasen; nur plan-konform zerlegen oder entlasten
keine fachliche Authority im Renderer, UI oder Projection-Code neu erzeugen
API und Renderer sind Konsumenten sauberer State-/Domain-Ergebnisse, nicht deren Ersatz
14. Verbindliche Benennungen
Routen
CONVERSATION
EXPLORATION
GOVERNED
Outward classes
conversational_answer
structured_clarification
governed_state_update
technical_preselection
candidate_shortlist
inquiry_ready
Pflichtmetrik
fit_score
Nicht wieder einführen
instant_light_reply
light_exploration
governed_needed
governed_recommendation
manufacturer_match_result
rfq_ready
„Wahrscheinlichkeit“ als fachliche Output-Metrik
15. Matching-, Review- und Inquiry-Regeln
Matching

Nie:

ohne technische Einengung
ohne passende Requirement-/Decision-Basis
ohne klare Capability-/Constraint-Prüfung
Inquiry / RFQ-nahe Freigaben

Nie:

direkt aus freiem Chattext
ohne Admissibility-Logik
ohne Review-/Gate-Logik
ohne offene Punkte sauber sichtbar zu halten
Herstellerbezug
Herstellerfinalität bleibt erhalten
Ranking nie als absolute Wahrheit formulieren
Sponsored-/Listing-Effekte nie als technischer Fit ausgeben
16. Prompting-Regeln
Verbindlich
produktive Prompts als Jinja2-Templates
PromptRegistry statt verstreuter harter Strings
Renderer mit strukturiertem State-Kontext
Guardrail- und Fallback-Denke respektieren
Verboten
neue produktive Prompt-f-strings in Python
harte Prompt-Logik in zufälligen Helferdateien
Umgehung von Guard-/Fallback-Mechanismen
17. Was du ausdrücklich NICHT tun sollst
backend/app/langgraph_v2/ weiterentwickeln
_legacy_v2/ ausbauen
neue Peer-Agents oder Multi-Agenten-Theater bauen
fachliche Authority ins LLM verschieben
Matching oder Inquiry direkt aus Freitext ableiten
selection.py funktional erweitern
alte verbotene Namen wieder einführen
STS als externen Standard darstellen
neue produktive Prompts als Python-f-strings bauen
ohne Not große Dateien / Strukturen verschieben
ohne Verifikation „fertig“ melden
bei Dokumentkonflikt stillschweigend improvisieren
18. Definition of Done

Eine Aufgabe ist nur dann fertig, wenn:

die Dokumentenhierarchie respektiert wurde,
keine Invariante verletzt wurde,
der Patch minimal und nachvollziehbar ist,
der betroffene Ist-Zustand vor der Änderung geprüft wurde,
relevante Tests / Checks ausgeführt wurden oder eine echte Blockade sauber benannt ist,
keine verbotenen Legacy-Namen oder Pfade neu gestärkt wurden,
der Ergebnisbericht enthält:
geänderte Dateien
funktionale Änderung
Verifikation
offene Risiken
19. Umgang mit Unklarheit

Wenn eine Aufgabe unklar, aber teilweise ausführbar ist:

betroffenen Bereich lesen
kleinste sichere Interpretation wählen
nur den eindeutig belegbaren Teil umsetzen
Annahmen offen benennen
nicht spekulativ ausweiten

Wenn eine echte Architekturentscheidung nötig wäre, die nicht aus den normativen Dokumenten ableitbar ist:

nicht frei entscheiden
Konflikt oder Entscheidungspunkt klar benennen
20. Schlussregel

Im Zweifel zuerst diese Fragen beantworten:

Bleibt backend/app/agent/ die einzige produktive Zielarchitektur?
Spricht nach außen genau eine Stimme?
Setzt das LLM irgendwo fachliche Authority direkt?
Wird ein Legacy-Pfad oder Altname wieder aufgewertet?
Ist die Änderung durch Zielarchitektur und Umbauplan V2 gedeckt?
Wurde zuerst gelesen, dann gepatcht, dann verifiziert?

Wenn eine dieser Fragen problematisch ist, ist die Lösung noch nicht sauber genug.
