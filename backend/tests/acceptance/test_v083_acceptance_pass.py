from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EVENT_MODEL = REPO_ROOT / "docs" / "implementation" / "event_model"


@dataclass(frozen=True)
class SliceEvidence:
    gwt_ids: tuple[str, ...]
    files: tuple[tuple[str, tuple[str, ...]], ...]


CORE_SLICE_EVIDENCE: dict[str, SliceEvidence] = {
    "S-CONV-001": SliceEvidence(
        gwt_ids=("GWT-CONV-001",),
        files=(
            (
                "backend/tests/unit/services/test_v083_conversation_routing.py",
                ("test_greeting_routes_to_frontdoor_without_governed_case_intake", "fast_responder"),
            ),
        ),
    ),
    "S-KNOW-001": SliceEvidence(
        gwt_ids=("GWT-CONV-002",),
        files=(
            (
                "backend/tests/unit/services/test_knowledge_answer_rag_first.py",
                ("test_was_ist_fkm_stays_general_knowledge_not_governed_case_intake", "no_case_created"),
            ),
        ),
    ),
    "S-TRIAGE-001": SliceEvidence(
        gwt_ids=("GWT-CONV-003",),
        files=(
            (
                "backend/tests/unit/services/test_v083_conversation_routing.py",
                ("Diese Dichtung leckt schon wieder", "empathic_triage"),
            ),
        ),
    ),
    "S-CASE-001": SliceEvidence(
        gwt_ids=("GWT-CASE-001",),
        files=(
            (
                "backend/tests/unit/domain/test_case_type.py",
                ("ConversationIntent.new_rfq", "CaseType.new_rfq"),
            ),
        ),
    ),
    "S-SEAL-001": SliceEvidence(
        gwt_ids=("GWT-SEAL-001",),
        files=(
            (
                "backend/tests/unit/domain/test_seal_type.py",
                ("radial_shaft_seal", "Simmerring"),
            ),
        ),
    ),
    "S-UPLOAD-001": SliceEvidence(
        gwt_ids=("GWT-UPLOAD-001", "GWT-UPLOAD-003"),
        files=(
            (
                "frontend/src/lib/ragRedaction.spec.ts",
                ("redacts unix", "sanitizeRagPayload"),
            ),
            (
                "frontend/src/components/rag/RagDocumentGrid.test.tsx",
                ("Evidence-Kandidat", "nicht automatisch bestaetigt"),
            ),
        ),
    ),
    "S-RAG-001": SliceEvidence(
        gwt_ids=("GWT-RAG-001", "GWT-RAG-002", "GWT-RAG-003"),
        files=(
            (
                "backend/tests/unit/services/test_knowledge_answer_rag_first.py",
                ("rag_verified", "test_rag_miss_does_not_call_llm_fallback"),
            ),
        ),
    ),
    "S-FALLBACK-001": SliceEvidence(
        gwt_ids=("GWT-RAG-004", "GWT-RAG-005", "GWT-RAG-006"),
        files=(
            (
                "backend/tests/unit/services/test_knowledge_llm_fallback.py",
                ("llm_research_fallback", "unvalidated", "not_final_release"),
            ),
            (
                "frontend/src/components/dashboard/DecisionUnderstandingPanel.test.tsx",
                ("LLM-Recherche ist nicht validiert", "validationStatus: \"unvalidated\""),
            ),
        ),
    ),
    "S-RFQ-001": SliceEvidence(
        gwt_ids=("GWT-RFQ-001", "GWT-RFQ-002"),
        files=(
            (
                "backend/tests/unit/services/test_rfq_preview_service.py",
                ("RFQ_PREVIEW_SECTIONS", "rfq_freeze", "stale"),
            ),
        ),
    ),
    "S-CONSENT-001": SliceEvidence(
        gwt_ids=("GWT-RFQ-003", "GWT-RFQ-004", "GWT-RFQ-005"),
        files=(
            (
                "backend/tests/unit/services/test_rfq_preview_service.py",
                ("user_acknowledged_no_final_release", "ExportBlocked", "ExternalDispatchBlocked"),
            ),
        ),
    ),
    "S-MATCH-001": SliceEvidence(
        gwt_ids=("GWT-MATCH-001", "GWT-MATCH-002", "GWT-MATCH-004", "GWT-MATCH-005"),
        files=(
            (
                "backend/tests/unit/services/test_manufacturer_fit_matrix.py",
                ("test_unpaid_perfect_partner_is_excluded", "PARTNER_NETWORK_DISCLOSURE"),
            ),
            (
                "frontend/src/components/dashboard/ManufacturerFitPanel.test.tsx",
                ("Partnernetzwerk", "An Hersteller senden"),
            ),
        ),
    ),
    "S-MATCH-002": SliceEvidence(
        gwt_ids=("GWT-MATCH-003", "GWT-MATCH-005"),
        files=(
            (
                "backend/tests/unit/services/test_manufacturer_fit_matrix.py",
                ("test_no_fit_state_is_supported_with_disclosure", "no_suitable_partner"),
            ),
        ),
    ),
    "S-COMPAT-001": SliceEvidence(
        gwt_ids=("GWT-SUPPORT-001", "GWT-SUPPORT-002"),
        files=(
            (
                "backend/tests/unit/services/test_compatibility_inquiry.py",
                ("compatibility_inquiry", "hersteller- oder compoundpruefung erforderlich"),
            ),
        ),
    ),
    "S-COMPLAINT-001": SliceEvidence(
        gwt_ids=("GWT-SUPPORT-004",),
        files=(
            (
                "backend/tests/unit/services/test_complaint_failure_intake_service.py",
                ("complaint_case", "liability"),
            ),
            (
                "backend/tests/unit/services/test_support_artifact_service.py",
                ("test_support_artifacts_contain_no_liability_or_final_claim", "customer_reply_draft"),
            ),
        ),
    ),
    "S-FAILURE-001": SliceEvidence(
        gwt_ids=("GWT-SUPPORT-003",),
        files=(
            (
                "backend/tests/unit/services/test_complaint_failure_intake_service.py",
                ("failure_analysis", "confirmed_cause"),
            ),
        ),
    ),
    "S-REPLACE-001": SliceEvidence(
        gwt_ids=("GWT-CASE-006",),
        files=(
            (
                "backend/tests/unit/services/test_replacement_legacy_part_service.py",
                ("replacement_reorder", "identity_confidence"),
            ),
        ),
    ),
    "S-LEGACY-001": SliceEvidence(
        gwt_ids=("GWT-SEAL-005",),
        files=(
            (
                "backend/tests/unit/services/test_replacement_legacy_part_service.py",
                ("unknown_legacy_part", "identity_confidence"),
            ),
        ),
    ),
    "S-CERT-001": SliceEvidence(
        gwt_ids=("GWT-CERT-001",),
        files=(
            (
                "backend/tests/unit/services/test_compliance_certificate_checklist_service.py",
                ("compliance_certificate_request", "required_missing"),
            ),
        ),
    ),
    "S-EMERGENCY-001": SliceEvidence(
        gwt_ids=("GWT-CASE-007",),
        files=(
            (
                "backend/tests/unit/services/test_shallow_mode_intake_service.py",
                ("emergency_mro", "next_question.count(\"?\") == 1"),
            ),
        ),
    ),
    "S-DRAWING-001": SliceEvidence(
        gwt_ids=("GWT-DRAWING-001",),
        files=(
            (
                "backend/tests/unit/services/test_shallow_mode_intake_service.py",
                ("drawing_review", "candidate_review"),
            ),
        ),
    ),
    "S-QUOTE-001": SliceEvidence(
        gwt_ids=("GWT-QUOTE-001",),
        files=(
            (
                "backend/tests/unit/services/test_shallow_mode_intake_service.py",
                ("quote_comparison", "does_not_recommend_cheapest"),
            ),
        ),
    ),
    "S-SUBST-001": SliceEvidence(
        gwt_ids=("GWT-SUBST-001",),
        files=(
            (
                "backend/tests/unit/services/test_shallow_mode_intake_service.py",
                ("material_substitution", "Hersteller- oder Compoundpruefung"),
            ),
        ),
    ),
}


CRITICAL_FIELD_MATRIX_ROWS = (
    "source_type",
    "validation_status",
    "llm_fallback_answer",
    "fallback_label",
    "rfq_case_revision",
    "consent_no_final_release",
    "consent_open_points_understood",
    "consent_export_intent",
    "export_allowed",
    "active_paid",
    "fit_score",
    "partner_network_disclosure",
    "artifact_status",
    "stale_status",
)


PRODUCT_COPY_FILES = (
    "backend/app/templates/rfq_template.html",
    "backend/app/api/v1/renderers/rfq_html.py",
    "frontend/src/components/dashboard/DecisionUnderstandingPanel.tsx",
    "frontend/src/components/dashboard/ManufacturerFitPanel.tsx",
    "frontend/src/components/dashboard/RfqPane.tsx",
)


FORBIDDEN_PRODUCT_COPY = (
    "validated engineering state",
    "based on validated",
    "final freigegeben",
    "garantiert passend",
    "sicher passend",
    "an hersteller senden",
    "sent to manufacturer",
    "automatic dispatch",
    "manufacturer approval",
    "best manufacturer",
)


def _read(path: str | Path) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_active_v083_ssot_files_exist() -> None:
    required = (
        "AGENTS.md",
        "docs/implementation/SEALAI_V08_3_EVENT_MODELED_CODEX_IMPLEMENTATION_CONCEPT.md",
        "docs/implementation/SEALAI_V08_2_STACK_AUDIT_IST.md",
        "docs/implementation/SEALAI_V08_3_IMPLEMENTATION_ROADMAP_FROM_AUDIT.md",
        "docs/implementation/SEALAI_PILOT_READINESS_IMPLEMENTATION_CONCEPT.md",
        "docs/implementation/event_model/00_method.md",
        "docs/implementation/event_model/03_scenario_slices.md",
        "docs/implementation/event_model/04_field_origin_destination_matrix.md",
        "docs/implementation/event_model/06_security_boundary_map.md",
        "docs/implementation/event_model/07_gwt_specs.md",
    )

    missing = [path for path in required if not (REPO_ROOT / path).is_file()]

    assert missing == [], missing


def test_core_slices_have_gwt_specs_and_current_test_evidence() -> None:
    scenario_slices = _read(EVENT_MODEL / "03_scenario_slices.md")
    gwt_specs = _read(EVENT_MODEL / "07_gwt_specs.md")

    missing: list[str] = []

    for slice_id, evidence in CORE_SLICE_EVIDENCE.items():
        if f"## {slice_id}" not in scenario_slices:
            missing.append(f"{slice_id}: missing scenario slice")
            continue

        section = scenario_slices.split(f"## {slice_id}", 1)[1].split("\n## ", 1)[0]
        for required_phrase in ("Command", "Events", "Views", "Forbidden side effects", "Given-When-Then tests"):
            if required_phrase not in section:
                missing.append(f"{slice_id}: missing {required_phrase}")

        for gwt_id in evidence.gwt_ids:
            if gwt_id not in gwt_specs:
                missing.append(f"{slice_id}: missing {gwt_id}")

        for relative_path, tokens in evidence.files:
            test_file = REPO_ROOT / relative_path
            if not test_file.is_file():
                missing.append(f"{slice_id}: missing test file {relative_path}")
                continue

            content = test_file.read_text(encoding="utf-8")
            for token in tokens:
                if token not in content:
                    missing.append(f"{slice_id}: {relative_path} missing token {token!r}")

    assert missing == [], missing


def test_origin_destination_matrix_covers_critical_acceptance_fields() -> None:
    matrix = _read(EVENT_MODEL / "04_field_origin_destination_matrix.md")
    missing: list[str] = []

    for field in CRITICAL_FIELD_MATRIX_ROWS:
        row_prefix = f"| {field} |"
        if row_prefix not in matrix:
            missing.append(f"{field}: missing matrix row")
            continue
        row = next(line for line in matrix.splitlines() if line.startswith(row_prefix))
        if row.count("|") < 9:
            missing.append(f"{field}: incomplete origin/destination row")
        if row.rstrip().endswith("|  |") or "Must never be used for" in row:
            missing.append(f"{field}: missing explicit forbidden-use boundary")

    assert missing == [], missing


def test_security_boundary_map_covers_acceptance_risk_gates() -> None:
    boundary_map = _read(EVENT_MODEL / "06_security_boundary_map.md")
    required_boundaries = (
        "Tenant isolation",
        "Upload/document IP safety",
        "LLM fallback not validated",
        "RFQ consent",
        "RFQ export",
        "No automatic dispatch",
        "Partner-network disclosure",
        "No paid technical ranking",
        "Compliance overclaim prevention",
        "Support/complaint liability boundary",
        "Path redaction",
        "Secret handling",
    )

    missing = [boundary for boundary in required_boundaries if boundary not in boundary_map]

    assert missing == [], missing


def test_product_copy_avoids_final_release_validation_and_dispatch_claims() -> None:
    violations: list[str] = []

    for relative_path in PRODUCT_COPY_FILES:
        source = _read(relative_path).casefold()
        for phrase in FORBIDDEN_PRODUCT_COPY:
            if phrase.casefold() in source:
                violations.append(f"{relative_path}: {phrase}")

    assert violations == [], violations


def test_acceptance_gate_itself_tracks_v083_required_outcomes() -> None:
    roadmap = _read("docs/implementation/SEALAI_V08_3_IMPLEMENTATION_ROADMAP_FROM_AUDIT.md")
    required_outcomes = (
        "alle Kernflows haben Slice",
        "alle Kernflows haben Tests",
        "keine unvalidierte LLM-Info wird Wahrheit",
        "keine unsafe Copy",
        "kein Matching ohne Disclosure",
        "kein Export ohne Consent",
        "kein Cross-Tenant-Leak",
    )

    missing = [outcome for outcome in required_outcomes if outcome not in roadmap]

    assert missing == [], missing
