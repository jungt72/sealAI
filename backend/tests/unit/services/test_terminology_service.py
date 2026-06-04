from __future__ import annotations

import inspect
from datetime import date

import pytest
import sqlalchemy as sa

from app.services import terminology_service as service_module
from app.services.terminology_service import (
    NormalizationStatus,
    TerminologyService,
    normalize_term_text,
)


@pytest.fixture
def db():
    engine = sa.create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        _create_schema(conn)
        _seed_registry(conn)
    with engine.begin() as conn:
        yield conn


@pytest.fixture
def service() -> TerminologyService:
    return TerminologyService()


def _create_schema(conn) -> None:
    conn.execute(
        sa.text(
            """
            CREATE TABLE generic_concepts (
                concept_id VARCHAR(36) PRIMARY KEY,
                canonical_name VARCHAR(128) NOT NULL UNIQUE,
                display_name VARCHAR(255) NOT NULL,
                standards_refs TEXT NOT NULL DEFAULT '[]',
                engineering_path VARCHAR(64) NOT NULL,
                sealing_material_family VARCHAR(64) NOT NULL DEFAULT 'unknown',
                description TEXT,
                structural_parameters TEXT NOT NULL DEFAULT '{}',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE product_terms (
                term_id VARCHAR(36) PRIMARY KEY,
                term_text VARCHAR(255) NOT NULL,
                normalized_term VARCHAR(255) NOT NULL,
                term_language VARCHAR(8) NOT NULL DEFAULT 'de',
                term_type VARCHAR(32) NOT NULL,
                originating_manufacturer_id VARCHAR(36),
                is_trademark BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE term_mappings (
                mapping_id VARCHAR(36) PRIMARY KEY,
                term_id VARCHAR(36) NOT NULL REFERENCES product_terms(term_id),
                concept_id VARCHAR(36) NOT NULL REFERENCES generic_concepts(concept_id),
                source_type VARCHAR(64) NOT NULL,
                source_reference TEXT NOT NULL,
                confidence SMALLINT NOT NULL,
                validity_from DATE,
                validity_to DATE,
                reviewer_status VARCHAR(32) NOT NULL DEFAULT 'pending',
                reviewer_id VARCHAR(36),
                review_notes TEXT,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            CREATE TABLE term_audit_log (
                audit_id VARCHAR(36) PRIMARY KEY,
                mapping_id VARCHAR(36),
                concept_id VARCHAR(36),
                term_id VARCHAR(36),
                action VARCHAR(64) NOT NULL,
                actor_id VARCHAR(255),
                actor_type VARCHAR(32) NOT NULL DEFAULT 'system',
                payload TEXT NOT NULL DEFAULT '{}',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
            """
        )
    )


def _insert_concept(conn, concept_id: str, canonical_name: str, display_name: str, family: str) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO generic_concepts (
                concept_id, canonical_name, display_name, standards_refs,
                engineering_path, sealing_material_family, description,
                structural_parameters
            ) VALUES (
                :concept_id, :canonical_name, :display_name, '[]',
                :engineering_path, :family, :description, '{}'
            )
            """
        ),
        {
            "concept_id": concept_id,
            "canonical_name": canonical_name,
            "display_name": display_name,
            "engineering_path": "static" if "static" in canonical_name else "rwdr",
            "family": family,
            "description": display_name,
        },
    )


def _insert_term(
    conn,
    term_id: str,
    term_text: str,
    term_type: str,
    concept_id: str,
    *,
    language: str = "de",
    manufacturer_id: str | None = None,
    source_type: str = "manufacturer_datasheet",
    source_reference: str | None = None,
    confidence: int = 4,
    reviewer_status: str = "published",
    is_active: bool = True,
    validity_from: str | None = None,
    validity_to: str | None = None,
    is_trademark: bool = False,
    mapping_suffix: str = "1",
) -> None:
    conn.execute(
        sa.text(
            """
            INSERT OR IGNORE INTO product_terms (
                term_id, term_text, normalized_term, term_language, term_type,
                originating_manufacturer_id, is_trademark
            ) VALUES (
                :term_id, :term_text, :normalized_term, :language, :term_type,
                :manufacturer_id, :is_trademark
            )
            """
        ),
        {
            "term_id": term_id,
            "term_text": term_text,
            "normalized_term": normalize_term_text(term_text),
            "language": language,
            "term_type": term_type,
            "manufacturer_id": manufacturer_id,
            "is_trademark": is_trademark,
        },
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO term_mappings (
                mapping_id, term_id, concept_id, source_type, source_reference,
                confidence, validity_from, validity_to, reviewer_status, is_active
            ) VALUES (
                :mapping_id, :term_id, :concept_id, :source_type,
                :source_reference, :confidence, :validity_from, :validity_to,
                :reviewer_status, :is_active
            )
            """
        ),
        {
            "mapping_id": f"map-{term_id}-{mapping_suffix}",
            "term_id": term_id,
            "concept_id": concept_id,
            "source_type": source_type,
            "source_reference": source_reference or f"seed:{term_text}",
            "confidence": confidence,
            "validity_from": validity_from,
            "validity_to": validity_to,
            "reviewer_status": reviewer_status,
            "is_active": is_active,
        },
    )


def _seed_registry(conn) -> None:
    _insert_concept(conn, "c-ptfe-spring", "rwdr_ptfe_lip_spring_loaded", "Spring-energized PTFE lip seal", "ptfe_virgin")
    _insert_concept(conn, "c-ptfe-non-spring", "rwdr_ptfe_lip_non_spring", "Non-spring PTFE lip seal", "ptfe_virgin")
    _insert_concept(conn, "c-elastomer", "rwdr_elastomer_standard", "Standard elastomer radial shaft seal", "elastomer_fkm")
    _insert_concept(conn, "c-cassette", "rwdr_elastomer_cassette", "Cassette-type radial shaft seal", "elastomer_nbr")
    _insert_concept(conn, "c-v-ring", "rwdr_elastomer_v_ring", "V-ring axial-acting elastomer seal", "elastomer_nbr")
    _insert_concept(conn, "c-static-oring", "static_o_ring", "O-ring static seal", "elastomer_fkm")

    _insert_term(conn, "t-simmerring", "Simmerring", "brand_name", "c-elastomer", manufacturer_id="m-freudenberg", is_trademark=True, confidence=5)
    _insert_term(conn, "t-simmerring-ptfe", "Simmerring PTFE", "brand_name", "c-ptfe-spring", manufacturer_id="m-freudenberg", is_trademark=True, confidence=5)
    _insert_term(conn, "t-premium-sine", "Premium Sine Seal", "brand_name", "c-elastomer", manufacturer_id="m-freudenberg", confidence=4)
    _insert_term(conn, "t-pop", "PTFE POP Seal", "brand_name", "c-ptfe-spring", manufacturer_id="m-freudenberg", confidence=4)
    _insert_term(conn, "t-variseal", "Turcon Variseal", "brand_name", "c-ptfe-spring", manufacturer_id="m-trelleborg", is_trademark=True, confidence=5)
    _insert_term(conn, "t-roto-variseal", "Turcon Roto Variseal", "brand_name", "c-ptfe-spring", manufacturer_id="m-trelleborg", is_trademark=True, confidence=5)
    _insert_term(conn, "t-variseal-m2", "Variseal M2", "series_name", "c-ptfe-spring", manufacturer_id="m-trelleborg", confidence=4)
    _insert_term(conn, "t-skf-ptfe", "SKF PTFE seal", "generic_term", "c-ptfe-spring", manufacturer_id="m-skf", confidence=4)
    _insert_term(conn, "t-ptfe-rwdr-de", "PTFE Radialwellendichtring", "generic_term", "c-ptfe-spring", confidence=4, source_type="expert_judgment")
    _insert_term(conn, "t-ptfe-rwdr-abbr", "PTFE-RWDR", "abbreviation", "c-ptfe-spring", confidence=4, source_type="expert_judgment")
    _insert_term(conn, "t-teflon", "Teflon seal", "colloquial", "c-ptfe-spring", confidence=3, source_type="expert_judgment")
    _insert_term(conn, "t-lip-ptfe", "Lip seal PTFE", "generic_term", "c-ptfe-spring", language="en", confidence=4, source_type="expert_judgment")
    _insert_term(conn, "t-oil-seal", "Oil seal", "generic_term", "c-elastomer", language="en", confidence=4, source_type="expert_judgment")
    _insert_term(conn, "t-wellendichtring", "Wellendichtring", "generic_term", "c-elastomer", confidence=3, source_type="expert_judgment")
    _insert_term(conn, "t-cassette", "Cassette seal", "series_name", "c-cassette", language="en", confidence=4)
    _insert_term(conn, "t-v-ring", "V-Ring", "generic_term", "c-v-ring", confidence=4)
    _insert_term(conn, "t-shaft-seal", "Shaft seal", "generic_term", "c-elastomer", language="en", confidence=3, mapping_suffix="elastomer")
    _insert_term(conn, "t-shaft-seal", "Shaft seal", "generic_term", "c-ptfe-spring", language="en", confidence=3, mapping_suffix="ptfe")
    _insert_term(conn, "t-dichtring", "Dichtring", "colloquial", "c-elastomer", confidence=2, mapping_suffix="rwdr")
    _insert_term(conn, "t-dichtring", "Dichtring", "colloquial", "c-static-oring", confidence=2, mapping_suffix="static")
    _insert_term(conn, "t-pending", "Pending Seal", "brand_name", "c-ptfe-spring", reviewer_status="pending")
    _insert_term(conn, "t-inactive", "Inactive Seal", "brand_name", "c-ptfe-spring", is_active=False)
    _insert_term(conn, "t-old", "Old Seal", "brand_name", "c-ptfe-non-spring", validity_from="2020-01-01", validity_to="2021-01-01")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" Turcon®  Variseal™ ", "turcon variseal"),
        ("PTFE-RWDR", "ptfe rwdr"),
        ("V_Ring", "v ring"),
        ("Öl-Dichtung", "oel dichtung"),
        ("Maß", "mass"),
    ],
)
def test_normalize_term_text(raw: str, expected: str) -> None:
    assert normalize_term_text(raw) == expected


@pytest.mark.parametrize(
    ("query", "language", "expected_concept"),
    [
        ("Simmerring", "de", "rwdr_elastomer_standard"),
        ("simmerring", "de", "rwdr_elastomer_standard"),
        ("Simmerring®", "de", "rwdr_elastomer_standard"),
        ("Simmerring PTFE", "de", "rwdr_ptfe_lip_spring_loaded"),
        ("Premium Sine Seal", "de", "rwdr_elastomer_standard"),
        ("PTFE POP Seal", "de", "rwdr_ptfe_lip_spring_loaded"),
        ("Turcon Variseal", "de", "rwdr_ptfe_lip_spring_loaded"),
        ("Turcon-Roto Variseal", "de", "rwdr_ptfe_lip_spring_loaded"),
        ("Variseal M2", "de", "rwdr_ptfe_lip_spring_loaded"),
        ("SKF PTFE seal", "de", "rwdr_ptfe_lip_spring_loaded"),
        ("PTFE Radialwellendichtring", "de", "rwdr_ptfe_lip_spring_loaded"),
        ("PTFE RWDR", "de", "rwdr_ptfe_lip_spring_loaded"),
        ("Teflon seal", "de", "rwdr_ptfe_lip_spring_loaded"),
        ("Lip seal PTFE", "en", "rwdr_ptfe_lip_spring_loaded"),
        ("Oil seal", "en", "rwdr_elastomer_standard"),
        ("Wellendichtring", "de", "rwdr_elastomer_standard"),
        ("Cassette-seal", "en", "rwdr_elastomer_cassette"),
        ("V Ring", "de", "rwdr_elastomer_v_ring"),
    ],
)
def test_lookup_seed_mapping_cases(
    service: TerminologyService,
    db,
    query: str,
    language: str,
    expected_concept: str,
) -> None:
    matches = service.lookup_term(db, query, language=language)

    assert len(matches) >= 1
    assert matches[0].concept.canonical_name == expected_concept
    assert matches[0].provenance.source_reference.startswith("seed:")
    assert matches[0].provenance.confidence >= 2


@pytest.mark.parametrize(
    ("query", "language"),
    [
        ("Unbekannter Herstellername", "de"),
        ("", "de"),
        ("   ", "de"),
        ("radial shaft seal", "de"),
        ("Wellendichtring", "en"),
    ],
)
def test_lookup_unknown_terms_returns_empty(
    service: TerminologyService,
    db,
    query: str,
    language: str,
) -> None:
    assert service.lookup_term(db, query, language=language) == []


@pytest.mark.parametrize(
    ("query", "language", "expected_status", "expected_concept"),
    [
        ("Simmerring PTFE", "de", NormalizationStatus.UNIQUE, "rwdr_ptfe_lip_spring_loaded"),
        ("Simmerring", "de", NormalizationStatus.UNIQUE, "rwdr_elastomer_standard"),
        ("PTFE-RWDR", "de", NormalizationStatus.UNIQUE, "rwdr_ptfe_lip_spring_loaded"),
        ("Teflon seal", "de", NormalizationStatus.UNIQUE, "rwdr_ptfe_lip_spring_loaded"),
        ("Oil seal", "en", NormalizationStatus.UNIQUE, "rwdr_elastomer_standard"),
        ("Shaft seal", "en", NormalizationStatus.AMBIGUOUS, None),
        ("Dichtring", "de", NormalizationStatus.AMBIGUOUS, None),
        ("not registered", "en", NormalizationStatus.NO_MATCH, None),
        ("Pending Seal", "de", NormalizationStatus.NO_MATCH, None),
        ("Inactive Seal", "de", NormalizationStatus.NO_MATCH, None),
    ],
)
def test_normalize_term_status_cases(
    service: TerminologyService,
    db,
    query: str,
    language: str,
    expected_status: NormalizationStatus,
    expected_concept: str | None,
) -> None:
    result = service.normalize_term(db, query, language=language)

    assert result.status is expected_status
    if expected_concept is None:
        assert result.concept is None
    else:
        assert result.concept is not None
        assert result.concept.canonical_name == expected_concept


def test_multiple_manufacturer_terms_can_normalize_to_same_generic_concept(
    service: TerminologyService,
    db,
) -> None:
    concepts = {
        service.normalize_term(db, term).concept.canonical_name
        for term in ("Simmerring PTFE", "Turcon Variseal", "PTFE POP Seal")
    }

    assert concepts == {"rwdr_ptfe_lip_spring_loaded"}


@pytest.mark.parametrize(
    ("query", "manufacturer_id", "include_generic_scope", "expected_count"),
    [
        ("Simmerring", "m-freudenberg", True, 1),
        ("Simmerring", "m-trelleborg", True, 0),
        ("Turcon Variseal", "m-trelleborg", False, 1),
        ("Turcon Variseal", "m-freudenberg", False, 0),
        ("PTFE-RWDR", "m-freudenberg", True, 1),
        ("PTFE-RWDR", "m-freudenberg", False, 0),
    ],
)
def test_lookup_respects_manufacturer_scope(
    service: TerminologyService,
    db,
    query: str,
    manufacturer_id: str,
    include_generic_scope: bool,
    expected_count: int,
) -> None:
    matches = service.lookup_term(
        db,
        query,
        manufacturer_id=manufacturer_id,
        include_generic_scope=include_generic_scope,
    )

    assert len(matches) == expected_count


def test_provenance_fields_are_returned(service: TerminologyService, db) -> None:
    match = service.lookup_term(db, "Turcon Variseal")[0]

    assert match.term.term_id == "t-variseal"
    assert match.term.originating_manufacturer_id == "m-trelleborg"
    assert match.term.is_trademark is True
    assert match.provenance.mapping_id == "map-t-variseal-1"
    assert match.provenance.source_type == "manufacturer_datasheet"
    assert match.provenance.reviewer_status == "published"
    assert match.provenance.is_active is True
    assert match.match_kind in {"raw_exact", "normalized_exact"}


def test_as_of_filters_expired_mapping(service: TerminologyService, db) -> None:
    assert service.normalize_term(db, "Old Seal", as_of=date(2020, 6, 1)).status is (
        NormalizationStatus.UNIQUE
    )
    assert service.normalize_term(db, "Old Seal", as_of=date(2022, 1, 1)).status is (
        NormalizationStatus.NO_MATCH
    )


def test_published_only_can_include_pending_mapping(service: TerminologyService, db) -> None:
    assert service.normalize_term(db, "Pending Seal").status is NormalizationStatus.NO_MATCH
    assert (
        service.normalize_term(db, "Pending Seal", published_only=False).status
        is NormalizationStatus.UNIQUE
    )


def test_active_only_can_include_inactive_mapping(service: TerminologyService, db) -> None:
    assert service.normalize_term(db, "Inactive Seal").status is NormalizationStatus.NO_MATCH
    assert (
        service.normalize_term(db, "Inactive Seal", active_only=False).status
        is NormalizationStatus.UNIQUE
    )


def test_lookup_audit_writes_event_for_matches(service: TerminologyService, db) -> None:
    matches = service.lookup_term(db, "Simmerring PTFE", audit=True, actor_id="tester")

    assert len(matches) == 1
    audit = db.execute(sa.text("SELECT action, actor_id FROM term_audit_log")).mappings().one()
    assert audit["action"] == "lookup_term"
    assert audit["actor_id"] == "tester"


def test_normalization_audit_writes_event_with_status(service: TerminologyService, db) -> None:
    result = service.normalize_term(db, "Simmerring PTFE", audit=True, actor_id="tester")

    assert result.status is NormalizationStatus.UNIQUE
    audit = db.execute(sa.text("SELECT action, payload FROM term_audit_log")).mappings().one()
    assert audit["action"] == "normalize_term"
    assert '"status": "unique"' in audit["payload"]


def test_record_audit_event_rejects_missing_target(service: TerminologyService, db) -> None:
    with pytest.raises(ValueError, match="requires mapping_id"):
        service.record_audit_event(db, action="bad_event")


def test_service_has_no_langgraph_agent_or_fastapi_imports() -> None:
    source = inspect.getsource(service_module)

    assert "app.agent" not in source
    assert "langgraph" not in source.lower()
    assert "fastapi" not in source.lower()
