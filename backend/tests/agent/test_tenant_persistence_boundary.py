import asyncio
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

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

from app.services.history.persist import (
    CANONICAL_STATE_AUTHORITY,
    STRUCTURED_CASE_RECORD_TYPE,
    _build_legacy_storage_key,
    _build_structured_case_payload,
    build_structured_case_storage_key,
    delete_structured_case,
    load_structured_case,
)


def _state(tenant_id="tenant-a"):
    return {"messages": [], "sealing_state": {"cycle": {}}, "working_profile": {}, "relevant_fact_cards": [], "tenant_id": tenant_id}


def _meta(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"):
    return {
        "record_type": STRUCTURED_CASE_RECORD_TYPE,
        "case_id": case_id,
        "session_id": case_id,
        "owner_id": owner_id,
        "runtime_path": "STRUCTURED_QUALIFICATION",
        "binding_level": "ORIENTATION",
        "sealing_state": {"cycle": {}},
        "case_state": None,
        "persisted_lifecycle": None,
        "persisted_concurrency_token": None,
        "working_profile": {},
        "relevant_fact_cards": [],
        "messages": [],
        "tenant_id": tenant_id,
    }


def test_storage_key_is_tenant_scoped():
    assert build_structured_case_storage_key("tenant-a", "user-1", "case-1") == "agent_case:tenant-a:user-1:case-1"
    assert _build_legacy_storage_key("user-1", "case-1") == "agent_case:user-1:case-1"


def test_build_payload_carries_explicit_tenant_id():
    payload = _build_structured_case_payload(tenant_id="caller-tenant", owner_id="user-1", case_id="case-1", state=_state("state-tenant"), runtime_path="STRUCTURED_QUALIFICATION", binding_level="ORIENTATION")
    assert payload.tenant_id == "caller-tenant"


def test_build_payload_marks_case_state_as_canonical_authority():
    payload = _build_structured_case_payload(
        tenant_id="caller-tenant",
        owner_id="user-1",
        case_id="case-1",
        state=_state("state-tenant"),
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
    )
    assert payload.canonical_state_authority == CANONICAL_STATE_AUTHORITY


def test_build_payload_hardens_canonical_case_state_buckets():
    payload = _build_structured_case_payload(
        tenant_id="caller-tenant",
        owner_id="user-1",
        case_id="case-1",
        state=_state("state-tenant"),
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
    )

    assert payload.case_state is not None
    assert payload.case_state["observed_inputs"]["records"] == []
    assert payload.case_state["normalized_parameters"] == {}
    assert payload.case_state["parameter_meta"] == {}
    assert payload.case_state["derived_engineering_values"] == {}
    assert payload.case_state["evidence_state"]["evidence_ref_count"] == 0
    assert payload.case_state["governance_state"]["release_status"] == "inadmissible"
    assert payload.case_state["matching_state"]["selection_status"] == "not_started"
    assert payload.case_state["rfq_state"]["rfq_admissibility"] == "inadmissible"


def test_build_payload_persists_case_lifecycle_snapshot_case_state_first():
    payload = _build_structured_case_payload(
        tenant_id="tenant-a",
        owner_id="user-1",
        case_id="case-1",
        state={
            "messages": [],
            "sealing_state": {
                "cycle": {"phase": "legacy_phase"},
                "governance": {"release_status": "inadmissible"},
                "selection": {"selected_partner_id": "legacy-partner"},
                "handover": {
                    "is_handover_ready": False,
                    "handover_status": "not_ready",
                    "rfq_confirmed": False,
                    "handover_completed": False,
                    "rfq_html_report": None,
                },
            },
            "case_state": {
                "case_meta": {"phase": "case_state_phase"},
                "governance_state": {
                    "release_status": "rfq_ready",
                    "review_state": "approved",
                    "review_required": False,
                },
                "recipient_selection": {"selected_partner_id": "case-state-partner"},
                "rfq_state": {
                    "rfq_admissibility": "ready",
                    "status": "ready",
                    "handover_ready": True,
                    "handover_status": "releasable",
                    "rfq_confirmed": True,
                    "rfq_handover_initiated": True,
                    "rfq_html_report_present": True,
                },
            },
            "working_profile": {},
            "relevant_fact_cards": [],
        },
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
    )

    assert payload.persisted_lifecycle == {
        "phase": "case_state_phase",
        "release_status": "rfq_ready",
        "review_state": "approved",
        "review_required": False,
        "selected_partner_id": "case-state-partner",
        "rfq_admissibility": "ready",
        "rfq_status": "ready",
        "handover_ready": True,
        "handover_status": "releasable",
        "rfq_confirmed": True,
        "rfq_handover_initiated": True,
        "rfq_html_report_present": True,
    }


def test_build_payload_persists_dual_backed_concurrency_token_bridge():
    payload = _build_structured_case_payload(
        tenant_id="tenant-a",
        owner_id="user-1",
        case_id="case-1",
        state={
            "messages": [],
            "sealing_state": {
                "cycle": {
                    "analysis_cycle_id": "cycle-bridge",
                    "state_revision": 8,
                    "snapshot_parent_revision": 7,
                }
            },
            "working_profile": {},
            "relevant_fact_cards": [],
        },
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
    )

    assert payload.case_state is not None
    assert payload.case_state["case_meta"]["analysis_cycle_id"] == "cycle-bridge"
    assert payload.case_state["case_meta"]["state_revision"] == 8
    assert payload.case_state["case_meta"]["snapshot_parent_revision"] == 7
    assert payload.persisted_concurrency_token == {
        "state_revision": 8,
        "snapshot_parent_revision": 7,
        "analysis_cycle_id": "cycle-bridge",
    }


def test_build_payload_uses_case_state_case_meta_as_primary_concurrency_source():
    payload = _build_structured_case_payload(
        tenant_id="tenant-a",
        owner_id="user-1",
        case_id="case-1",
        state={
            "messages": [],
            "sealing_state": {
                "cycle": {
                    "analysis_cycle_id": "legacy-cycle",
                    "state_revision": 3,
                    "snapshot_parent_revision": 2,
                }
            },
            "case_state": {
                "case_meta": {
                    "analysis_cycle_id": "case-cycle",
                    "state_revision": 9,
                    "snapshot_parent_revision": 8,
                    "version": 9,
                }
            },
            "working_profile": {},
            "relevant_fact_cards": [],
        },
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
    )

    assert payload.persisted_concurrency_token == {
        "state_revision": 9,
        "snapshot_parent_revision": 8,
        "analysis_cycle_id": "case-cycle",
    }


def test_load_structured_case_fails_closed_on_tenantless_legacy_record():
    transcript = MagicMock()
    transcript.user_id = "user-1"
    transcript.metadata_json = _meta(None)
    session = AsyncMock()
    session.get = AsyncMock(side_effect=[None, transcript])
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=type("ChatTranscript", (), {}))
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        result = asyncio.run(load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))
    assert result is None


def test_delete_structured_case_uses_tenant_scoped_key_first():
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_chat_transcript = type("ChatTranscript", (), {})
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=fake_chat_transcript)
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        asyncio.run(delete_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))
    assert session.get.await_args_list[0].args == (fake_chat_transcript, "agent_case:tenant-a:user-1:case-1")


def test_load_structured_case_preserves_canonical_derived_engineering_values():
    metadata = _meta("tenant-a")
    metadata["case_state"] = {
        "derived_engineering_values": {
            "rwdr_tool_runs": [
                {
                    "inputs": {"shaft_diameter_mm": 50.0, "rpm": 1500.0},
                    "result": {"status": "ok", "v_surface_m_s": 3.9},
                }
            ]
        }
    }
    transcript = MagicMock()
    transcript.user_id = "user-1"
    transcript.metadata_json = metadata
    session = AsyncMock()
    session.get = AsyncMock(return_value=transcript)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=type("ChatTranscript", (), {}))
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        result = asyncio.run(load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))

    assert result is not None
    assert result["case_state"]["derived_engineering_values"]["rwdr_tool_runs"][0]["result"]["v_surface_m_s"] == 3.9


def test_load_structured_case_applies_persisted_lifecycle_fallbacks():
    metadata = _meta("tenant-a")
    metadata["persisted_lifecycle"] = {
        "phase": "persisted_phase",
        "release_status": "rfq_ready",
        "review_state": "approved",
        "review_required": False,
        "selected_partner_id": "persisted-partner",
        "rfq_admissibility": "ready",
        "rfq_status": "ready",
        "handover_ready": True,
        "handover_status": "releasable",
        "rfq_confirmed": True,
        "rfq_handover_initiated": True,
        "rfq_html_report_present": True,
    }
    transcript = MagicMock()
    transcript.user_id = "user-1"
    transcript.metadata_json = metadata
    session = AsyncMock()
    session.get = AsyncMock(return_value=transcript)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=type("ChatTranscript", (), {}))
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        result = asyncio.run(load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))

    assert result is not None
    assert result["case_state"]["case_meta"]["phase"] == "persisted_phase"
    assert result["case_state"]["governance_state"]["release_status"] == "rfq_ready"
    assert result["case_state"]["governance_state"]["review_state"] == "approved"
    assert result["case_state"]["governance_state"]["review_required"] is False
    assert result["case_state"]["recipient_selection"]["selected_partner_id"] == "persisted-partner"
    assert result["case_state"]["rfq_state"]["rfq_admissibility"] == "ready"
    assert result["case_state"]["rfq_state"]["status"] == "ready"
    assert result["case_state"]["rfq_state"]["handover_ready"] is True
    assert result["case_state"]["rfq_state"]["handover_status"] == "releasable"
    assert result["case_state"]["rfq_state"]["rfq_confirmed"] is True
    assert result["case_state"]["rfq_state"]["rfq_handover_initiated"] is True
    assert result["case_state"]["rfq_state"]["rfq_html_report_present"] is True


def test_load_structured_case_prefers_persisted_case_state_for_outward_lifecycle_when_sealing_state_lacks_fields():
    metadata = _meta("tenant-a")
    metadata["case_state"] = {
        "case_meta": {
            "phase": "case_state_phase",
            "analysis_cycle_id": "cycle-case",
            "state_revision": 8,
            "snapshot_parent_revision": 7,
        },
        "governance_state": {
            "release_status": "rfq_ready",
            "review_state": "approved",
            "review_required": False,
        },
        "recipient_selection": {"selected_partner_id": "case-state-partner"},
        "rfq_state": {
            "rfq_admissibility": "ready",
            "status": "ready",
            "handover_ready": True,
            "handover_status": "releasable",
            "rfq_confirmed": True,
            "rfq_handover_initiated": True,
            "rfq_html_report_present": True,
        },
    }
    transcript = MagicMock()
    transcript.user_id = "user-1"
    transcript.metadata_json = metadata
    session = AsyncMock()
    session.get = AsyncMock(return_value=transcript)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=type("ChatTranscript", (), {}))
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        result = asyncio.run(load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))

    assert result is not None
    assert result["case_state"]["case_meta"]["phase"] == "case_state_phase"
    assert result["case_state"]["governance_state"]["release_status"] == "rfq_ready"
    assert result["case_state"]["governance_state"]["review_state"] == "approved"
    assert result["case_state"]["governance_state"]["review_required"] is False
    assert result["case_state"]["recipient_selection"]["selected_partner_id"] == "case-state-partner"
    assert result["case_state"]["rfq_state"]["rfq_admissibility"] == "ready"
    assert result["case_state"]["rfq_state"]["status"] == "ready"
    assert result["case_state"]["rfq_state"]["handover_ready"] is True
    assert result["case_state"]["rfq_state"]["handover_status"] == "releasable"
    assert result["case_state"]["rfq_state"]["rfq_confirmed"] is True
    assert result["case_state"]["rfq_state"]["rfq_handover_initiated"] is True
    assert result["case_state"]["rfq_state"]["rfq_html_report_present"] is True


def test_load_structured_case_prefers_persisted_outward_lifecycle_over_conflicting_sealing_state():
    metadata = _meta("tenant-a")
    metadata["sealing_state"] = {
        "cycle": {"phase": "legacy_phase"},
        "governance": {
            "release_status": "inadmissible",
            "rfq_admissibility": "inadmissible",
        },
        "review": {
            "review_state": "pending",
            "review_required": True,
        },
        "selection": {
            "selected_partner_id": "legacy-partner",
        },
        "handover": {
            "is_handover_ready": False,
            "handover_status": "not_ready",
            "rfq_confirmed": False,
            "handover_completed": False,
            "rfq_html_report": None,
        },
    }
    metadata["case_state"] = {
        "case_meta": {"phase": "case_state_phase"},
        "governance_state": {
            "release_status": "rfq_ready",
            "review_state": "approved",
            "review_required": False,
        },
        "recipient_selection": {"selected_partner_id": "case-state-partner"},
        "rfq_state": {
            "rfq_admissibility": "ready",
            "status": "ready",
            "handover_ready": True,
            "handover_status": "releasable",
            "rfq_confirmed": True,
            "rfq_handover_initiated": True,
            "rfq_html_report_present": True,
        },
    }
    metadata["persisted_lifecycle"] = {
        "phase": "persisted_phase",
        "release_status": "persisted_release",
        "review_state": "persisted_review",
        "review_required": True,
        "selected_partner_id": "persisted-partner",
        "rfq_admissibility": "persisted_rfq",
        "rfq_status": "persisted_status",
        "handover_ready": False,
        "handover_status": "persisted_handover",
        "rfq_confirmed": False,
        "rfq_handover_initiated": False,
        "rfq_html_report_present": False,
    }
    transcript = MagicMock()
    transcript.user_id = "user-1"
    transcript.metadata_json = metadata
    session = AsyncMock()
    session.get = AsyncMock(return_value=transcript)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=type("ChatTranscript", (), {}))
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        result = asyncio.run(load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))

    assert result is not None
    assert result["case_state"]["case_meta"]["phase"] == "case_state_phase"
    assert result["case_state"]["governance_state"]["release_status"] == "rfq_ready"
    assert result["case_state"]["governance_state"]["review_state"] == "approved"
    assert result["case_state"]["governance_state"]["review_required"] is False
    assert result["case_state"]["recipient_selection"]["selected_partner_id"] == "case-state-partner"
    assert result["case_state"]["rfq_state"]["rfq_admissibility"] == "ready"
    assert result["case_state"]["rfq_state"]["status"] == "ready"
    assert result["case_state"]["rfq_state"]["handover_ready"] is True
    assert result["case_state"]["rfq_state"]["handover_status"] == "releasable"
    assert result["case_state"]["rfq_state"]["rfq_confirmed"] is True
    assert result["case_state"]["rfq_state"]["rfq_handover_initiated"] is True
    assert result["case_state"]["rfq_state"]["rfq_html_report_present"] is True


def test_load_structured_case_applies_persisted_concurrency_token_fallback():
    metadata = _meta("tenant-a")
    metadata["persisted_concurrency_token"] = {
        "state_revision": 9,
        "snapshot_parent_revision": 8,
        "analysis_cycle_id": "cycle-persisted",
    }
    transcript = MagicMock()
    transcript.user_id = "user-1"
    transcript.metadata_json = metadata
    session = AsyncMock()
    session.get = AsyncMock(return_value=transcript)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=type("ChatTranscript", (), {}))
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        result = asyncio.run(load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))

    assert result is not None
    assert result["case_state"]["case_meta"]["state_revision"] == 9
    assert result["case_state"]["case_meta"]["snapshot_parent_revision"] == 8
    assert result["case_state"]["case_meta"]["analysis_cycle_id"] == "cycle-persisted"


def test_load_structured_case_prefers_persisted_case_meta_token_over_conflicting_sealing_cycle():
    metadata = _meta("tenant-a")
    metadata["sealing_state"] = {
        "cycle": {
            "state_revision": 3,
            "snapshot_parent_revision": 2,
            "analysis_cycle_id": "legacy-cycle",
        }
    }
    metadata["case_state"] = {
        "case_meta": {
            "state_revision": 9,
            "snapshot_parent_revision": 8,
            "analysis_cycle_id": "case-cycle",
            "version": 9,
        }
    }
    metadata["persisted_concurrency_token"] = {
        "state_revision": 7,
        "snapshot_parent_revision": 6,
        "analysis_cycle_id": "persisted-cycle",
    }
    transcript = MagicMock()
    transcript.user_id = "user-1"
    transcript.metadata_json = metadata
    session = AsyncMock()
    session.get = AsyncMock(return_value=transcript)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=type("ChatTranscript", (), {}))
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        result = asyncio.run(load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))

    assert result is not None
    assert result["case_state"]["case_meta"]["state_revision"] == 9
    assert result["case_state"]["case_meta"]["snapshot_parent_revision"] == 8
    assert result["case_state"]["case_meta"]["analysis_cycle_id"] == "case-cycle"
    assert result["case_state"]["case_meta"]["version"] == 9


def test_load_structured_case_prefers_persisted_canonical_handover_and_dispatch_basis_slices():
    metadata = _meta("tenant-a")
    metadata["sealing_state"] = {
        "cycle": {},
        "governance": {
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "compound_required",
        },
        "review": {
            "review_required": False,
            "review_state": "approved",
        },
        "handover": {
            "is_handover_ready": True,
            "handover_status": "releasable",
            "target_system": "legacy_portal",
            "handover_payload": {
                "qualified_material_ids": ["legacy-mat"],
                "qualified_materials": [{"manufacturer_name": "Legacy"}],
                "confirmed_parameters": {"temperature": {"value": 80.0, "unit": "C"}},
                "dimensions": {"rod_diameter_mm": 9.0},
                "rfq_admissibility": "ready",
            },
        },
        "dispatch_intent": {
            "dispatch_status": "dispatch_ready",
            "dispatch_ready": True,
            "recipient_refs": [{"manufacturer_name": "Legacy", "candidate_ids": ["legacy::candidate"]}],
            "requirement_class": {"requirement_class_id": "legacy::rc"},
            "recommendation_identity": {"candidate_id": "legacy::candidate"},
        },
        "dispatch_event": {
            "event_status": "event_dispatch_would_run",
            "would_dispatch": True,
            "recipient_refs": [{"manufacturer_name": "Legacy", "candidate_ids": ["legacy::candidate"]}],
            "requirement_class": {"requirement_class_id": "legacy::rc"},
            "recommendation_identity": {"candidate_id": "legacy::candidate"},
            "event_id": "dispatch_event::legacy",
            "event_key": "legacy",
        },
    }
    metadata["case_state"] = {
        "rfq_state": {
            "rfq_admissibility": "ready",
            "status": "ready",
            "handover_ready": True,
            "handover_status": "releasable",
            "rfq_object": {
                "object_type": "rfq_payload_basis",
                "object_version": "rfq_payload_basis_v1",
                "qualified_material_ids": ["canonical-mat"],
                "qualified_materials": [{"manufacturer_name": "Canonical"}],
                "confirmed_parameters": {"temperature": {"value": 120.0, "unit": "C"}},
                "dimensions": {"rod_diameter_mm": 14.2},
                "target_system": "canonical_portal",
            },
        },
        "dispatch_intent": {
            "dispatch_status": "blocked",
            "dispatch_ready": False,
            "recipient_refs": [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}],
            "requirement_class": {"requirement_class_id": "canonical::rc"},
            "recommendation_identity": {"candidate_id": "canonical::candidate"},
        },
        "dispatch_event": {
            "event_status": "event_dispatch_missing_basis",
            "would_dispatch": False,
            "recipient_refs": [{"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}],
            "requirement_class": {"requirement_class_id": "canonical::rc"},
            "recommendation_identity": {"candidate_id": "canonical::candidate"},
        },
    }
    transcript = MagicMock()
    transcript.user_id = "user-1"
    transcript.metadata_json = metadata
    session = AsyncMock()
    session.get = AsyncMock(return_value=transcript)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=type("ChatTranscript", (), {}))
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        result = asyncio.run(load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))

    assert result is not None
    assert result["case_state"]["rfq_state"]["rfq_object"]["qualified_material_ids"] == ["canonical-mat"]
    assert result["case_state"]["rfq_state"]["rfq_object"]["target_system"] == "canonical_portal"
    assert result["case_state"]["dispatch_intent"]["dispatch_status"] == "blocked"
    assert result["case_state"]["dispatch_intent"]["dispatch_ready"] is False
    assert result["case_state"]["dispatch_intent"]["recipient_refs"] == [
        {"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}
    ]
    assert result["case_state"]["dispatch_intent"]["requirement_class"]["requirement_class_id"] == "canonical::rc"
    assert result["case_state"]["dispatch_event"]["event_status"] == "event_dispatch_missing_basis"
    assert result["case_state"]["dispatch_event"]["would_dispatch"] is False
    assert result["case_state"]["dispatch_event"]["recipient_refs"] == [
        {"manufacturer_name": "Canonical", "candidate_ids": ["canonical::candidate"]}
    ]
    assert result["case_state"]["dispatch_event"]["recommendation_identity"]["candidate_id"] == "canonical::candidate"
    assert result["sealing_state"]["dispatch_event"]["event_id"] == "dispatch_event::legacy"


def test_load_structured_case_preserves_canonical_matching_state():
    metadata = _meta("tenant-a")
    metadata["sealing_state"] = {
        "cycle": {},
        "governance": {
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "compound_required",
        },
        "selection": {
            "selection_status": "shortlisted",
            "winner_candidate_id": "ptfe::g25::acme",
            "viable_candidate_ids": ["ptfe::g25::acme"],
            "blocked_candidates": [],
            "output_blocked": False,
            "recommendation_artifact": {
                "candidate_projection": {
                    "candidate_id": "ptfe::g25::acme",
                    "material_family": "PTFE",
                    "specificity_level": "compound_required",
                }
            },
        },
        "review": {
            "review_required": False,
            "review_state": "approved",
        },
    }
    metadata["case_state"] = {
        "requirement_class": {
            "object_type": "requirement_class",
            "object_version": "requirement_class_v1",
            "requirement_class_id": "compound::ptfe::g25::acme",
            "derivation_basis": "compound",
            "specificity_level": "compound_required",
            "material_family": "PTFE",
            "candidate_id": "ptfe::g25::acme",
            "manufacturer_specific": False,
        },
        "matching_state": {
            "matchable": True,
            "ready_for_matching": True,
            "matchability_status": "ready_for_matching",
            "recommendation_identity": {
                "candidate_id": "ptfe::g25::acme",
                "material_family": "PTFE",
                "specificity_level": "compound_required",
            },
            "requirement_class": {
                "object_type": "requirement_class",
                "object_version": "requirement_class_v1",
                "requirement_class_id": "compound::ptfe::g25::acme",
                "derivation_basis": "compound",
                "specificity_level": "compound_required",
                "material_family": "PTFE",
                "candidate_id": "ptfe::g25::acme",
                "manufacturer_specific": False,
            },
            "requirement_class_hint": "compound::ptfe::g25::acme",
        },
        "result_contract": {
            "recommendation_identity": {
                "candidate_id": "ptfe::g25::acme",
                "material_family": "PTFE",
                "specificity_level": "compound_required",
            },
            "requirement_class": {
                "object_type": "requirement_class",
                "object_version": "requirement_class_v1",
                "requirement_class_id": "compound::ptfe::g25::acme",
                "derivation_basis": "compound",
                "specificity_level": "compound_required",
                "material_family": "PTFE",
                "candidate_id": "ptfe::g25::acme",
                "manufacturer_specific": False,
            },
            "requirement_class_hint": "compound::ptfe::g25::acme",
        },
    }
    transcript = MagicMock()
    transcript.user_id = "user-1"
    transcript.metadata_json = metadata
    session = AsyncMock()
    session.get = AsyncMock(return_value=transcript)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=type("ChatTranscript", (), {}))
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        result = asyncio.run(load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))

    assert result is not None
    assert result["case_state"]["requirement_class"]["requirement_class_id"] == "compound::ptfe::g25::acme"
    assert result["case_state"]["matching_state"]["matchability_status"] == "ready_for_matching"
    assert result["case_state"]["matching_state"]["requirement_class"]["requirement_class_id"] == "compound::ptfe::g25::acme"
    assert result["case_state"]["matching_state"]["requirement_class_hint"] == "compound::ptfe::g25::acme"


def test_load_structured_case_preserves_canonical_rfq_state():
    metadata = _meta("tenant-a")
    metadata["sealing_state"] = {
        "cycle": {},
        "governance": {
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "compound_required",
        },
        "selection": {
            "selection_status": "shortlisted",
            "winner_candidate_id": "ptfe::g25::acme",
            "viable_candidate_ids": ["ptfe::g25::acme"],
            "blocked_candidates": [],
            "output_blocked": False,
            "recommendation_artifact": {
                "candidate_projection": {
                    "candidate_id": "ptfe::g25::acme",
                    "material_family": "PTFE",
                    "specificity_level": "compound_required",
                }
            },
        },
        "review": {
            "review_required": False,
            "review_state": "approved",
        },
        "handover": {
            "is_handover_ready": True,
            "handover_status": "releasable",
            "handover_payload": {
                "qualified_material_ids": ["ptfe::g25::acme"],
                "confirmed_parameters": {"temperature_c": 120},
            },
        },
    }
    metadata["case_state"] = {
        "rfq_state": {
            "status": "ready",
            "rfq_admissibility": "ready",
            "blocking_reasons": [],
            "open_points": [],
            "requirement_class": {
                "object_type": "requirement_class",
                "object_version": "requirement_class_v1",
                "requirement_class_id": "compound::ptfe::g25::acme",
                "derivation_basis": "compound",
                "specificity_level": "compound_required",
                "material_family": "PTFE",
                "candidate_id": "ptfe::g25::acme",
                "manufacturer_specific": False,
            },
            "requirement_class_hint": "compound::ptfe::g25::acme",
            "recipient_selection": {
                "object_type": "recipient_selection",
                "object_version": "recipient_selection_v1",
                "selection_status": "selected_recipient",
                "recipient_selection_ready": True,
                "selected_recipient_refs": [
                    {
                        "manufacturer_name": "Acme",
                        "candidate_ids": ["ptfe::g25::acme"],
                    }
                ],
                "candidate_recipient_refs": [
                    {
                        "manufacturer_name": "Acme",
                        "candidate_ids": ["ptfe::g25::acme"],
                    }
                ],
                "non_selected_recipient_refs": [],
                "selection_basis_summary": {
                    "candidate_count": 1,
                    "selected_count": 1,
                    "has_selected_manufacturer_ref": True,
                    "derived_from_matching_outcome": True,
                },
                "selected_manufacturer_ref": {
                    "manufacturer_name": "Acme",
                    "candidate_ids": ["ptfe::g25::acme"],
                },
            },
            "rfq_dispatch": {
                "object_type": "rfq_dispatch",
                "object_version": "rfq_dispatch_v1",
                "dispatch_ready": True,
                "dispatch_status": "dispatch_ready",
                "dispatch_blockers": [],
                "dispatch_open_points": [],
                "recipient_basis_summary": {
                    "recipient_count": 1,
                    "has_selected_manufacturer_ref": True,
                    "derived_from_matching_outcome": True,
                    "handover_status": "releasable",
                    "handover_ready": True,
                },
                "recipient_refs": [
                    {
                        "manufacturer_name": "Acme",
                        "candidate_ids": ["ptfe::g25::acme"],
                    }
                ],
                "selected_manufacturer_ref": {
                    "manufacturer_name": "Acme",
                    "candidate_ids": ["ptfe::g25::acme"],
                },
                "rfq_object_basis": {
                    "object_type": "rfq_payload_basis",
                    "object_version": "rfq_payload_basis_v1",
                    "payload_present": True,
                    "qualified_material_ids": ["ptfe::g25::acme"],
                },
                "manufacturer_validation_required": False,
                "review_required": False,
                "contract_obsolete": False,
            },
        },
        "result_contract": {
            "recommendation_identity": {
                "candidate_id": "ptfe::g25::acme",
                "material_family": "PTFE",
                "specificity_level": "compound_required",
            },
            "requirement_class": {
                "object_type": "requirement_class",
                "object_version": "requirement_class_v1",
                "requirement_class_id": "compound::ptfe::g25::acme",
                "derivation_basis": "compound",
                "specificity_level": "compound_required",
                "material_family": "PTFE",
                "candidate_id": "ptfe::g25::acme",
                "manufacturer_specific": False,
            },
            "requirement_class_hint": "compound::ptfe::g25::acme",
        },
    }
    transcript = MagicMock()
    transcript.user_id = "user-1"
    transcript.metadata_json = metadata
    session = AsyncMock()
    session.get = AsyncMock(return_value=transcript)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=type("ChatTranscript", (), {}))
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        result = asyncio.run(load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))

    assert result is not None
    assert result["case_state"]["recipient_selection"]["selection_status"] == "no_recipient_candidates"
    assert result["case_state"]["rfq_state"]["status"] == "ready"
    assert result["case_state"]["rfq_state"]["requirement_class"]["requirement_class_id"] == "compound::ptfe::g25::acme"
    assert result["case_state"]["rfq_state"]["rfq_object"]["payload_present"] is True
    assert result["case_state"]["rfq_state"]["rfq_object"]["requirement_class"]["requirement_class_id"] == "compound::ptfe::g25::acme"
    assert result["case_state"]["rfq_state"]["rfq_object"]["qualified_material_ids"] == ["ptfe::g25::acme"]
    assert result["case_state"]["rfq_state"]["recipient_selection"]["selection_status"] == "no_recipient_candidates"
    assert result["case_state"]["rfq_state"]["rfq_dispatch"]["dispatch_ready"] is False
    assert result["case_state"]["rfq_state"]["rfq_dispatch"]["dispatch_status"] == "not_ready_no_recipients"
    assert result["case_state"]["rfq_state"]["rfq_dispatch"]["dispatch_blockers"] == ["no_recipient_refs"]
    assert result["case_state"]["rfq_state"]["rfq_dispatch"]["rfq_object_basis"]["qualified_material_ids"] == ["ptfe::g25::acme"]


def test_load_structured_case_preserves_canonical_manufacturer_state():
    metadata = _meta("tenant-a")
    metadata["sealing_state"] = {
        "cycle": {},
        "governance": {
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "compound_required",
        },
        "selection": {
            "selection_status": "shortlisted",
            "winner_candidate_id": "ptfe::g25::acme",
            "viable_candidate_ids": ["ptfe::g25::acme"],
            "blocked_candidates": [],
            "output_blocked": False,
            "recommendation_artifact": {
                "candidate_projection": {
                    "candidate_id": "ptfe::g25::acme",
                    "material_family": "PTFE",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                    "candidate_kind": "manufacturer_grade",
                    "specificity_level": "compound_required",
                }
            },
        },
        "review": {
            "review_required": False,
            "review_state": "approved",
        },
        "handover": {
            "is_handover_ready": True,
            "handover_status": "releasable",
            "handover_payload": {
                "qualified_materials": [
                    {
                        "candidate_id": "ptfe::g25::acme",
                        "material_family": "PTFE",
                        "grade_name": "G25",
                        "manufacturer_name": "Acme",
                    }
                ]
            },
        },
    }
    metadata["case_state"] = {
        "manufacturer_state": {
            "manufacturer_specific": True,
            "manufacturer_specificity_status": "manufacturer_specific",
            "manufacturer_capabilities": [
                {
                    "object_type": "manufacturer_capability",
                    "object_version": "manufacturer_capability_v1",
                    "manufacturer_name": "Acme",
                    "capability_sources": ["recommendation_identity", "rfq_qualified_material"],
                    "capability_hints": ["rfq_qualified_material"],
                    "material_families": ["PTFE"],
                    "grade_names": ["G25"],
                    "candidate_kinds": ["manufacturer_grade"],
                    "candidate_ids": ["ptfe::g25::acme"],
                    "requirement_class_ids": ["compound::ptfe::g25::acme"],
                    "rfq_qualified": True,
                }
            ],
            "requirement_class": {
                "object_type": "requirement_class",
                "object_version": "requirement_class_v1",
                "requirement_class_id": "compound::ptfe::g25::acme",
                "derivation_basis": "compound",
                "specificity_level": "compound_required",
                "material_family": "PTFE",
                "candidate_id": "ptfe::g25::acme",
                "manufacturer_name": "Acme",
                "manufacturer_specific": True,
            },
            "requirement_class_hint": "compound::ptfe::g25::acme",
        },
        "result_contract": {
            "recommendation_identity": {
                "candidate_id": "ptfe::g25::acme",
                "material_family": "PTFE",
                "grade_name": "G25",
                "manufacturer_name": "Acme",
                "specificity_level": "compound_required",
            },
            "requirement_class": {
                "object_type": "requirement_class",
                "object_version": "requirement_class_v1",
                "requirement_class_id": "compound::ptfe::g25::acme",
                "derivation_basis": "compound",
                "specificity_level": "compound_required",
                "material_family": "PTFE",
                "candidate_id": "ptfe::g25::acme",
                "grade_name": "G25",
                "manufacturer_name": "Acme",
                "manufacturer_specific": True,
            },
            "requirement_class_hint": "compound::ptfe::g25::acme",
        },
    }
    transcript = MagicMock()
    transcript.user_id = "user-1"
    transcript.metadata_json = metadata
    session = AsyncMock()
    session.get = AsyncMock(return_value=transcript)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=type("ChatTranscript", (), {}))
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        result = asyncio.run(load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))

    assert result is not None
    assert result["case_state"]["manufacturer_state"]["manufacturer_specific"] is True
    assert result["case_state"]["manufacturer_state"]["manufacturer_capabilities"][0]["manufacturer_name"] == "Acme"
    assert result["case_state"]["manufacturer_state"]["manufacturer_capabilities"][0]["requirement_class_ids"] == ["compound::ptfe::g25::acme"]
    assert result["case_state"]["manufacturer_state"]["requirement_class"]["requirement_class_id"] == "compound::ptfe::g25::acme"
    assert result["case_state"]["manufacturer_state"]["manufacturer_refs"][0]["manufacturer_name"] == "Acme"
    assert result["case_state"]["manufacturer_state"]["qualified_materials"][0]["candidate_id"] == "ptfe::g25::acme"


def test_load_structured_case_preserves_matching_outcome():
    metadata = _meta("tenant-a")
    metadata["case_state"] = {
        "matching_state": {
            "matching_outcome": {
                "status": "matched_primary_candidate",
                "reason": "Primary match candidate selected from canonical winner/viable candidate truth.",
                "primary_match_candidate": {
                    "candidate_id": "ptfe::g25::acme",
                    "manufacturer_name": "Acme",
                },
            }
        }
    }
    transcript = MagicMock()
    transcript.user_id = "user-1"
    transcript.metadata_json = metadata
    session = AsyncMock()
    session.get = AsyncMock(return_value=transcript)
    session_ctx = MagicMock()
    session_ctx.__aenter__ = AsyncMock(return_value=session)
    session_ctx.__aexit__ = AsyncMock(return_value=False)
    fake_db = types.SimpleNamespace(AsyncSessionLocal=lambda: session_ctx)
    fake_models = types.SimpleNamespace(ChatTranscript=type("ChatTranscript", (), {}))
    with patch.dict(sys.modules, {"app.database": fake_db, "app.models.chat_transcript": fake_models}):
        result = asyncio.run(load_structured_case(tenant_id="tenant-a", owner_id="user-1", case_id="case-1"))

    assert result is not None
    assert result["case_state"]["matching_state"]["matching_outcome"]["status"] == "matched_primary_candidate"
