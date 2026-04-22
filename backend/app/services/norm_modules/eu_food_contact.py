from __future__ import annotations

from .base import (
    EscalationPolicy,
    NormCheckContext,
    NormCheckFinding,
    NormCheckResult,
    NormCheckStatus,
    NormModule,
    missing_fields,
)
from .certification import (
    context_text_indicates_food_contact,
    region_matches,
    summarize_certification_evidence,
)


class EuFoodContactModule(NormModule):
    module_id = "norm_eu_food_contact"
    version = "1.0.0"
    references = ("EU 10/2011", "EU 1935/2004")

    _required_fields = [
        "medium_name",
        "sealing_material_family",
        "material_name",
        "temperature_c",
        "cleaning_regime",
    ]
    _accepted_standards = ("EU 10/2011", "EU 1935/2004", "EC 1935/2004")

    def applies_to(self, context: NormCheckContext) -> bool:
        return context_text_indicates_food_contact(context) and (
            region_matches(context, {"eu", "europe", "european_union"})
            or str(context.get("food_contact_region") or "").strip().lower() in {"", "unknown"}
        )

    def required_fields(self) -> list[str]:
        return list(self._required_fields)

    def escalation_policy(self) -> EscalationPolicy:
        return EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW

    def check(self, context: NormCheckContext) -> NormCheckResult:
        if not self.applies_to(context):
            return NormCheckResult(
                module_id=self.module_id,
                version=self.version,
                status=NormCheckStatus.NOT_APPLICABLE,
                applies=False,
                escalation=EscalationPolicy.OUT_OF_SCOPE,
                references=self.references,
            )

        missing = missing_fields(context, self.required_fields())
        if missing:
            return NormCheckResult(
                module_id=self.module_id,
                version=self.version,
                status=NormCheckStatus.INSUFFICIENT_DATA,
                applies=True,
                missing_required_fields=missing,
                escalation=EscalationPolicy.BLOCK_UNTIL_MISSING_FIELDS,
                references=self.references,
                findings=(
                    NormCheckFinding(
                        code="eu_food_contact_missing_required_fields",
                        message="EU food-contact precheck requires medium, material, temperature, and cleaning-regime context.",
                        severity="blocking",
                    ),
                ),
            )

        evidence = summarize_certification_evidence(context, self._accepted_standards)
        if evidence.has_negative_evidence:
            return NormCheckResult(
                module_id=self.module_id,
                version=self.version,
                status=NormCheckStatus.FAIL,
                applies=True,
                escalation=EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW,
                references=self.references,
                findings=(
                    NormCheckFinding(
                        code="eu_food_contact_negative_evidence",
                        message="Context explicitly indicates missing or invalid EU food-contact certification.",
                        severity="error",
                        field="certification_records",
                    ),
                ),
            )

        findings = []
        if not evidence.has_positive_evidence:
            findings.append(
                NormCheckFinding(
                    code="eu_food_contact_evidence_missing",
                    message="No EU 10/2011 or EU 1935/2004 evidence record is present.",
                    severity="review",
                    field="certification_records",
                )
            )
        if not evidence.has_manufacturer_declaration:
            findings.append(
                NormCheckFinding(
                    code="eu_food_contact_declaration_missing",
                    message="Manufacturer declaration for food-contact use is missing.",
                    severity="review",
                    field="manufacturer_declaration_present",
                )
            )
        if not evidence.has_traceability:
            findings.append(
                NormCheckFinding(
                    code="eu_food_contact_traceability_missing",
                    message="Traceability for the certified grade or batch is missing.",
                    severity="review",
                    field="traceability_present",
                )
            )
        if not evidence.has_migration_test:
            findings.append(
                NormCheckFinding(
                    code="eu_food_contact_migration_test_missing",
                    message="Migration-test evidence is missing; manufacturer review is required.",
                    severity="review",
                    field="migration_test_available",
                )
            )

        if findings:
            return NormCheckResult(
                module_id=self.module_id,
                version=self.version,
                status=NormCheckStatus.REVIEW_REQUIRED,
                applies=True,
                escalation=EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW,
                references=self.references,
                findings=tuple(findings),
            )

        return NormCheckResult(
            module_id=self.module_id,
            version=self.version,
            status=NormCheckStatus.PASS,
            applies=True,
            escalation=EscalationPolicy.NO_ESCALATION,
            references=self.references,
            findings=(
                NormCheckFinding(
                    code="eu_food_contact_minimal_evidence_present",
                    message=(
                        "Minimal EU food-contact evidence is present; this is not a final legal "
                        "or manufacturer release."
                    ),
                ),
            ),
        )
