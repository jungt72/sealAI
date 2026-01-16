import os


def _bootstrap_test_env() -> None:
    os.environ.setdefault("POSTGRES_USER", "sealai")
    os.environ.setdefault("POSTGRES_PASSWORD", "sealai")
    os.environ.setdefault("POSTGRES_HOST", "localhost")
    os.environ.setdefault("POSTGRES_PORT", "5432")
    os.environ.setdefault("POSTGRES_DB", "sealai")

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        database_url = (
            f"postgresql://{os.environ['POSTGRES_USER']}:"
            f"{os.environ['POSTGRES_PASSWORD']}@"
            f"{os.environ['POSTGRES_HOST']}:"
            f"{os.environ['POSTGRES_PORT']}/"
            f"{os.environ['POSTGRES_DB']}"
        )
        os.environ.setdefault("DATABASE_URL", database_url)
    os.environ.setdefault("POSTGRES_SYNC_URL", database_url)

    os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
    os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
    os.environ.setdefault("QDRANT_COLLECTION", "test_collection")

    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("NEXTAUTH_URL", "http://localhost:3000")
    os.environ.setdefault("NEXTAUTH_SECRET", "test-nextauth-secret")

    issuer = os.environ.setdefault("KEYCLOAK_ISSUER", "http://localhost:8080/realms/sealai")
    os.environ.setdefault(
        "KEYCLOAK_JWKS_URL",
        f"{issuer}/protocol/openid-connect/certs",
    )
    os.environ.setdefault("KEYCLOAK_CLIENT_ID", "sealai-test")
    os.environ.setdefault("KEYCLOAK_CLIENT_SECRET", "sealai-test-secret")
    os.environ.setdefault("KEYCLOAK_EXPECTED_AZP", "sealai-test")


_bootstrap_test_env()
