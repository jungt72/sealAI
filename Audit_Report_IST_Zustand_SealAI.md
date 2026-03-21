# Audit Report — IST-Zustand SealAI
**Datum:** 2026-03-20
**Grundlage:** `konzept/SealAI_Umbauplan_Single_Source_of_Truth.md`
**Scope:** Read-only. Keine Code-Änderungen.

---

## Vorabbefund: Zwei parallele Stacks

Vor der Vektoranalyse ein kritischer Befund, der den gesamten Report strukturiert:

Die Codebase enthält **zwei parallel existierende Backend-Stacks**:

| Stack | Pfad | State | API-Prefix |
|-------|------|-------|------------|
| **LangGraph v2 (alt)** | `backend/app/langgraph_v2/` | `SealAIState` (flach + Pillars) | `/api/v1/langgraph-v2/` |
| **Agent (neu)** | `backend/app/agent/` | `SealingAIState` (5-Layer) + `AgentState` | `/api/agent/` |

Der Umbauplan bezieht sich auf den **neuen Agent-Stack** als Zielarchitektur. Die RWDR-Berechnungslogik und der SSE-Multiplexer existieren aber **nur im alten LangGraph-v2-Stack** und sind noch nicht auf den neuen Stack portiert.

Dieser Split ist der größte architektonische Gap.

---

## Vektor 1 — CORE & STATE (Preserve-Check)

### 1a. SealingAIState — 5-Layer-State

**Datei:** `backend/app/agent/agent/state.py`, Zeilen 49–177

Der 5-Layer-State ist vollständig implementiert und entspricht dem Zielbild (P1 im Umbauplan).

**Layer-Struktur:**

```python
# state.py:49-101 — Layer-Definitionen
class ObservedLayer(TypedDict):      # L1: immutable raw intake
    observed_inputs: List[ObservedInputRecord]
    raw_parameters: Dict[str, Any]

class NormalizedLayer(TypedDict):    # L2: Identity Gating
    identity_records: Dict[str, IdentityRecord]
    normalized_parameters: Dict[str, Any]

class AssertedLayer(TypedDict):      # L3: Typed Profiles
    medium_profile: Dict[str, Any]
    machine_profile: Dict[str, Any]
    installation_profile: Dict[str, Any]
    operating_conditions: Dict[str, Any]
    sealing_requirement_spec: Dict[str, Any]

class GovernanceLayer(TypedDict):    # L4: Compliance & Gates
    release_status: ReleaseStatus
    rfq_admissibility: RFQAdmissibility
    specificity_level: SpecificityLevel
    scope_of_validity: List[str]
    assumptions_active: List[str]
    gate_failures: List[str]
    unknowns_release_blocking: List[str]
    unknowns_manufacturer_validation: List[str]
    conflicts: List[Dict[str, Any]]

class CycleLayer(TypedDict):         # L5: Determinismus & Revision
    analysis_cycle_id: str
    snapshot_parent_revision: int
    superseded_by_cycle: Optional[str]
    contract_obsolete: bool
    contract_obsolete_reason: Optional[str]
    state_revision: int
```

**Masterklasse** (state.py:150–177):
```python
class SealingAIState(TypedDict):
    observed: ObservedLayer
    normalized: NormalizedLayer
    asserted: AssertedLayer
    governance: GovernanceLayer
    cycle: CycleLayer
    selection: SelectionLayer        # non-binding UI projection only
    result_contract: NotRequired[Dict[str, Any]]

class AgentState(TypedDict):         # LangGraph orchestration wrapper
    messages: Annotated[List[AnyMessage], add_messages]
    sealing_state: SealingAIState
    relevant_fact_cards: List[Dict[str, Any]]
    working_profile: Dict[str, Any]
    tenant_id: Optional[str]
    owner_id: NotRequired[Optional[str]]
    loaded_state_revision: NotRequired[int]
    case_state: NotRequired[CaseState]
    result_form: NotRequired[Optional[str]]
```

**Bewertung:** P1 (Preserve) — vollständig konform. Dieser State ist der stärkste Baustein im System.

**IST-Gap:** Der alte LangGraph-v2-Stack verwendet `SealAIState` (flache Pillar-Struktur in `backend/app/langgraph_v2/state.py`) — ein separates, strukturell schwächeres State-Modell, das noch parallel produktiv läuft.

---

### 1b. Guard-Mechanik / Invarianten / Whitelists

**Datei:** `backend/app/agent/agent/logic.py`, Zeilen 18–60

**Normative Enumerations (Whitelists):**
```python
# logic.py:18-46
_NORMATIVE_RELEASE_STATUSES = {
    "inadmissible", "precheck_only",
    "manufacturer_validation_required", "rfq_ready", "not_applicable",
}
_NORMATIVE_RFQ_ADMISSIBILITY = {"inadmissible", "provisional", "ready", "not_applicable"}
_NORMATIVE_SPECIFICITY = {
    "family_only", "subfamily", "compound_required", "product_family_required",
}
_BLOCKING_CONFLICT_SEVERITIES = {"CRITICAL", "BLOCKING_UNKNOWN"}
_BLOCKING_CONFLICT_TYPES = {
    "domain_limit_violation", "parameter_conflict", "scope_conflict",
    "condition_conflict", "compound_specificity_conflict",
    "identity_unresolved", "temporal_validity_conflict", "assumption_conflict",
}
_MANUFACTURER_CONFLICT_TYPES = {
    "manufacturer_scope_required", "resolution_requires_manufacturer_scope",
}
```

**State-Shape-Enforcement** (logic.py:57–60):
```python
def _ensure_state_shape(state: SealingAIState) -> SealingAIState:
    """Blueprint Section 02/12: keep all five layers and mandatory governance fields present."""
    state.setdefault("observed", {"observed_inputs": [], "raw_parameters": {}})
    # ... enforces all five layers
```

**Material-Pattern-Guards** (logic.py:48–54):
```python
_MATERIAL_FAMILY_PATTERN = re.compile(r"\b(NBR|PTFE|FKM|FFKM|EPDM|SILIKON)\b", re.I)
_SPECIFIC_GRADE_PATTERN = re.compile(r"\b(?:grade|compound|typ|type)\s*[:\-]?\s*([a-z0-9._-]+)\b", re.I)
_FILLER_HINT_PATTERN = re.compile(r"\b(filled|glass[- ]filled|carbon[- ]filled|bronze[- ]filled)\b", re.I)
```

**Claim-Conflict-Evaluation** — deterministisch, außerhalb des LLM:
- Datei: `logic.py`, Funktion `evaluate_claim_conflicts()` (~Zeile 831)
- Checks: Physics Limits, Domain Constraints, Conflict Severity

**Bewertung:** P2 (Preserve) — solide Guard-Mechanik vorhanden.

---

### 1c. RWDR-Vertical-Slice

**Befund: RWDR-Logik existiert NUR im alten LangGraph-v2-Stack.**

**Datei (LangGraph v2):** `backend/app/services/rag/nodes/p4_live_calc.py`, Zeilen 30–35, 160–274

```python
# p4_live_calc.py:30-34 — RWDR-Limits
_RWDR_SPEED_LIMIT_NBR = 12.0      # m/s
_RWDR_SPEED_LIMIT_MAX = 35.0      # m/s
_RWDR_HRC_MIN_HIGH_SPEED = 45.0   # HRC
_RWDR_HIGH_SPEED_THRESHOLD = 4.0  # m/s Schwelle für High-Speed-Check
```

```python
# p4_live_calc.py:178-190 — RWDR-Berechnung
# Standard RWDR approximation: Pr [W] ≈ 0.5 * d1 [mm] * vs [m/s]
# HRC Warning: Standard limit OR RWDR expert high speed limit
# RWDR expert: < 45 HRC at high speed (v > 4 m/s)
```

Im neuen Agent-Stack gibt es nur einen **Versions-Platzhalter**:
- Datei: `backend/app/agent/case_state.py`, Zeile 35:
  `rwdr_config_version: str | None`
- Datei: `backend/app/agent/api/router.py`, Zeile 38–53:
  `_build_structured_version_provenance(*, decision, rwdr_config_version=None)` — Parameter immer `None`

**Gap zu P3:** Der RWDR-Vertical-Slice ist **nicht portiert** auf den neuen Agent-Stack. Er lebt im alten Stack und wird über die LangGraph-v2-Pipeline aktiviert. Der neue Agent-Stack hat keinen deterministischen Berechnungspfad für RWDR.

---

### 1d. Visible Narrative / Case Projection

**Datei:** `backend/app/agent/case_state.py`, Zeilen 363–394

**Funktion:** `build_visible_case_narrative()`

```python
# case_state.py:363-394
def build_visible_case_narrative(
    *,
    state: dict[str, Any],        # ACHTUNG: wird via `del state` sofort verworfen
    case_state: dict[str, Any] | None,
    binding_level: str,           # ACHTUNG: wird via `del binding_level` sofort verworfen
    policy_context: dict[str, Any] | None = None,
) -> VisibleCaseNarrative:
    del state, binding_level      # <-- BEIDE PARAMETER WERDEN VERWORFEN
    effective_policy = policy_context
    case_meta = (case_state or {}).get("case_meta") or {}
    if effective_policy is None:
        effective_policy = case_meta.get("policy_narrative_snapshot")
    coverage_scope = _build_visible_coverage_scope(effective_policy)
    summary = "Aktuelle technische Richtung: No active technical direction."
    prefix = _coverage_prefix((effective_policy or {}).get("coverage_status"))
    if prefix:
        summary = prefix + summary
    return {
        "governed_summary": summary,
        "technical_direction": [],      # <-- IMMER LEER
        "validity_envelope": [],         # <-- IMMER LEER
        "next_best_inputs": [],          # <-- IMMER LEER
        "suggested_next_questions": [], # <-- IMMER LEER
        "failure_analysis": [],          # <-- IMMER LEER
        "case_summary": [],              # <-- IMMER LEER
        "qualification_status": [],      # <-- IMMER LEER
        "coverage_scope": coverage_scope,
    }
```

**Gap zu P4:** Die Funktion liefert einen strukturierten Vertrag, aber **7 von 8 Feldern sind immer leere Listen**. Die eigentlichen Fachprojektionen (technical_direction, validity_envelope, next_best_inputs, etc.) sind Stubs. Die Parameter `state` und `binding_level` werden unmittelbar verworfen — fachlich relevante Eingaben, die laut Umbauplan die Projektion steuern sollten.

**Versionierungsstruktur ist vorhanden:**
```python
# case_state.py:9-12
PROJECTION_VERSION = "visible_case_narrative_v1"
CASE_STATE_BUILDER_VERSION = "case_state_builder_v1"
DETERMINISTIC_SERVICE_VERSION = "deterministic_stack_v1"
DETERMINISTIC_DATA_VERSION = "promoted_registry_v1"
```

---

## Vektor 2 — ROUTING & INTERACTION POLICY (R1 & R2)

### 2a. Aktuelle Routing-Logik

**Datei:** `backend/app/agent/runtime.py`, Zeilen 1–55

```python
# runtime.py:24-54 — VOLLSTÄNDIGE Interaction Policy
INTERACTION_POLICY_VERSION = "interaction_policy_v1"

def evaluate_interaction_policy(message: str) -> InteractionPolicyDecision:
    lowered = message.lower()
    if "was ist" in lowered:           # ← EINZIGER KNOWLEDGE-TRIGGER
        return InteractionPolicyDecision(
            result_form="guided", path="fast", stream_mode="reply_only",
            interaction_class="KNOWLEDGE", runtime_path="FAST_KNOWLEDGE",
            binding_level="KNOWLEDGE", has_case_state=False,
        )
    if "berechne" in lowered:          # ← EINZIGER CALCULATION-TRIGGER
        return InteractionPolicyDecision(
            result_form="guided", path="fast", stream_mode="reply_only",
            interaction_class="CALCULATION", runtime_path="FAST_CALCULATION",
            binding_level="CALCULATION", has_case_state=False,
        )
    return InteractionPolicyDecision(  # ← ALLES ANDERE → QUALIFICATION
        result_form="qualified", path="structured",
        stream_mode="structured_progress_stream",
        interaction_class="QUALIFICATION",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
        has_case_state=True,
    )
```

**Gap zu R1:** Dies ist genau der im Umbauplan beschriebene IST-Zustand — eine Keyword-Approximation. Die Policy-Felder `coverage_status`, `boundary_flags`, `escalation_reason`, `required_fields` sind in der Datenklasse zwar definiert, werden aber nie befüllt (immer `None` / leer). Es gibt:
- **keine** ambiguity evaluation
- **keine** completeness evaluation
- **keine** coverage check
- **keine** risk/binding evaluation
- **keinen** intent classifier
- **keine** LLM-gestützte Vorstrukturierung

**Kritischer Impact:** Jede Anfrage, die nicht "was ist" oder "berechne" enthält, landet im schweren `STRUCTURED_QUALIFICATION`-Pfad. Eine Anfrage wie "Welches Material nehme ich für Hydrauliköl?" aktiviert die volle Qualification-Pipeline.

---

### 2b. Graph-internes Routing

**Datei:** `backend/app/agent/agent/graph.py`, Zeilen 279–290

```python
# graph.py:279-290 — Einziger Graph-Router
def router(state: AgentState) -> Literal["evidence_tool_node", "selection_node"]:
    """Conditional Edge zur Prüfung auf Tool-Calls. Deterministisches Routing (Blueprint Section 03)."""
    last_message = state.get("messages", [])[-1] if state.get("messages") else None
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "evidence_tool_node"
    return "selection_node"
```

Dieser interne Router ist korrekt deterministisch (P2). Er entscheidet aber nur, ob ein LLM-Tool-Call vorliegt — er implementiert keine Interaction Policy.

**Graph-Topologie:**
```
START → reasoning_node → [router] → evidence_tool_node → reasoning_node (loop)
                                  ↘ selection_node → final_response_node → END
```

---

### 2c. Guidance vs. Qualification — Trennung

**Datei:** `backend/app/agent/api/router.py`, Zeilen 262–296

```python
# router.py:262-296 — Pfad-Dispatch
decision = evaluate_interaction_policy(request.message)

if not decision.has_case_state:
    # GUIDANCE-PFAD: Fast, kein case_state, session-basiert
    # ... führt execute_agent() aus, gibt guidance_response zurück
    payload = _build_guidance_response_payload(decision, ...)
    return ChatResponse(sealing_state=..., **payload)

# QUALIFICATION-PFAD: Strukturiert, mit case_state, persistiert
state = await prepare_structured_state(request, current_user=current_user)
updated_state = execute_agent(state)
visible_case_narrative = build_visible_case_narrative(...)
payload = build_runtime_payload(decision, ..., case_state=..., visible_case_narrative=...)
await persist_structured_state(...)
return ChatResponse(sealing_state=..., **payload)
```

**Befund:** Die Trennung existiert strukturell (`has_case_state`), aber:
1. **Beide Pfade rufen `execute_agent()` auf** — denselben schweren LangGraph-Graph. Der Guidance-Pfad ist nicht wirklich leichter.
2. Der Guidance-Pfad basiert auf 2 Keywords (`"was ist"`, `"berechne"`). Alle anderen Anfragen landen in Qualification.
3. **Gap zu R2:** Guidance ist kein eigenständiger leichter Mode — es ist dieselbe Pipeline mit anderem Payload-Format.

---

## Vektor 3 — TENANT SAFETY & RAG (R4 / Phase 0A.1)

### KRITISCHER BEFUND: tenant_id wird absichtlich verworfen

**Datei:** `backend/app/agent/agent/graph.py`, Zeilen 45–53

```python
# graph.py:45-47 — KRITISCH: tenant_id wird verworfen
async def retrieve_rag_context(query: str, tenant_id: str | None) -> list[Any]:
    del tenant_id                               # ← ABSICHTLICHES VERWERFEN
    return retrieve_fact_cards_fallback(query)  # ← Lokales JSON, kein Tenant-Scope
```

Das ist das `del tenant_id`-Muster, das im Umbauplan explizit als zu behebende Verletzung der harten Regel "tenant_id darf nie mehr verworfen werden" genannt wird.

**Verlauf der tenant_id:**

1. **Korrekt gesetzt** im Router (router.py:267):
   ```python
   tenant_id = current_user.tenant_id or owner_id
   SESSION_STORE[cache_key] = {... "tenant_id": tenant_id ...}
   ```

2. **Korrekt propagiert** im AgentState (state.py:173):
   ```python
   tenant_id: Optional[str]
   ```

3. **Korrekt ausgelesen** im reasoning_node (graph.py:69):
   ```python
   tenant_id = state.get("tenant_id")
   ```

4. **Übergeben** an retrieve_rag_context (graph.py:82):
   ```python
   relevant_cards = await retrieve_rag_context(query, tenant_id)
   ```

5. **Verworfen** in retrieve_rag_context (graph.py:46):
   ```python
   del tenant_id   # ← HIER BRICHT DIE KETTE
   ```

---

### 3a. Agent-RAG-Adapter — IST-Zustand

**Primärpfad** (graph.py:79–86):
```python
# graph.py:79-96
path_used = "real_rag"
try:
    relevant_cards = await retrieve_rag_context(query, tenant_id)
    # ↑ retrieve_rag_context macht: del tenant_id; return retrieve_fact_cards_fallback(query)
except Exception as e:
    logger.error(f"[RAG] Real-RAG Error, falling back: {e}", exc_info=True)
    relevant_cards = []
    path_used = "real_rag_error_fallback"

# Fallback
if not relevant_cards and query:
    relevant_cards = retrieve_fact_cards_fallback(query)  # ← Wieder kein Tenant-Scope
    path_used = "pseudo_rag_fallback"

logger.info(f"[RAG] Path: {path_used}, Hits: {len(relevant_cards)}, Tenant: {tenant_id}")
# ↑ tenant_id wird geloggt, aber nicht für Filtering genutzt
```

**Der "primäre RAG-Pfad" ist eine leere Hülle:**
`retrieve_rag_context` ruft intern sofort `retrieve_fact_cards_fallback` auf. Es gibt keine echte Anbindung an Qdrant oder den Hybrid-Retrieval-Stack.

**Fallback** (graph.py:50–53):
```python
# graph.py:50-53 — Lokales JSON
def retrieve_fact_cards_fallback(query: str) -> list[Any]:
    kb_path = os.path.join(os.path.dirname(__file__), "..", "..", "knowledge_base.json")
    cards = load_fact_cards(kb_path)
    return retrieve_fact_cards(query, cards)
```

Das lokale `knowledge_base.json` hat keinen Tenant-Scope. Alle Tenants sehen dieselben Daten.

---

### 3b. Reale Retrieval-Infrastruktur im alten Stack

Im **LangGraph-v2-Stack** existiert eine vollwertige Retrieval-Infrastruktur:
- Qdrant-Collection `sealai_knowledge` mit tenant-sicherem Filter (`p2_rag_lookup.py`)
- Hybrid-Retrieval (BM25 + Vector)
- `_build_qdrant_filter()` mit Tenant-Scoping

Diese Infrastruktur ist **nicht angebunden** an den neuen Agent-Stack.

---

### 3c. Tools — keine RAG-Integration

**Datei:** `backend/app/agent/agent/tools.py`

Das einzige Tool ist `submit_claim()` — kein Retrieval-Tool. RAG passiert im reasoning_node als Kontext-Injektion, nicht als explizites Agent-Tool. Eine tenant-sichere RAG-Tool-Anbindung fehlt vollständig.

---

## Vektor 4 — STREAMING & OUTPUT (R7 / Phase 0A.4)

### Zwei völlig verschiedene Streaming-Architekturen

Der SSE-Multiplexer mit Node-Filter ist **ausschließlich für den LangGraph-v2-Stack** gebaut. Der neue Agent-Stack verwendet ein einfaches Generator-Pattern.

---

### 4a. LangGraph-v2-Stack: SSE Multiplexer mit Node-Filter

**Datei:** `backend/app/api/v1/sse_runtime.py`, Zeilen 539–558

```python
# sse_runtime.py:539-558 — Node-Whitelist für Streaming
if event_name == "on_chat_model_stream":
    tags = raw_event.get("tags") or []
    tagged_nodes = _extract_stream_nodes_from_tags(tags)
    speaking_nodes = set(tagged_nodes)
    if node_name:
        speaking_nodes.add(str(node_name))
    allowed_speaking_nodes = {
        "response_node",
        "contract_first_output_node",
        "node_finalize",
        "final_answer_node",
    }
    is_speaking = any(node in allowed_speaking_nodes for node in speaking_nodes)
    if is_speaking:
        chunk_text = _extract_chunk_text_from_stream_event(data.get("chunk"))
        if chunk_text:
            token_seen = True
            await _queue_emit("text_chunk", {"type": "text_chunk", "text": chunk_text})
            await _queue_emit("token", {"type": "token", "text": chunk_text})
    continue
```

Im LangGraph-v2-Stack ist R7 (Streaming-Filter) bereits **korrekt implementiert**. Nur 4 explizit genannte Output-Nodes dürfen Tokens streamen. Reasoning/Tool/Intermediate Nodes werden gefiltert.

---

### 4b. Neuer Agent-Stack: Kein Node-Filter

**Datei:** `backend/app/agent/api/router.py`, Zeilen 210–243

```python
# router.py:210-243 — Streaming im Agent-Stack (OHNE Node-Filter)
async def event_generator(request: ChatRequest):
    session_id = request.session_id
    # ... state setup
    try:
        async for chunk in app.astream(current_state):
            if final_state := chunk.get("final_response_node"):
                SESSION_STORE[session_id] = final_state
                yield f"data: {json.dumps({'state': final_state['sealing_state'], 'working_profile': final_state.get('working_profile', {})})}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
```

**Befunde:**
1. Kein Node-Filter — der Stream gibt nur den finalen State aus (`final_response_node`-Chunk)
2. Es werden keine Tokens/Text-Chunks gestreamt — nur State-Snapshots als JSON
3. Kein SSE-Event-Multiplexer mit strukturierten Event-Types (`text_chunk`, `token`, `node_status`, etc.)
4. **Der `/api/agent/chat` (non-stream) Endpoint** (`execute_agent()`) ist vollständig **synchron** — kein Streaming-Feedback

**Gap zu R7 im neuen Stack:** Der Agent-Stack hat kein echtes Token-Streaming. Der Nutzer sieht keinen progressiven Antwortaufbau. Der `/chat/stream` Endpoint liefert nur binäre State-Dumps pro Node-Abschluss.

---

### 4c. Synchrones execute_agent

**Datei:** `backend/app/agent/api/router.py`, Zeilen 273–279 + 282

```python
# router.py: beide Hauptpfade rufen synchrones execute_agent() auf
updated_state = execute_agent(current_state)   # Guidance-Pfad
# ...
updated_state = execute_agent(state)           # Qualification-Pfad
```

Auch wenn der LangGraph-Graph async-Nodes hat (`async def reasoning_node`), wird über `execute_agent()` synchron aufgerufen. Dies blockiert den Event-Loop während des LLM-Calls.

---

## Zusammenfassung: Gap-Matrix

| Umbauplan-AP | IST-Zustand | Gap-Schwere | Betroffene Datei(en) |
|-------------|-------------|-------------|----------------------|
| **P1 — 5-Layer-State** | ✅ Vollständig implementiert | Kein Gap | `agent/state.py:150` |
| **P2 — Guard-Mechanik** | ✅ Whitelists + Conflict-Evaluator vorhanden | Kein Gap | `agent/logic.py:18-46` |
| **P3 — RWDR-Slice** | ⚠️ Nur im alten LangGraph-v2-Stack | Nicht portiert auf Agent-Stack | `services/rag/nodes/p4_live_calc.py` |
| **P4 — Visible Narrative** | ⚠️ Struktur vorhanden, 7/8 Felder leer | Stub-Zustand | `agent/case_state.py:363` |
| **R1 — Interaction Policy** | ❌ 2-Keyword-Approximation | HOCH: kein Intent-Classifier, keine Coverage | `agent/runtime.py:24-54` |
| **R2 — Guidance vs. Qualification** | ❌ Beide Pfade rufen denselben schweren Graph | HOCH: keine echte Pfad-Trennung | `agent/api/router.py:262-296` |
| **R4 — Agent-RAG tenant-safe** | ❌ `del tenant_id` in graph.py:46 | KRITISCH: Tenant-Isolation gebrochen | `agent/agent/graph.py:45-47` |
| **R7 — Streaming Node-Filter** | ⚠️ Im alten Stack vorhanden, nicht im neuen | MITTEL: kein Token-Streaming im Agent | `agent/api/router.py:210-243` |
| **A1 — Coverage-Kommunikation** | ❌ Nicht vorhanden | HOCH: kein boundary output | — |
| **A2 — Versionierung** | ⚠️ Felder in VersionProvenance vorhanden, nicht vollständig befüllt | MITTEL | `agent/case_state.py:24-36` |
| **A5 — Tenant-sichere End-to-End-Pfade** | ❌ RAG bricht Tenant-Scoping | KRITISCH | `agent/agent/graph.py:45-47` |

---

## Kritische Code-Snippets für Phase 0A

### 0A.1 — tenant_id in RAG reparieren

**Zu refactoren:**
```python
# backend/app/agent/agent/graph.py:45-47
# AKTUELL (BROKEN):
async def retrieve_rag_context(query: str, tenant_id: str | None) -> list[Any]:
    del tenant_id                              # ← ENTFERNEN
    return retrieve_fact_cards_fallback(query) # ← ERSETZEN durch echtes Qdrant-Retrieval
```

**Angebundener Retrieval-Stack existiert im LangGraph-v2-Pfad:**
- `backend/app/services/rag/nodes/p2_rag_lookup.py` — Hybrid Retrieval mit `_build_qdrant_filter()`
- `backend/app/services/rag/hybrid_retrieve.py` — echte Qdrant+BM25-Implementierung

---

### 0A.2 — Interaction Policy ersetzen

**Zu refactoren:**
```python
# backend/app/agent/runtime.py:24-54
# AKTUELL:
def evaluate_interaction_policy(message: str) -> InteractionPolicyDecision:
    lowered = message.lower()
    if "was ist" in lowered:   # ← NUR 2 KEYWORDS
        ...
    if "berechne" in lowered:
        ...
    return ...QUALIFICATION    # ← ALLES ANDERE = QUALIFICATION
```

**Soll:** LLM-gestützte Intent-Vorklassifikation + deterministischer Policy-Gate (Coverage, Completeness, Risk).

---

### 0A.3 — Guidance-Pfad von Qualification trennen

**Zu refactoren:**
```python
# backend/app/agent/api/router.py:262-296
# AKTUELL: beide Pfade rufen execute_agent() auf
if not decision.has_case_state:
    ...
    updated_state = execute_agent(current_state)  # ← Voller Graph
    ...
updated_state = execute_agent(state)              # ← Voller Graph
```

**Soll:** Guidance nutzt leichten Fast-Path (LLM-only oder LLM + leichte Lookups), Qualification nutzt vollen Graph.

---

### 0A.4 — Token-Streaming für Agent-Stack

**Zu ergänzen:**
```python
# backend/app/agent/api/router.py:210-243
# AKTUELL: nur State-Dump pro Node
async for chunk in app.astream(current_state):
    if final_state := chunk.get("final_response_node"):
        yield f"data: {json.dumps({'state': final_state['sealing_state']})}\n\n"
```

**Soll:** SSE-Multiplexer mit Node-Whitelist analog zu `sse_runtime.py:539-558`, Token-Streaming nur für Output-Nodes.

---

## Dateifokus Phase 0A

| Phase | Datei | Priorität |
|-------|-------|-----------|
| 0A.1 (RAG tenant-safe) | `backend/app/agent/agent/graph.py` | SOFORT |
| 0A.1 (RAG tenant-safe) | `backend/app/services/rag/hybrid_retrieve.py` | SOFORT |
| 0A.2 (Interaction Policy) | `backend/app/agent/runtime.py` | SOFORT |
| 0A.2 (Interaction Policy) | `backend/app/agent/api/router.py` | SOFORT |
| 0A.3 (Guidance vs Qual) | `backend/app/agent/api/router.py` | HOCH |
| 0A.3 (Guidance vs Qual) | `backend/app/agent/agent/graph.py` | HOCH |
| 0A.4 (Streaming) | `backend/app/agent/api/router.py` | MITTEL |
| 0A.5 (Versionierung) | `backend/app/agent/case_state.py` | MITTEL |

---

*Report erstellt: 2026-03-20 — Read-only Audit, keine Code-Änderungen*
