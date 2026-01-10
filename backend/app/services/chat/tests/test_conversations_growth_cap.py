import importlib
from unittest.mock import MagicMock


def test_upsert_trims_conversation_zset(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_USER", "sealai")
    monkeypatch.setenv("POSTGRES_PASSWORD", "sealai")
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "sealai")
    monkeypatch.setenv("DATABASE_URL", "postgresql://sealai:sealai@localhost:5432/sealai")
    monkeypatch.setenv("POSTGRES_SYNC_URL", "postgresql://sealai:sealai@localhost:5432/sealai")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("QDRANT_COLLECTION", "test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("NEXTAUTH_URL", "http://localhost")
    monkeypatch.setenv("NEXTAUTH_SECRET", "secret")
    monkeypatch.setenv("KEYCLOAK_ISSUER", "http://localhost")
    monkeypatch.setenv("KEYCLOAK_JWKS_URL", "http://localhost/jwks")
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "client")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "secret")
    monkeypatch.setenv("KEYCLOAK_EXPECTED_AZP", "client")

    conversations = importlib.import_module("app.services.chat.conversations")
    conversations.settings.chat_max_conversations_per_user = 2

    redis_client = MagicMock()
    pipeline = MagicMock()
    redis_client.pipeline.return_value = pipeline
    redis_client.hgetall.return_value = {}
    monkeypatch.setattr(conversations, "_redis_client", lambda: redis_client)

    conversations.upsert_conversation(
        owner_id="user-1",
        conversation_id="chat-1",
        first_user_message="hi",
    )

    key_set = "chat:conversations:user-1"
    redis_client.zremrangebyrank.assert_called_once_with(key_set, 0, -3)
