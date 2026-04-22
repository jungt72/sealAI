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
