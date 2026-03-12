from app.agent.domain.datasheet_contract import (
    AuditContract,
    DataExtractionMethod,
    DataOriginType,
    DatasheetContractV23,
    DatasheetSpecificityLevel,
    DocumentBindingStrength,
    DocumentClass,
    DocumentCollisionStatus,
    DocumentIdentity,
    DocumentMetadata,
    EvidenceStrengthClass,
)


def test_marketing_estimate_never_becomes_release_relevant():
    contract = DatasheetContractV23(
        document_identity=DocumentIdentity(
            source_ref="DOC-1",
            source_type="manufacturer_datasheet",
            source_rank=2,
            document_class=DocumentClass.manufacturer_datasheet,
        ),
        document_metadata=DocumentMetadata(
            manufacturer_name="Acme",
            product_line="G-Series",
            grade_name="G461",
            material_family="PTFE",
            revision_date="2024-01-15",
        ),
        audit=AuditContract(
            document_binding_strength=DocumentBindingStrength.direct_document,
            data_extraction_method=DataExtractionMethod.manual_structured,
            data_origin_type=DataOriginType.marketing_estimate,
            evidence_strength_class=EvidenceStrengthClass.strong,
            context_completeness_score=95,
            audit_gate_passed=True,
        ),
    )

    assert contract.selection_readiness.release_relevant is False
    assert contract.selection_readiness.rfq_ready_eligible is False
    assert "marketing_estimate_never_release_relevant" in contract.selection_readiness.blocking_reasons


def test_distributor_sheet_ceiling_blocks_compound_level_without_linked_grade_sheet():
    contract = DatasheetContractV23(
        document_identity=DocumentIdentity(
            source_ref="DOC-2",
            source_type="distributor_sheet",
            source_rank=2,
            document_class=DocumentClass.distributor_sheet,
        ),
        document_metadata=DocumentMetadata(
            manufacturer_name="Acme",
            product_line="G-Series",
            grade_name="G461",
            material_family="PTFE",
            published_at="2024-01-15",
        ),
        audit=AuditContract(
            document_binding_strength=DocumentBindingStrength.source_registry_bound,
            data_extraction_method=DataExtractionMethod.deterministic_parser,
            data_origin_type=DataOriginType.distributor_sheet,
            evidence_strength_class=EvidenceStrengthClass.qualified,
            context_completeness_score=90,
            audit_gate_passed=True,
        ),
    )

    assert contract.selection_readiness.compound_level_allowed is False
    assert contract.selection_readiness.max_specificity_level == DatasheetSpecificityLevel.subfamily
    assert "distributor_sheet_ceiling_without_manufacturer_grade_sheet" in contract.selection_readiness.blocking_reasons


def test_unresolved_document_collision_disables_selection():
    contract = DatasheetContractV23(
        document_identity=DocumentIdentity(
            source_ref="DOC-3",
            source_type="manufacturer_grade_sheet",
            source_rank=1,
            document_class=DocumentClass.manufacturer_grade_sheet,
        ),
        document_metadata=DocumentMetadata(
            manufacturer_name="Acme",
            grade_name="G461",
            material_family="PTFE",
            document_revision="Rev. 3",
        ),
        audit=AuditContract(
            document_binding_strength=DocumentBindingStrength.direct_document,
            data_extraction_method=DataExtractionMethod.manual_structured,
            data_origin_type=DataOriginType.manufacturer_grade_sheet,
            evidence_strength_class=EvidenceStrengthClass.strong,
            context_completeness_score=95,
            document_collision_status=DocumentCollisionStatus.unresolved,
            audit_gate_passed=True,
        ),
    )

    assert contract.selection_readiness.selection_allowed is False
    assert contract.selection_readiness.rfq_ready_eligible is False
    assert "document_collision_unresolved" in contract.selection_readiness.blocking_reasons


def test_audit_gate_and_color_binding_block_rfq_ready():
    contract = DatasheetContractV23(
        document_identity=DocumentIdentity(
            source_ref="DOC-4",
            source_type="certificate",
            source_rank=1,
            document_class=DocumentClass.certificate,
        ),
        document_metadata=DocumentMetadata(
            manufacturer_name="Acme",
            grade_name="G461",
            material_family="PTFE",
            published_at="2024-01-15",
            certificate_color_dependent=True,
        ),
        audit=AuditContract(
            document_binding_strength=DocumentBindingStrength.direct_document,
            data_extraction_method=DataExtractionMethod.manual_structured,
            data_origin_type=DataOriginType.certificate,
            evidence_strength_class=EvidenceStrengthClass.strong,
            context_completeness_score=95,
            audit_gate_passed=False,
        ),
    )

    assert contract.selection_readiness.compound_level_allowed is True
    assert contract.selection_readiness.release_relevant is False
    assert contract.selection_readiness.rfq_ready_eligible is False
    assert "audit_gate_not_passed" in contract.selection_readiness.blocking_reasons
    assert "color_binding_missing" in contract.selection_readiness.blocking_reasons
