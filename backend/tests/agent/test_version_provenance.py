import hashlib
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

from app.agent.agent.graph import _VISIBLE_REPLY_SYSTEM_PROMPT, VISIBLE_REPLY_PROMPT_HASH
from app.agent.agent.prompts import REASONING_PROMPT_HASH, REASONING_PROMPT_VERSION, SYSTEM_PROMPT_TEMPLATE
from app.agent.api.router import _build_fast_path_version_provenance, _build_structured_version_provenance
from app.agent.case_state import (
    CASE_STATE_BUILDER_VERSION,
    DETERMINISTIC_DATA_VERSION,
    DETERMINISTIC_SERVICE_VERSION,
    PROJECTION_VERSION,
    build_case_state,
)
from app.agent.runtime import INTERACTION_POLICY_VERSION, evaluate_interaction_policy


def test_reasoning_prompt_hash_is_deterministic():
    assert REASONING_PROMPT_HASH == hashlib.sha256(SYSTEM_PROMPT_TEMPLATE.encode()).hexdigest()[:12]


def test_visible_reply_prompt_hash_is_deterministic():
    assert VISIBLE_REPLY_PROMPT_HASH == hashlib.sha256(_VISIBLE_REPLY_SYSTEM_PROMPT.encode()).hexdigest()[:12]


def test_policy_decision_carries_policy_version():
    assert evaluate_interaction_policy("Was ist PTFE?").policy_version == INTERACTION_POLICY_VERSION


def test_version_constants_are_strings():
    assert REASONING_PROMPT_VERSION
    assert CASE_STATE_BUILDER_VERSION
    assert PROJECTION_VERSION
    assert DETERMINISTIC_SERVICE_VERSION
    assert DETERMINISTIC_DATA_VERSION


def test_build_case_state_with_provenance_populates_case_meta():
    state = {"messages": [], "sealing_state": {"cycle": {"state_revision": 1, "analysis_cycle_id": "cycle-1"}}, "working_profile": {}, "relevant_fact_cards": []}
    cs = build_case_state(
        state,
        session_id="s1",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
        version_provenance={"model_id": "gpt-4o-mini", "policy_version": INTERACTION_POLICY_VERSION, "projection_version": PROJECTION_VERSION, "case_state_builder_version": CASE_STATE_BUILDER_VERSION, "service_version": DETERMINISTIC_SERVICE_VERSION, "data_version": DETERMINISTIC_DATA_VERSION},
    )
    assert cs["case_meta"]["version_provenance"]["model_version"] == "gpt-4o-mini"
    assert cs["audit_trail"][0]["details"]["version_provenance"]["policy_version"] == INTERACTION_POLICY_VERSION


def test_structured_provenance_has_required_fields():
    decision = evaluate_interaction_policy("empfehle ein Material")
    vp = _build_structured_version_provenance(decision=decision)
    assert vp["model_id"] == "gpt-4o-mini"
    assert vp["data_version"] == DETERMINISTIC_DATA_VERSION
    assert vp["service_version"] == DETERMINISTIC_SERVICE_VERSION


def test_fast_path_provenance_has_no_data_version():
    decision = evaluate_interaction_policy("Was ist PTFE?")
    vp = _build_fast_path_version_provenance(decision=decision)
    assert vp["model_id"] is None
    assert "data_version" not in vp
