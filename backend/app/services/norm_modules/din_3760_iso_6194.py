from __future__ import annotations

from typing import Any

from .base import (
    EscalationPolicy,
    NormCheckContext,
    NormCheckFinding,
    NormCheckResult,
    NormCheckStatus,
    NormModule,
    missing_fields,
    to_float,
)


class Din3760Iso6194Module(NormModule):
    module_id = "norm_din_3760_iso_6194"
    version = "1.0.0"
    references = ("DIN 3760", "ISO 6194")

    _required_fields = [
        "engineering_path",
        "shaft_diameter_mm",
        "housing_bore_diameter_mm",
        "seal_width_mm",
        "seal_type",
    ]
    _known_type_designations = {"A", "AS", "B", "BS", "C", "CS"}

    def applies_to(self, context: NormCheckContext) -> bool:
        engineering_path = _norm_text(context.get("engineering_path"))
        if engineering_path == "rwdr":
            return True

        seal_kind = _norm_text(context.get("seal_kind") or context.get("seal_type_family"))
        motion_type = _norm_text(context.get("motion_type"))
        return seal_kind in {"rwdr", "radial_shaft_seal"} or motion_type == "rotary"

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
                findings=(
                    NormCheckFinding(
                        code="din_iso_not_rwdr_scope",
                        message="DIN 3760 / ISO 6194 module only applies to RWDR or rotary shaft seal contexts.",
                    ),
                ),
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
                        code="din_iso_missing_required_fields",
                        message="Required DIN 3760 / ISO 6194 precheck fields are missing.",
                        severity="blocking",
                    ),
                ),
            )

        findings = list(self._geometry_findings(context))
        findings.extend(self._type_findings(context))
        findings.extend(self._review_findings(context))

        if any(finding.severity == "error" for finding in findings):
            status = NormCheckStatus.FAIL
            escalation = EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW
        elif any(finding.severity == "review" for finding in findings):
            status = NormCheckStatus.REVIEW_REQUIRED
            escalation = EscalationPolicy.REQUIRE_MANUFACTURER_REVIEW
        else:
            status = NormCheckStatus.PASS
            escalation = EscalationPolicy.NO_ESCALATION
            findings.append(
                NormCheckFinding(
                    code="din_iso_basic_precheck_passed",
                    message=(
                        "Basic RWDR type and dimensional plausibility precheck passed; "
                        "this is not a final norm conformity or manufacturer release."
                    ),
                )
            )

        return NormCheckResult(
            module_id=self.module_id,
            version=self.version,
            status=status,
            applies=True,
            findings=tuple(findings),
            escalation=escalation,
            references=self.references,
        )

    def _geometry_findings(self, context: NormCheckContext) -> tuple[NormCheckFinding, ...]:
        shaft = to_float(context.get("shaft_diameter_mm"))
        housing = to_float(context.get("housing_bore_diameter_mm"))
        width = to_float(context.get("seal_width_mm"))
        findings: list[NormCheckFinding] = []

        for field_name, value in (
            ("shaft_diameter_mm", shaft),
            ("housing_bore_diameter_mm", housing),
            ("seal_width_mm", width),
        ):
            if value is None:
                findings.append(
                    NormCheckFinding(
                        code="din_iso_numeric_field_invalid",
                        message=f"{field_name} must be a numeric millimetre value.",
                        severity="error",
                        field=field_name,
                    )
                )
            elif value <= 0:
                findings.append(
                    NormCheckFinding(
                        code="din_iso_dimension_not_positive",
                        message=f"{field_name} must be greater than zero.",
                        severity="error",
                        field=field_name,
                    )
                )

        if shaft is not None and housing is not None and shaft > 0 and housing > 0:
            if housing <= shaft:
                findings.append(
                    NormCheckFinding(
                        code="din_iso_housing_not_larger_than_shaft",
                        message="housing_bore_diameter_mm must be larger than shaft_diameter_mm.",
                        severity="error",
                        field="housing_bore_diameter_mm",
                    )
                )

        return tuple(findings)

    def _type_findings(self, context: NormCheckContext) -> tuple[NormCheckFinding, ...]:
        seal_type = _norm_text(context.get("seal_type")).upper()
        if seal_type not in self._known_type_designations:
            return (
                NormCheckFinding(
                    code="din_iso_unknown_type_designation",
                    message="Seal type is not one of the supported DIN/ISO RWDR type designations.",
                    severity="review",
                    field="seal_type",
                ),
            )
        return ()

    def _review_findings(self, context: NormCheckContext) -> tuple[NormCheckFinding, ...]:
        findings: list[NormCheckFinding] = []
        pressure = to_float(context.get("pressure_bar"))
        if pressure is not None and pressure > 0:
            findings.append(
                NormCheckFinding(
                    code="din_iso_pressure_requires_review",
                    message="Pressure-loaded rotary shaft seal cases require manufacturer review.",
                    severity="review",
                    field="pressure_bar",
                )
            )

        shaft_surface = _norm_text(context.get("shaft_surface_finish"))
        if shaft_surface in {"damaged", "grooved", "corroded"}:
            findings.append(
                NormCheckFinding(
                    code="din_iso_counterface_condition_review",
                    message="Counterface condition can invalidate a basic RWDR norm precheck.",
                    severity="review",
                    field="shaft_surface_finish",
                )
            )

        temperature = to_float(context.get("temperature_c"))
        if temperature is not None and abs(temperature) > 260:
            findings.append(
                NormCheckFinding(
                    code="din_iso_temperature_extreme_review",
                    message="Extreme temperature requires material- and manufacturer-specific review.",
                    severity="review",
                    field="temperature_c",
                )
            )

        return tuple(findings)


def _norm_text(value: Any) -> str:
    return str(value or "").strip().lower()
