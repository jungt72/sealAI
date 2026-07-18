"""Executable governance contract for the ratified sealingAI SSoT."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SSOT_DIR = REPO / "docs" / "ssot"
EXPECTED_SOURCE_SHA256 = (
    "066dd803b7013fa8b7fdcac4703dee63c3fb183a55d7ef4e2cca76e963802580"
)


def _json(name: str) -> dict:
    return json.loads((SSOT_DIR / name).read_text(encoding="utf-8"))


def test_ratified_ssot_source_and_projection_are_tracked() -> None:
    source = SSOT_DIR / "sealingAI_SSoT_v2.0.docx"
    projection = SSOT_DIR / "sealingAI_SSoT_v2.0.md"

    assert source.is_file()
    assert projection.is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED_SOURCE_SHA256
    assert EXPECTED_SOURCE_SHA256 in projection.read_text(encoding="utf-8")


def test_operating_contract_points_to_the_ratified_authority() -> None:
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")

    assert "docs/ssot/sealingAI_SSoT_v2.0.md" in agents
    assert "## Ratified SSoT v2.0" in agents
    assert "Leitbild V3" not in agents
    assert "Full Leitbild text is held by the owner locally" not in agents


def test_registry_names_only_the_v2_runtime_as_canonical() -> None:
    registry = (REPO / "docs" / "architecture" / "SSOT_REGISTRY.md").read_text(
        encoding="utf-8"
    )

    assert "backend/sealai_v2/" in registry
    assert "`backend/app/` is retired" in registry
    assert "backend/app/agent/api" not in registry
    assert "Current architecture direction: V10" not in registry


def test_machine_readable_map_is_complete_and_self_consistent() -> None:
    mapping = _json("ssot-map.json")

    assert mapping["ssot"]["version"] == "2.0"
    assert mapping["ssot"]["status"] == "ratified"
    assert mapping["ssot"]["source_sha256"] == EXPECTED_SOURCE_SHA256
    assert set(mapping["hard_gates"]) == {f"G{i}" for i in range(1, 9)}
    assert set(mapping["changes"]) == {f"M{i}" for i in range(1, 17)}

    allowed = {
        "implemented",
        "partial",
        "remediation_required",
        "external_review_required",
        "owner_inputs_required",
        "pilot_required",
        "separate_plan_required",
        "not_implemented",
        "adjudicated_replay_required",
        "instrumentation_required",
    }
    for gate in mapping["hard_gates"].values():
        assert gate["status"] in allowed
        assert gate["evidence"]
        for evidence in gate["evidence"]:
            assert (REPO / evidence).exists(), evidence
    assert set(mapping["changes"].values()) <= allowed


def test_maturity_manifest_cannot_claim_unbounded_availability() -> None:
    maturity = _json("product-maturity.json")
    allowed = set(maturity["status_values"])

    assert set(maturity["horizons"]) == {f"H{i}" for i in range(6)}
    for horizon in maturity["horizons"].values():
        assert horizon["status"] in allowed
        assert horizon["public_label"]
    for mode in maturity["modes"].values():
        assert mode["status"] in allowed
        assert mode["horizon"] in maturity["horizons"]
        assert mode["activation_gate"]

    assert maturity["horizons"]["H3"]["status"] != "verified_available"
    assert maturity["horizons"]["H4"]["status"] != "verified_available"
    assert maturity["horizons"]["H5"]["status"] != "verified_available"
    assert maturity["modes"]["manufacturer_fit"]["status"] != "verified_available"
    assert maturity["horizons"]["H1"]["status"] == "in_build"
    assert (
        "independent_domain_review_of_seed_claims"
        in maturity["modes"]["knowledge"]["activation_blockers"]
    )

    material = maturity["capabilities"]["material_constraints"]
    assert material["implementation_status"] == (
        "med_norm_01_empty_catalog_inert_default_off_sampling_zero"
    )
    assert material["contract_version"] == "MED-NORM-01.v1"
    assert {
        "MAT-GOV-03C",
        "reviewed_media_catalog_content",
        "material_rule_evidence",
        "tested_shadow_purge_and_maintenance_role",
        "mat_gov_02_payload_and_hard_gate_followups",
        "owner_activation",
    } <= set(material["activation_blockers"])
    assert material["scope_limit"] == (
        "empty_tenant_isolated_catalog_and_internal_attribution_no_public_runtime_"
        "production_migration_or_sampling"
    )


def test_seed_review_state_never_launders_model_review_into_authority() -> None:
    import sys

    sys.path.insert(0, str(REPO / "backend"))
    from sealai_v2.knowledge.fachkarten import load_fachkarten

    catalog = load_fachkarten()
    for card in catalog.cards:
        for claim in card.reviewed_claims():
            assert claim.reviewed_by
            assert claim.reviewed_at
            assert claim.review_expires_at
            assert not any(
                marker in claim.reviewed_by.lower()
                for marker in ("codex", "llm", "model", "agent", "release-bootstrap")
            )


def test_runtime_maturity_projection_matches_governance_manifest() -> None:
    runtime_manifest = json.loads(
        (REPO / "backend" / "sealai_v2" / "config" / "product_maturity.json").read_text(
            encoding="utf-8"
        )
    )

    assert runtime_manifest == _json("product-maturity.json")


def test_rwdr_limited_cutover_is_bound_to_owner_review_evidence() -> None:
    evidence_dir = SSOT_DIR / "reviews" / "2026-07-14-rwdr-adaptive-interview-cutover"
    expected_hashes = {
        "worksheet.csv": "55d2b802738f41d81a671fdafe92e897298ad05ed08b1ba55309b8464a90d883",
        "review_attestation.json": "d55f0303aad47dde87dd4a1f7f3bb831f77c495f2e2a1bd5a772dc870da81e05",
        "adjudication.json": "bcdc176800614c8bfd8e56909b128fb400b95af9a971c4cdff4f5f5c411a5c56",
        "manifest.json": "24856baa82dd710576c4276fac1722cc47d8a6858d3c634393d8881f0810bc1b",
    }
    for name, expected in expected_hashes.items():
        assert (
            hashlib.sha256((evidence_dir / name).read_bytes()).hexdigest() == expected
        )

    adjudication = json.loads(
        (evidence_dir / "adjudication.json").read_text(encoding="utf-8")
    )
    assert adjudication["review_set_id"] == "rwdr-shadow-controlled-v2"
    assert adjudication["review_units"] == 30
    assert adjudication["preferences"] == {"controller": 30, "legacy": 0, "tie": 0}
    assert adjudication["zero_controller_critical_gate_skips"] is True
    assert adjudication["additional_llm_calls"] == 0
    assert adjudication["network_calls"] == 0
    assert adjudication["automatic_activation_authorized"] is False

    maturity = _json("product-maturity.json")["capabilities"]["adaptive_interview_rwdr"]
    assert maturity["status"] == "pilot"
    assert maturity["scope_limit"] == "explicit_rwdr_cases_only"
    assert maturity["activation_decision"] == "ODR-10"

    decisions = (SSOT_DIR / "OWNER_DECISION_REGISTER.md").read_text(encoding="utf-8")
    assert "## ODR-10: Limited RWDR adaptive-interview cutover" in decisions
    assert "paid Eval-REPLAY" in decisions


def test_governed_runtime_flags_are_allowlisted_into_production_compose() -> None:
    compose = (REPO / "docker-compose.deploy.yml").read_text(encoding="utf-8")

    for setting in (
        "SEALAI_V2_KNOWLEDGE_MODE_ENABLED",
        "SEALAI_V2_KNOWLEDGE_REVIEW_ENABLED",
        "SEALAI_V2_COMPATIBILITY_MATRIX_ENABLED",
        "SEALAI_V2_MATERIAL_CONSTRAINTS_ENABLED",
        "SEALAI_V2_CASE_DECISION_RECORDS_ENABLED",
        "SEALAI_V2_CAPABILITY_PROFILES_ENABLED",
        "SEALAI_V2_MANUFACTURER_FIT_ENABLED",
        "SEALAI_V2_MANUFACTURER_HANDOFF_ENABLED",
        "SEALAI_V2_AUTH_CAPABILITY_REVIEWER_ROLE",
        "SEALAI_V2_AUTH_KNOWLEDGE_REVIEWER_ROLE",
        "SEALAI_V2_AUTH_DECISION_REVIEWER_ROLE",
    ):
        assert setting in compose


def test_keycloak_provisioning_covers_governed_reviewer_roles() -> None:
    provisioning = (REPO / "ops" / "keycloak_ensure_roles.sh").read_text(
        encoding="utf-8"
    )

    for role in (
        "capability_reviewer",
        "knowledge_reviewer",
        "decision_reviewer",
    ):
        assert f'"{role}"' in provisioning


def test_keycloak_mfa_runs_only_after_user_identification() -> None:
    provisioning = (REPO / "ops" / "keycloak_ensure_roles.sh").read_text(
        encoding="utf-8"
    )

    assert "provider=auth-conditional-otp-form" not in provisioning
    assert '.providerId == "auth-username-password-form"' in provisioning
    assert '.providerId == "conditional-user-configured"' in provisioning
    assert "otp_requirement=DISABLED" in provisioning
    assert "otp_requirement=CONDITIONAL" in provisioning
    assert "'$value | @uri'" in provisioning
    assert "OTP still executes before user identification" in provisioning


def test_keycloak_theme_does_not_hide_password_group_with_remember_me() -> None:
    theme_properties = (
        REPO / "keycloak/themes/sealai-b2b/login/theme.properties"
    ).read_text(encoding="utf-8")
    theme_css = (
        REPO / "keycloak/themes/sealai-b2b/login/resources/css/sealai-b2b-v31.css"
    ).read_text(encoding="utf-8")

    assert "css/sealai-b2b-v31.css" in theme_properties
    assert ".pf-v5-c-form__group:has(.pf-v5-c-check)" not in theme_css
    assert ".pf-v5-c-check {" in theme_css


def test_owner_decisions_and_companion_contracts_are_present() -> None:
    decisions = (SSOT_DIR / "OWNER_DECISION_REGISTER.md").read_text(encoding="utf-8")
    for number in range(1, 9):
        assert f"ODR-{number:02d}" in decisions
    assert "ODR-12: MAT-GOV-03A technical snapshot foundation" in decisions
    assert "ODR-13: MAT-GOV-03B local shadow/pinning implementation" in decisions
    assert "INTERMEDIATE_CLAUDE_GATES_WAIVED_BY_OWNER" in decisions
    assert "sampling remains `0`" in decisions
    assert "creates no activation authority" in decisions

    for name in (
        "INVARIANT_MAPPING.md",
        "PAIN_EVIDENCE_LEDGER.md",
        "INTEROPERABILITY_CHARTER.md",
        "QUALITY_ASSURANCE_PLAN.md",
        "IMPLEMENTATION_AUDIT_2026-07-11.md",
    ):
        assert (SSOT_DIR / name).is_file(), name
