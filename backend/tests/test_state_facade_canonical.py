import copy
import importlib
import os
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


for key, value in {
    "POSTGRES_USER": "sealai",
    "POSTGRES_PASSWORD": "secret",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "sealai",
    "DATABASE_URL": "postgresql+asyncpg://sealai:secret@localhost:5432/sealai",
    "POSTGRES_SYNC_URL": "postgresql://sealai:secret@localhost:5432/sealai",
    "OPENAI_API_KEY": "test-key",
    "QDRANT_URL": "http://localhost:6333",
    "QDRANT_COLLECTION": "sealai",
    "REDIS_URL": "redis://localhost:6379/0",
    "NEXTAUTH_URL": "http://localhost:3000",
    "NEXTAUTH_SECRET": "dummy-secret",
    "KEYCLOAK_ISSUER": "http://localhost:8080/realms/test",
    "KEYCLOAK_JWKS_URL": "http://localhost:8080/realms/test/protocol/openid-connect/certs",
    "KEYCLOAK_CLIENT_ID": "sealai-backend",
    "KEYCLOAK_CLIENT_SECRET": "client-secret",
    "KEYCLOAK_EXPECTED_AZP": "sealai-frontend",
}.items():
    os.environ.setdefault(key, value)

os.environ.setdefault("postgres_user", "sealai")
os.environ.setdefault("postgres_password", "secret")
os.environ.setdefault("postgres_host", "localhost")
os.environ.setdefault("postgres_port", "5432")
os.environ.setdefault("postgres_db", "sealai")
os.environ.setdefault("database_url", "sqlite+aiosqlite:///tmp.db")
os.environ.setdefault("POSTGRES_SYNC_URL", "sqlite:///tmp.db")
os.environ.setdefault("openai_api_key", "test-key")
os.environ.setdefault("qdrant_url", "http://localhost:6333")
os.environ.setdefault("qdrant_collection", "sealai")
os.environ.setdefault("redis_url", "redis://localhost:6379/0")
os.environ.setdefault("nextauth_url", "http://localhost:3000")
os.environ.setdefault("nextauth_secret", "dummy-secret")
os.environ.setdefault("keycloak_issuer", "http://localhost:8080/realms/test")
os.environ.setdefault("keycloak_jwks_url", "http://localhost:8080/realms/test/protocol/openid-connect/certs")
os.environ.setdefault("keycloak_client_id", "sealai-backend")
os.environ.setdefault("keycloak_client_secret", "client-secret")
os.environ.setdefault("keycloak_expected_azp", "sealai-frontend")


def test_v1_state_facade_reads_canonical_persisted_state(monkeypatch) -> None:
    auth_deps = importlib.import_module("app.services.auth.dependencies")
    state_mod = importlib.import_module("app.api.v1.endpoints.state")

    persisted_state = {
        "messages": [],
        "working_profile": {"medium": "water"},
        "case_state": {
            "case_meta": {
                "phase": "case_state_phase",
            },
            "requirement_class": {
                "object_type": "requirement_class",
                "object_version": "requirement_class_v1",
                "requirement_class_id": "compound::ptfe::g25::acme",
                "derivation_basis": "compound",
                "specificity_level": "compound_required",
                "material_family": "PTFE",
                "candidate_id": "ptfe::g25::acme",
                "candidate_kind": "manufacturer_grade",
                "grade_name": "G25",
                "manufacturer_name": "Acme",
                "manufacturer_specific": True,
            },
            "recipient_selection": {
                "object_type": "recipient_selection",
                "object_version": "recipient_selection_v1",
                "selection_status": "selected_recipient",
                "recipient_selection_ready": True,
                "selected_recipient_refs": [
                    {
                        "manufacturer_name": "Acme",
                        "candidate_ids": ["ptfe::g25::acme"],
                        "material_families": ["PTFE"],
                    }
                ],
                "candidate_recipient_refs": [
                    {
                        "manufacturer_name": "Acme",
                        "candidate_ids": ["ptfe::g25::acme"],
                        "material_families": ["PTFE"],
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
                    "material_families": ["PTFE"],
                },
                "selected_partner_id": "case-state-partner",
            },
            "parameter_meta": {
                "material": {
                    "source": "normalizer",
                    "confidence": "high",
                }
            },
            "governance_state": {
                "scope_of_validity": [
                    "manufacturer_validation_scope",
                    "release_blocked_pending_unknowns",
                ],
                "required_disclaimers": [
                    "Manufacturer validation required.",
                ],
                "review_required": True,
                "review_state": "pending",
            },
            "rfq_state": {
                "status": "ready",
                "rfq_confirmed": True,
                "rfq_handover_initiated": True,
                "rfq_html_report_present": True,
                "handover_ready": True,
                "blockers": [],
                "open_points": ["compound pending"],
                "blocking_reasons": [],
                "recommendation_identity": {
                    "candidate_id": "ptfe::g25::acme",
                    "material_family": "PTFE",
                },
                "requirement_class": {
                    "object_type": "requirement_class",
                    "object_version": "requirement_class_v1",
                    "requirement_class_id": "compound::ptfe::g25::acme",
                    "derivation_basis": "compound",
                    "specificity_level": "compound_required",
                    "material_family": "PTFE",
                    "candidate_id": "ptfe::g25::acme",
                    "candidate_kind": "manufacturer_grade",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                    "manufacturer_specific": True,
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
                            "material_families": ["PTFE"],
                        }
                    ],
                    "candidate_recipient_refs": [
                        {
                            "manufacturer_name": "Acme",
                            "candidate_ids": ["ptfe::g25::acme"],
                            "material_families": ["PTFE"],
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
                        "material_families": ["PTFE"],
                    },
                },
                "rfq_object": {
                    "object_type": "rfq_payload_basis",
                    "requirement_class": {
                        "object_type": "requirement_class",
                        "object_version": "requirement_class_v1",
                        "requirement_class_id": "compound::ptfe::g25::acme",
                        "derivation_basis": "compound",
                        "specificity_level": "compound_required",
                        "material_family": "PTFE",
                        "candidate_id": "ptfe::g25::acme",
                        "candidate_kind": "manufacturer_grade",
                        "grade_name": "G25",
                        "manufacturer_name": "Acme",
                        "manufacturer_specific": True,
                    },
                    "payload_present": True,
                    "qualified_material_ids": ["ptfe::g25::acme"],
                },
                "rfq_dispatch": {
                    "object_type": "rfq_dispatch",
                    "object_version": "rfq_dispatch_v1",
                    "dispatch_ready": True,
                    "dispatch_status": "dispatch_ready",
                    "dispatch_blockers": [],
                    "dispatch_open_points": ["compound pending"],
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
                            "material_families": ["PTFE"],
                        }
                    ],
                    "recipient_selection": {
                        "object_type": "recipient_selection",
                        "object_version": "recipient_selection_v1",
                        "selection_status": "selected_recipient",
                        "recipient_selection_ready": True,
                        "selected_recipient_refs": [
                            {
                                "manufacturer_name": "Acme",
                                "candidate_ids": ["ptfe::g25::acme"],
                                "material_families": ["PTFE"],
                            }
                        ],
                        "candidate_recipient_refs": [
                            {
                                "manufacturer_name": "Acme",
                                "candidate_ids": ["ptfe::g25::acme"],
                                "material_families": ["PTFE"],
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
                            "material_families": ["PTFE"],
                        },
                    },
                    "selected_manufacturer_ref": {
                        "manufacturer_name": "Acme",
                        "candidate_ids": ["ptfe::g25::acme"],
                        "material_families": ["PTFE"],
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
                "contract_obsolete": True,
                "invalidation_reasons": ["analysis_cycle_advanced"],
                "recommendation_identity": {
                    "candidate_id": "ptfe::g25::acme",
                    "candidate_kind": "manufacturer_grade",
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
                    "candidate_kind": "manufacturer_grade",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                    "manufacturer_specific": True,
                },
                "requirement_class_hint": "compound::ptfe::g25::acme",
            },
            "sealing_requirement_spec": {
                "requirement_class": {
                    "object_type": "requirement_class",
                    "object_version": "requirement_class_v1",
                    "requirement_class_id": "compound::ptfe::g25::acme",
                    "derivation_basis": "compound",
                    "specificity_level": "compound_required",
                    "material_family": "PTFE",
                    "candidate_id": "ptfe::g25::acme",
                    "candidate_kind": "manufacturer_grade",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                    "manufacturer_specific": True,
                },
                "requirement_class_hint": "compound::ptfe::g25::acme",
                "recommendation_identity": {
                    "candidate_id": "ptfe::g25::acme",
                    "material_family": "PTFE",
                },
            },
            "matching_state": {
                "matchable": True,
                "ready_for_matching": True,
                "matchability_status": "ready_for_matching",
                "recommendation_identity": {
                    "candidate_id": "ptfe::g25::acme",
                    "candidate_kind": "manufacturer_grade",
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
                    "candidate_kind": "manufacturer_grade",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                    "manufacturer_specific": True,
                },
                "requirement_class_hint": "compound::ptfe::g25::acme",
                "candidate_summary": {
                    "winner_candidate_id": "ptfe::g25::acme",
                },
                "match_candidates": [
                    {
                        "candidate_id": "ptfe::g25::acme",
                        "material_family": "PTFE",
                        "manufacturer_name": "Acme",
                        "viability_status": "viable",
                    }
                ],
                "matching_outcome": {
                    "status": "matched_primary_candidate",
                    "reason": "Primary match candidate selected from canonical winner/viable candidate truth.",
                    "primary_match_candidate": {
                        "candidate_id": "ptfe::g25::acme",
                        "manufacturer_name": "Acme",
                    },
                    "selected_manufacturer_ref": {
                        "manufacturer_name": "Acme",
                        "candidate_ids": ["ptfe::g25::acme"],
                        "material_families": ["PTFE"],
                    },
                },
            },
            "manufacturer_state": {
                "manufacturer_specific": True,
                "manufacturer_specificity_status": "manufacturer_specific",
                "manufacturer_refs": [
                    {
                        "manufacturer_name": "Acme",
                        "candidate_ids": ["ptfe::g25::acme"],
                        "material_families": ["PTFE"],
                        "grade_names": ["G25"],
                        "candidate_kinds": ["manufacturer_grade"],
                        "capability_hints": ["manufacturer_grade_candidate", "rfq_qualified_material"],
                        "source_refs": ["recommendation_identity", "match_candidate", "rfq_qualified_material"],
                        "qualified_for_rfq": True,
                    }
                ],
                "manufacturer_capabilities": [
                    {
                        "object_type": "manufacturer_capability",
                        "object_version": "manufacturer_capability_v1",
                        "manufacturer_name": "Acme",
                        "capability_sources": ["recommendation_identity", "match_candidate", "rfq_qualified_material"],
                        "capability_hints": ["manufacturer_grade_candidate", "rfq_qualified_material"],
                        "material_families": ["PTFE"],
                        "grade_names": ["G25"],
                        "candidate_kinds": ["manufacturer_grade"],
                        "candidate_ids": ["ptfe::g25::acme"],
                        "requirement_class_ids": ["compound::ptfe::g25::acme"],
                        "rfq_qualified": True,
                        "evidence_refs": ["fc-1"],
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
                    "candidate_kind": "manufacturer_grade",
                    "grade_name": "G25",
                    "manufacturer_name": "Acme",
                    "manufacturer_specific": True,
                },
                "requirement_class_hint": "compound::ptfe::g25::acme",
                "qualified_materials": [
                    {
                        "candidate_id": "ptfe::g25::acme",
                        "material_family": "PTFE",
                        "grade_name": "G25",
                        "manufacturer_name": "Acme",
                    }
                ],
            },
        },
        "sealing_state": {
            "cycle": {"state_revision": 4, "phase": "legacy_phase"},
            "governance": {"release_status": "rfq_ready", "rfq_admissibility": "ready"},
            "handover": {"is_handover_ready": False},
            "review": {"review_required": True, "review_state": "legacy_pending", "review_reason": "manual review"},
            "selection": {"selected_partner_id": "legacy-partner"},
        },
    }

    with patch(
        "app.agent.api.router.load_canonical_state",
        new=AsyncMock(return_value=copy.deepcopy(persisted_state)),
    ) as mock_load:
        app = FastAPI()
        app.include_router(getattr(state_mod, "router"))
        app.dependency_overrides[auth_deps.get_current_request_user] = lambda: auth_deps.RequestUser(
            user_id="alice",
            username="alice",
            sub="alice",
            roles=[],
            scopes=[],
            tenant_id="tenant-a",
        )
        client = TestClient(app)
        response = client.get(
            "/state/case-1",
            headers={"X-Request-Id": "state-facade-1"},
        )

    assert response.status_code == 200
    assert mock_load.await_count == 1
    body = response.json()
    assert body["metadata"]["thread_id"] == "case-1"
    assert body["working_profile"]["medium"] == "water"
    assert body["governance_metadata"]["release_status"] == "rfq_ready"
    assert body["parameter_provenance"]["material"]["source"] == "normalizer"
    assert body["state"]["system"]["answer_contract"]["required_disclaimers"] == ["Manufacturer validation required."]
    assert body["state"]["system"]["rfq_admissibility"]["open_points"] == ["compound pending"]
    assert body["governance_metadata"]["scope_of_validity"] == ["manufacturer_validation_scope", "release_blocked_pending_unknowns"]
    assert body["governance_metadata"]["required_disclaimers"] == ["Manufacturer validation required."]
    assert body["governance_metadata"]["review_required"] is True
    assert body["governance_metadata"]["review_state"] == "pending"
    assert body["governance_metadata"]["contract_obsolete"] is True
    assert body["governance_metadata"]["contract_obsolete_reason"] == ["analysis_cycle_advanced"]
    assert body["state"]["system"]["governance_metadata"]["required_disclaimers"] == ["Manufacturer validation required."]
    assert body["recommendation_contract"]["requirement_class_hint"] == "compound::ptfe::g25::acme"
    assert body["recommendation_contract"]["requirement_class"]["requirement_class_id"] == "compound::ptfe::g25::acme"
    assert body["requirement_class"]["requirement_class_id"] == "compound::ptfe::g25::acme"
    assert body["recipient_selection"]["selection_status"] == "selected_recipient"
    assert body["recipient_selection"]["selected_partner_id"] == "case-state-partner"
    assert body["recipient_selection"]["selected_recipient_refs"][0]["manufacturer_name"] == "Acme"
    assert body["requirement_class_hint"] == "compound::ptfe::g25::acme"
    assert body["state"]["system"]["answer_contract"]["requirement_class"]["requirement_class_id"] == "compound::ptfe::g25::acme"
    assert body["state"]["system"]["answer_contract"]["requirement_class_hint"] == "compound::ptfe::g25::acme"
    assert body["recommendation_contract"]["recommendation_identity"]["candidate_id"] == "ptfe::g25::acme"
    assert body["sealing_requirement_spec"]["requirement_class"]["requirement_class_id"] == "compound::ptfe::g25::acme"
    assert body["sealing_requirement_spec"]["recommendation_identity"]["material_family"] == "PTFE"
    assert body["matching_state"]["matchability_status"] == "ready_for_matching"
    assert body["matching_state"]["match_candidates"][0]["candidate_id"] == "ptfe::g25::acme"
    assert body["matching_state"]["requirement_class"]["requirement_class_id"] == "compound::ptfe::g25::acme"
    assert body["state"]["system"]["matching_state"]["requirement_class_hint"] == "compound::ptfe::g25::acme"
    assert body["matching_outcome"]["status"] == "matched_primary_candidate"
    assert body["matching_outcome"]["primary_match_candidate"]["candidate_id"] == "ptfe::g25::acme"
    assert body["rfq_state"]["status"] == "ready"
    assert body["rfq_state"]["requirement_class"]["requirement_class_id"] == "compound::ptfe::g25::acme"
    assert body["rfq_state"]["rfq_object"]["qualified_material_ids"] == ["ptfe::g25::acme"]
    assert body["rfq_state"]["rfq_object"]["requirement_class"]["requirement_class_id"] == "compound::ptfe::g25::acme"
    assert body["rfq_state"]["rfq_dispatch"]["dispatch_ready"] is True
    assert body["rfq_state"]["rfq_dispatch"]["dispatch_status"] == "dispatch_ready"
    assert body["rfq_state"]["recipient_selection"]["selection_status"] == "selected_recipient"
    assert body["rfq_state"]["rfq_dispatch"]["recipient_selection"]["selection_status"] == "selected_recipient"
    assert body["rfq_state"]["rfq_dispatch"]["selected_manufacturer_ref"]["manufacturer_name"] == "Acme"
    assert body["rfq_state"]["rfq_dispatch"]["rfq_object_basis"]["qualified_material_ids"] == ["ptfe::g25::acme"]
    assert body["state"]["system"]["rfq_state"]["requirement_class_hint"] == "compound::ptfe::g25::acme"
    assert body["state"]["reasoning"]["phase"] == "case_state_phase"
    assert body["metadata"]["phase"] == "case_state_phase"
    assert body["state"]["reasoning"]["selected_partner_id"] == "case-state-partner"
    assert body["state"]["system"]["rfq_confirmed"] is True
    assert body["state"]["system"]["rfq_handover_initiated"] is True
    assert body["state"]["system"]["rfq_html_report_present"] is True
    assert body["is_handover_ready"] is True
    assert body["manufacturer_state"]["manufacturer_refs"][0]["manufacturer_name"] == "Acme"
    assert body["manufacturer_state"]["qualified_materials"][0]["candidate_id"] == "ptfe::g25::acme"
    assert body["manufacturer_state"]["manufacturer_capabilities"][0]["manufacturer_name"] == "Acme"
    assert body["manufacturer_state"]["manufacturer_capabilities"][0]["requirement_class_ids"] == ["compound::ptfe::g25::acme"]
    assert body["manufacturer_state"]["manufacturer_capabilities"][0]["rfq_qualified"] is True
    assert body["manufacturer_state"]["requirement_class"]["requirement_class_id"] == "compound::ptfe::g25::acme"
    assert body["state"]["system"]["manufacturer_state"]["requirement_class_hint"] == "compound::ptfe::g25::acme"


def test_workspace_projection_prefers_case_state_lifecycle_fields(monkeypatch) -> None:
    auth_deps = importlib.import_module("app.services.auth.dependencies")
    state_mod = importlib.import_module("app.api.v1.endpoints.state")

    persisted_state = {
        "messages": [],
        "working_profile": {"medium": "water"},
        "case_state": {
            "case_meta": {"phase": "case-workspace-phase"},
            "governance_state": {
                "release_status": "rfq_ready",
                "rfq_admissibility": "ready",
                "review_required": False,
                "review_state": "approved",
            },
            "recipient_selection": {
                "selected_partner_id": "case-workspace-partner",
            },
            "rfq_state": {
                "status": "ready",
                "rfq_confirmed": True,
                "rfq_handover_initiated": True,
                "rfq_html_report_present": True,
                "handover_ready": True,
                "blockers": [],
                "open_points": [],
            },
            "result_contract": {
                "release_status": "rfq_ready",
                "required_disclaimers": [],
            },
        },
        "sealing_state": {
            "cycle": {"state_revision": 4, "phase": "legacy-workspace-phase"},
            "governance": {"release_status": "rfq_ready", "rfq_admissibility": "ready"},
            "handover": {"is_handover_ready": False},
            "selection": {"selected_partner_id": "legacy-workspace-partner"},
        },
    }

    with patch(
        "app.agent.api.router.load_canonical_state",
        new=AsyncMock(return_value=copy.deepcopy(persisted_state)),
    ):
        app = FastAPI()
        app.include_router(getattr(state_mod, "router"))
        app.dependency_overrides[auth_deps.get_current_request_user] = lambda: auth_deps.RequestUser(
            user_id="alice",
            username="alice",
            sub="alice",
            roles=[],
            scopes=[],
            tenant_id="tenant-a",
        )
        client = TestClient(app)
        response = client.get(
            "/state/workspace",
            params={"thread_id": "case-1"},
            headers={"X-Request-Id": "state-workspace-1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["case_summary"]["phase"] == "case-workspace-phase"
    assert body["partner_matching"]["selected_partner_id"] == "case-workspace-partner"
    assert body["rfq_status"]["rfq_confirmed"] is True
    assert body["rfq_status"]["handover_initiated"] is True
    assert body["rfq_status"]["has_html_report"] is True
    assert body["rfq_status"]["handover_ready"] is True
