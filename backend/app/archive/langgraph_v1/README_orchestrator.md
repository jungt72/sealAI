# SealAI Orchestrator – Supervisor Stack

Dieses Dokument beschreibt Aufbau, Konfiguration und Offline-Verhalten des Multi-Agent-Orchestrators in `backend/app/langgraph`.

## Konfigurationsschema (`config/agents.yaml`)

```yaml
version: 1

supervisor:
  model: "${SUPERVISOR_MODEL:${OPENAI_MODEL:gpt-4o-mini}}"
  output_mode: "final"          # "final" | "stream" | "accumulate"
  allow_forward_message: true
  handoff_tool_prefix: "handoff_to_"
  max_handoffs: 5
  prompt: |
    # Supervisor (Projekt: ACME)
    Du orchestrierst mehrere spezialisierte Worker ...
  workers:
    - name: "profil"
      description: "Extrahiert/verdichtet Nutzer- und Projektprofile ..."
    - name: "validierung"
    - name: "material"
    - name: "standards"

domains:
  <domain-name>:
    model: "<LLM-Name oder ${ENV:Fallback}>"
    tools: ["optional_tool_module"]
    routing:
      description: "Freitext-Beschreibung für den Router & Logs."
    prompt:
      system: |
        Systemprompt für den Domänen-Agenten.
      overrides:
        temperature: 0.2          # optional; überschreibt Model-Defaults
        max_output_tokens: 800    # optional
```

### Regeln

- **Supervisor**: Alle Parameter sind optional überschreibbar via ENV (`${SUPERVISOR_MODEL}` etc.). `workers` definiert die Tool-Namen (`handoff_to_<name>`) und Beschreibungen.
- **Domänen**: Jede Domäne benötigt `routing.description` und `prompt.system`. `tools: []` erzeugt einen reinen reasoning Agent (z. B. `validierung`).
- **Model-Overrides**: `prompt.overrides` wirkt auf Temperatur/Tokens des Domänen-Modells.

Konfigurationsänderungen wirken ohne Codeänderung beim nächsten Graph-Build (`build_supervisor()` lädt die YAML-Datei neu).

## Supervisor-Fabrik

`nodes/supervisor_factory.py` erzeugt den Graphen:

1. Lädt Supervisor- und Domain-Cfg (`AgentsConfig`).
2. Baut für jeden Worker ein `CompiledStateGraph` via `create_domain_agent`.
3. Registriert pro Worker ein Handoff-Tool (`handoff_to_<worker>`).
4. Erstellt den Supervisor-Agenten (`create_supervisor`) inkl. optionalem `forward_message`-Tool.
5. Erzwingt max. Handoffs über den Konfig-Wert (`supervisor.max_handoffs`).

`create_supervisor(...)` akzeptiert sowohl `WorkerBinding`-Instanzen als auch Mappings:

```python
create_supervisor(
    state_schema=SealAIState,
    workers=[{"name": "profil", "graph": profile_graph}],
    handoff_tool_prefix="handoff_to_",
    output_mode="final",
    allow_forward_message=True,
    supervisor_prompt=rendered_prompt,
    model=supervisor_llm,
    max_handoffs=5,
)
```

## Offline-Simulation

Aktiviert durch `LANGGRAPH_USE_FAKE_LLM=1` (oder fehlenden `OPENAI_API_KEY`):

- Domänen-Llms werden durch `_OfflineDomainModel` ersetzt (deterministische Antworten).
- Der Supervisor nutzt eine heuristische Router-Node:
  - Alle Worker stehen weiterhin als Handoff-Targets zur Verfügung.
  - Responses werden nacheinander in `messages` angefügt.
  - `slots["handoff_history"]` dokumentiert die Reihenfolge.
- Tool-Aufrufe werden synchron in Python ausgeführt; externe HTTP-Calls entfallen.

Limitierung: Komplexe mehrstufige Routings (z. B. Debatte) werden heuristisch entschieden, nicht via LLM. Für Integrationstests genügt dies und verhindert Netzwerkzugriffe.

## Tests

| Testdatei | Zweck |
|-----------|-------|
| `tests/test_config.py` | Validiert Schema (`version`, `supervisor`, `domains`, Pflichtfelder). |
| `tests/test_supervisor_routing.py` | Stellt sicher, dass Handoff-Tools erzeugt werden. |
| `tests/test_offline_sim.py` | Prüft Offline-Handoff zwischen allen Workern. |
| `tests/test_prompts_snapshot.py` | Snapshot des Supervisor-Systemprompts (Schutz vor unbeabsichtigten Änderungen). |

Die Tests laufen via `pytest` und werden im CI eingebunden.

Snapshots liegen in `tests/__snapshots__/`.

## Migration

1. Alte Top-Level-Domänen (`material`, `profil`, …) nach `domains:` verschieben.
2. `description` → `routing.description`, `prompt` → `prompt.system`.
3. Supervisor-Parameter in `supervisor:` konsolidieren.
4. Code, der `AgentsConfig.domain_cfg(...)` konsumiert, funktioniert unverändert; Felder heißen jetzt `routing_description` und `prompt.system`.
5. Optional: `supervisor.max_handoffs` auf gewünschte Grenze setzen (Default 5).

## Logging & Monitoring

- Jeder Handoff wird in `_handoff_trace` protokolliert und landet in `slots["handoff_history"]`.
- Bei Überschreitung `max_handoffs` schreibt der Supervisor ein Warn-Log.
- Ergänzend empfiehlt sich eine strukturierte Auswertung über die Checkpointer-Daten (nicht Teil dieses Dokuments).
