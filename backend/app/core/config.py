# backend/app/core/config.py
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import os
import sys
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


def _running_pytest() -> bool:
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules


def _ensure_pytest_env_defaults() -> None:
    if not _running_pytest():
        return
    database_url = os.getenv("DATABASE_URL") or os.getenv("database_url")
    if not database_url:
        user = os.getenv("POSTGRES_USER") or os.getenv("postgres_user") or "sealai"
        password = os.getenv("POSTGRES_PASSWORD") or os.getenv("postgres_password") or "sealai"
        host = os.getenv("POSTGRES_HOST") or os.getenv("postgres_host") or "localhost"
        port = os.getenv("POSTGRES_PORT") or os.getenv("postgres_port") or "5432"
        db = os.getenv("POSTGRES_DB") or os.getenv("postgres_db") or "sealai"
        database_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
        os.environ.setdefault("DATABASE_URL", database_url)
        os.environ.setdefault("database_url", database_url)
    os.environ.setdefault("POSTGRES_SYNC_URL", database_url)


_ensure_pytest_env_defaults()


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
    openai_model: str = "gpt-5-mini"

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
    chat_max_conversations_per_user: int = 50
    chat_history_ttl_days: int = 30

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
