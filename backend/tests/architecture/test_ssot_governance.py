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
                for marker in ("codex", "llm", "model", "agent")
            )


def test_runtime_maturity_projection_matches_governance_manifest() -> None:
    runtime_manifest = json.loads(
        (REPO / "backend" / "sealai_v2" / "config" / "product_maturity.json").read_text(
            encoding="utf-8"
        )
    )

    assert runtime_manifest == _json("product-maturity.json")


def test_governed_runtime_flags_are_allowlisted_into_production_compose() -> None:
    compose = (REPO / "docker-compose.deploy.yml").read_text(encoding="utf-8")

    for setting in (
        "SEALAI_V2_KNOWLEDGE_MODE_ENABLED",
        "SEALAI_V2_KNOWLEDGE_REVIEW_ENABLED",
        "SEALAI_V2_COMPATIBILITY_MATRIX_ENABLED",
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


def test_owner_decisions_and_companion_contracts_are_present() -> None:
    decisions = (SSOT_DIR / "OWNER_DECISION_REGISTER.md").read_text(encoding="utf-8")
    for number in range(1, 9):
        assert f"ODR-{number:02d}" in decisions

    for name in (
        "INVARIANT_MAPPING.md",
        "PAIN_EVIDENCE_LEDGER.md",
        "INTEROPERABILITY_CHARTER.md",
        "QUALITY_ASSURANCE_PLAN.md",
        "IMPLEMENTATION_AUDIT_2026-07-11.md",
    ):
        assert (SSOT_DIR / name).is_file(), name
