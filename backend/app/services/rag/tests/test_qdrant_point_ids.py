from __future__ import annotations

from types import SimpleNamespace

from app.services.rag.qdrant_point_ids import (
    build_point_ids,
    file_source_id,
    qdrant_point_id,
)


def test_qdrant_point_id_is_stable_for_same_inputs() -> None:
    first = qdrant_point_id(
        tenant_id="tenant-1",
        source_id="source-1",
        chunk_index=0,
        chunk_text="hello",
    )
    second = qdrant_point_id(
        tenant_id="tenant-1",
        source_id="source-1",
        chunk_index=0,
        chunk_text="hello",
    )
    assert first == second


def test_qdrant_point_id_changes_with_tenant() -> None:
    base = qdrant_point_id(
        tenant_id="tenant-1",
        source_id="source-1",
        chunk_index=0,
        chunk_text="hello",
    )
    other = qdrant_point_id(
        tenant_id="tenant-2",
        source_id="source-1",
        chunk_index=0,
        chunk_text="hello",
    )
    assert base != other


def test_qdrant_point_id_changes_with_chunk_index() -> None:
    base = qdrant_point_id(
        tenant_id="tenant-1",
        source_id="source-1",
        chunk_index=0,
        chunk_text="hello",
    )
    other = qdrant_point_id(
        tenant_id="tenant-1",
        source_id="source-1",
        chunk_index=1,
        chunk_text="hello",
    )
    assert base != other


def test_qdrant_point_id_changes_with_source() -> None:
    base = qdrant_point_id(
        tenant_id="tenant-1",
        source_id="source-1",
        chunk_index=0,
        chunk_text="hello",
    )
    other = qdrant_point_id(
        tenant_id="tenant-1",
        source_id="source-2",
        chunk_index=0,
        chunk_text="hello",
    )
    assert base != other


def test_build_point_ids_uses_chunk_index_and_text() -> None:
    chunks = [SimpleNamespace(page_content="hello"), SimpleNamespace(page_content="world")]
    ids = build_point_ids(tenant_id="tenant-1", source_id="source-1", chunks=chunks)
    assert len(ids) == 2
    assert ids[0] != ids[1]


def test_file_source_id_is_stable_for_same_file(tmp_path) -> None:
    file_path = tmp_path / "doc.txt"
    file_path.write_text("abc", encoding="utf-8")
    first = file_source_id(str(file_path))
    second = file_source_id(str(file_path))
    assert first == second
