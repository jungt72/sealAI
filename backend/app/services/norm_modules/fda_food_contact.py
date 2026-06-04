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


class FdaFoodContactModule(NormModule):
    module_id = "norm_fda_food_contact"
    version = "1.0.0"
    references = ("FDA 21 CFR 177.1550", "FDA 21 CFR 177.2600")

    _required_fields = [
        "medium_name",
        "sealing_material_family",
        "material_name",
        "temperature_c",
        "intended_us_market",
    ]
    _accepted_standards = ("FDA 21 CFR 177.1550", "FDA 21 CFR 177.2600", "21 CFR 177")

    def applies_to(self, context: NormCheckContext) -> bool:
        return context_text_indicates_food_contact(context) and (
            region_matches(context, {"us", "usa", "united_states", "fda"})
            or bool(context.get("intended_us_market"))
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
                        code="fda_food_contact_missing_required_fields",
                        message="FDA food-contact precheck requires medium, material, temperature, and US-market context.",
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
                        code="fda_food_contact_negative_evidence",
                        message="Context explicitly indicates missing or invalid FDA food-contact certification.",
                        severity="error",
                        field="certification_records",
                    ),
                ),
            )

        findings = []
        if not evidence.has_positive_evidence:
            findings.append(
                NormCheckFinding(
                    code="fda_food_contact_evidence_missing",
                    message="No FDA 21 CFR food-contact evidence record is present.",
                    severity="review",
                    field="certification_records",
                )
            )
        if not evidence.has_manufacturer_declaration:
            findings.append(
                NormCheckFinding(
                    code="fda_food_contact_declaration_missing",
                    message="Manufacturer declaration for FDA food-contact use is missing.",
                    severity="review",
                    field="manufacturer_declaration_present",
                )
            )
        if not evidence.has_traceability:
            findings.append(
                NormCheckFinding(
                    code="fda_food_contact_traceability_missing",
                    message="Traceability for the FDA-relevant grade or batch is missing.",
                    severity="review",
                    field="traceability_present",
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
                    code="fda_food_contact_minimal_evidence_present",
                    message=(
                        "Minimal FDA food-contact evidence is present; this is not a final "
                        "regulatory or manufacturer release."
                    ),
                ),
            ),
        )
