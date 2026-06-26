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
    # Recent EXCHANGES kept verbatim in the L1 working window (older turns drop off; the structured
    # case-state is what survives — build-spec §7 "strukturierter Zustand überlebt Summarisierung").
    memory_window_turns: int = 6
    # Durable persistence (build-spec §3: Postgres = system-of-record). SET → memory layers 1-3 +
    # the L4 cross-session seam are backed by the durable SQLAlchemy adapters (survive a restart);
    # UNSET → the in-process store (offline eval/CI stay hermetic — no DB, no key). A pure config
    # swap behind the same Protocols (M3 lazy-adapter pattern); value is never logged.
    # Env: SEALAI_V2_DATABASE_URL (e.g. postgresql+psycopg2://…@postgres:5432/sealai_v2).
    database_url: str | None = None

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
    # Multilingual SOTA dense embedding via local FastEmbed (no API, nothing leaves the box; strong on
    # German). e5 needs the "query:"/"passage:" prefix convention — handled in the adapter/ingestor.
    # (bge-m3 is NOT available in fastembed 0.8.0 — verified; e5-large-multilingual is the SOTA pick.)
    embed_model: str = "intfloat/multilingual-e5-large"
    embed_cache_dir: str | None = (
        None  # FastEmbed model cache dir; None → library default
    )
