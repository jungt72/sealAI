"""0B.2: Coverage/Boundary Communication — narrative projection hardening.

Verifies that:
  - coverage_scope is empty without policy_context (fast paths stay lean)
  - guided partial path → coverage_boundary item present with medium severity
  - escalation_reason present → escalation_context item present
  - no escalation_reason → no escalation_context item
  - in_scope qualified → no coverage_boundary item (clean fast path)
  - orientation_only → medium-severity coverage_boundary
  - governed_summary is prefixed for guided downgrade paths
  - governed_summary is NOT prefixed for in-scope qualified paths
  - VisibleCaseNarrativeResponse accepts coverage_scope field
  - out_of_scope produces high-severity coverage_boundary
"""
import pytest

from app.agent.case_state import build_visible_case_narrative, _build_visible_coverage_scope
from app.agent.api.models import VisibleCaseNarrativeResponse, VisibleCaseNarrativeItemResponse

# ── Minimal state fixture ────────────────────────────────────────────────────

_MINIMAL_STATE: dict = {
    "messages": [],
    "sealing_state": {},
    "working_profile": {},
    "case_state": None,
}

_MINIMAL_CASE_STATE: dict = {
    "qualification_results": {},
    "result_contract": {
        "binding_level": "ORIENTATION",
        "rfq_admissibility": "inadmissible",
        "release_status": "inadmissible",
        "specificity_level": "family_only",
        "contract_obsolete": False,
        "invalidation_requires_recompute": False,
        "invalidation_reasons": [],
        "qualified_action": {
            "action": "none",
            "allowed": False,
            "rfq_ready": False,
            "binding_level": "ORIENTATION",
            "summary": "qualified_action_blocked",
            "block_reasons": [],
        },
        "evidence_ref_count": 0,
        "evidence_refs": [],
        "source_ref": "test",
    },
    "readiness": {},
    "invalidation_state": {},
    "qualified_action_gate": {"allowed": False, "block_reasons": [], "binding_level": "ORIENTATION", "summary": "blocked"},
    "case_meta": {"binding_level": "ORIENTATION"},
}


# ── 1. Empty coverage_scope without policy_context ───────────────────────────

def test_coverage_scope_empty_without_policy_context():
    """Fast paths without policy_context must produce an empty coverage_scope."""
    result = build_visible_case_narrative(
        state=_MINIMAL_STATE,
        case_state=_MINIMAL_CASE_STATE,
        binding_level="ORIENTATION",
        policy_context=None,
    )
    assert result["coverage_scope"] == []


def test_coverage_scope_builder_returns_empty_for_none():
    assert _build_visible_coverage_scope(None) == []


# ── 2. Guided partial path — coverage_boundary present ──────────────────────

def test_partial_coverage_produces_coverage_boundary_item():
    policy_context = {"coverage_status": "partial", "boundary_flags": [], "escalation_reason": None, "required_fields": []}
    items = _build_visible_coverage_scope(policy_context)
    keys = [item["key"] for item in items]
    assert "coverage_boundary" in keys


def test_partial_coverage_boundary_has_medium_severity():
    policy_context = {"coverage_status": "partial", "boundary_flags": [], "escalation_reason": None, "required_fields": []}
    items = _build_visible_coverage_scope(policy_context)
    boundary = next(item for item in items if item["key"] == "coverage_boundary")
    assert boundary["severity"] == "medium"


def test_partial_coverage_boundary_flags_appear_in_detail():
    policy_context = {
        "coverage_status": "partial",
        "boundary_flags": ["missing_pressure", "missing_temperature"],
        "escalation_reason": None,
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    boundary = next(item for item in items if item["key"] == "coverage_boundary")
    assert boundary["detail"] is not None
    assert "pressure" in boundary["detail"].lower() or "missing" in boundary["detail"].lower()


# ── 3. escalation_reason → escalation_context item ──────────────────────────

def test_escalation_reason_produces_escalation_context_item():
    policy_context = {
        "coverage_status": "partial",
        "boundary_flags": [],
        "escalation_reason": "missing_operating_conditions",
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    keys = [item["key"] for item in items]
    assert "escalation_context" in keys


def test_no_escalation_reason_produces_no_escalation_context():
    policy_context = {"coverage_status": "partial", "boundary_flags": [], "escalation_reason": None, "required_fields": []}
    items = _build_visible_coverage_scope(policy_context)
    keys = [item["key"] for item in items]
    assert "escalation_context" not in keys


# ── 4. in_scope → no coverage_boundary when no flags ────────────────────────

def test_in_scope_without_flags_produces_no_coverage_boundary():
    """Clean in-scope with no flags: fast path stays lean, no item emitted."""
    policy_context = {"coverage_status": "in_scope", "boundary_flags": [], "escalation_reason": None, "required_fields": []}
    items = _build_visible_coverage_scope(policy_context)
    keys = [item["key"] for item in items]
    assert "coverage_boundary" not in keys


def test_in_scope_with_flags_produces_low_severity_boundary():
    """in-scope but with boundary flags: low-severity note emitted."""
    policy_context = {
        "coverage_status": "in_scope",
        "boundary_flags": ["edge_case_compound"],
        "escalation_reason": None,
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    keys = [item["key"] for item in items]
    assert "coverage_boundary" in keys
    boundary = next(item for item in items if item["key"] == "coverage_boundary")
    assert boundary["severity"] == "low"


# ── 5. orientation_only → medium severity ───────────────────────────────────

def test_orientation_only_produces_medium_severity():
    policy_context = {"coverage_status": "orientation_only", "boundary_flags": [], "escalation_reason": None, "required_fields": []}
    items = _build_visible_coverage_scope(policy_context)
    boundary = next((item for item in items if item["key"] == "coverage_boundary"), None)
    assert boundary is not None
    assert boundary["severity"] == "medium"


# ── 6. out_of_scope → high severity ─────────────────────────────────────────

def test_out_of_scope_produces_high_severity():
    policy_context = {"coverage_status": "out_of_scope", "boundary_flags": [], "escalation_reason": None, "required_fields": []}
    items = _build_visible_coverage_scope(policy_context)
    boundary = next((item for item in items if item["key"] == "coverage_boundary"), None)
    assert boundary is not None
    assert boundary["severity"] == "high"


# ── 7. governed_summary prefix for downgrade path ───────────────────────────

def test_governed_summary_prefixed_for_partial_coverage():
    result = build_visible_case_narrative(
        state=_MINIMAL_STATE,
        case_state=_MINIMAL_CASE_STATE,
        binding_level="ORIENTATION",
        policy_context={"coverage_status": "partial", "boundary_flags": [], "escalation_reason": None, "required_fields": []},
    )
    assert result["governed_summary"].startswith("[Teilweise abgedeckt]")


def test_governed_summary_prefixed_for_orientation_only():
    result = build_visible_case_narrative(
        state=_MINIMAL_STATE,
        case_state=_MINIMAL_CASE_STATE,
        binding_level="ORIENTATION",
        policy_context={"coverage_status": "orientation_only", "boundary_flags": [], "escalation_reason": None, "required_fields": []},
    )
    assert result["governed_summary"].startswith("[Nur Orientierung]")


def test_governed_summary_not_prefixed_for_in_scope():
    """in_scope qualified path — governed_summary must NOT get a coverage prefix."""
    result = build_visible_case_narrative(
        state=_MINIMAL_STATE,
        case_state=_MINIMAL_CASE_STATE,
        binding_level="ORIENTATION",
        policy_context={"coverage_status": "in_scope", "boundary_flags": [], "escalation_reason": None, "required_fields": []},
    )
    assert not result["governed_summary"].startswith("[")


def test_governed_summary_not_prefixed_without_policy_context():
    result = build_visible_case_narrative(
        state=_MINIMAL_STATE,
        case_state=_MINIMAL_CASE_STATE,
        binding_level="ORIENTATION",
        policy_context=None,
    )
    assert not result["governed_summary"].startswith("[")


def test_governed_summary_escalation_suffix_appended():
    result = build_visible_case_narrative(
        state=_MINIMAL_STATE,
        case_state=_MINIMAL_CASE_STATE,
        binding_level="ORIENTATION",
        policy_context={
            "coverage_status": "partial",
            "boundary_flags": [],
            "escalation_reason": "missing_operating_conditions",
            "required_fields": [],
        },
    )
    assert "Eskalation:" in result["governed_summary"]


# ── 8. VisibleCaseNarrativeResponse accepts coverage_scope ──────────────────

def test_response_model_accepts_coverage_scope_field():
    narrative = VisibleCaseNarrativeResponse(
        governed_summary="Test summary.",
        coverage_scope=[
            VisibleCaseNarrativeItemResponse(
                key="coverage_boundary",
                label="Coverage Boundary",
                value="Teilweise abgedeckt",
                severity="medium",
            )
        ],
    )
    assert len(narrative.coverage_scope) == 1
    assert narrative.coverage_scope[0].key == "coverage_boundary"


def test_response_model_coverage_scope_defaults_to_empty():
    narrative = VisibleCaseNarrativeResponse(governed_summary="Test.")
    assert narrative.coverage_scope == []


# ── 9. Max item count — never exceeds 2 ─────────────────────────────────────

def test_coverage_scope_max_two_items():
    """coverage_scope must never emit more than 2 items."""
    policy_context = {
        "coverage_status": "out_of_scope",
        "boundary_flags": ["flag_a", "flag_b"],
        "escalation_reason": "requires_expert_review",
        "required_fields": ["pressure", "temperature"],
    }
    items = _build_visible_coverage_scope(policy_context)
    assert len(items) <= 2
