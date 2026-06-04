from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


ADVISORY_DISCLAIMER = "Nicht alle Umstände dieses konkreten Falls konnten berücksichtigt werden."


class AdvisorySeverity(str, Enum):
    INFO = "info"
    CAUTION = "caution"
    WARNING = "warning"


class AdvisoryCategory(str, Enum):
    MATERIAL_SUBOPTIMAL = "material_suboptimal"
    LIFESPAN_EXPECTATION_MISMATCH = "lifespan_expectation_mismatch"
    SHAFT_REQUIREMENTS_CONCERN = "shaft_requirements_concern"
    NORM_COMPLIANCE_ALERT = "norm_compliance_alert"
    DRY_RUN_RISK = "dry_run_risk"
    MEDIUM_INCOMPATIBILITY_HINT = "medium_incompatibility_hint"
    INSTALLATION_CONCERN = "installation_concern"
    QUANTITY_ECONOMIC_CONSIDERATION = "quantity_economic_consideration"


INITIAL_ADVISORY_CATEGORIES: tuple[AdvisoryCategory, ...] = tuple(AdvisoryCategory)


@dataclass(frozen=True, slots=True)
class Advisory:
    advisory_id: str
    category: AdvisoryCategory
    severity: AdvisorySeverity
    title: str
    message: str
    reason_code: str
    triggering_parameters: tuple[str, ...] = ()
    evidence_tags: tuple[str, ...] = ()
    recommended_action: str = ""
    blocking: bool = False
    disclaimer: str = ADVISORY_DISCLAIMER


@dataclass(frozen=True, slots=True)
class AdvisorySummary:
    advisories: tuple[Advisory, ...]
    blocking_count: int
    highest_severity: AdvisorySeverity | None
    categories_present: tuple[AdvisoryCategory, ...]


class AdvisoryEngine:
    """Deterministic advisory core for structured case/capability/norm signals."""

    def evaluate_advisories(self, context: Mapping[str, Any]) -> list[Advisory]:
        advisories: list[Advisory] = []
        for rule in (
            self._material_suboptimal,
            self._missing_critical_input,
            self._norm_review_required,
            self._food_contact_review_required,
            self._atex_capability_gap,
            self._quantity_capability_gap,
            self._geometry_consistency_issue,
            self._dry_run_risk,
            self._operating_envelope_review,
            self._installation_concern,
            self._manufacturer_review_required,
        ):
            advisory = rule(context)
            if advisory is not None:
                advisories.append(advisory)
        return advisories

    def evaluate_advisory_summary(self, context: Mapping[str, Any]) -> AdvisorySummary:
        advisories = tuple(self.evaluate_advisories(context))
        highest = _highest_severity(advisories)
        categories = tuple(dict.fromkeys(advisory.category for advisory in advisories))
        return AdvisorySummary(
            advisories=advisories,
            blocking_count=sum(1 for advisory in advisories if advisory.blocking),
            highest_severity=highest,
            categories_present=categories,
        )

    def _material_suboptimal(self, context: Mapping[str, Any]) -> Advisory | None:
        triggers: list[str] = []
        if bool(context.get("material_suboptimal")):
            triggers.append("material_suboptimal")
        if bool(context.get("material_review_needed")):
            triggers.append("material_review_needed")
        if _sequence(context.get("material_suitability_hints")):
            triggers.append("material_suitability_hints")
        suitability_status = _normalized_text(context.get("material_suitability_status"))
        if suitability_status in {"suboptimal", "review_required", "not_recommended"}:
            triggers.append("material_suitability_status")
        if not triggers:
            return None
        return Advisory(
            advisory_id="adv_material_suboptimal",
            category=AdvisoryCategory.MATERIAL_SUBOPTIMAL,
            severity=AdvisorySeverity.CAUTION,
            title="Material suitability needs review",
            message="Structured material signals indicate that the current material choice may be suboptimal.",
            reason_code="material_suboptimal",
            triggering_parameters=tuple(dict.fromkeys(triggers)),
            evidence_tags=("material_suitability", "case_input"),
            recommended_action="Keep the material choice as a review item until grade-specific evidence is available.",
            blocking=False,
        )

    def _missing_critical_input(self, context: Mapping[str, Any]) -> Advisory | None:
        missing = tuple(str(item) for item in _sequence(context.get("missing_critical_fields")))
        if not missing:
            missing = tuple(str(item) for item in _sequence(context.get("missing_fields")) if item)
        if not missing:
            return None
        return Advisory(
            advisory_id="adv_missing_critical_input",
            category=AdvisoryCategory.SHAFT_REQUIREMENTS_CONCERN,
            severity=AdvisorySeverity.WARNING,
            title="Critical input missing",
            message="Important technical inputs are still missing before the case can be qualified.",
            reason_code="missing_critical_input",
            triggering_parameters=missing,
            evidence_tags=("case_input",),
            recommended_action="Collect the missing fields before treating the case as technically ready.",
            blocking=True,
        )

    def _norm_review_required(self, context: Mapping[str, Any]) -> Advisory | None:
        norm_results = _sequence(context.get("norm_results"))
        flagged = [
            result for result in norm_results
            if _norm_status(result) in {"review_required", "fail", "insufficient_data"}
        ]
        if not flagged:
            return None
        blocking = any(_norm_status(result) in {"fail", "insufficient_data"} for result in flagged)
        modules = tuple(filter(None, (_norm_module_id(result) for result in flagged)))
        return Advisory(
            advisory_id="adv_norm_review_required",
            category=AdvisoryCategory.NORM_COMPLIANCE_ALERT,
            severity=AdvisorySeverity.WARNING if blocking else AdvisorySeverity.CAUTION,
            title="Norm review required",
            message="At least one deterministic norm module requires review or more evidence.",
            reason_code="norm_review_required",
            triggering_parameters=modules,
            evidence_tags=("norm_modules",),
            recommended_action="Resolve missing norm inputs or route the case to manufacturer review.",
            blocking=blocking,
        )

    def _food_contact_review_required(self, context: Mapping[str, Any]) -> Advisory | None:
        if not bool(context.get("food_contact_required")):
            return None
        if bool(context.get("food_contact_evidence_complete")):
            return None
        return Advisory(
            advisory_id="adv_food_contact_review_required",
            category=AdvisoryCategory.NORM_COMPLIANCE_ALERT,
            severity=AdvisorySeverity.CAUTION,
            title="Food-contact evidence needs review",
            message="Food-contact use is indicated, but the structured evidence is incomplete.",
            reason_code="food_contact_review_required",
            triggering_parameters=("food_contact_required", "food_contact_evidence_complete"),
            evidence_tags=("food_contact", "norm_modules"),
            recommended_action="Request grade-specific EU/FDA declarations and traceability before release.",
            blocking=False,
        )

    def _atex_capability_gap(self, context: Mapping[str, Any]) -> Advisory | None:
        if not bool(context.get("atex_required")):
            return None
        if bool(context.get("has_atex_capable_claim")):
            return None
        return Advisory(
            advisory_id="adv_atex_capability_gap",
            category=AdvisoryCategory.NORM_COMPLIANCE_ALERT,
            severity=AdvisorySeverity.WARNING,
            title="ATEX capability claim missing",
            message="The case indicates ATEX relevance, but no ATEX-capable manufacturer claim is available.",
            reason_code="atex_capability_gap",
            triggering_parameters=("atex_required", "has_atex_capable_claim"),
            evidence_tags=("manufacturer_capability_claims",),
            recommended_action="Use ATEX as a hard capability prefilter and request manufacturer confirmation.",
            blocking=True,
        )

    def _quantity_capability_gap(self, context: Mapping[str, Any]) -> Advisory | None:
        quantity = _to_int(context.get("quantity_requested"))
        if quantity is None:
            return None
        if bool(context.get("quantity_capability_available")):
            return None
        minimum = _to_int(context.get("minimum_order_pieces"))
        triggers = ["quantity_requested", "quantity_capability_available"]
        if minimum is not None:
            triggers.append("minimum_order_pieces")
        return Advisory(
            advisory_id="adv_quantity_capability_gap",
            category=AdvisoryCategory.QUANTITY_ECONOMIC_CONSIDERATION,
            severity=AdvisorySeverity.WARNING if quantity <= 10 else AdvisorySeverity.CAUTION,
            title="Quantity capability gap",
            message="Requested quantity is not covered by the available manufacturer capability signal.",
            reason_code="quantity_capability_gap",
            triggering_parameters=tuple(triggers),
            evidence_tags=("manufacturer_capability_claims", "small_quantity"),
            recommended_action="Filter for matching lot-size capability before preparing an inquiry.",
            blocking=quantity <= 10,
        )

    def _geometry_consistency_issue(self, context: Mapping[str, Any]) -> Advisory | None:
        if bool(context.get("geometry_consistency_issue")):
            return _geometry_advisory(("geometry_consistency_issue",))

        shaft = _to_float(context.get("shaft_diameter_mm"))
        housing = _to_float(context.get("housing_bore_diameter_mm"))
        if shaft is not None and housing is not None and housing <= shaft:
            return _geometry_advisory(("shaft_diameter_mm", "housing_bore_diameter_mm"))
        return None

    def _dry_run_risk(self, context: Mapping[str, Any]) -> Advisory | None:
        explicit_risk = bool(context.get("dry_run_risk"))
        dry_run_possible = bool(context.get("dry_run_possible"))
        dry_run_disallowed = context.get("dry_run_allowed") is False
        if not explicit_risk and not (dry_run_possible and dry_run_disallowed):
            return None
        triggers = ["dry_run_risk"] if explicit_risk else []
        if dry_run_possible:
            triggers.append("dry_run_possible")
        if dry_run_disallowed:
            triggers.append("dry_run_allowed")
        return Advisory(
            advisory_id="adv_dry_run_risk",
            category=AdvisoryCategory.DRY_RUN_RISK,
            severity=AdvisorySeverity.WARNING,
            title="Dry-run risk needs review",
            message="Structured signals indicate possible dry running where dry running is not allowed.",
            reason_code="dry_run_risk",
            triggering_parameters=tuple(dict.fromkeys(triggers)),
            evidence_tags=("operating_condition", "case_input"),
            recommended_action="Clarify lubrication, start-up, and upset conditions before preselection.",
            blocking=False,
        )

    def _operating_envelope_review(self, context: Mapping[str, Any]) -> Advisory | None:
        if not (
            bool(context.get("operating_envelope_review_required"))
            or bool(context.get("extreme_operating_conditions"))
            or _sequence(context.get("operating_envelope_warnings"))
        ):
            return None
        return Advisory(
            advisory_id="adv_operating_envelope_review",
            category=AdvisoryCategory.MEDIUM_INCOMPATIBILITY_HINT,
            severity=AdvisorySeverity.CAUTION,
            title="Operating envelope needs review",
            message="Operating conditions are incomplete or outside a simple low-risk envelope.",
            reason_code="operating_envelope_review",
            triggering_parameters=("operating_envelope",),
            evidence_tags=("calculation", "case_input"),
            recommended_action="Review pressure, temperature, speed, medium and duty cycle before preselection.",
            blocking=False,
        )

    def _installation_concern(self, context: Mapping[str, Any]) -> Advisory | None:
        triggers: list[str] = []
        if bool(context.get("installation_concern")):
            triggers.append("installation_concern")
        if bool(context.get("mounting_concern")):
            triggers.append("mounting_concern")
        if _sequence(context.get("installation_warnings")):
            triggers.append("installation_warnings")
        difficulty = _normalized_text(context.get("installation_difficulty"))
        if difficulty in {"high", "critical", "review_required"}:
            triggers.append("installation_difficulty")
        if not triggers:
            return None
        return Advisory(
            advisory_id="adv_installation_concern",
            category=AdvisoryCategory.INSTALLATION_CONCERN,
            severity=AdvisorySeverity.CAUTION,
            title="Installation concern needs review",
            message="Structured installation signals indicate a mounting or assembly concern.",
            reason_code="installation_concern",
            triggering_parameters=tuple(dict.fromkeys(triggers)),
            evidence_tags=("installation", "case_input"),
            recommended_action="Clarify installation constraints before treating the inquiry package as complete.",
            blocking=False,
        )

    def _manufacturer_review_required(self, context: Mapping[str, Any]) -> Advisory | None:
        if not bool(context.get("manufacturer_review_required")):
            return None
        reason = str(context.get("manufacturer_review_reason") or "manufacturer_review_required")
        return Advisory(
            advisory_id="adv_manufacturer_review_required",
            category=AdvisoryCategory.LIFESPAN_EXPECTATION_MISMATCH,
            severity=AdvisorySeverity.CAUTION,
            title="Manufacturer review required",
            message="Structured signals indicate that manufacturer review is needed before release.",
            reason_code="manufacturer_review_required",
            triggering_parameters=(reason,),
            evidence_tags=("manufacturer_review",),
            recommended_action="Keep the case in review and do not present it as manufacturer-approved.",
            blocking=False,
        )


def evaluate_advisories(context: Mapping[str, Any]) -> list[Advisory]:
    return AdvisoryEngine().evaluate_advisories(context)


def evaluate_advisory_summary(context: Mapping[str, Any]) -> AdvisorySummary:
    return AdvisoryEngine().evaluate_advisory_summary(context)


def _geometry_advisory(triggering_parameters: tuple[str, ...]) -> Advisory:
    return Advisory(
        advisory_id="adv_geometry_consistency_issue",
        category=AdvisoryCategory.SHAFT_REQUIREMENTS_CONCERN,
        severity=AdvisorySeverity.WARNING,
        title="Geometry consistency issue",
        message="Structured geometry inputs contain an inconsistency that can invalidate preselection.",
        reason_code="geometry_consistency_issue",
        triggering_parameters=triggering_parameters,
        evidence_tags=("case_input", "geometry"),
        recommended_action="Resolve the geometry inconsistency before generating an inquiry package.",
        blocking=True,
    )


def _sequence(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)


def _norm_status(result: Any) -> str:
    value = _get(result, "status")
    return str(getattr(value, "value", value) or "").lower()


def _norm_module_id(result: Any) -> str:
    return str(_get(result, "module_id") or "")


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _normalized_text(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _to_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _highest_severity(advisories: Sequence[Advisory]) -> AdvisorySeverity | None:
    order = {
        AdvisorySeverity.INFO: 1,
        AdvisorySeverity.CAUTION: 2,
        AdvisorySeverity.WARNING: 3,
    }
    highest: AdvisorySeverity | None = None
    for advisory in advisories:
        if highest is None or order[advisory.severity] > order[highest]:
            highest = advisory.severity
    return highest
