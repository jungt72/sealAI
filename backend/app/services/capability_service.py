from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

import sqlalchemy as sa


CAPABILITY_TYPES = {
    "product_family",
    "operating_envelope",
    "material_expertise",
    "geometry_range",
    "norm_capability",
    "medium_experience",
    "lot_size_capability",
    "certification",
}
SOURCE_TYPES = {
    "self_declared",
    "datasheet_extracted",
    "third_party_verified",
    "customer_reference",
}
CLAIM_STATUSES = {"draft", "active", "expired", "withdrawn"}


@dataclass(frozen=True, slots=True)
class CapabilityClaimCreate:
    claim_id: str
    manufacturer_id: str
    capability_type: str
    source_type: str
    source_reference: str
    confidence: int
    validity_from: date
    engineering_path: str | None = None
    sealing_material_family: str | None = None
    capability_payload: Mapping[str, Any] | None = None
    validity_to: date | None = None
    verified_at: datetime | None = None
    verified_by: str | None = None
    status: str | None = None
    minimum_order_pieces: int | None = None
    typical_minimum_pieces: int | None = None
    maximum_order_pieces: int | None = None
    preferred_batch_min_pieces: int | None = None
    preferred_batch_max_pieces: int | None = None
    accepts_single_pieces: bool | None = None
    atex_capable: bool | None = None
    rapid_manufacturing_available: bool | None = None
    rapid_manufacturing_surcharge_percent: int | None = None
    rapid_manufacturing_leadtime_hours: int | None = None
    standard_leadtime_weeks: int | None = None


@dataclass(frozen=True, slots=True)
class CapabilityClaimUpdate:
    capability_type: str | None = None
    engineering_path: str | None = None
    sealing_material_family: str | None = None
    capability_payload: Mapping[str, Any] | None = None
    source_type: str | None = None
    source_reference: str | None = None
    confidence: int | None = None
    validity_from: date | None = None
    validity_to: date | None = None
    verified_at: datetime | None = None
    verified_by: str | None = None
    status: str | None = None
    minimum_order_pieces: int | None = None
    typical_minimum_pieces: int | None = None
    maximum_order_pieces: int | None = None
    preferred_batch_min_pieces: int | None = None
    preferred_batch_max_pieces: int | None = None
    accepts_single_pieces: bool | None = None
    atex_capable: bool | None = None
    rapid_manufacturing_available: bool | None = None
    rapid_manufacturing_surcharge_percent: int | None = None
    rapid_manufacturing_leadtime_hours: int | None = None
    standard_leadtime_weeks: int | None = None


@dataclass(frozen=True, slots=True)
class ManufacturerCapabilityClaim:
    claim_id: str
    manufacturer_id: str
    capability_type: str
    engineering_path: str | None
    sealing_material_family: str | None
    capability_payload: Any
    source_type: str
    source_reference: str
    confidence: int
    validity_from: date
    validity_to: date | None
    verified_at: datetime | None
    verified_by: str | None
    status: str
    minimum_order_pieces: int | None
    typical_minimum_pieces: int | None
    maximum_order_pieces: int | None
    preferred_batch_min_pieces: int | None
    preferred_batch_max_pieces: int | None
    accepts_single_pieces: bool | None
    atex_capable: bool | None
    rapid_manufacturing_available: bool | None
    rapid_manufacturing_surcharge_percent: int | None
    rapid_manufacturing_leadtime_hours: int | None
    standard_leadtime_weeks: int | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class NumericRange:
    min: float | None = None
    max: float | None = None
    unit: str = ""

    def includes(self, value: float | int | None) -> bool:
        if value is None:
            return True
        number = float(value)
        if self.min is not None and number < self.min:
            return False
        if self.max is not None and number > self.max:
            return False
        return True


@dataclass(frozen=True, slots=True)
class ManufacturerCapabilityProfile:
    """Typed ADR-010 capability profile derived from granular claims."""

    manufacturer_id: str
    supported_asset_types: tuple[str, ...] = ()
    supported_seal_types: tuple[str, ...] = ()
    supported_material_families: tuple[str, ...] = ()
    diameter_range_mm: NumericRange = NumericRange(unit="mm")
    pressure_range_bar: NumericRange = NumericRange(unit="bar")
    temperature_range_c: NumericRange = NumericRange(unit="degC")
    industries: tuple[str, ...] = ()
    certifications: tuple[str, ...] = ()
    food_capable: bool | None = None
    pharma_capable: bool | None = None
    atex_capable: bool | None = None
    small_quantity_capable: bool | None = None
    prototype_capable: bool | None = None
    geographic_scope: tuple[str, ...] = ()
    response_model: str | None = None
    evidence_level: str = "unknown"
    standard_leadtime_weeks: int | None = None
    source_claim_ids: tuple[str, ...] = ()
    open_profile_gaps: tuple[str, ...] = ()


class CapabilityValidationError(ValueError):
    pass


class CapabilityService:
    """Small DB-backed CRUD service for manufacturer capability claims."""

    def create_claim(
        self,
        db: Any,
        claim: CapabilityClaimCreate,
    ) -> ManufacturerCapabilityClaim:
        self._validate_create(claim)
        values = {
            "claim_id": claim.claim_id,
            "manufacturer_id": claim.manufacturer_id,
            "capability_type": claim.capability_type,
            "engineering_path": claim.engineering_path,
            "sealing_material_family": claim.sealing_material_family,
            "source_type": claim.source_type,
            "source_reference": claim.source_reference,
            "confidence": claim.confidence,
            "validity_from": claim.validity_from,
            "validity_to": claim.validity_to,
            "verified_at": claim.verified_at,
            "verified_by": claim.verified_by,
            "minimum_order_pieces": claim.minimum_order_pieces,
            "typical_minimum_pieces": claim.typical_minimum_pieces,
            "maximum_order_pieces": claim.maximum_order_pieces,
            "preferred_batch_min_pieces": claim.preferred_batch_min_pieces,
            "preferred_batch_max_pieces": claim.preferred_batch_max_pieces,
            "accepts_single_pieces": claim.accepts_single_pieces,
            "atex_capable": claim.atex_capable,
            "rapid_manufacturing_available": claim.rapid_manufacturing_available,
            "rapid_manufacturing_surcharge_percent": claim.rapid_manufacturing_surcharge_percent,
            "rapid_manufacturing_leadtime_hours": claim.rapid_manufacturing_leadtime_hours,
            "standard_leadtime_weeks": claim.standard_leadtime_weeks,
        }
        if claim.capability_payload is not None:
            values["capability_payload"] = json.dumps(dict(claim.capability_payload), sort_keys=True)
        if claim.status is not None:
            values["status"] = claim.status

        columns = list(values.keys())
        placeholders = [f":{column}" for column in columns]
        self._execute(
            db,
            sa.text(
                f"""
                INSERT INTO manufacturer_capability_claims (
                    {", ".join(columns)}
                ) VALUES (
                    {", ".join(placeholders)}
                )
                """
            ),
            values,
        )
        created = self.get_claim(db, claim.claim_id)
        if created is None:
            raise RuntimeError("created capability claim could not be reloaded")
        return created

    def get_claim(
        self,
        db: Any,
        claim_id: str,
    ) -> ManufacturerCapabilityClaim | None:
        result = self._execute(
            db,
            sa.text(
                """
                SELECT *
                FROM manufacturer_capability_claims
                WHERE claim_id = :claim_id
                """
            ),
            {"claim_id": claim_id},
        )
        row = result.mappings().first()
        return self._row_to_claim(row) if row is not None else None

    def list_claims(
        self,
        db: Any,
        *,
        manufacturer_id: str | None = None,
        engineering_path: str | None = None,
        sealing_material_family: str | None = None,
        capability_type: str | None = None,
        status: str | None = None,
        atex_capable: bool | None = None,
    ) -> list[ManufacturerCapabilityClaim]:
        filters: list[str] = []
        params: dict[str, Any] = {}
        for column, value in (
            ("manufacturer_id", manufacturer_id),
            ("engineering_path", engineering_path),
            ("sealing_material_family", sealing_material_family),
            ("capability_type", capability_type),
            ("status", status),
            ("atex_capable", atex_capable),
        ):
            if value is not None:
                filters.append(f"{column} = :{column}")
                params[column] = value

        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        result = self._execute(
            db,
            sa.text(
                f"""
                SELECT *
                FROM manufacturer_capability_claims
                {where}
                ORDER BY manufacturer_id ASC, capability_type ASC, claim_id ASC
                """
            ),
            params,
        )
        return [self._row_to_claim(row) for row in result.mappings().all()]

    def update_claim(
        self,
        db: Any,
        claim_id: str,
        patch: CapabilityClaimUpdate,
    ) -> ManufacturerCapabilityClaim | None:
        self._validate_update(patch)
        values = self._update_values(patch)
        if not values:
            return self.get_claim(db, claim_id)

        values["claim_id"] = claim_id
        assignments = [f"{column} = :{column}" for column in values if column != "claim_id"]
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        result = self._execute(
            db,
            sa.text(
                f"""
                UPDATE manufacturer_capability_claims
                SET {", ".join(assignments)}
                WHERE claim_id = :claim_id
                """
            ),
            values,
        )
        if getattr(result, "rowcount", 0) == 0:
            return None
        return self.get_claim(db, claim_id)

    def delete_claim(self, db: Any, claim_id: str) -> bool:
        result = self._execute(
            db,
            sa.text(
                """
                DELETE FROM manufacturer_capability_claims
                WHERE claim_id = :claim_id
                """
            ),
            {"claim_id": claim_id},
        )
        return bool(getattr(result, "rowcount", 0))

    def filter_claims_for_quantity(
        self,
        db: Any,
        *,
        quantity_requested: int,
        manufacturer_id: str | None = None,
        engineering_path: str | None = None,
        sealing_material_family: str | None = None,
        status: str | None = "active",
        atex_capable: bool | None = None,
    ) -> list[ManufacturerCapabilityClaim]:
        if quantity_requested <= 0:
            raise CapabilityValidationError("quantity_requested must be positive")

        filters = [
            "capability_type = 'lot_size_capability'",
            "minimum_order_pieces IS NOT NULL",
            "minimum_order_pieces <= :quantity_requested",
            "(maximum_order_pieces IS NULL OR maximum_order_pieces >= :quantity_requested)",
        ]
        params: dict[str, Any] = {"quantity_requested": quantity_requested}

        # Supplement v3 §47: quantity <= 10 is a hard filter on accepts_single_pieces.
        if quantity_requested <= 10:
            filters.append("accepts_single_pieces IS TRUE")

        for column, value in (
            ("manufacturer_id", manufacturer_id),
            ("engineering_path", engineering_path),
            ("sealing_material_family", sealing_material_family),
            ("status", status),
            ("atex_capable", atex_capable),
        ):
            if value is not None:
                filters.append(f"{column} = :{column}")
                params[column] = value

        result = self._execute(
            db,
            sa.text(
                f"""
                SELECT *
                FROM manufacturer_capability_claims
                WHERE {" AND ".join(filters)}
                ORDER BY
                    CASE WHEN typical_minimum_pieces IS NULL THEN 1 ELSE 0 END,
                    typical_minimum_pieces ASC,
                    minimum_order_pieces ASC,
                    claim_id ASC
                """
            ),
            params,
        )
        return [self._row_to_claim(row) for row in result.mappings().all()]

    def build_profile(
        self,
        db: Any,
        manufacturer_id: str,
        *,
        status: str | None = "active",
    ) -> ManufacturerCapabilityProfile:
        claims = self.list_claims(db, manufacturer_id=manufacturer_id, status=status)
        return build_capability_profile(manufacturer_id, claims)

    def list_profiles(
        self,
        db: Any,
        *,
        status: str | None = "active",
    ) -> list[ManufacturerCapabilityProfile]:
        claims = self.list_claims(db, status=status)
        grouped: dict[str, list[ManufacturerCapabilityClaim]] = {}
        for claim in claims:
            grouped.setdefault(claim.manufacturer_id, []).append(claim)
        return [
            build_capability_profile(manufacturer_id, grouped[manufacturer_id])
            for manufacturer_id in sorted(grouped)
        ]

    def _validate_create(self, claim: CapabilityClaimCreate) -> None:
        for field_name in (
            "claim_id",
            "manufacturer_id",
            "capability_type",
            "source_type",
            "source_reference",
        ):
            if not str(getattr(claim, field_name) or "").strip():
                raise CapabilityValidationError(f"{field_name} is required")
        if claim.validity_from is None:
            raise CapabilityValidationError("validity_from is required")
        self._validate_common(
            capability_type=claim.capability_type,
            source_type=claim.source_type,
            source_reference=claim.source_reference,
            confidence=claim.confidence,
            validity_from=claim.validity_from,
            validity_to=claim.validity_to,
            status=claim.status,
            minimum_order_pieces=claim.minimum_order_pieces,
            typical_minimum_pieces=claim.typical_minimum_pieces,
            maximum_order_pieces=claim.maximum_order_pieces,
            preferred_batch_min_pieces=claim.preferred_batch_min_pieces,
            preferred_batch_max_pieces=claim.preferred_batch_max_pieces,
            accepts_single_pieces=claim.accepts_single_pieces,
            capability_type_for_lot=claim.capability_type,
        )

    def _validate_update(self, patch: CapabilityClaimUpdate) -> None:
        self._validate_common(
            capability_type=patch.capability_type,
            source_type=patch.source_type,
            source_reference=patch.source_reference,
            confidence=patch.confidence,
            validity_from=patch.validity_from,
            validity_to=patch.validity_to,
            status=patch.status,
            minimum_order_pieces=patch.minimum_order_pieces,
            typical_minimum_pieces=patch.typical_minimum_pieces,
            maximum_order_pieces=patch.maximum_order_pieces,
            preferred_batch_min_pieces=patch.preferred_batch_min_pieces,
            preferred_batch_max_pieces=patch.preferred_batch_max_pieces,
            accepts_single_pieces=patch.accepts_single_pieces,
            capability_type_for_lot=patch.capability_type,
        )

    @staticmethod
    def _validate_common(
        *,
        capability_type: str | None,
        source_type: str | None,
        source_reference: str | None,
        confidence: int | None,
        validity_from: date | None,
        validity_to: date | None,
        status: str | None,
        minimum_order_pieces: int | None,
        typical_minimum_pieces: int | None,
        maximum_order_pieces: int | None,
        preferred_batch_min_pieces: int | None,
        preferred_batch_max_pieces: int | None,
        accepts_single_pieces: bool | None,
        capability_type_for_lot: str | None,
    ) -> None:
        if capability_type is not None and capability_type not in CAPABILITY_TYPES:
            raise CapabilityValidationError(f"unknown capability_type: {capability_type}")
        if source_type is not None and source_type not in SOURCE_TYPES:
            raise CapabilityValidationError(f"unknown source_type: {source_type}")
        if source_reference is not None and not str(source_reference).strip():
            raise CapabilityValidationError("source_reference must not be blank")
        if confidence is not None and not 1 <= int(confidence) <= 5:
            raise CapabilityValidationError("confidence must be between 1 and 5")
        if status is not None and status not in CLAIM_STATUSES:
            raise CapabilityValidationError(f"unknown status: {status}")
        if validity_from is not None and validity_to is not None and validity_to < validity_from:
            raise CapabilityValidationError("validity_to must be greater than or equal to validity_from")

        for field_name, value in (
            ("minimum_order_pieces", minimum_order_pieces),
            ("typical_minimum_pieces", typical_minimum_pieces),
            ("maximum_order_pieces", maximum_order_pieces),
            ("preferred_batch_min_pieces", preferred_batch_min_pieces),
            ("preferred_batch_max_pieces", preferred_batch_max_pieces),
        ):
            if value is not None and value <= 0:
                raise CapabilityValidationError(f"{field_name} must be positive")

        if (
            minimum_order_pieces is not None
            and typical_minimum_pieces is not None
            and typical_minimum_pieces < minimum_order_pieces
        ):
            raise CapabilityValidationError("typical_minimum_pieces must be >= minimum_order_pieces")
        if (
            typical_minimum_pieces is not None
            and maximum_order_pieces is not None
            and maximum_order_pieces < typical_minimum_pieces
        ):
            raise CapabilityValidationError("maximum_order_pieces must be >= typical_minimum_pieces")
        if (
            preferred_batch_min_pieces is not None
            and preferred_batch_max_pieces is not None
            and preferred_batch_max_pieces < preferred_batch_min_pieces
        ):
            raise CapabilityValidationError("preferred_batch_max_pieces must be >= preferred_batch_min_pieces")
        if accepts_single_pieces is True and minimum_order_pieces is not None and minimum_order_pieces > 1:
            raise CapabilityValidationError("accepts_single_pieces requires minimum_order_pieces <= 1")
        if capability_type_for_lot == "lot_size_capability":
            required = {
                "minimum_order_pieces": minimum_order_pieces,
                "typical_minimum_pieces": typical_minimum_pieces,
                "maximum_order_pieces": maximum_order_pieces,
                "accepts_single_pieces": accepts_single_pieces,
            }
            missing = [name for name, value in required.items() if value is None]
            if missing:
                raise CapabilityValidationError(
                    "lot_size_capability requires " + ", ".join(missing)
                )

    @staticmethod
    def _update_values(patch: CapabilityClaimUpdate) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for field_name in CapabilityClaimUpdate.__dataclass_fields__:
            value = getattr(patch, field_name)
            if value is None:
                continue
            if field_name == "capability_payload":
                values[field_name] = json.dumps(dict(value), sort_keys=True)
            else:
                values[field_name] = value
        return values

    @staticmethod
    def _row_to_claim(row: Mapping[str, Any]) -> ManufacturerCapabilityClaim:
        payload = row["capability_payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                pass
        return ManufacturerCapabilityClaim(
            claim_id=str(row["claim_id"]),
            manufacturer_id=str(row["manufacturer_id"]),
            capability_type=str(row["capability_type"]),
            engineering_path=row["engineering_path"],
            sealing_material_family=row["sealing_material_family"],
            capability_payload=payload,
            source_type=str(row["source_type"]),
            source_reference=str(row["source_reference"]),
            confidence=int(row["confidence"]),
            validity_from=row["validity_from"],
            validity_to=row["validity_to"],
            verified_at=row["verified_at"],
            verified_by=row["verified_by"],
            status=str(row["status"]),
            minimum_order_pieces=row["minimum_order_pieces"],
            typical_minimum_pieces=row["typical_minimum_pieces"],
            maximum_order_pieces=row["maximum_order_pieces"],
            preferred_batch_min_pieces=row["preferred_batch_min_pieces"],
            preferred_batch_max_pieces=row["preferred_batch_max_pieces"],
            accepts_single_pieces=(
                None if row["accepts_single_pieces"] is None else bool(row["accepts_single_pieces"])
            ),
            atex_capable=(
                None if row["atex_capable"] is None else bool(row["atex_capable"])
            ),
            rapid_manufacturing_available=(
                None
                if row["rapid_manufacturing_available"] is None
                else bool(row["rapid_manufacturing_available"])
            ),
            rapid_manufacturing_surcharge_percent=row["rapid_manufacturing_surcharge_percent"],
            rapid_manufacturing_leadtime_hours=row["rapid_manufacturing_leadtime_hours"],
            standard_leadtime_weeks=row["standard_leadtime_weeks"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _execute(db: Any, statement: sa.TextClause, params: Mapping[str, Any]):
        return db.execute(statement, dict(params))


def build_capability_profile(
    manufacturer_id: str,
    claims: list[ManufacturerCapabilityClaim] | tuple[ManufacturerCapabilityClaim, ...],
) -> ManufacturerCapabilityProfile:
    active_claims = [
        claim
        for claim in claims
        if claim.manufacturer_id == manufacturer_id and claim.status == "active"
    ]
    asset_types: set[str] = set()
    seal_types: set[str] = set()
    material_families: set[str] = set()
    industries: set[str] = set()
    certifications: set[str] = set()
    geographic_scope: set[str] = set()
    diameter = NumericRange(unit="mm")
    pressure = NumericRange(unit="bar")
    temperature = NumericRange(unit="degC")
    food_capable: bool | None = None
    pharma_capable: bool | None = None
    atex_capable: bool | None = None
    small_quantity_capable: bool | None = None
    prototype_capable: bool | None = None
    response_model: str | None = None
    standard_leadtime_weeks: int | None = None
    evidence_scores: list[int] = []
    source_claim_ids: list[str] = []

    for claim in active_claims:
        payload = claim.capability_payload if isinstance(claim.capability_payload, Mapping) else {}
        source_claim_ids.append(claim.claim_id)
        evidence_scores.append(int(claim.confidence))
        if claim.engineering_path:
            seal_types.add(str(claim.engineering_path))
        if claim.sealing_material_family:
            material_families.add(str(claim.sealing_material_family))
        if claim.atex_capable is not None:
            atex_capable = bool(claim.atex_capable)
        if claim.accepts_single_pieces is not None:
            small_quantity_capable = bool(claim.accepts_single_pieces)
        if claim.rapid_manufacturing_available is not None:
            prototype_capable = bool(claim.rapid_manufacturing_available)
        if claim.standard_leadtime_weeks is not None:
            standard_leadtime_weeks = _min_int(standard_leadtime_weeks, claim.standard_leadtime_weeks)

        asset_types.update(_strings(payload.get("supported_asset_types")))
        seal_types.update(_strings(payload.get("supported_seal_types")))
        material_families.update(_strings(payload.get("supported_material_families")))
        industries.update(_strings(payload.get("industries")))
        certifications.update(_strings(payload.get("certifications")))
        geographic_scope.update(_strings(payload.get("geographic_scope")))

        diameter = _merge_range(diameter, payload, "diameter", "mm")
        pressure = _merge_range(pressure, payload, "pressure", "bar")
        temperature = _merge_range(temperature, payload, "temperature", "degC")

        food_capable = _coalesce_bool(food_capable, payload.get("food_capable"))
        pharma_capable = _coalesce_bool(pharma_capable, payload.get("pharma_capable"))
        atex_capable = _coalesce_bool(atex_capable, payload.get("atex_capable"))
        small_quantity_capable = _coalesce_bool(small_quantity_capable, payload.get("small_quantity_capable"))
        prototype_capable = _coalesce_bool(prototype_capable, payload.get("prototype_capable"))
        response_model = _first_text(response_model, payload.get("response_model"))

    gaps = _profile_gaps(
        asset_types=asset_types,
        seal_types=seal_types,
        material_families=material_families,
        diameter=diameter,
        pressure=pressure,
        temperature=temperature,
        geographic_scope=geographic_scope,
        response_model=response_model,
    )
    return ManufacturerCapabilityProfile(
        manufacturer_id=manufacturer_id,
        supported_asset_types=tuple(sorted(asset_types)),
        supported_seal_types=tuple(sorted(seal_types)),
        supported_material_families=tuple(sorted(material_families)),
        diameter_range_mm=diameter,
        pressure_range_bar=pressure,
        temperature_range_c=temperature,
        industries=tuple(sorted(industries)),
        certifications=tuple(sorted(certifications)),
        food_capable=food_capable,
        pharma_capable=pharma_capable,
        atex_capable=atex_capable,
        small_quantity_capable=small_quantity_capable,
        prototype_capable=prototype_capable,
        geographic_scope=tuple(sorted(geographic_scope)),
        response_model=response_model,
        evidence_level=_evidence_level(evidence_scores),
        standard_leadtime_weeks=standard_leadtime_weeks,
        source_claim_ids=tuple(source_claim_ids),
        open_profile_gaps=tuple(gaps),
    )


def _strings(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Mapping):
        values = value.values()
    else:
        try:
            values = list(value)
        except TypeError:
            values = [value]
    return {str(item).strip() for item in values if str(item).strip()}


def _merge_range(
    current: NumericRange,
    payload: Mapping[str, Any],
    prefix: str,
    unit: str,
) -> NumericRange:
    nested = payload.get(f"{prefix}_range") if isinstance(payload.get(f"{prefix}_range"), Mapping) else {}
    minimum = _number(_first_present(payload, f"{prefix}_min_{unit}", nested, "min"))
    maximum = _number(_first_present(payload, f"{prefix}_max_{unit}", nested, "max"))
    return NumericRange(
        min=_min_non_none(current.min, minimum),
        max=_max_non_none(current.max, maximum),
        unit=unit,
    )


def _first_present(
    primary: Mapping[str, Any],
    primary_key: str,
    secondary: Mapping[str, Any],
    secondary_key: str,
) -> Any:
    if primary_key in primary:
        return primary[primary_key]
    return secondary.get(secondary_key)


def _profile_gaps(
    *,
    asset_types: set[str],
    seal_types: set[str],
    material_families: set[str],
    diameter: NumericRange,
    pressure: NumericRange,
    temperature: NumericRange,
    geographic_scope: set[str],
    response_model: str | None,
) -> list[str]:
    gaps: list[str] = []
    if not asset_types:
        gaps.append("supported_asset_types")
    if not seal_types:
        gaps.append("supported_seal_types")
    if not material_families:
        gaps.append("supported_material_families")
    if diameter.min is None or diameter.max is None:
        gaps.append("diameter_range")
    if pressure.min is None or pressure.max is None:
        gaps.append("pressure_range")
    if temperature.min is None or temperature.max is None:
        gaps.append("temperature_range")
    if not geographic_scope:
        gaps.append("geographic_scope")
    if response_model is None:
        gaps.append("response_model")
    return gaps


def _evidence_level(scores: list[int]) -> str:
    if not scores:
        return "unknown"
    best = max(scores)
    if best >= 5:
        return "verified"
    if best >= 4:
        return "documented"
    if best >= 2:
        return "self_declared"
    return "weak"


def _coalesce_bool(current: bool | None, raw: Any) -> bool | None:
    if raw is None:
        return current
    return bool(raw)


def _first_text(current: str | None, raw: Any) -> str | None:
    if current:
        return current
    text = str(raw or "").strip()
    return text or None


def _min_int(current: int | None, candidate: int | None) -> int | None:
    if candidate is None:
        return current
    if current is None:
        return int(candidate)
    return min(current, int(candidate))


def _min_non_none(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return min(left, right)


def _max_non_none(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
