from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.rag.rag_schema import ChunkMetadata, TempRange


def test_chunk_metadata_requires_core_fields_in_strict_mode() -> None:
    with pytest.raises(ValidationError):
        ChunkMetadata(
            tenant_id="tenant-1",
            doc_id="doc-1",
            document_id="doc-1",
            chunk_id="chunk-1",
            chunk_hash="hash-1",
            source_uri="/tmp/doc.txt",
            chunk_index=0,
            # Missing material_code/shore_hardness/temp_range
        )


def test_chunk_metadata_accepts_dynamic_additional_metadata() -> None:
    meta = ChunkMetadata(
        tenant_id="tenant-1",
        doc_id="doc-1",
        document_id="doc-1",
        chunk_id="chunk-1",
        chunk_hash="hash-1",
        source_uri="/tmp/doc.txt",
        chunk_index=0,
        material_code="PTFE",
        shore_hardness=79,
        temp_range=TempRange(min_c=-200.0, max_c=260.0),
        additional_metadata={
            "density_kg_m3": 2200.0,
            "thermal_conductivity_w_mk": 0.25,
            "custom_vendor_code": "KYR-PTFE-79X",
            "application_domains": ["seals", "wire_insulation"],
        },
    )
    assert meta.additional_metadata.get("density_kg_m3") == 2200.0
    assert meta.additional_metadata.get("custom_vendor_code") == "KYR-PTFE-79X"
