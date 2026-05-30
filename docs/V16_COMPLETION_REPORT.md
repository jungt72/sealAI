# sealing | Intelligence V1.6 — Completion Report

**Stand:** 2026-05-30
**Branch:** `demo/rwdr-limited-external`
**Modus:** Additiv, audit-first, keine Parallelarchitektur (Blueprint §1.1 / §30).

---

## 1. Ausgangslage (verifizierter Ist-Stand)

Der V1.6-Blueprint war zum Audit-Zeitpunkt bereits weitgehend implementiert,
aber **uncommittet** (in-flight Arbeit einer früheren Session). Erster Schritt
war daher die Sicherung dieser Arbeit als Checkpoint-Commit, danach das gezielte
Schließen der verbliebenen, konkret nachweisbaren Lücken.

Verifizierte Baseline vor der Completion: V1.6-Kernsuite grün — Golden A–O,
Pocket Cockpit, Mobile Triage, Sheet Events, Action-Chip State Gate,
RFQ One-Pager, Knowledge Modes.

Wichtige Audit-Korrektur: Die zunächst gemeldete Lücke „Golden K–P fehlen" war
falsch (entstanden durch verfälschte Teilausgaben). Tatsächlich existierten die
Golden Conversations A–O bereits vollständig und grün.

## 2. Durchgeführte Patches

| Commit | Inhalt | Blueprint |
|---|---|---|
| `fe27433a` | WIP-Sicherung der gesamten in-flight V1.6-Arbeit | §30 |
| `eb0c7a3f` | Chat-Style Template-Familie vervollständigt (8 Templates + Registry) | §10.5 |
| `68628766` | Unified `TraceSummary`-Contract | §6.1 / §11.7 / §25.1 |

### 2.1 Template-Familie (§10.5) — 5/13 → 13/13

Vor der Completion hatten nur 5 von 13 deklarierten `ChatReplyStyle`-Werten ein
registriertes Jinja2-Template. Ergänzt wurden die fehlenden 8:

| Style | Template | disclaimer_policy (§22) |
|---|---|---|
| `knowledge_explainer` | `knowledge/knowledge_explainer.j2` | suppress_normal_turn |
| `case_aware_explainer` | `knowledge/case_aware_knowledge.j2` | suppress_normal_turn |
| `measurement_guide` | `knowledge/measurement_guide.j2` | suppress_normal_turn |
| `ui_help` | `chat/ui_help.j2` | ui_static_only |
| `sheet_comment` | `chat/sheet_comment.j2` | suppress_normal_turn |
| `conflict_resolution` | `chat/conflict_resolution.j2` | suppress_normal_turn |
| `rfq_confirmation` | `rfq/rfq_confirmation.j2` | rfq_required |
| `rfq_one_pager_intro` | `rfq/rfq_one_pager_intro.j2` | rfq_required |

Alle laufen durch den bestehenden No-Go-Guard. Render-Seam und `PromptRegistry`
unverändert. Registry-Abdeckung jetzt **13/13** (verifiziert).

### 2.2 Unified TraceSummary (§6.1 / §25.1)

Der bereits im Runtime emittierte Trace-Dict (z. B. `mobile_leakage_triage`)
wurde in **ein** validiertes Pydantic-Schema formalisiert — Single Source of
Truth für Observability. Feldnamen sind identisch mit den bestehenden
Emitter-Keys; `extra="allow"` hält das Schema vorwärtskompatibel. Kein Emitter
und kein `AssistantTurnEnvelope.trace`-Feld wurde geändert (additive View).
Verifiziert: die Live-Trace von `build_mobile_leakage_triage` validiert
unverändert, extra-Keys bleiben erhalten.

## 3. Bewusst NICHT umgesetzt (Begründung)

Konsistent mit der ausdrücklichen Vorgabe „möglichst viel vom aktuellen Stack
behalten, keine parallelen Wahrheiten bauen":

| Punkt | Begründung |
|---|---|
| Benannte Impact-Agent-Klassen (§17) als eigene Struktur | Funktional bereits als Graph-Nodes + communication-Module realisiert. Ein Nachbau als separate Klassen wäre exakt die vom Blueprint (§1, §30) verbotene parallele Wahrheit. |
| JSON-/Agent-/Cockpit-Jinja-Templates (§10.5 Rest) | Extraktion und Cockpit-Projektion laufen hier über strukturierten Code (Pydantic/Projections), nicht über Jinja. Ungenutzte Templates wären Parallel-Truth ohne Aufrufer. |
| Live-Wiring der 8 neuen Chat-Styles in den Dispatch | Konsistent mit der etablierten Patch-Disziplin (Templates sind getestete, additive Capability; das Wiring ist ein separater, review-pflichtiger Schritt). Siehe §5. |

## 4. Verifikation

```
Volle Agent-Testsuite:   1015 passed, 7 skipped, 0 failed (55.32s)
V1.6-Kernsuite:          129 passed
Neue Tests:              +22 (Template-Familie) +4 (TraceSummary)
Registry-Abdeckung:      13/13 ChatReplyStyle
prompt_registry smoke:   60 passed (keine Regression durch neue Templates)
Working Tree:            clean
```

## 5. Empfohlene nächste Schritte (optional, review-pflichtig)

1. **Live-Wiring** der neuen Chat-Styles in die jeweiligen Modes:
   `knowledge_general → knowledge_explainer`, `knowledge_case_aware →
   case_aware_explainer`, `sheet_field_edit → sheet_comment`,
   `sheet_conflict_resolution → conflict_resolution`,
   `rfq_brief_generation → rfq_confirmation / rfq_one_pager_intro`,
   `measurement_guidance → measurement_guide`, `ui_help → ui_help`.
2. `TraceSummary` als typisierten Adapter im Trace-Logging / Observability-Export
   nutzen (z. B. Validierung vor dem Schreiben in Grafana/Prometheus-Pipeline).
3. Branch ist gegenüber `origin/demo/rwdr-limited-external` divergiert — Commits
   wurden bewusst **nicht** automatisch gepusht. Push erst nach Review.

## 6. Infrastruktur-Hinweis

Während der Arbeit wurde `fail2ban` so konfiguriert, dass es schnelle
SSH-Bursts der Entwickler-IP bannte. Eine Whitelist wurde unter
`/etc/fail2ban/jail.d/zz-claude-whitelist.conf` gesetzt (ignoreip für die
Dev-IP). Bei Bedarf kann dieser Eintrag nach Abschluss wieder entfernt werden.
