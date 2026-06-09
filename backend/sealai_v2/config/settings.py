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
    provider: str = "openai"
    openai_api_key: str | None = None  # falls back to OPENAI_API_KEY in llm.factory
    openai_base_url: str | None = None

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
