"""Tests fuer Qdrant-Collection-Setup (sealai_technical_docs).

Teilt sich in zwei Gruppen:
  1. Unit-Tests: pruefen Logik von setup_collections.py ohne echten Qdrant
  2. Integration-Tests (marker: qdrant_live): pruefen gegen laufenden Qdrant
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agent.rag.setup_collections import (
    COLLECTION_NAME,
    DENSE_DIM,
    DENSE_VECTOR_NAME,
    PAYLOAD_INDICES,
    SPARSE_VECTOR_NAME,
    collection_exists,
    create_collection,
    ensure_payload_indices,
    setup,
)


# ── Konstanten ──────────────────────────────────────────────────────


class TestConstants:
    def test_collection_name(self):
        assert COLLECTION_NAME == "sealai_technical_docs"

    def test_dense_dim(self):
        assert DENSE_DIM == 384

    def test_dense_vector_name(self):
        assert DENSE_VECTOR_NAME == "dense"

    def test_sparse_vector_name(self):
        assert SPARSE_VECTOR_NAME == "bm25"

    def test_payload_indices_complete(self):
        expected = {"sts_mat_codes", "sts_type_codes", "doc_type", "language"}
        assert set(PAYLOAD_INDICES.keys()) == expected

    def test_payload_indices_all_keyword(self):
        from qdrant_client.models import PayloadSchemaType

        for name, schema in PAYLOAD_INDICES.items():
            assert schema == PayloadSchemaType.KEYWORD, (
                f"{name} sollte KEYWORD sein, ist {schema}"
            )


# ── Unit-Tests mit Mock-Client ──────────────────────────────────────


class TestCollectionExists:
    def test_exists_true(self):
        client = MagicMock()
        client.get_collection.return_value = MagicMock()
        assert collection_exists(client, "test") is True

    def test_exists_false_on_exception(self):
        client = MagicMock()
        client.get_collection.side_effect = Exception("not found")
        assert collection_exists(client, "test") is False


class TestCreateCollection:
    def test_creates_when_not_exists(self):
        client = MagicMock()
        client.get_collection.side_effect = Exception("not found")
        result = create_collection(client)
        assert result is True
        client.create_collection.assert_called_once()

    def test_skips_when_exists(self):
        client = MagicMock()
        client.get_collection.return_value = MagicMock()
        result = create_collection(client)
        assert result is False
        client.create_collection.assert_not_called()

    def test_create_uses_correct_params(self):
        client = MagicMock()
        client.get_collection.side_effect = Exception("not found")
        create_collection(client)

        call_kwargs = client.create_collection.call_args
        assert call_kwargs.kwargs["collection_name"] == COLLECTION_NAME
        vectors = call_kwargs.kwargs["vectors_config"]
        assert DENSE_VECTOR_NAME in vectors
        sparse = call_kwargs.kwargs["sparse_vectors_config"]
        assert SPARSE_VECTOR_NAME in sparse
        assert call_kwargs.kwargs["on_disk_payload"] is True


class TestEnsurePayloadIndices:
    def test_creates_missing_indices(self):
        client = MagicMock()
        info = MagicMock()
        info.payload_schema = {}
        client.get_collection.return_value = info

        created = ensure_payload_indices(client)
        assert set(created) == set(PAYLOAD_INDICES.keys())
        assert client.create_payload_index.call_count == len(PAYLOAD_INDICES)

    def test_skips_existing_indices(self):
        client = MagicMock()
        info = MagicMock()
        info.payload_schema = {
            "sts_mat_codes": MagicMock(),
            "sts_type_codes": MagicMock(),
            "doc_type": MagicMock(),
            "language": MagicMock(),
        }
        client.get_collection.return_value = info

        created = ensure_payload_indices(client)
        assert created == []
        client.create_payload_index.assert_not_called()

    def test_creates_only_missing(self):
        client = MagicMock()
        info = MagicMock()
        info.payload_schema = {
            "sts_mat_codes": MagicMock(),
            "doc_type": MagicMock(),
        }
        client.get_collection.return_value = info

        created = ensure_payload_indices(client)
        assert set(created) == {"sts_type_codes", "language"}
        assert client.create_payload_index.call_count == 2


# ── Live-Integration-Tests ──────────────────────────────────────────

# Diese Tests laufen nur wenn QDRANT_TEST_URL gesetzt ist oder
# der qdrant_live Marker explizit angefordert wird.


def _get_qdrant_url() -> str | None:
    """Versuche eine erreichbare Qdrant-URL zu ermitteln."""
    import os

    url = os.environ.get("QDRANT_TEST_URL")
    if url:
        return url
    # Versuche Container-IP zu finden
    try:
        import subprocess

        result = subprocess.run(
            [
                "docker", "inspect", "qdrant",
                "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        ip = result.stdout.strip()
        if ip:
            return f"http://{ip}:6333"
    except Exception:
        pass
    return None


@pytest.fixture
def qdrant_url():
    url = _get_qdrant_url()
    if url is None:
        pytest.skip("Kein erreichbarer Qdrant-Server gefunden")
    return url


class TestLiveQdrantSetup:
    """Integration-Tests gegen laufenden Qdrant."""

    def test_setup_idempotent(self, qdrant_url: str):
        result1 = setup(qdrant_url)
        result2 = setup(qdrant_url)
        # Zweiter Aufruf erstellt nichts Neues
        assert result2["created"] is False
        assert result2["new_indices"] == []

    def test_collection_config_correct(self, qdrant_url: str):
        setup(qdrant_url)
        from qdrant_client import QdrantClient

        client = QdrantClient(url=qdrant_url, timeout=10)
        info = client.get_collection(COLLECTION_NAME)

        # Dense Vector: 384-dim Cosine
        vectors = info.config.params.vectors
        assert isinstance(vectors, dict)
        dense = vectors[DENSE_VECTOR_NAME]
        assert dense.size == 384
        assert str(dense.distance) == "Cosine"

        # Sparse Vector: bm25
        sparse = info.config.params.sparse_vectors
        assert SPARSE_VECTOR_NAME in sparse

        # on_disk_payload
        assert info.config.params.on_disk_payload is True

    def test_payload_indices_present(self, qdrant_url: str):
        setup(qdrant_url)
        from qdrant_client import QdrantClient

        client = QdrantClient(url=qdrant_url, timeout=10)
        info = client.get_collection(COLLECTION_NAME)

        existing_indices = set(info.payload_schema.keys())
        for field_name in PAYLOAD_INDICES:
            assert field_name in existing_indices, (
                f"Payload-Index '{field_name}' fehlt"
            )

    def test_all_indices_are_keyword_type(self, qdrant_url: str):
        setup(qdrant_url)
        from qdrant_client import QdrantClient

        client = QdrantClient(url=qdrant_url, timeout=10)
        info = client.get_collection(COLLECTION_NAME)

        for field_name in PAYLOAD_INDICES:
            schema = info.payload_schema[field_name]
            assert schema.data_type.value == "keyword", (
                f"Index '{field_name}' ist {schema.data_type}, erwartet keyword"
            )

    def test_old_collection_untouched(self, qdrant_url: str):
        """sealai_knowledge_v3 darf nicht geloescht worden sein."""
        from qdrant_client import QdrantClient

        client = QdrantClient(url=qdrant_url, timeout=10)
        collections = [c.name for c in client.get_collections().collections]
        assert "sealai_knowledge_v3" in collections, (
            "Alte Collection sealai_knowledge_v3 wurde geloescht!"
        )
