from __future__ import annotations

import re
import uuid
import json
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Mapping

import sqlalchemy as sa


class NormalizationStatus(str, Enum):
    UNIQUE = "unique"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class GenericConcept:
    concept_id: str
    canonical_name: str
    display_name: str
    standards_refs: Any
    engineering_path: str
    sealing_material_family: str
    description: str | None
    structural_parameters: Any


@dataclass(frozen=True, slots=True)
class ProductTerm:
    term_id: str
    term_text: str
    normalized_term: str
    term_language: str
    term_type: str
    originating_manufacturer_id: str | None
    is_trademark: bool


@dataclass(frozen=True, slots=True)
class MappingProvenance:
    mapping_id: str
    source_type: str
    source_reference: str
    confidence: int
    reviewer_status: str
    validity_from: date | None
    validity_to: date | None
    is_active: bool
    reviewer_id: str | None
    review_notes: str | None


@dataclass(frozen=True, slots=True)
class LookupMatch:
    term: ProductTerm
    concept: GenericConcept
    provenance: MappingProvenance
    match_kind: str
    normalized_query: str


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    status: NormalizationStatus
    query: str
    normalized_query: str
    matches: tuple[LookupMatch, ...]
    concept: GenericConcept | None = None
    reasoning: str = ""


class TerminologyService:
    """Small DB-backed terminology lookup and normalization service.

    The service is deterministic and operates only on the terminology registry
    tables introduced in Patch 3.1. It does not import graph runtimes, web
    framework dependencies, or agent runtime modules.
    """

    def lookup_term(
        self,
        db: Any,
        text: str,
        *,
        language: str = "de",
        manufacturer_id: str | None = None,
        include_generic_scope: bool = True,
        published_only: bool = True,
        active_only: bool = True,
        as_of: date | None = None,
        audit: bool = False,
        actor_id: str | None = None,
        actor_type: str = "system",
    ) -> list[LookupMatch]:
        normalized_query = normalize_term_text(text)
        if not normalized_query:
            return []

        rows = self._fetch_lookup_rows(
            db,
            raw_text=str(text or "").strip(),
            normalized_query=normalized_query,
            language=language,
            manufacturer_id=manufacturer_id,
            include_generic_scope=include_generic_scope,
            published_only=published_only,
            active_only=active_only,
            as_of=as_of,
        )
        matches = [self._row_to_match(row, normalized_query) for row in rows]

        if audit:
            for match in matches:
                self.record_audit_event(
                    db,
                    action="lookup_term",
                    mapping_id=match.provenance.mapping_id,
                    concept_id=match.concept.concept_id,
                    term_id=match.term.term_id,
                    actor_id=actor_id,
                    actor_type=actor_type,
                    payload={
                        "query": text,
                        "normalized_query": normalized_query,
                        "match_kind": match.match_kind,
                    },
                )

        return matches

    def normalize_term(
        self,
        db: Any,
        text: str,
        *,
        language: str = "de",
        manufacturer_id: str | None = None,
        include_generic_scope: bool = True,
        published_only: bool = True,
        active_only: bool = True,
        as_of: date | None = None,
        audit: bool = False,
        actor_id: str | None = None,
        actor_type: str = "system",
    ) -> NormalizationResult:
        normalized_query = normalize_term_text(text)
        matches = tuple(
            self.lookup_term(
                db,
                text,
                language=language,
                manufacturer_id=manufacturer_id,
                include_generic_scope=include_generic_scope,
                published_only=published_only,
                active_only=active_only,
                as_of=as_of,
                audit=False,
            )
        )

        if not matches:
            return NormalizationResult(
                status=NormalizationStatus.NO_MATCH,
                query=text,
                normalized_query=normalized_query,
                matches=matches,
                reasoning="terminology_not_recognized",
            )

        concepts = {match.concept.concept_id: match.concept for match in matches}
        if len(concepts) > 1:
            result = NormalizationResult(
                status=NormalizationStatus.AMBIGUOUS,
                query=text,
                normalized_query=normalized_query,
                matches=matches,
                reasoning="multiple_concepts_matched",
            )
        else:
            concept = next(iter(concepts.values()))
            result = NormalizationResult(
                status=NormalizationStatus.UNIQUE,
                query=text,
                normalized_query=normalized_query,
                matches=matches,
                concept=concept,
                reasoning="single_concept_matched",
            )

        if audit:
            for match in matches:
                self.record_audit_event(
                    db,
                    action="normalize_term",
                    mapping_id=match.provenance.mapping_id,
                    concept_id=match.concept.concept_id,
                    term_id=match.term.term_id,
                    actor_id=actor_id,
                    actor_type=actor_type,
                    payload={
                        "query": text,
                        "normalized_query": normalized_query,
                        "status": result.status.value,
                    },
                )

        return result

    def record_audit_event(
        self,
        db: Any,
        *,
        action: str,
        mapping_id: str | None = None,
        concept_id: str | None = None,
        term_id: str | None = None,
        actor_id: str | None = None,
        actor_type: str = "system",
        payload: Mapping[str, Any] | None = None,
    ) -> str:
        if not (mapping_id or concept_id or term_id):
            raise ValueError("term_audit_log requires mapping_id, concept_id, or term_id")

        audit_id = str(uuid.uuid4())
        self._execute(
            db,
            sa.text(
                """
                INSERT INTO term_audit_log (
                    audit_id, mapping_id, concept_id, term_id, action,
                    actor_id, actor_type, payload
                ) VALUES (
                    :audit_id, :mapping_id, :concept_id, :term_id, :action,
                    :actor_id, :actor_type, :payload
                )
                """
            ),
            {
                "audit_id": audit_id,
                "mapping_id": mapping_id,
                "concept_id": concept_id,
                "term_id": term_id,
                "action": action,
                "actor_id": actor_id,
                "actor_type": actor_type,
                "payload": json.dumps(dict(payload or {}), sort_keys=True),
            },
        )
        return audit_id

    def _fetch_lookup_rows(
        self,
        db: Any,
        *,
        raw_text: str,
        normalized_query: str,
        language: str,
        manufacturer_id: str | None,
        include_generic_scope: bool,
        published_only: bool,
        active_only: bool,
        as_of: date | None,
    ) -> list[Mapping[str, Any]]:
        scope_filter = "1 = 1"
        params: dict[str, Any] = {
            "raw_text": raw_text.lower(),
            "normalized_query": normalized_query,
            "language": language,
            "manufacturer_id": manufacturer_id,
            "as_of": as_of,
        }

        if manufacturer_id is not None and include_generic_scope:
            scope_filter = (
                "(pt.originating_manufacturer_id = :manufacturer_id "
                "OR pt.originating_manufacturer_id IS NULL)"
            )
        elif manufacturer_id is not None:
            scope_filter = "pt.originating_manufacturer_id = :manufacturer_id"

        reviewer_filter = "AND tm.reviewer_status = 'published'" if published_only else ""
        active_filter = "AND tm.is_active IS TRUE" if active_only else ""
        validity_filter = ""
        if as_of is not None:
            validity_filter = (
                "AND (tm.validity_from IS NULL OR tm.validity_from <= :as_of) "
                "AND (tm.validity_to IS NULL OR tm.validity_to >= :as_of)"
            )

        statement = sa.text(
            f"""
            SELECT
                pt.term_id,
                pt.term_text,
                pt.normalized_term,
                pt.term_language,
                pt.term_type,
                pt.originating_manufacturer_id,
                pt.is_trademark,
                gc.concept_id,
                gc.canonical_name,
                gc.display_name,
                gc.standards_refs,
                gc.engineering_path,
                gc.sealing_material_family,
                gc.description,
                gc.structural_parameters,
                tm.mapping_id,
                tm.source_type,
                tm.source_reference,
                tm.confidence,
                tm.validity_from,
                tm.validity_to,
                tm.reviewer_status,
                tm.reviewer_id,
                tm.review_notes,
                tm.is_active,
                CASE
                    WHEN lower(pt.term_text) = :raw_text THEN 'raw_exact'
                    ELSE 'normalized_exact'
                END AS match_kind
            FROM product_terms pt
            JOIN term_mappings tm ON tm.term_id = pt.term_id
            JOIN generic_concepts gc ON gc.concept_id = tm.concept_id
            WHERE pt.term_language = :language
              AND (
                  lower(pt.term_text) = :raw_text
                  OR pt.normalized_term = :normalized_query
              )
              AND {scope_filter}
              {reviewer_filter}
              {active_filter}
              {validity_filter}
            ORDER BY
                CASE WHEN lower(pt.term_text) = :raw_text THEN 0 ELSE 1 END,
                tm.confidence DESC,
                gc.canonical_name ASC,
                pt.term_text ASC
            """
        )
        result = self._execute(db, statement, params)
        return [dict(row) for row in result.mappings().all()]

    @staticmethod
    def _row_to_match(row: Mapping[str, Any], normalized_query: str) -> LookupMatch:
        term = ProductTerm(
            term_id=str(row["term_id"]),
            term_text=str(row["term_text"]),
            normalized_term=str(row["normalized_term"]),
            term_language=str(row["term_language"]),
            term_type=str(row["term_type"]),
            originating_manufacturer_id=row["originating_manufacturer_id"],
            is_trademark=bool(row["is_trademark"]),
        )
        concept = GenericConcept(
            concept_id=str(row["concept_id"]),
            canonical_name=str(row["canonical_name"]),
            display_name=str(row["display_name"]),
            standards_refs=row["standards_refs"],
            engineering_path=str(row["engineering_path"]),
            sealing_material_family=str(row["sealing_material_family"]),
            description=row["description"],
            structural_parameters=row["structural_parameters"],
        )
        provenance = MappingProvenance(
            mapping_id=str(row["mapping_id"]),
            source_type=str(row["source_type"]),
            source_reference=str(row["source_reference"]),
            confidence=int(row["confidence"]),
            reviewer_status=str(row["reviewer_status"]),
            validity_from=row["validity_from"],
            validity_to=row["validity_to"],
            is_active=bool(row["is_active"]),
            reviewer_id=row["reviewer_id"],
            review_notes=row["review_notes"],
        )
        return LookupMatch(
            term=term,
            concept=concept,
            provenance=provenance,
            match_kind=str(row["match_kind"]),
            normalized_query=normalized_query,
        )

    @staticmethod
    def _execute(db: Any, statement: sa.TextClause, params: Mapping[str, Any]):
        return db.execute(statement, dict(params))


_TRADEMARK_CHARS = str.maketrans(
    {
        "®": " ",
        "™": " ",
        "©": " ",
    }
)
_SEPARATOR_PATTERN = re.compile(r"[\s\-_–—/]+", re.UNICODE)


def normalize_term_text(text: str) -> str:
    normalized = str(text or "").translate(_TRADEMARK_CHARS).lower().strip()
    normalized = normalized.replace("ä", "ae")
    normalized = normalized.replace("ö", "oe")
    normalized = normalized.replace("ü", "ue")
    normalized = normalized.replace("ß", "ss")
    normalized = _SEPARATOR_PATTERN.sub(" ", normalized)
    return " ".join(normalized.split())
