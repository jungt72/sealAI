# backend/app/core/config.py
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import structlog

# Initialisierung von structlog für strukturiertes Logging
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

    # Qdrant RAG
    qdrant_url: str
    qdrant_collection: str
    rag_k: int = 4
    qdrant_filter_metadata: Optional[dict] = None  # Neu: Optionale Filter für Metadata
    debug_qdrant: bool = False

    # Redis Memory & Sessions
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_url: str
    redis_db: int = 0
    redis_ttl: int = 60 * 60 * 24  # 24h

    # Neu: Redis-URL (bereits vorhanden, aber explizit für Konsistenz)
    REDIS_URL: str = "redis://redis:6379/0"  # Default-Wert hartcodiert, um NameError zu vermeiden

    # Auth / Keycloak / NextAuth
    nextauth_url: str
    nextauth_secret: str
    keycloak_issuer: str
    keycloak_jwks_url: str
    keycloak_client_id: str
    keycloak_client_secret: str
    keycloak_expected_azp: str
    backend_keycloak_issuer: str

    # LangChain Tracing etc.
    langchain_tracing_v2: bool = True  # Neu: Standardmäßig aktiviert
    langchain_endpoint: Optional[str] = "https://api.smith.langchain.com"
    langchain_api_key: Optional[str] = None
    langchain_project: Optional[str] = "sealai"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
