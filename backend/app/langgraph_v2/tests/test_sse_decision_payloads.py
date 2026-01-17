import os

os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_COLLECTION", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEXTAUTH_URL", "http://localhost:3000")
os.environ.setdefault("NEXTAUTH_SECRET", "test")
os.environ.setdefault("KEYCLOAK_ISSUER", "http://localhost:8080/realms/test")
os.environ.setdefault("KEYCLOAK_JWKS_URL", "http://localhost:8080/realms/test/protocol/openid-connect/certs")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "test")
os.environ.setdefault("KEYCLOAK_CLIENT_SECRET", "test")
os.environ.setdefault("KEYCLOAK_EXPECTED_AZP", "test")

from app.api.v1.endpoints import langgraph_v2 as lg


def test_build_supervisor_decision_payload():
    payload = lg._build_supervisor_decision_payload(
        {"next_action": "RUN_PANEL_NORMS_RAG", "next_action_reason": "needs_rag"},
        chat_id="chat-1",
        request_id="req-1",
    )
    assert payload == {
        "action": "RUN_PANEL_NORMS_RAG",
        "reason": "needs_rag",
        "chat_id": "chat-1",
        "request_id": "req-1",
    }


def test_knowledge_target_from_state():
    assert lg._knowledge_target_from_state({"last_node": "knowledge_material_node"}) == "material"
    assert lg._knowledge_target_from_state({"last_node": "knowledge_lifetime_node"}) == "lifetime"
    assert lg._knowledge_target_from_state({"last_node": "generic_sealing_qa_node"}) == "generic"
    assert lg._knowledge_target_from_state({"last_node": "other"}) is None
