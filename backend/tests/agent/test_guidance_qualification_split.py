import os

for key, value in {
    "postgres_user": "test",
    "postgres_password": "test",
    "postgres_host": "localhost",
    "postgres_port": "5432",
    "postgres_db": "test",
    "database_url": "sqlite+aiosqlite:///tmp.db",
    "POSTGRES_SYNC_URL": "sqlite:///tmp.db",
    "openai_api_key": "test",
    "qdrant_url": "http://localhost",
    "redis_url": "redis://localhost:6379/0",
    "nextauth_url": "http://localhost",
    "nextauth_secret": "secret",
    "keycloak_issuer": "http://localhost",
    "keycloak_jwks_url": "http://localhost/jwks",
    "keycloak_client_id": "client",
    "keycloak_client_secret": "secret",
    "keycloak_expected_azp": "client",
}.items():
    os.environ.setdefault(key, value)

from app.agent.api.router import _build_conversation_response_payload


def test_guidance_payload_has_no_case_state_or_result_contract():
    decision = type(
        "Decision",
        (),
        {
            "result_form": "guided",
            "path": "structured",
            "stream_mode": "structured_progress_stream",
            "interaction_class": "GUIDANCE",
            "runtime_path": "STRUCTURED_GUIDANCE",
            "binding_level": "ORIENTATION",
            "has_case_state": True,
            "coverage_status": "partial",
            "boundary_flags": ("orientation_only",),
            "escalation_reason": None,
            "required_fields": (),
        },
    )()
    payload = _build_conversation_response_payload(
        decision,
        session_id="s1",
        reply="Orientierung.",
        state={"messages": [], "sealing_state": {}, "working_profile": {}},
    )
    assert payload["binding_level"] == "ORIENTATION"
    assert payload["result_form"] == "guided"
    assert payload["case_state"] is None
    assert payload["result_contract"] is None
    assert payload["qualified_action_gate"] is None
    assert payload["visible_case_narrative"] is not None
