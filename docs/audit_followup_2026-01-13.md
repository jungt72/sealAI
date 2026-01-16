START: BASELINE REPO MAP
A) Concise tree (max depth 4)

backend/app/api
├── __init__.py
├── tests
│   ├── test_ai_beratung_stm_keying.py
│   ├── test_langgraph_v2_confirm_go.py
│   ├── test_langgraph_v2_dedup_client.py
│   ├── test_langgraph_v2_dedup_loop_safety.py
│   ├── test_langgraph_v2_endpoint.py
│   ├── test_langgraph_v2_param_sync_integration.py
│   ├── test_langgraph_v2_sse.py
│   ├── test_langgraph_v2_sse_scope.py
│   ├── test_langgraph_v2_sse_trace.py
│   ├── test_rag_list.py
│   ├── test_rag_upload_limits.py
│   ├── test_rag_upload.py
│   └── test_rag_worker.py
└── v1
    ├── api.py
    ├── dependencies
    ├── endpoints
    └── schemas

backend/app/langgraph_v2
├── constants.py
├── contracts.py
├── nodes
│   ├── nodes_confirm.py
│   ├── nodes_consulting.py
│   ├── nodes_discovery.py
│   ├── nodes_error.py
│   ├── nodes_flows.py
│   ├── nodes_frontdoor.py
│   ├── nodes_intent.py
│   ├── nodes_knowledge.py
│   ├── nodes_preflight.py
│   ├── nodes_resume.py
│   ├── nodes_supervisor.py
│   ├── nodes_validation.py
│   └── response_node.py
├── sealai_graph_v2.py
├── state
│   └── sealai_state.py
├── tools
│   └── parameter_tools.py
└── utils
    ├── checkpointer.py
    ├── confirm_checkpoint.py
    ├── confirm_go.py
    ├── db.py
    ├── jinja.py
    ├── json_sanitizer.py
    ├── llm_factory.py
    ├── messages.py
    ├── output_sanitizer.py
    ├── parameter_extraction.py
    ├── parameter_patch.py
    ├── rag.py
    ├── rag_safety.py
    ├── rag_tool.py
    ├── state_debug.py
    └── threading.py

backend/app/services
├── auth
│   ├── dependencies.py
│   ├── jwt_utils.py
│   ├── scope.py
│   └── token.py
├── chat
│   ├── conversations.py
│   ├── persistence.py
│   ├── rate_limit.py
│   ├── security.py
│   ├── validation.py
│   ├── ws_commons.py
│   ├── ws_config.py
│   └── ws_streaming.py
├── history
│   └── persist.py
├── jobs
│   ├── queue.py
│   └── worker.py
├── langgraph
│   ├── domains
│   ├── graph
│   ├── prompt_templates
│   ├── prompts
│   └── rules
├── memory
│   ├── conversation_memory.py
│   └── memory_core.py
├── rag
│   ├── bm25_store.py
│   ├── document.py
│   ├── embeddings.py
│   ├── qdrant_bootstrap.py
│   ├── qdrant_naming.py
│   ├── qdrant_point_ids.py
│   ├── rag_ingest.py
│   ├── rag_orchestrator.py
│   └── rag_safety.py
├── qdrant_client.py
├── redis_client.py
└── sse_broadcast.py

backend/app/prompts
├── confirm_gate.j2
├── discovery_summarize.j2
├── final_answer_discovery_v2.j2
├── final_answer_explanation_v2.j2
├── final_answer_out_of_scope_v2.j2
├── final_answer_recommendation_v2.j2
├── final_answer_router.j2
├── final_answer_smalltalk_v2.j2
├── final_answer_troubleshooting_v2.j2
├── frontdoor_discovery_prompt.jinja2
├── leakage_troubleshooting.j2
├── material_comparison.j2
├── response_router.j2
├── senior_policy_de.j2
└── troubleshooting_explainer.j2

backend/app/models
├── beratungsergebnis.py
├── chat_message.py
├── chat_transcript.py
├── form_result.py
├── long_term_memory.py
├── postgres_logger.py
└── rag_document.py

backend/tests
├── contract
├── integration
├── quality
├── conftest.py
├── test_auth_dependencies.py
├── test_dependency_sanity.py
├── test_langgraph_compile.py
├── test_langgraph_parameters_patch.py
├── test_metrics_endpoint.py
├── test_obs_min.py
├── test_parameter_guardrails.py
├── test_parameter_lww.py
├── test_param_snapshot.py
├── test_rag_hybrid_retrieval.py
├── test_rag_ingest_metadata.py
├── test_rag_orchestrator_retry.py
├── test_rag_orchestrator_sources.py
├── test_request_id_middleware.py
├── test_security.py
├── test_smoke_health.py
├── test_sse_broadcast.py
└── test_sse_replay_backend.py

tests
├── api
├── keycloak
├── langgraph
├── langgraph_v2
├── ws
├── conftest.py
├── test_api_langgraph.py
├── test_consult_e2e.py
├── test_consult_graph_nodes.py
├── test_recommend_node.py
└── test_supervisor_router.py

B) FastAPI routers + prefixes (incl. v2 chat/SSE endpoints)
- api router includes
  - Path: backend/app/api/v1/api.py:20-37
  - Excerpt:
    ```py
    api_router = APIRouter()
    api_router.include_router(ping.router)
    api_router.include_router(chat_history.router)
    api_router.include_router(langgraph_v2.router, prefix="/langgraph", tags=["langgraph-v2"])
    api_router.include_router(langgraph_health.router, prefix="/langgraph", tags=["langgraph-v2"])
    api_router.include_router(state.router, prefix="/langgraph", tags=["langgraph-v2"])
    api_router.include_router(auth.router)
    api_router.include_router(memory.router)
    api_router.include_router(users.router)
    api_router.include_router(rag.router)
    api_router.include_router(rfq_endpoint.router, prefix="/rfq", tags=["rfq"])
    ```
- API mount prefix
  - Path: backend/app/main.py:137-138
  - Excerpt:
    ```py
    # v1-API mounten
    app.include_router(api_router, prefix="/api/v1")
    ```
- v2 chat/SSE endpoint definition
  - Path: backend/app/api/v1/endpoints/langgraph_v2.py:1129-1184
  - Excerpt:
    ```py
    @router.post("/chat/v2")
    async def langgraph_chat_v2_endpoint(...):
        ...
        return StreamingResponse(
            _event_stream_v2(...),
            media_type="text/event-stream",
            headers=headers,
        )
    ```
- RAG router prefix
  - Path: backend/app/api/v1/endpoints/rag.py:20-21
  - Excerpt:
    ```py
    router = APIRouter(prefix="/rag", tags=["rag"])
    ```
- Memory router prefix
  - Path: backend/app/api/v1/endpoints/memory.py:22
  - Excerpt:
    ```py
    router = APIRouter(prefix="/memory", tags=["memory"])
    ```
- Chat history router prefix
  - Path: backend/app/api/v1/endpoints/chat_history.py:22
  - Excerpt:
    ```py
    router = APIRouter(prefix="/chat", tags=["chat"])
    ```
- RFQ router prefix
  - Path: backend/app/api/v1/api.py:39-40
  - Excerpt:
    ```py
    api_router.include_router(rfq_endpoint.router, prefix="/rfq", tags=["rfq"])
    ```

C) thread_id / chat_id / session_id usage and mapping
- v2 chat uses chat_id for thread_id in graph config
  - Path: backend/app/api/v1/endpoints/langgraph_v2.py:1136-1173
  - Excerpt:
    ```py
    request.chat_id = normalize_chat_id(request.chat_id, request_id=request_id)
    ...
    _event_stream_v2(
        request,
        user_id=scoped_user_id,
        tenant_id=scoped_tenant_id,
        ...
    )
    ```
  - Path: backend/app/langgraph_v2/sealai_graph_v2.py:562-586
  - Excerpt:
    ```py
    def build_v2_config(*, thread_id: str, user_id: str, tenant_id: str | None = None) -> Dict[str, Any]:
        configurable = {
            "thread_id": thread_id,
            "user_id": user_id,
            "checkpoint_ns": checkpoint_ns,
        }
    ```
- chat_id normalization = UUIDv4 (thread_id is a UUID string)
  - Path: backend/app/services/chat/validation.py:5-29
  - Excerpt:
    ```py
    def normalize_chat_id(chat_id: str | None, request_id: str | None = None) -> str:
        ...
        if not raw:
            return str(uuid.uuid4())
    ```
- chat history uses conversation_id (same as chat_id/thread_id) keyed by user_id
  - Path: backend/app/api/v1/endpoints/chat_history.py:120-125
  - Excerpt:
    ```py
    def _resolve_owner_ids(current_user: RequestUser) -> OwnerIds:
        canonical_id = canonical_user_id(current_user)
        ...
        legacy_owner_id = current_user.sub if current_user.sub != canonical_id else None
    ```
- session_id used in legacy DB models (separate from chat_id/thread_id)
  - Path: backend/app/models/chat_message.py:9-12
  - Excerpt:
    ```py
    username = Column(String, index=True)
    session_id = Column(String, index=True)
    ```
  - Path: backend/app/models/beratungsergebnis.py:10-12
  - Excerpt:
    ```py
    username = Column(String, index=True)
    session_id = Column(String, index=True)
    ```
  - Path: backend/app/models/postgres_logger.py:10-17
  - Excerpt:
    ```py
    async def log_message_to_db(..., session_id: str, ...):
        message = ChatMessage(username=username, session_id=session_id, ...)
    ```
- thread_id appears as state field in LangGraph v2 state (ties to chat_id)
  - Path: backend/app/langgraph_v2/state/sealai_state.py:307-315
  - Excerpt:
    ```py
    class SealAIState(BaseModel):
        ...
        thread_id: Optional[str] = None
    ```

SECTION 1 — MULTI-TENANCY END-TO-END (DB / JWT / Qdrant / Redis)
1.1 JWT → RequestUser
- Keycloak JWT verification/decoding
  - Path: backend/app/services/auth/token.py:101-158
  - Excerpt:
    ```py
    def verify_access_token(token: str) -> dict[str, Any]:
        ...
        claims: dict[str, Any] = jwt.decode(
            token,
            public_key_pem,
            algorithms=list(ALLOWED_ALGS),
            issuer=REALM_ISSUER,
            options=decode_options,
        )
    ```
- tenant_id claim and user_id claim
  - Path: backend/app/services/auth/dependencies.py:46-62
  - Excerpt:
    ```py
    def _resolve_user_id(payload: dict) -> str:
        claim = (os.getenv("AUTH_USER_ID_CLAIM") or "sub").strip()
        ...
    def _resolve_tenant_id(payload: dict) -> str | None:
        claim = (os.getenv("AUTH_TENANT_ID_CLAIM") or "tenant_id").strip()
    ```
- fallback for missing tenant_id (user_id/sub) gated by env
  - Path: backend/app/services/auth/dependencies.py:106-138
  - Excerpt:
    ```py
    def canonical_tenant_id(user: RequestUser) -> str:
        if user.tenant_id:
            return validate_tenant_id(user.tenant_id)
        allow_fallback = os.getenv("ALLOW_TENANT_FALLBACK") == "1"
        if allow_fallback:
            fallback = user.user_id or user.sub
            ...
            return validate_tenant_id(fallback)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, ...)
    ```
- RequestUser definition + fields
  - Path: backend/app/services/auth/dependencies.py:30-36
  - Excerpt:
    ```py
    @dataclass(frozen=True)
    class RequestUser:
        user_id: str
        username: str
        sub: str
        roles: list[str]
        tenant_id: str | None = None
    ```

1.2 Postgres schema + repositories
- chat_messages table (no tenant_id)
  - Path: backend/app/models/chat_message.py:6-14
  - Excerpt:
    ```py
    class ChatMessage(Base):
        __tablename__ = "chat_messages"
        id = Column(Integer, primary_key=True, index=True)
        username = Column(String, index=True)
        session_id = Column(String, index=True)
    ```
- chat_transcripts table (no tenant_id column in model)
  - Path: backend/app/models/chat_transcript.py:8-18
  - Excerpt:
    ```py
    class ChatTranscript(Base):
        __tablename__ = "chat_transcripts"
        chat_id = Column(String, primary_key=True)
        user_id = Column(String, nullable=False, index=True)
    ```
- form_results table (no tenant_id)
  - Path: backend/app/models/form_result.py:7-15
  - Excerpt:
    ```py
    class FormResult(Base):
        __tablename__ = "form_results"
        username = Column(String, index=True)
    ```
- rag_documents table (tenant_id present)
  - Path: backend/app/models/rag_document.py:9-21
  - Excerpt:
    ```py
    class RagDocument(Base):
        __tablename__ = "rag_documents"
        document_id = Column(String, primary_key=True, index=True)
        tenant_id = Column(String, index=True, nullable=False)
    ```
- beratungsergebnisse table (session_id, no tenant_id)
  - Path: backend/app/models/beratungsergebnis.py:7-16
  - Excerpt:
    ```py
    class Beratungsergebnis(Base):
        __tablename__ = "beratungsergebnisse"
        username = Column(String, index=True)
        session_id = Column(String, index=True)
    ```
- Chat transcript repository (intended tenant filter) but model lacks tenant_id
  - Path: backend/app/services/chat/persistence.py:34-75
  - Excerpt:
    ```py
    stmt = select(ChatTranscript).where(
        ChatTranscript.chat_id == chat_id,
        ChatTranscript.tenant_id == tenant_id,
    )
    ...
    transcript = ChatTranscript(
        chat_id=chat_id,
        user_id=user_id,
        tenant_id=tenant_id,
    )
    ```
- Chat transcript async persistence (no tenant filter, uses PK only)
  - Path: backend/app/services/history/persist.py:40-55
  - Excerpt:
    ```py
    existing = await session.get(ChatTranscript, chat_id)
    if existing:
        existing.summary = summary
    else:
        session.add(ChatTranscript(chat_id=chat_id, user_id=user_id, ...))
    ```
- Rag document queries filter by tenant but use current_user.user_id
  - Path: backend/app/api/v1/endpoints/rag.py:84-90
  - Excerpt:
    ```py
    tenant_id = current_user.user_id
    ```
  - Path: backend/app/api/v1/endpoints/rag.py:251-252
  - Excerpt:
    ```py
    stmt = select(RagDocument).where(RagDocument.tenant_id == current_user.user_id)
    ```
- Potential leak paths (no tenant filter):
  - Chat transcript persistence via history service is not tenant-scoped (see above).
  - ChatMessage/Postgres logger uses username + session_id only (no tenant).
    - Path: backend/app/models/postgres_logger.py:10-32
    - Excerpt:
      ```py
      async def get_messages_for_session(db: AsyncSession, username: str, session_id: str):
          result = await db.execute(select(ChatMessage)
              .where(ChatMessage.username == username)
              .where(ChatMessage.session_id == session_id))
      ```

1.3 Qdrant tenant filter
- RAG collection naming by tenant
  - Path: backend/app/services/rag/qdrant_naming.py:4-15
  - Excerpt:
    ```py
    def qdrant_collection_name(*, base: str, prefix: str | None, tenant_id: str | None) -> str:
        if clean_prefix and clean_tenant:
            return f"{clean_prefix}:{clean_tenant}"
    ```
- Qdrant search filter uses metadata_filters only (tenant filter optional)
  - Path: backend/app/services/rag/rag_orchestrator.py:292-314
  - Excerpt:
    ```py
    def _qdrant_search_with_retry(..., metadata_filters: Optional[Dict[str, Any]] = None):
        query_filter = None
        if metadata_filters:
            query_filter = qmodels.Filter(must=[...])
    ```
- hybrid_retrieve passes metadata_filters through without enforcing tenant
  - Path: backend/app/services/rag/rag_orchestrator.py:430-453
  - Excerpt:
    ```py
    def hybrid_retrieve(*, query: str, tenant: Optional[str], ... metadata_filters: Optional[Dict[str, Any]] = None):
        collection = _collection_for_tenant(tenant)
        vec_hits, qdrant_meta = _qdrant_search_with_retry(
            vec, collection, top_k=vector_k, metadata_filters=metadata_filters
        )
    ```
- Tenant filter enforced by LangGraph v2 tool (strict)
  - Path: backend/app/langgraph_v2/utils/rag_tool.py:30-58
  - Excerpt:
    ```py
    if not tenant:
        raise ValueError("missing tenant_id for RAG retrieval")
    filters = {"tenant_id": tenant}
    ...
    results, metrics = hybrid_retrieve(..., metadata_filters=filters, tenant=tenant, ...)
    ```
- Upsert/ingest writes tenant_id into metadata + collection naming by tenant
  - Path: backend/app/services/rag/rag_ingest.py:58-121
  - Excerpt:
    ```py
    if tenant_id:
        metadata["tenant_id"] = tenant_id
    ...
    collection_name = qdrant_collection_name(..., tenant_id=tenant_id)
    ```
- LTM Qdrant (memory) uses user filter only (no tenant field)
  - Path: backend/app/services/memory/memory_core.py:63-69
  - Excerpt:
    ```py
    def _build_user_filter(user: str, chat_id: Optional[str] = None) -> models.Filter:
        must = [models.FieldCondition(key="user", match=models.MatchValue(value=user))]
    ```

1.4 Redis tenant scoping
- LangGraph v2 checkpointer namespace includes tenant_id
  - Path: backend/app/langgraph_v2/sealai_graph_v2.py:550-586
  - Excerpt:
    ```py
    def _tenant_checkpoint_namespace(base: str, tenant_id: str | None) -> str:
        ...
    def build_v2_config(..., tenant_id: str | None = None):
        checkpoint_ns = _tenant_checkpoint_namespace(base_namespace, tenant_id)
    ```
- Checkpointer key prefix + TTL (minutes via LANGGRAPH_CHECKPOINT_TTL)
  - Path: backend/app/langgraph_v2/utils/checkpointer.py:38-59
  - Excerpt:
    ```py
    def _parse_checkpointer_ttl() -> Optional[int]:
        ttl_env = (os.getenv("LANGGRAPH_CHECKPOINT_TTL") or "").strip()
    def _resolve_checkpointer_settings(namespace: str | None):
        prefix = (os.getenv("LANGGRAPH_CHECKPOINT_PREFIX") or "lg:cp").strip()
    ```
- SSE replay Redis keys are tenant-scoped
  - Path: backend/app/services/sse_broadcast.py:150-153
  - Excerpt:
    ```py
    def _get_redis_key(self, user_id: str, chat_id: str, tenant_id: Optional[str]) -> str:
        if tenant_id:
            return f"sse:replay:{tenant_id}:{user_id}:{chat_id}"
    ```
- SSE replay TTL semantics (seconds, from env)
  - Path: backend/app/services/sse_broadcast.py:270-281
  - Excerpt:
    ```py
    ttl = int(os.getenv("SSE_REPLAY_TTL", "3600"))
    return RedisReplayBackend(..., ttl_sec=ttl, ...)
    ```
- SSE replay record TTL applied on every write
  - Path: backend/app/services/sse_broadcast.py:195-199
  - Excerpt:
    ```py
    pipe.rpush(key, payload)
    pipe.ltrim(key, -self._max_buffer, -1)
    pipe.expire(key, self._ttl_sec)
    ```
- Conversation metadata keys are per owner_id (not tenant_id)
  - Path: backend/app/services/chat/conversations.py:56-62
  - Excerpt:
    ```py
    def _sorted_set_key(owner_id: str) -> str:
        return f"chat:conversations:{owner_id}"
    def _hash_key(owner_id: str, conversation_id: str) -> str:
        return f"chat:conversation:{owner_id}:{conversation_id}"
    ```

SECTION 2 — SSE REPLAY CONTRACT (event_id, reconnect, duplication)
2.1 Server contract
- SSE endpoint path + StreamingResponse
  - Path: backend/app/api/v1/endpoints/langgraph_v2.py:1129-1184
  - Excerpt:
    ```py
    @router.post("/chat/v2")
    async def langgraph_chat_v2_endpoint(...):
        last_event_id = raw_request.headers.get("Last-Event-ID")
        return StreamingResponse(_event_stream_v2(...), media_type="text/event-stream", headers=headers)
    ```
- event_id generation (per tenant/user/chat) and monotonicity
  - Path: backend/app/services/sse_broadcast.py:75-109
  - Excerpt:
    ```py
    key = (tenant_id, user_id, chat_id)
    seq = self._seq_counters.get(key, 0) + 1
    self._seq_counters[key] = seq
    ```
  - Path: backend/app/services/sse_broadcast.py:183-202
  - Excerpt:
    ```py
    # Redis: RPUSH + LLEN used as seq
    pipe.rpush(key, payload)
    ...
    seq = results[0]
    ```
  - Note: Redis replay uses list length as seq; comments warn seq is not stable after LTRIM.
    - Path: backend/app/services/sse_broadcast.py:228-244
    - Excerpt:
      ```py
      # CRITICAL: We should use a separate counter or store the stable seq in payload.
      # Current implementation uses 1-based index as seq ... Not stable!
      ```
- Last-Event-ID parsing
  - Path: backend/app/api/v1/endpoints/langgraph_v2.py:373-374
  - Excerpt:
    ```py
    def _parse_last_event_id(last_event_id: str | None, *, chat_id: str) -> int | None:
        return sse_broadcast.parse_last_event_id(chat_id, last_event_id)
    ```
  - Path: backend/app/services/sse_broadcast.py:305-318
  - Excerpt:
    ```py
    def parse_last_event_id(chat_id: str, last_event_id: str | None) -> Optional[int]:
        if raw.isdigit(): return int(raw)
        if ":" in raw: ...
    ```
- Replay logic on reconnect (buffer_miss => resync_required)
  - Path: backend/app/api/v1/endpoints/langgraph_v2.py:649-667
  - Excerpt:
    ```py
    last_seq = _parse_last_event_id(last_event_id, chat_id=req.chat_id)
    if last_seq is not None:
        replay, buffer_miss = await sse_broadcast.replay_after(...)
        if buffer_miss:
            await _emit_event("resync_required", {"reason": "buffer_miss"})
    ```

2.2 Client contract (frontend)
- SSE client stores last_event_id and passes Last-Event-ID
  - Path: frontend/src/lib/useChatSseV2.ts:445-480
  - Excerpt:
    ```ts
    let lastEventId = lastEventByRunRef.current.get(runKey) ?? null;
    ...
    sessionStorage.getItem(buildLastEventStorageKey(chatId, clientMsgId))
    ...
    headers: { Accept: 'text/event-stream', ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}) }
    ```
- SSE proxy forwards Last-Event-ID to backend
  - Path: frontend/src/app/api/chat/route.ts:105-119
  - Excerpt:
    ```ts
    const url = `${getBackendInternalBase()}/api/v1/langgraph/chat/v2`;
    const lastEventId = req.headers.get("last-event-id") ?? "";
    ...
    ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
    ```
- Reconnect FSM + event parsing
  - Path: frontend/src/lib/useChatSseV2.ts:523-640
  - Excerpt:
    ```ts
    const { event, data, id } = parseSseFrame(part);
    ...
    if (event === 'error') { ... setStatus('offline') ... }
    if (event === 'done') { ... setStatus('connected') ... }
    ```
- Auth expiry handling (401/403 -> onAuthExpired)
  - Path: frontend/src/lib/useChatSseV2.ts:493-507
  - Excerpt:
    ```ts
    if (res.status === 401 || res.status === 403) {
        setStatus('offline');
        onAuthExpired?.();
        return;
    }
    ```
- Potential mismatch note: backend event_id may be unstable in Redis replay (seq not stable after trim), while client assumes id monotonic per stream (see server-side note above).

SECTION 3 — PARAM SYNC (LWW) CONTRACT
3.1 Canonical state + naming
- Backend canonical parameter keys (TechnicalParameters)
  - Path: backend/app/langgraph_v2/state/sealai_state.py:139-230
  - Excerpt:
    ```py
    class TechnicalParameters(BaseModel):
        pressure_bar: Optional[float] = Field(default=None, alias="pressure")
        temperature_C: Optional[float] = None
        shaft_diameter: Optional[float] = None
        ...
    ```
- Frontend UI field mapping (sidebar)
  - Path: frontend/src/app/dashboard/components/Chat/ParameterFormSidebar.tsx:40-99
  - Excerpt:
    ```ts
    const FORM_SECTIONS: FormSection[] = [
      { name: "shaft_diameter", ... },
      { name: "pressure_bar", ... },
      { name: "temperature_C", ... },
      ...
    ];
    ```
- Frontend param alias mapping (pressure -> pressure_bar)
  - Path: frontend/src/lib/stores/paramStore.tsx:84-106
  - Excerpt:
    ```ts
    if (Object.prototype.hasOwnProperty.call(normalized, "pressure")) {
      normalized.pressure_bar = value;
      delete normalized.pressure;
    }
    ```
- Sidebar legacy mapping (form field names -> v2 keys)
  - Path: frontend/src/lib/v2ParameterPatch.ts:45-54
  - Excerpt:
    ```ts
    setNumber("pressure_bar", patch["druck_bar"]);
    setNumber("temperature_C", patch["temp_max_c"]);
    setNumber("shaft_diameter", patch["wellen_mm"]);
    ```

3.2 LWW enforcement
- LWW implemented in backend patch endpoint
  - Path: backend/app/langgraph_v2/utils/parameter_patch.py:304-361
  - Excerpt:
    ```py
    def apply_parameter_patch_lww(..., base_versions: Mapping[str, int] | None = None, ...):
        if base_versions is not None:
            base_v = int(base_versions.get(key, current_v))
            if base_v < current_v:
                rejected_fields.append({"field": key, "reason": "stale"})
        merged_versions[key] = current_v + 1
        merged_updated_at[key] = float(now_fn())
    ```
  - Path: backend/app/api/v1/endpoints/langgraph_v2.py:1380-1434
  - Excerpt:
    ```py
    ) = apply_parameter_patch_lww(..., base_versions=body.base_versions)
    ...
    await graph.aupdate_state(..., "parameter_versions": merged_versions, "parameter_updated_at": merged_updated_at)
    ```
- Client sends base_versions from local versions
  - Path: frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:770-781
  - Excerpt:
    ```ts
    const baseVersions: Record<string, number> = {};
    baseVersions[key] = typeof localVersion === "number" ? localVersion : 0;
    await patchV2Parameters({ chatId, token, parameters: cleaned, baseVersions });
    ```
- LWW bypass paths (non-versioned writes via provenance-only merge)
  - Path: backend/app/langgraph_v2/tools/parameter_tools.py:101-142
  - Excerpt:
    ```py
    merged_params, merged_provenance = apply_parameter_patch_with_provenance(...)
    return {"parameters": TechnicalParameters(**merged_params), "parameter_provenance": merged_provenance}
    ```
  - Path: backend/app/langgraph_v2/nodes/nodes_frontdoor.py:224-241
  - Excerpt:
    ```py
    merged_params, merged_provenance = apply_parameter_patch_with_provenance(...)
    return {"parameters": parameters, "parameter_provenance": merged_provenance}
    ```
  - Observation: these writes do not increment parameter_versions or parameter_updated_at, so client LWW is enforced only for patch endpoint, not for LLM/system parameter updates.

SECTION 4 — PROMPTS (Jinja2) SINGLE SOURCE OF TRUTH
- v2 prompt loader (StrictUndefined, PROMPTS_DIR)
  - Path: backend/app/langgraph_v2/utils/jinja.py:9-24
  - Excerpt:
    ```py
    PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
    return Environment(..., undefined=StrictUndefined, ...)
    ```
- v1/legacy prompt renderer (no StrictUndefined)
  - Path: backend/app/langgraph/utils/jinja_renderer.py:3-9
  - Excerpt:
    ```py
    from jinja2 import Template
    ...
    template = Template(f.read())
    ```
- Prompt directories (examples)
  - backend/app/prompts (v2)
    - Path: backend/app/prompts/confirm_gate.j2:1-9
    - Excerpt:
      ```jinja2
      {# System Prompt #}
      SUMMARY: {{ summary or 'Keine Zusammenfassung vorhanden' }}
      ```
  - backend/app/services/langgraph/prompts (legacy)
    - Path: backend/app/services/langgraph/prompts/ask_missing.jinja2:1-10
    - Excerpt:
      ```jinja2
      {# backend/app/services/langgraph/prompts/ask_missing.jinja2 #}
      ...
      ```
  - backend/app/services/langgraph/prompt_templates (legacy)
    - Path: backend/app/services/langgraph/prompt_templates/global_system.jinja2:1-10
    - Excerpt:
      ```jinja2
      {# SealAI – Globaler Systemprompt #}
      ...
      ```
  - backend/app/services/prompt_templates (extra)
    - Path: backend/app/services/prompt_templates/intent_router.jinja2:1-10
    - Excerpt:
      ```jinja2
      # Rolle
      Du agierst als Intent-Router...
      ```
  - backend/templates_backup (backup copy)
    - Path: backend/templates_backup/global_system.jinja2:1-10
    - Excerpt:
      ```jinja2
      {# SealAI – Globaler Systemprompt #}
      ...
      ```
  - backend/app/archive/langgraph_v1/prompts (archive)
    - Path: backend/app/archive/langgraph_v1/prompts/confirm_gate.de.j2:1-10
    - Excerpt:
      ```jinja2
      {% set title = "Confirm Gate" %}
      ...
      ```
- Duplicate/overlapping templates observed (e.g., global_system.jinja2 appears in services/langgraph/prompt_templates and templates_backup; ask_missing.jinja2 appears in services/langgraph/prompts and templates_backup).
- Minimal consolidation steps (no implementation yet):
  1) Treat `backend/app/prompts` as sole v2 source; keep StrictUndefined.
  2) Mark `backend/templates_backup` and `backend/app/archive/langgraph_v1/prompts` as read-only snapshots (exclude from runtime loaders).
  3) For legacy langgraph prompt usage, reduce to one directory (`backend/app/services/langgraph/prompts` or `.../prompt_templates`) and update loader to avoid duplicates.

SECTION 5 — LEGACY LANGGRAPH (v1) AND “WILDWUCHS”
- Legacy langgraph module is still imported by v2 state (shared IO types)
  - Path: backend/app/langgraph_v2/state/sealai_state.py:14-15
  - Excerpt:
    ```py
    from app.langgraph.io import AskMissingRequest, CoverageAnalysis, ParameterProfile
    ```
- Legacy langgraph prompts are still present under backend/app/services/langgraph/* (potentially importable via legacy loaders)
  - Path: backend/app/services/langgraph/prompts/ask_missing.jinja2:1-6
  - Excerpt:
    ```jinja2
    {# backend/app/services/langgraph/prompts/ask_missing.jinja2 #}
    ...
    ```
- Root-level helper scripts that should move to backend/scripts or tests/integration
  - Path: smoke_test.py:1-24
  - Excerpt:
    ```py
    from app.services.langgraph.graph_factory import get_graph
    from app.services.langgraph.runtime import ainvoke_langgraph
    ```
  - Path: test_stream.py:1-16
  - Excerpt:
    ```py
    url = "http://localhost:8000/api/v1/langgraph/chat/stream"
    ```
  - Path: test_langchain.py:1-18
  - Excerpt:
    ```py
    from langchain_openai import OpenAIEmbeddings
    ```
  - Path: test_llm.py:1-12
  - Excerpt:
    ```py
    llm = ChatOpenAI(..., streaming=True)
    ```

SECTION 6 — TESTS & PROOF SCRIPTS
- Pytest discovery configuration (only `tests/` by default)
  - Path: pytest.ini:1-4
  - Excerpt:
    ```ini
    [pytest]
    testpaths = tests
    addopts = -m "not e2e"  -q
    ```
- Test directories present (not all discovered by default)
  - Evidence: tree output above shows `backend/tests` and `backend/app/**/tests` but pytest.ini only points at `tests/`.
- Existing tenant isolation tests
  - DB chat transcript tenant scoping
    - Path: backend/app/services/chat/tests/test_persistence_tenant_scoping.py:7-45
    - Excerpt:
      ```py
      async def test_persist_chat_transcript_uses_tenant_id():
          ...
          added_obj = mock_session.add.call_args[0][0]
          assert added_obj.tenant_id == tenant_id
      ```
  - Redis tenant isolation
    - Path: backend/app/services/tests/test_redis_tenant_isolation.py:6-31
    - Excerpt:
      ```py
      async def test_sse_broadcast_keys_contain_tenant():
          tenant_id = "tenantA"
          chat_id = "chat123"
          key = manager._get_redis_key(chat_id, tenant_id)
          assert f"sse:events:{tenant_id}:{chat_id}" in key or f"sse:events:{tenant_id}/{chat_id}" in key
      ```
  - Qdrant tenant filter
    - Path: backend/app/services/rag/tests/test_qdrant_tenant_filter.py:74-95
    - Excerpt:
      ```py
      def test_rag_orchestrator_hybrid_retrieve_filter():
          ...
          filters = kwargs.get("metadata_filters")
      ```
  - Auth tenant enforcement
    - Path: backend/app/services/auth/tests/test_tenant_enforcement.py:25-61
    - Excerpt:
      ```py
      def test_canonical_tenant_id_fallback_disabled_explicit():
          ...\n        with pytest.raises(HTTPException) as exc:\n            canonical_tenant_id(user)
      ```
- SSE replay tests
  - Path: backend/tests/test_sse_replay_backend.py:8-22
  - Excerpt:
    ```py
    def test_build_replay_backend_defaults_to_memory(monkeypatch):
        ...\n    def test_build_replay_backend_redis_selected(monkeypatch):
        ...
    ```
  - Path: backend/app/services/tests/test_sse_broadcast_loop_safety.py:17-38
  - Excerpt:
    ```py
    def test_sse_manager_scoped_to_event_loop(monkeypatch) -> None:
        ...\n    assert manager_a is manager_a_second
    ```
- LWW param sync tests
  - Path: backend/tests/test_parameter_lww.py:4-21
  - Excerpt:
    ```py
    def test_parameter_patch_rejects_stale_base_version() -> None:
        ...\n    assert rejected == [{\"field\": \"pressure_bar\", \"reason\": \"stale\"}]
    ```
  - Path: backend/app/api/tests/test_langgraph_v2_param_sync_integration.py:42-60
  - Excerpt:
    ```py
    def test_param_patch_state_chat_config_alignment(monkeypatch):
        ...\n    assert state_response[\"parameters\"][\"medium\"] == \"oil\"
    ```
- Proposed minimal new tests (do not implement yet)
  1) backend/tests/test_chat_transcript_tenant_scope.py — ensure ChatTranscript queries include tenant_id and schema has tenant_id column.
  2) backend/tests/test_rag_endpoint_tenant_claim.py — ensure RAG endpoints use canonical_tenant_id (Keycloak claim) not user_id.
  3) backend/tests/test_sse_replay_sequence_stability.py — verify replay event_id monotonicity across trims (Redis backend).
  4) frontend/tests/useChatSseV2_last_event_id.test.ts — ensure Last-Event-ID persistence matches server replay contract.

SECTION 7 — FIX PLAN (PATCH ORDER) + VERIFICATION
Fix Plan (Patch-Order)
1) Tenant isolation end-to-end
   - Risk notes: schema migration for chat_transcripts/legacy tables; Redis keys may need namespace migration; ensure Keycloak tenant claim is present in prod.
2) SSE replay correctness
   - Risk notes: changing replay storage (e.g., Redis Stream/Sorted Set) may break existing clients; event_id semantics must remain backward compatible.
3) LWW contract enforcement
   - Risk notes: LWW versions on LLM updates could reject or reorder expected parameter changes; requires careful source tagging.
4) Prompts consolidation
   - Risk notes: loader path changes could break legacy imports; must maintain existing template names.
5) Legacy cleanup
   - Risk notes: shared types imported from app.langgraph.io are used by v2; removal requires migration of IO models.
6) Test structure
   - Risk notes: enabling backend/tests in pytest default could surface failing tests; may need marker strategy.

Verification Plan (exact commands)
1) Tenant isolation end-to-end
   - `pytest backend/tests/test_security.py -q`
   - `pytest backend/app/services/tests/test_redis_tenant_isolation.py -q`
   - `pytest backend/app/services/rag/tests/test_qdrant_tenant_filter.py -q`
   - `python -c "from app.services.auth.dependencies import canonical_tenant_id"`
2) SSE replay correctness
   - `pytest backend/tests/test_sse_replay_backend.py -q`
   - `pytest backend/app/services/tests/test_sse_broadcast_loop_safety.py -q`
   - `curl -N -H "Authorization: Bearer $TOKEN" -H "Last-Event-ID: 1" -H "Content-Type: application/json" \
      http://localhost:8000/api/v1/langgraph/chat/v2 -d '{"input":"hi","chat_id":"<uuid>"}'`
3) LWW contract
   - `pytest backend/tests/test_parameter_lww.py -q`
   - `pytest backend/app/api/tests/test_langgraph_v2_param_sync_integration.py -q`
4) Prompts consolidation
   - `pytest backend/tests/contract/test_prompt_render_contract.py -q`
5) Legacy cleanup
   - `rg -n "app\.langgraph" backend/app -g"*.py"`
6) Test structure
   - `pytest -q`
