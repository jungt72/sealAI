from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import os
import sys
import structlog

class Settings(BaseSettings):
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

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
