from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    ContextHintState,
    EvidenceState,
    GovernanceState,
    GovernedSessionState,
    MatchingState,
)
from app.api.v1.projections.case_workspace import (
    project_case_workspace,
    project_case_workspace_from_governed_state,
)


def test_workspace_projection_includes_clarification_communication_context() -> None:
    projection = project_case_workspace(
        {
            "conversation": {"thread_id": "case-123"},
            "working_profile": {
                "engineering_profile": {
                    "medium": "Dampf",
                    "temperature_c": 180,
                },
                "completeness": {
                    "missing_critical_parameters": ["Medium", "Betriebsdruck"],
                },
            },
            "reasoning": {
                "phase": "clarification",
                "state_revision": 2,
            },
            "system": {
                "governance_metadata": {
                    "release_status": "manufacturer_validation_required",
                    "unknowns_release_blocking": [],
                    "unknowns_manufacturer_validation": ["Werkstofffreigabe"],
                    "assumptions_active": [],
                },
                "rfq_admissibility": {
                    "release_status": "manufacturer_validation_required",
                    "status": "manufacturer_validation_required",
                    "blockers": [],
                    "open_points": [],
                },
                "matching_state": {},
                "rfq_state": {},
                "manufacturer_state": {},
            },
        }
    )

    assert projection.communication_context.conversation_phase == "clarification"
    assert projection.communication_context.turn_goal == "clarify_primary_open_point"
    assert projection.communication_context.primary_question == "Koennen Sie Betriebsdruck noch einordnen?"
    assert projection.communication_context.supporting_reason is not None
    assert "Medium: Dampf" in projection.communication_context.confirmed_facts_summary
    assert "Betriebsdruck" in projection.communication_context.open_points_summary
    assert "Medium" not in projection.communication_context.open_points_summary


def test_workspace_projection_exposes_medium_context_as_separate_orienting_slice() -> None:
    projection = project_case_workspace(
        {
            "conversation": {"thread_id": "case-456"},
            "working_profile": {
                "engineering_profile": {"medium": "Salzwasser"},
                "completeness": {"missing_critical_parameters": []},
            },
            "reasoning": {"phase": "recommendation", "state_revision": 4},
            "system": {
                "governance_metadata": {"release_status": "precheck_only"},
                "rfq_admissibility": {"release_status": "precheck_only", "status": "precheck_only"},
                "medium_context": {
                    "medium_label": "Salzwasser",
                    "status": "available",
                    "scope": "orientierend",
                    "summary": "Allgemeiner Medium-Kontext fuer salzhaltige wasserbasierte Anwendungen.",
                    "properties": ["wasserbasiert", "salzhaltig"],
                    "challenges": ["Korrosionsrisiko an Metallkomponenten beachten"],
                    "followup_points": ["Salzkonzentration", "Temperatur"],
                    "confidence": "medium",
                    "source_type": "llm_general_knowledge",
                    "not_for_release_decisions": True,
                    "disclaimer": "Allgemeiner Medium-Kontext, nicht als Freigabe.",
                },
                "matching_state": {},
                "rfq_state": {},
                "manufacturer_state": {},
            },
        }
    )

    assert projection.medium_context.status == "available"
    assert projection.medium_context.medium_label == "Salzwasser"
    assert projection.medium_context.scope == "orientierend"
    assert projection.medium_context.not_for_release_decisions is True


def test_workspace_projection_exposes_live_calc_as_technical_derivation() -> None:
    projection = project_case_workspace(
        {
            "conversation": {"thread_id": "case-456"},
            "working_profile": {
                "engineering_profile": {"medium": "Dampf"},
                "completeness": {"missing_critical_parameters": []},
                "live_calc_tile": {
                    "status": "ok",
                    "v_surface_m_s": 3.93,
                    "pv_value_mpa_m_s": 0.39,
                    "dn_value": 75000,
                    "notes": ["Dn-Wert im Richtbereich."],
                },
            },
            "reasoning": {"phase": "recommendation", "state_revision": 4},
            "system": {
                "governance_metadata": {"release_status": "precheck_only"},
                "rfq_admissibility": {"release_status": "precheck_only", "status": "precheck_only"},
                "matching_state": {},
                "rfq_state": {},
                "manufacturer_state": {},
            },
        }
    )

    assert len(projection.technical_derivations) == 1
    assert projection.technical_derivations[0].calc_type == "rwdr"
    assert projection.technical_derivations[0].v_surface_m_s == 3.93
    assert projection.technical_derivations[0].dn_value == 75000


def test_workspace_projection_exposes_registered_checks_in_cockpit() -> None:
    projection = project_case_workspace(
        {
            "conversation": {"thread_id": "case-checks"},
            "working_profile": {
                "engineering_profile": {
                    "medium": "Oel",
                    "movement_type": "rotary",
                    "installation": "Radialwellendichtring",
                    "shaft_diameter_mm": 50.0,
                    "speed_rpm": 1500.0,
                    "pressure_bar": 1.0,
                },
                "completeness": {"missing_critical_parameters": []},
                "live_calc_tile": {
                    "status": "ok",
                    "v_surface_m_s": 3.93,
                    "pv_value_mpa_m_s": 0.39,
                    "dn_value": 75000,
                    "notes": ["Dn-Wert im Richtbereich."],
                },
            },
            "reasoning": {"phase": "recommendation", "state_revision": 4},
            "system": {
                "governance_metadata": {"release_status": "precheck_only"},
                "rfq_admissibility": {"release_status": "precheck_only", "status": "precheck_only"},
                "matching_state": {},
                "rfq_state": {},
                "manufacturer_state": {},
            },
        }
    )

    checks_by_id = {check.calc_id: check for check in projection.cockpit_view.checks}

    assert projection.cockpit_view.engineering_path == "rwdr"
    assert set(checks_by_id) == {
        "rwdr_circumferential_speed",
        "rwdr_pv_precheck",
        "rwdr_dn_value",
    }
    assert checks_by_id["rwdr_circumferential_speed"].output_key == "v_surface_m_s"
    assert checks_by_id["rwdr_circumferential_speed"].value == 3.93
    assert checks_by_id["rwdr_circumferential_speed"].required_inputs == [
        "shaft_diameter_mm",
        "speed_rpm",
    ]
    assert checks_by_id["rwdr_pv_precheck"].value == 0.39
    assert "not a final effective contact-pressure PV model" in checks_by_id["rwdr_pv_precheck"].guardrails


def test_workspace_projection_exposes_missing_input_fallback_for_registered_checks() -> None:
    projection = project_case_workspace(
        {
            "conversation": {"thread_id": "case-missing-check-inputs"},
            "working_profile": {
                "engineering_profile": {
                    "medium": "Oel",
                    "movement_type": "rotary",
                    "installation": "Radialwellendichtring",
                    "shaft_diameter_mm": 50.0,
                },
                "completeness": {"missing_critical_parameters": []},
            },
            "reasoning": {"phase": "clarification", "state_revision": 4},
            "system": {
                "governance_metadata": {"release_status": "precheck_only"},
                "rfq_admissibility": {"release_status": "precheck_only", "status": "precheck_only"},
                "matching_state": {},
                "rfq_state": {},
                "manufacturer_state": {},
            },
        }
    )

    checks_by_id = {check.calc_id: check for check in projection.cockpit_view.checks}

    assert checks_by_id["rwdr_circumferential_speed"].status == "insufficient_data"
    assert checks_by_id["rwdr_circumferential_speed"].missing_inputs == ["speed_rpm"]
    assert checks_by_id["rwdr_circumferential_speed"].value is None
    assert checks_by_id["rwdr_pv_precheck"].missing_inputs == ["speed_rpm", "pressure_bar"]
    assert checks_by_id["rwdr_pv_precheck"].fallback_behavior == (
        "insufficient_data_when_required_inputs_missing"
    )


def test_workspace_projection_exposes_structured_canonical_parameters() -> None:
    projection = project_case_workspace(
        {
            "conversation": {"thread_id": "case-params"},
            "working_profile": {
                "engineering_profile": {
                    "medium": "Salzwasser",
                    "pressure_bar": 10.0,
                    "temperature_c": 80.0,
                    "sealing_type": "mechanical_seal",
                    "duty_profile": "continuous",
                    "shaft_diameter_mm": 50.0,
                    "speed_rpm": 6000.0,
                    "installation": "rotierende Wellenabdichtung",
                    "movement_type": "rotary",
                    "contamination": "abrasive",
                    "compliance": ["food_contact"],
                    "medium_qualifiers": ["chlorides_or_salinity"],
                },
                "completeness": {"missing_critical_parameters": []},
            },
            "reasoning": {"phase": "recommendation", "state_revision": 4},
            "system": {
                "governance_metadata": {"release_status": "precheck_only"},
                "rfq_admissibility": {"release_status": "precheck_only", "status": "precheck_only"},
                "matching_state": {},
                "rfq_state": {},
                "manufacturer_state": {},
            },
        }
    )

    assert projection.parameters["medium"] == "Salzwasser"
    assert projection.parameters["pressure_bar"] == 10.0
    assert projection.parameters["temperature_c"] == 80.0
    assert projection.parameters["sealing_type"] == "mechanical_seal"
    assert projection.parameters["duty_profile"] == "continuous"
    assert projection.parameters["shaft_diameter_mm"] == 50.0
    assert projection.parameters["speed_rpm"] == 6000.0
    assert projection.parameters["installation"] == "rotierende Wellenabdichtung"
    assert projection.parameters["contamination"] == "abrasive"
    assert projection.parameters["compliance"] == ["food_contact"]
    assert projection.parameters["medium_qualifiers"] == ["chlorides_or_salinity"]
    assert projection.parameters["motion_type"] == "rotary"


def test_workspace_projection_derives_ssot_routing_fields() -> None:
    projection = project_case_workspace(
        {
            "conversation": {"thread_id": "case-routing"},
            "working_profile": {
                "engineering_profile": {
                    "medium": "Salzwasser",
                    "pressure_bar": 6.0,
                    "temperature_c": 35.0,
                    "movement_type": "rotary",
                    "installation": "Chemiepumpe",
                    "geometry_locked": True,
                    "old_part_known": True,
                },
                "completeness": {"coverage_score": 0.7, "missing_critical_parameters": []},
            },
            "reasoning": {"phase": "clarification", "state_revision": 1},
            "system": {
                "governance_metadata": {"release_status": "precheck_only"},
                "rfq_admissibility": {"release_status": "precheck_only", "status": "precheck_only"},
                "matching_state": {},
                "rfq_state": {},
                "manufacturer_state": {},
            },
        }
    )

    assert projection.request_type == "retrofit"
    assert projection.engineering_path == "ms_pump"
    assert projection.cockpit_view.request_type == "retrofit"
    assert projection.cockpit_view.engineering_path == "ms_pump"
    assert [section.section_id for section in projection.cockpit_view.sections] == [
        "core_intake",
        "failure_drivers",
        "geometry_fit",
        "rfq_liability",
    ]
    assert projection.cockpit_view.missing_mandatory_keys == [
        "shaft_diameter_mm",
        "speed_rpm",
        "viscosity",
        "solids_percent",
        "runout_mm",
    ]
    assert projection.cockpit_view.readiness.status == "preliminary"


def test_workspace_projection_exposes_cockpit_property_provenance_when_available() -> None:
    projection = project_case_workspace(
        {
            "conversation": {"thread_id": "case-provenance"},
            "working_profile": {
                "engineering_profile": {
                    "medium": "Salzwasser",
                    "temperature_c": 40.0,
                    "pressure_bar": 5.0,
                },
                "completeness": {"coverage_score": 0.5, "missing_critical_parameters": []},
            },
            "reasoning": {
                "phase": "clarification",
                "parameter_provenance": {"pressure_bar": "user_override"},
                "parameter_confidence": {"pressure_bar": "confirmed"},
            },
            "system": {
                "governance_metadata": {"release_status": "precheck_only"},
                "rfq_admissibility": {"release_status": "precheck_only", "status": "precheck_only"},
                "matching_state": {},
                "rfq_state": {},
                "manufacturer_state": {},
            },
        }
    )

    core_intake = next(section for section in projection.cockpit_view.sections if section.section_id == "core_intake")
    pressure_property = next(prop for prop in core_intake.properties if prop.key == "pressure_bar")

    assert pressure_property.origin == "user_override"
    assert pressure_property.confidence == "confirmed"
    assert pressure_property.is_confirmed is True


def test_governed_workspace_projection_reframes_after_linear_and_medium_correction() -> None:
    projection = project_case_workspace_from_governed_state(
        GovernedSessionState(
            analysis_cycle=3,
            asserted=AssertedState(
                assertions={
                    "medium": AssertedClaim(
                        field_name="medium",
                        asserted_value="Wasser mit Reinigeranteil",
                    ),
                },
                blocking_unknowns=["pressure_bar", "temperature_c"],
            ),
            governance=GovernanceState(
                gov_class="B",
                rfq_admissible=False,
                open_validation_points=["pressure_bar", "temperature_c"],
            ),
            motion_hint=ContextHintState(
                label="linear",
                confidence="high",
                source_turn_ref="turn:3",
                source_turn_index=3,
                source_type="deterministic_text_inference",
            ),
            application_hint=ContextHintState(
                label="linear_sealing",
                confidence="high",
                source_turn_ref="turn:3",
                source_turn_index=3,
                source_type="deterministic_text_inference",
            ),
        ),
        chat_id="case-789",
    )

    assert projection.communication_context.primary_question == "Welche Geometrie oder vorhandene Bauform liegt an der Dichtstelle vor?"
    assert projection.communication_context.confirmed_facts_summary[:3] == [
        "Bewegungsart: linear",
        "Anwendung: lineare Abdichtung",
        "Medium: Wasser mit Reinigeranteil",
    ]
    assert all("Welle" not in item and "RWDR" not in item for item in projection.communication_context.open_points_summary)
    assert projection.rfq_status.rfq_ready is False
    assert projection.partner_matching.matching_ready is False


def test_governed_workspace_projection_exposes_evidence_basis_classes() -> None:
    projection = project_case_workspace_from_governed_state(
        GovernedSessionState(
            asserted=AssertedState(
                assertions={
                    "medium": AssertedClaim(field_name="medium", asserted_value="Salzwasser"),
                    "pressure_bar": AssertedClaim(field_name="pressure_bar", asserted_value=10.0),
                }
            ),
            governance=GovernanceState(
                gov_class="A",
                rfq_admissible=True,
                open_validation_points=[],
            ),
            evidence=EvidenceState(
                evidence_present=True,
                evidence_count=1,
                trusted_sources_present=True,
                source_backed_findings=["medium"],
                deterministic_findings=["pressure_bar"],
                assumption_based_findings=["installation"],
                unresolved_open_points=["missing_source_for_compliance"],
                evidence_gaps=["missing_source_for_compliance"],
            ),
        ),
        chat_id="case-evidence",
    )

    assert projection.evidence_summary.evidence_present is True
    assert projection.evidence_summary.source_backed_findings == ["medium"]
    assert projection.claims_summary.by_origin["evidence"] == 1
    assert projection.claims_summary.by_origin["deterministic"] == 1
    assert projection.governance_status.assumptions_active == ["installation"]
    assert "missing_source_for_compliance" in projection.governance_status.unknowns_manufacturer_validation


def test_governed_workspace_projection_keeps_unreleased_matching_blocked() -> None:
    projection = project_case_workspace_from_governed_state(
        GovernedSessionState(
            governance=GovernanceState(
                gov_class="A",
                rfq_admissible=True,
                open_validation_points=[],
            ),
            matching=MatchingState(
                status="candidate_not_released",
                matchability_status="not_released",
                shortlist_ready=False,
                inquiry_ready=False,
                release_blockers=["demo_matching_catalog"],
                data_source="demo_catalog",
            ),
        ),
        chat_id="case-matching-blocked",
    )

    assert projection.partner_matching.matching_ready is False
    assert projection.partner_matching.shortlist_ready is False
    assert projection.partner_matching.inquiry_ready is False
    assert "demo_matching_catalog" in projection.partner_matching.blocking_reasons
    assert projection.partner_matching.data_source == "demo_catalog"
