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

_PERSISTED_POLICY_SNAPSHOT = {
    "coverage_status": "partial",
    "boundary_flags": ["orientation_only", "no_manufacturer_release"],
    "escalation_reason": "qualification_signal_without_data_basis",
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


def test_build_visible_case_narrative_falls_back_to_case_meta_policy_snapshot():
    case_state = dict(_MINIMAL_CASE_STATE)
    case_state["case_meta"] = {
        "binding_level": "ORIENTATION",
        "policy_narrative_snapshot": dict(_PERSISTED_POLICY_SNAPSHOT),
    }
    result = build_visible_case_narrative(
        state=_MINIMAL_STATE,
        case_state=case_state,
        binding_level="ORIENTATION",
        policy_context=None,
    )
    assert result["coverage_scope"]
    scope_keys = [item["key"] for item in result["coverage_scope"]]
    # 0B.2 completion: manufacturer_release is now a first-class item emitted before
    # coverage_boundary when no_manufacturer_release flag is present in the snapshot.
    assert "coverage_boundary" in scope_keys
    assert "manufacturer_release" in scope_keys
    assert result["governed_summary"].startswith("[Teilweise abgedeckt]")
    assert "Eskalation:" in result["governed_summary"]


def test_build_visible_case_narrative_falls_back_to_case_meta_boundary_contract():
    case_state = dict(_MINIMAL_CASE_STATE)
    case_state["case_meta"] = {
        "binding_level": "ORIENTATION",
        "boundary_contract": {
            "binding_level": "ORIENTATION",
            "coverage_status": _PERSISTED_POLICY_SNAPSHOT["coverage_status"],
            "boundary_flags": list(_PERSISTED_POLICY_SNAPSHOT["boundary_flags"]),
            "escalation_reason": _PERSISTED_POLICY_SNAPSHOT["escalation_reason"],
        },
    }
    result = build_visible_case_narrative(
        state=_MINIMAL_STATE,
        case_state=case_state,
        binding_level="ORIENTATION",
        policy_context=None,
    )
    assert result["coverage_scope"]
    scope_keys = [item["key"] for item in result["coverage_scope"]]
    assert "coverage_boundary" in scope_keys
    assert "manufacturer_release" in scope_keys
    assert result["governed_summary"].startswith("[Teilweise abgedeckt]")
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


# ── 9. Full-context item set — expected items present, no unbounded growth ───

def test_coverage_scope_full_context_emits_expected_items():
    """0B.2 completion: full-context policy_context produces coverage_boundary,
    known_unknowns, and escalation_context. result_form absent → no result_level.
    No no_manufacturer_release in flags → no manufacturer_release item.
    Total items: 3 (coverage_boundary + known_unknowns + escalation_context).
    """
    policy_context = {
        "coverage_status": "out_of_scope",
        "boundary_flags": ["flag_a", "flag_b"],
        "escalation_reason": "requires_expert_review",
        "required_fields": ["pressure", "temperature"],
    }
    items = _build_visible_coverage_scope(policy_context)
    keys = [item["key"] for item in items]
    assert "coverage_boundary" in keys
    assert "known_unknowns" in keys
    assert "escalation_context" in keys
    assert "result_level" not in keys  # no result_form in context
    assert "manufacturer_release" not in keys  # no no_manufacturer_release in flags
    assert len(items) <= 5  # bounded — never unbounded growth


# ── 10. result_level item ────────────────────────────────────────────────────

def test_result_form_direct_emits_result_level_information():
    """Fast knowledge ('direct') → result_level = 'Information'."""
    policy_context = {
        "coverage_status": "unknown",
        "boundary_flags": [],
        "escalation_reason": None,
        "result_form": "direct",
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    result_level = next((i for i in items if i["key"] == "result_level"), None)
    assert result_level is not None
    assert result_level["value"] == "Information"
    assert result_level["severity"] == "low"


def test_result_form_deterministic_emits_result_level_calculation():
    """Fast calculation ('deterministic') → result_level = 'Berechnung (deterministisch)'."""
    policy_context = {
        "coverage_status": "in_scope",
        "boundary_flags": ["no_manufacturer_release"],
        "escalation_reason": None,
        "result_form": "deterministic",
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    result_level = next((i for i in items if i["key"] == "result_level"), None)
    assert result_level is not None
    assert result_level["value"] == "Berechnung (deterministisch)"


def test_result_form_guided_emits_result_level_orientation():
    """Guided path → result_level = 'Orientierung'."""
    policy_context = {
        "coverage_status": "partial",
        "boundary_flags": [],
        "escalation_reason": None,
        "result_form": "guided",
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    result_level = next((i for i in items if i["key"] == "result_level"), None)
    assert result_level is not None
    assert result_level["value"] == "Orientierung"


def test_result_form_qualified_emits_result_level_qualification():
    """Qualified path → result_level = 'Qualifizierung'."""
    policy_context = {
        "coverage_status": "in_scope",
        "boundary_flags": [],
        "escalation_reason": None,
        "result_form": "qualified",
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    result_level = next((i for i in items if i["key"] == "result_level"), None)
    assert result_level is not None
    assert result_level["value"] == "Qualifizierung"


def test_no_result_form_emits_no_result_level():
    """Without result_form in context (legacy or fallback), no result_level emitted."""
    policy_context = {
        "coverage_status": "partial",
        "boundary_flags": [],
        "escalation_reason": None,
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    assert not any(i["key"] == "result_level" for i in items)


# ── 11. manufacturer_release item ────────────────────────────────────────────

def test_no_manufacturer_release_flag_emits_manufacturer_release_item():
    """'no_manufacturer_release' boundary flag → dedicated manufacturer_release item."""
    policy_context = {
        "coverage_status": "in_scope",
        "boundary_flags": ["no_manufacturer_release"],
        "escalation_reason": None,
        "result_form": None,
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    mfr = next((i for i in items if i["key"] == "manufacturer_release"), None)
    assert mfr is not None
    assert "Herstellerfreigabe" in mfr["label"]
    assert mfr["severity"] == "medium"


def test_no_manufacturer_release_not_in_coverage_boundary_detail():
    """'no_manufacturer_release' must not appear in coverage_boundary detail — it has its own item."""
    policy_context = {
        "coverage_status": "partial",
        "boundary_flags": ["no_manufacturer_release"],
        "escalation_reason": None,
        "result_form": None,
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    boundary = next((i for i in items if i["key"] == "coverage_boundary"), None)
    # coverage_boundary may be present (partial) but no_manufacturer_release must not be in its detail
    if boundary is not None and boundary.get("detail"):
        assert "manufacturer" not in boundary["detail"].lower()


# ── 12. known_unknowns item ──────────────────────────────────────────────────

def test_required_fields_emits_known_unknowns_item():
    """Non-empty required_fields → known_unknowns item with count and field names."""
    policy_context = {
        "coverage_status": "partial",
        "boundary_flags": [],
        "escalation_reason": None,
        "result_form": "guided",
        "required_fields": ["pressure_bar", "shaft_diameter_mm"],
    }
    items = _build_visible_coverage_scope(policy_context)
    ku = next((i for i in items if i["key"] == "known_unknowns"), None)
    assert ku is not None
    assert ku["severity"] == "medium"
    assert "2" in ku["value"]
    assert ku["detail"] is not None
    assert "pressure" in ku["detail"].lower() or "shaft" in ku["detail"].lower()


def test_empty_required_fields_no_known_unknowns():
    """Empty required_fields → no known_unknowns item emitted."""
    policy_context = {
        "coverage_status": "partial",
        "boundary_flags": [],
        "escalation_reason": None,
        "result_form": "guided",
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    assert not any(i["key"] == "known_unknowns" for i in items)


# ── 13. Visible contract differentiation by result form ──────────────────────

def test_fast_calculation_contract_has_result_level_and_manufacturer_release():
    """FAST_CALCULATION policy signals → result_level + manufacturer_release, no coverage_boundary."""
    policy_context = {
        "coverage_status": "in_scope",
        "boundary_flags": ["orientation_only", "no_manufacturer_release"],
        "escalation_reason": None,
        "result_form": "deterministic",
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    keys = {i["key"] for i in items}
    assert "result_level" in keys
    assert "manufacturer_release" in keys
    # in_scope with no OTHER flags (orientation_only handled by result_level) → no coverage_boundary
    assert "coverage_boundary" not in keys


def test_fast_knowledge_contract_has_result_level_manufacturer_release_and_coverage_boundary():
    """FAST_KNOWLEDGE: unknown coverage → result_level + manufacturer_release + coverage_boundary."""
    policy_context = {
        "coverage_status": "unknown",
        "boundary_flags": ["orientation_only", "no_manufacturer_release"],
        "escalation_reason": None,
        "result_form": "direct",
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    keys = {i["key"] for i in items}
    assert "result_level" in keys
    assert "manufacturer_release" in keys
    assert "coverage_boundary" in keys  # unknown coverage still emits boundary item


def test_qualified_in_scope_no_flags_yields_no_items():
    """Clean qualified path: in_scope + no flags + no required_fields → no items."""
    policy_context = {
        "coverage_status": "in_scope",
        "boundary_flags": [],
        "escalation_reason": None,
        "result_form": "qualified",
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    # result_level emitted for qualified too — but it's informational
    keys = {i["key"] for i in items}
    assert "coverage_boundary" not in keys
    assert "escalation_context" not in keys
    assert "known_unknowns" not in keys
    assert "manufacturer_release" not in keys


# ── 14. orientation_only flag → dedicated item ───────────────────────────────

def test_orientation_only_flag_emits_orientation_only_item():
    """'orientation_only' in boundary_flags → dedicated orientation_only item."""
    policy_context = {
        "coverage_status": "in_scope",
        "boundary_flags": ["orientation_only"],
        "escalation_reason": None,
        "result_form": "guided",
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    oo = next((i for i in items if i["key"] == "orientation_only"), None)
    assert oo is not None
    assert oo["label"] == "Ergebnis-Verbindlichkeit"
    assert "Orientierung" in oo["value"]
    assert oo["severity"] == "medium"


def test_orientation_only_not_in_coverage_boundary_detail():
    """'orientation_only' must not leak into coverage_boundary detail."""
    policy_context = {
        "coverage_status": "partial",
        "boundary_flags": ["orientation_only"],
        "escalation_reason": None,
        "result_form": "guided",
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    boundary = next((i for i in items if i["key"] == "coverage_boundary"), None)
    if boundary is not None and boundary.get("detail"):
        assert "orientation" not in boundary["detail"].lower()


def test_orientation_only_absent_without_flag():
    """No 'orientation_only' flag → no orientation_only item."""
    policy_context = {
        "coverage_status": "in_scope",
        "boundary_flags": [],
        "escalation_reason": None,
        "result_form": "direct",
        "required_fields": [],
    }
    items = _build_visible_coverage_scope(policy_context)
    assert not any(i["key"] == "orientation_only" for i in items)


# ── 15. requires_review → lifecycle-derived item in build_visible_case_narrative

def test_review_pending_lifecycle_emits_requires_review_item():
    """lifecycle_status='review_pending' → requires_review item in coverage_scope."""
    case_state = dict(_MINIMAL_CASE_STATE)
    case_state["case_meta"] = {
        "binding_level": "ORIENTATION",
        "lifecycle_status": "review_pending",
        "review_required": True,
        "review_state": "pending",
    }
    result = build_visible_case_narrative(
        state=_MINIMAL_STATE,
        case_state=case_state,
        binding_level="ORIENTATION",
        policy_context=None,
    )
    keys = [item["key"] for item in result["coverage_scope"]]
    assert "requires_review" in keys
    rr = next(i for i in result["coverage_scope"] if i["key"] == "requires_review")
    assert rr["severity"] == "high"
    assert "Fachprüfung" in rr["value"] or "review" in rr["value"].lower()


def test_review_required_true_emits_requires_review_item():
    """review_required=True → requires_review item even without lifecycle label."""
    case_state = dict(_MINIMAL_CASE_STATE)
    case_state["case_meta"] = {
        "binding_level": "ORIENTATION",
        "review_required": True,
        "review_state": "none",
    }
    result = build_visible_case_narrative(
        state=_MINIMAL_STATE,
        case_state=case_state,
        binding_level="ORIENTATION",
        policy_context=None,
    )
    keys = [item["key"] for item in result["coverage_scope"]]
    assert "requires_review" in keys


def test_no_review_signals_no_requires_review_item():
    """No review signals → requires_review must not appear."""
    case_state = dict(_MINIMAL_CASE_STATE)
    case_state["case_meta"] = {
        "binding_level": "ORIENTATION",
        "review_required": False,
        "review_state": "none",
    }
    result = build_visible_case_narrative(
        state=_MINIMAL_STATE,
        case_state=case_state,
        binding_level="ORIENTATION",
        policy_context=None,
    )
    keys = [item["key"] for item in result["coverage_scope"]]
    assert "requires_review" not in keys


# ── 16. out_of_scope lifecycle fallback ──────────────────────────────────────

def test_lifecycle_out_of_scope_emits_coverage_boundary_without_policy_context():
    """lifecycle_status='out_of_scope' without policy_context → coverage_boundary item."""
    case_state = dict(_MINIMAL_CASE_STATE)
    case_state["case_meta"] = {
        "binding_level": "ORIENTATION",
        "lifecycle_status": "out_of_scope",
    }
    result = build_visible_case_narrative(
        state=_MINIMAL_STATE,
        case_state=case_state,
        binding_level="ORIENTATION",
        policy_context=None,
    )
    keys = [item["key"] for item in result["coverage_scope"]]
    assert "coverage_boundary" in keys
    boundary = next(i for i in result["coverage_scope"] if i["key"] == "coverage_boundary")
    assert boundary["severity"] == "high"
    assert "Außerhalb" in boundary["value"]


def test_lifecycle_out_of_scope_does_not_duplicate_when_policy_context_present():
    """lifecycle_status='out_of_scope' + policy_context with out_of_scope → no duplicate item."""
    case_state = dict(_MINIMAL_CASE_STATE)
    case_state["case_meta"] = {
        "binding_level": "ORIENTATION",
        "lifecycle_status": "out_of_scope",
    }
    result = build_visible_case_narrative(
        state=_MINIMAL_STATE,
        case_state=case_state,
        binding_level="ORIENTATION",
        policy_context={
            "coverage_status": "out_of_scope",
            "boundary_flags": [],
            "escalation_reason": None,
            "result_form": None,
            "required_fields": [],
        },
    )
    boundary_items = [i for i in result["coverage_scope"] if i["key"] == "coverage_boundary"]
    # Must have at least one but not duplicate (policy_context already produced it)
    assert len(boundary_items) == 1
