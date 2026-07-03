"""Model tiers + flags + run config (build-spec §3: Modellwahl ist Config, nicht hartkodieren).

Own pydantic-settings — never imports ``app.*``. Env prefix ``SEALAI_V2_`` (e.g.
``SEALAI_V2_L1_MODEL``). The OpenAI key falls back to the standard ``OPENAI_API_KEY``
when ``SEALAI_V2_OPENAI_API_KEY`` is unset (see ``llm.factory``).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SEALAI_V2_", extra="ignore")

    # --- provider / credentials ---
    provider: str = (
        "openai"  # global default provider; per-role *_provider override below
    )
    openai_api_key: str | None = None  # falls back to OPENAI_API_KEY in llm.factory
    openai_base_url: str | None = None
    # Mistral is OpenAI-API-compatible → it runs through the SAME OpenAiLlmClient adapter via
    # this base_url + key (llm.factory). Key falls back to MISTRAL_API_KEY when unset (mirrors
    # the openai_api_key → OPENAI_API_KEY fallback). VALUES are never read/logged by the agent.
    mistral_api_key: str | None = None
    mistral_base_url: str = "https://api.mistral.ai/v1"

    # --- per-role provider routing (model-swap eval): each None → falls back to ``provider``.
    # The MODEL strings live below; these pick which provider's client backs each role, so a
    # mixed cell (e.g. L1=mistral, L3=openai) is a pure config flip — no call-site change. ---
    l1_provider: str | None = None
    verifier_provider: str | None = None
    helper_provider: str | None = (
        None  # backs BOTH understand + distill (one helper knob)
    )
    judge_provider: str | None = (
        None  # eval-only; the matrix holds the judge fixed at baseline
    )

    # --- auth (M6c, P0): PUBLIC config, not secrets. Identity is derived ONLY from a token VERIFIED
    # against these (validate-in-V2). Empty jwks_url → auth not configured (routes 503 fail-closed). ---
    auth_jwks_url: str | None = None
    auth_issuer: str | None = None
    auth_audience: str | None = None
    auth_tenant_claim: str = "tenant_id"

    # --- model tiers (build-spec §3): strong frontier for L1; cheaper for judge/helper ---
    l1_model: str = "gpt-5.1"  # decision #1: OpenAI's strongest GPT; resolved against models.list() at runtime
    judge_model: str = (
        "gpt-4.1-mini"  # decision #1: cheaper tier (rubric-adherence is constrained)
    )
    helper_model: str = (
        "gpt-4.1-mini"  # soft `understand` intent — cheap, annotate-only
    )
    # L3 verifier (M2): strong-frontier, same as L1 for the FIRST measured L3 (owner decision #1);
    # model is config so a cross-vendor swap is a thin adapter + a config flip, no core change.
    verifier_model: str = "gpt-5.1"
    l1_temperature: float | None = None  # None → omit (max model-family compatibility)
    judge_temperature: float | None = 0.0
    helper_temperature: float | None = 0.0
    verifier_temperature: float | None = (
        None  # None → omit (model-family compatibility)
    )

    # --- flag defaults (production baseline = default-on; harness overrides per column) ---
    default_compliance_hint: bool = True
    default_safety_critical: bool = True

    # --- run knobs ---
    concurrency: int = 6
    request_timeout_s: float = 180.0
    max_retries: int = 3
    understand_enabled: bool = True
    # L3 is an always-on CORE trust layer (Prinzipien §2), NOT a feature flag. This toggle is an
    # incident-only kill-switch (default = enforced); set False only to restore service.
    verify_enabled: bool = True
    # L2 grounding (M3): retrieve reviewed Fachkarten into L1/L3. Default ON (core trust layer);
    # off → every answer is "vorläufig". Not a product feature flag — an incident kill-switch.
    ground_enabled: bool = True
    # M4 deterministic calc layer: evaluate the reviewed calc registry and inject computed values
    # into L1/L3. Default ON; off → no "Berechnete Werte" block. Incident kill-switch, not a flag.
    compute_enabled: bool = True
    # M5 memory: working window + structured case-state + history (in-process now; Redis/Postgres/
    # Qdrant adapters deferred). Default ON; off → no recall/record (incident kill-switch). Inert
    # without a per-turn session, so the single-turn eval stays a byte-identical no-op regardless.
    memory_enabled: bool = True
    # Light LLM distillation of STATED facts into the case-state (the re-ask keystone). Off → window
    # + history only, no distill LLM call / no fact extraction. Sub-toggle under memory_enabled.
    distill_enabled: bool = True
    # Medium Intelligence (Phase 2): helper-LLM research of the stated medium → the MEDIUM tab. OFF by
    # default — L1-NEUTRAL (never enters the prompt), so enabling adds only the tab + one helper call
    # per medium (cached); flip via SEALAI_V2_MEDIUM_INTEL_ENABLED when the owner wants it live.
    medium_intel_enabled: bool = False
    # sealingAI Memory Architecture V1.0 (Patch 8): assembles a bounded MemoryContextBundle (max 8
    # items, max 750 tokens, max 10% of prompt budget) from retrieved+revalidated+policy-gated
    # curated memory items. OFF by default — L1-NEUTRAL when off, same as Medium Intelligence (the
    # service is never constructed, PipelineResult.memory_context stays None). NOTE: even when ON,
    # this flag only computes + exposes the bundle (context_sources on the chat response) — it does
    # NOT yet inject memory into the L1 prompt text; that's a deliberately separate, later step
    # needing its own eval-verification pass. Flip via SEALAI_V2_MEMORY_CONTEXT_ENABLED.
    memory_context_enabled: bool = False
    # Patch 10 (Purge & Compliance): grace period between a memory item's soft-delete
    # (DELETED_PENDING_PURGE) and it becoming eligible for the periodic reap job's hard delete —
    # gives the "Aus Memory entfernen" Right Rail action (Patch 11, not yet built) an undo window
    # instead of an instant, irreversible purge. Applies regardless of memory_context_enabled — a
    # deleted item's grace period isn't gated by whether retrieval is currently active.
    memory_purge_grace_days: int = 30
    # Kandidaten-Spezifikation (Produktspec v3.1): deterministic candidate Bauform/Werkstoff/DIN as a
    # render surface. OFF by default — wired but inert until the owner lifts the governance NO-GO (expert
    # Fachfreigabe + DIN-Lizenz). L1-NEUTRAL (never enters the prompt); flip via SEALAI_V2_PRODUKTSPEC_ENABLED.
    produktspec_enabled: bool = False
    # V2.2 INC-COVERAGE-GATE (§4): deterministic case-level coverage_status before L1. OFF by default —
    # while OFF the gate is computed-but-not-coupled (golden byte-identical). Coupling the status to the
    # allowed L1 mode (§5) goes productive only when the extended ruler is green (I-CAL-1); flip via
    # SEALAI_V2_COVERAGE_GATE_ENABLED after an adjudicated eval-REPLAY.
    coverage_gate_enabled: bool = False
    # INC-NARRATOR-CONTRACT Phase 1: when ON, the kernel assembles the deterministic answer-contract
    # (status + allowed_claims + required/forbidden + allowed materials/values) and attaches it to the
    # result. INERT — the L1 prompt is NOT changed (byte-identical); the renderer that consumes the
    # contract is the next, also-gated phase. Flip via SEALAI_V2_RESPONSE_CONTRACT_ENABLED.
    response_contract_enabled: bool = False
    # P0-B (owner Leitbild-Audit 2026-07-02): widens the output_guard (forbidden phrase / invented
    # number / invented material) to turns WITHOUT a gegencheck_verdict — requires
    # response_contract_enabled=True. Never touches the L1 prompt/Renderer-Modus (guard-only contract,
    # see pipeline.py + response_contract.build_guard_contract docstrings for why that separation
    # matters — forcing Renderer-Modus onto a knowledge question would gut its teaching depth). OFF by
    # default → byte-identical (no guard_contract is built at all); flip via
    # SEALAI_V2_RESPONSE_CONTRACT_GENERAL_GUARD_ENABLED after a targeted eval on knowledge-turn
    # overblock rate (same measured-before-activation discipline as every other flag here).
    response_contract_general_guard_enabled: bool = False
    # INC-BASELINE-HARDENING (V2.2): two Free-Narrator baseline fixes the narrator-contract-replay
    # surfaced (NOT touched by the narrator contract — these are non-Gegencheck turns): (1) derive the
    # RWDR shaft Ø (Welle = d1) from a bare designation so the Umfangsgeschwindigkeit kern fires, plus
    # name the speed-trap as a qualitative Pflichtbefund; (2) forbid a material-FAMILY lock-in from an
    # UNCLEAR medium class (ask the class first). OFF by default → byte-identical (no extra binding, no
    # extra prompt block); flip via SEALAI_V2_BASELINE_HARDENING_ENABLED after an adjudicated eval-REPLAY.
    baseline_hardening_enabled: bool = False
    # Material-Parameter-Tabelle: render grounded material parameters (operating limits, Shore, …)
    # as a table for material-info / comparison turns. Numbers live in the kernel store (no L1
    # invention); OFF -> byte-identical. Flip via SEALAI_V2_MATERIAL_PARAM_TABLE_ENABLED.
    material_param_table_enabled: bool = False
    # Recent EXCHANGES kept verbatim in the L1 working window (older turns drop off; the structured
    # case-state is what survives — build-spec §7 "strukturierter Zustand überlebt Summarisierung").
    memory_window_turns: int = 6
    # Durable persistence (build-spec §3: Postgres = system-of-record). SET → memory layers 1-3 +
    # the L4 cross-session seam are backed by the durable SQLAlchemy adapters (survive a restart);
    # UNSET → the in-process store (offline eval/CI stay hermetic — no DB, no key). A pure config
    # swap behind the same Protocols (M3 lazy-adapter pattern); value is never logged.
    # Env: SEALAI_V2_DATABASE_URL (e.g. postgresql+psycopg2://…@postgres:5432/sealai_v2).
    database_url: str | None = None
    # Keycloak realm role that gates the owner/admin surface (Hersteller-Partner CRUD + lead retrieval).
    # Env: SEALAI_V2_AUTH_ADMIN_ROLE. Additive gate — tenant isolation is untouched.
    auth_admin_role: str = "admin"
    # Keycloak realm role for the manufacturer SELF-SERVICE surface (manage own partner record + leads).
    # Env: SEALAI_V2_AUTH_MANUFACTURER_ROLE.
    auth_manufacturer_role: str = "manufacturer"

    # --- L2 retrieval backend (Phase-1 Qdrant production adapter, behind the Retriever Protocol) ---
    # Two impls of the SAME Protocol: the in-process keyword matcher (CI/eval MEASUREMENT instrument —
    # deterministic, hermetic, no network) and the QdrantFachkartenRetriever (semantic, production).
    # This flips between them as pure config. Default "in_process" keeps offline eval/CI byte-stable;
    # "qdrant" requires ``qdrant_url`` set, else the factory fails safe back to in-process.
    retriever_backend: str = "in_process"  # "in_process" | "qdrant"
    qdrant_url: str | None = (
        None  # e.g. http://qdrant:6333; UNSET → in-process forced (fail-safe)
    )
    qdrant_collection: str = (
        "sealai_v2_fachkarten"  # OWN collection, separate from the V1 stack
    )
    qdrant_api_key: str | None = None  # value never logged
    # Embedding model: the PROD path is the OpenAI API ("text-embedding-3-small", 1536-dim) — strong on
    # German, reuses OPENAI_API_KEY, and crucially NO local model so NO RAM/OOM (the local e5-large model
    # OOM'd the 7.6 GB host). DATA leaves the box for the embedding call (it IS an API) — this is NOT a
    # no-egress path. The fastembed/e5-large option below is the OPTIONAL OFFLINE alternative (set
    # embed_provider="fastembed" + embed_model="intfloat/multilingual-e5-large" + the e5 prefixes).
    embed_model: str = "text-embedding-3-small"
    embed_cache_dir: str | None = (
        None  # FastEmbed model cache dir (offline path only); None → library default
    )
    # Embedding provider: "openai" (API text-embedding-3 — the RAM-safe PROD default) | "fastembed"
    # (local ONNX e5-large — offline, but OOM'd this host). Defaulting to openai makes _make_embedder
    # raise without OPENAI_API_KEY; on serve _build_retriever fail-safes to the in-process keyword
    # retriever, and the ingestion CLI requires the key explicitly.
    embed_provider: str = "openai"
    # e5 needs the "query:"/"passage:" asymmetry; openai/jina/MiniLM use "" (raw text). Empty by default
    # (the openai prod path); set the e5 prefixes only when switching to the fastembed offline option.
    embed_query_prefix: str = ""
    embed_passage_prefix: str = ""

    # --- Hybrid retrieval (dense + sparse BM25, RRF-fused, optional cross-encoder rerank) ---
    # 2026-07-03 owner directive: retrieval/ranking must stay deterministic — the LLM only formulates
    # the answer (Leitsatz L1). Dense-only embeddings blur exact German technical terms (DIN numbers,
    # compound nouns); adding a lexical (BM25) signal + fusing it with dense via Qdrant's native RRF is
    # itself deterministic (no model in the fusion step). The optional rerank stage is a discriminative
    # cross-encoder (scores relevance), NOT a generative LLM — consistent with the same doctrine.
    # Default OFF: flipping it on needs a Qdrant collection migration (a NEW "sparse" named vector must
    # be declared at collection-creation time, so existing points need re-ingestion) — an explicit,
    # owner-authorized ops step, not something that can be silently backfilled onto the live collection.
    qdrant_hybrid_enabled: bool = False
    # fastembed's bundled sparse model; ships German stopwords (verified: "german.txt" in its asset
    # list) — this is real BM25 term-frequency scoring, not a neural re-embedding of the dense model.
    qdrant_sparse_model: str = "Qdrant/bm25"
    # How many RRF-fused candidates to pull before the reviewed-backfill / rerank stages run. Mirrors
    # the existing dense-only candidate widening (_REVIEWED_BACKFILL_MAX_CANDIDATES) so behavior stays
    # comparable when toggling the flag.
    qdrant_hybrid_candidate_limit: int = 128
    # Independent of qdrant_hybrid_enabled (rerank works fine on dense-only candidates too), but only
    # meaningful together in practice. jina-reranker-v2-base-multilingual: German-capable cross-encoder,
    # already bundled in fastembed — confirmed via TextCrossEncoder.list_supported_models().
    qdrant_rerank_enabled: bool = False
    qdrant_rerank_model: str = "jinaai/jina-reranker-v2-base-multilingual"
    # How many top-ranked (post-fusion) candidates get sent through the cross-encoder. Small on purpose
    # — reranking is the expensive step (a full forward pass per candidate), only needs to resolve
    # ordering among the plausible top slice, not the whole candidate pool.
    qdrant_rerank_candidates: int = 20
