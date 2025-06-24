# backend/app/core/config.py

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    # Datenbank / SQLAlchemy
    database_url: str
    debug_sql: bool = False

    # OpenAI / LLM / LangChain
    openai_api_key: str
    openai_model: str = "gpt-4.1-mini"

    # Embeddings
    embedding_model: str = "BAAI/bge-base-en-v1.5"

    # Qdrant RAG
    qdrant_url: str
    qdrant_api_key: Optional[str] = None
    qdrant_collection: str
    rag_k: int = 4
    debug_qdrant: bool = False

    # Redis Memory & Sessions
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_ttl: int = 60 * 60 * 24  # 24h

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # Auth / Keycloak / NextAuth
    nextauth_url: str
    nextauth_secret: str
    keycloak_issuer: str
    keycloak_jwks_url: str
    keycloak_client_id: str
    keycloak_expected_azp: str

    # LangChain Tracing etc.
    langchain_tracing_v2: bool = False
    langchain_endpoint: Optional[str] = None
    langchain_api_key: Optional[str] = None
    langchain_project: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
