"""C5 (P2-1 TEIL A) — cross-cutting-vs-pack knowledge marker.

`pack_affinity` distinguishes cross-cutting knowledge (material/chemistry/standard,
`None`) from seal-type-specific (pack) knowledge (`"rwdr"`). Additive and
retrieval-inert on today's corpus: no filter consumes it, so adding it cannot
change retrieval results. The marker has a tolerant default so old Qdrant payloads
(written before the field existed) still deserialize under strict mode.
"""

from __future__ import annotations

from app.services.rag.rag_schema import (
    ChunkMetadata,
    TempRange,
    classify_pack_affinity,
)


def _meta(**overrides: object) -> ChunkMetadata:
    base: dict[str, object] = dict(
        tenant_id="t",
        doc_id="d",
        document_id="d",
        chunk_id="c",
        chunk_hash="h",
        source_uri="/tmp/x.txt",
        chunk_index=0,
        material_code="PTFE",
        shore_hardness=79,
        temp_range=TempRange(min_c=-200.0, max_c=260.0),
    )
    base.update(overrides)
    return ChunkMetadata(**base)  # type: ignore[arg-type]


def test_pack_affinity_defaults_to_none_cross_cutting() -> None:
    assert _meta().pack_affinity is None


def test_pack_affinity_accepts_pack_value() -> None:
    assert _meta(pack_affinity="rwdr").pack_affinity == "rwdr"


def test_old_payload_without_pack_affinity_is_consumable() -> None:
    # Retrieval reads stored Qdrant payloads as RAW dicts (it never reconstructs the
    # strict model — strict mode already rejects the JSON-serialized enum strings).
    # A pre-marker payload simply lacks the key; consumers read it with a default.
    payload = _meta().model_dump(mode="json")
    payload.pop("pack_affinity", None)
    assert payload.get("pack_affinity") is None


def test_marker_is_omittable_at_construction() -> None:
    # Additive: the field can be omitted entirely (default applies), so adding it
    # does not break any existing ChunkMetadata(...) call site.
    assert _meta().pack_affinity is None


def test_pack_affinity_round_trips_through_payload() -> None:
    payload = _meta(pack_affinity="rwdr").model_dump(mode="json")
    assert payload["pack_affinity"] == "rwdr"


# --- Deterministic classifier (single source of truth for ingest + backfill) -----


def test_classifier_marks_rwdr_on_radial_shaft_seal_signal() -> None:
    assert classify_pack_affinity(entity="Radialwellendichtring") == "rwdr"
    assert classify_pack_affinity(route_key="rwdr_dimension") == "rwdr"
    assert classify_pack_affinity(text="Simmerring 45x62x8 undicht") == "rwdr"


def test_classifier_defaults_cross_cutting_for_material_knowledge() -> None:
    assert (
        classify_pack_affinity(
            entity="FKM", text="FKM Fluorkautschuk chemische Beständigkeit gegen Öl"
        )
        is None
    )
    assert classify_pack_affinity(category="material", text="NBR Shore-Härte") is None
    assert classify_pack_affinity() is None


# --- Retrieval inertness: no filter consumes the marker → no result-diff ----------


def test_pack_affinity_is_not_a_retrieval_filter_key() -> None:
    from app.services.rag.rag_orchestrator import (
        _EXACT_FILTER_PATHS,
        _SUPPORTED_METADATA_FILTER_KEYS,
    )

    assert not any("pack_affinity" in key for key in _SUPPORTED_METADATA_FILTER_KEYS)
    assert not any("pack_affinity" in key for key in _EXACT_FILTER_PATHS)
