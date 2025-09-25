# backend/app/core/config.py
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import structlog

# Strukturiertes Logging (JSON)
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

class Settings(BaseSettings):
    # Datenbank / SQLAlchemy
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    postgres_db: str
    database_url: str
    debug_sql: bool = False

    # Neu: Postgres-Sync-URL (basierend auf database_url oder explizit)
    POSTGRES_SYNC_URL: str

    # OpenAI / LLM / LangChain
    openai_api_key: str
    openai_model: str = "gpt-4.1-mini"

    # Embeddings
    embedding_model: str = "BAAI/bge-base-en-v1.5"

    # Qdrant (RAG & LTM)
    qdrant_url: str
    qdrant_collection: str
    qdrant_collection_ltm: Optional[str] = None
    qdrant_api_key: Optional[str] = None
    rag_k: int = 4
    qdrant_filter_metadata: Optional[dict] = None
    debug_qdrant: bool = False

    # Redis Memory & Sessions
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_url: str
    redis_db: int = 0
    redis_ttl: int = 60 * 60 * 24  # 24h

    # Explizite REDIS_URL (Fallback für andere Komponenten)
    REDIS_URL: str = "redis://redis:6379/0"

    # Auth / Keycloak / NextAuth
    nextauth_url: str
    nextauth_secret: str
    keycloak_issuer: str
    keycloak_jwks_url: str
    keycloak_client_id: str
    keycloak_client_secret: str
    keycloak_expected_azp: str

    # LangChain Tracing etc.
    langchain_tracing_v2: bool = True
    langchain_endpoint: Optional[str] = "https://api.smith.langchain.com"
    langchain_api_key: Optional[str] = None
    langchain_project: Optional[str] = "sealai"

    # Feature-Flags
    ltm_enable: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # Wichtig: nicht mehr aus ENV lesen.
    # Der Backend-Issuer entspricht immer dem Keycloak-Issuer.
    @property
    def backend_keycloak_issuer(self) -> str:
        return self.keycloak_issuer


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
