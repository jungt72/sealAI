from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import os

class Settings(BaseSettings):
    # Application / startup controls
    app_name: str = "sealAI-backend"
    app_version: str = Field(default_factory=lambda: os.getenv("GIT_SHA", "dev"))
    app_env: str = "development"
    frontend_origin: str = "https://sealai.net"
    enable_cors: bool = True
    warmup_on_start: bool = False
    job_worker_enabled: bool = False
    job_worker_poll_sec: float = 1.5
    dev_clear_langgraph_checkpoints_on_startup: bool = False
    langgraph_v2_redis_url: Optional[str] = None
    qdrant_bootstrap_on_startup: bool = False
    audit_log_bootstrap_on_startup: bool = False
    fastapi_docs_enabled: bool = False

    # Datenbank
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    postgres_db: str
    database_url: str
    POSTGRES_SYNC_URL: str
    debug_sql: bool = False
    postgres_dsn: Optional[str] = None

    # LLM & RAG (Auditierte Werte)
    openai_api_key: str
    openai_model: str = "gpt-4o"
    openai_temperature: float = 0.0
    embedding_model: str = "BAAI/bge-base-en-v1.5"

    # Qdrant - Festgelegt auf sealai_knowledge
    qdrant_url: str
    qdrant_api_key: Optional[str] = None
    qdrant_collection: str = "sealai_knowledge"
    qdrant_collection_ltm: Optional[str] = "sealai_ltm"
    rag_k: int = 4
    gotenberg_url: Optional[str] = None
    tika_url: Optional[str] = None
    paperless_url: Optional[str] = None
    paperless_token: Optional[str] = None
    paperless_webhook_token: Optional[str] = None

    # Weiteres (Redis, Auth, Memory etc.)
    redis_url: str
    REDIS_URL: str = "redis://redis:6379/0"
    ltm_enable: bool = False
    chat_history_ttl_days: int = 30
    chat_max_conversations_per_user: int = 50
    nextauth_url: str
    nextauth_secret: str
    keycloak_issuer: str
    keycloak_jwks_url: str
    keycloak_client_id: str
    keycloak_client_secret: str
    keycloak_expected_azp: str

    # LangSmith / OpenTelemetry tracing (auto-picked up by LangChain via os.environ)
    langchain_tracing_v2: bool = False
    langchain_api_key: Optional[str] = None
    langchain_endpoint: Optional[str] = None
    langchain_project: str = "sealai-phase-h"

    # Prometheus metrics
    prometheus_enabled: bool = True

    # Rate limiting (upload endpoint)
    rate_limit_upload: int = 20        # max requests per window
    rate_limit_window_s: int = 60      # window size in seconds

    # Phase F Feature-Flags — default on so productive chat uses the
    # user-facing Runtime / Governed path unless explicitly disabled.
    # Rollback remains env-only: set either flag to false.
    SEALAI_ENABLE_BINARY_GATE: bool = True
    SEALAI_ENABLE_CONVERSATION_RUNTIME: bool = True
    ENABLE_LEGACY_V2_ENDPOINT: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def backend_keycloak_issuer(self) -> str:
        return self.keycloak_issuer

    @property
    def normalized_app_env(self) -> str:
        return (self.app_env or "").strip().lower()

    @property
    def is_dev_or_test(self) -> bool:
        return self.normalized_app_env in {"dev", "development", "local", "test"}

    @property
    def QDRANT_COLLECTION_NAME(self) -> str:
        return self.qdrant_collection

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
