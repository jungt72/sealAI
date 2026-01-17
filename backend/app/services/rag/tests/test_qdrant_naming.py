from app.services.rag.qdrant_naming import qdrant_collection_name


def test_qdrant_collection_name_prefix_and_tenant() -> None:
    assert qdrant_collection_name(base="sealai-docs", prefix="rag", tenant_id="tenant-1") == "rag:tenant-1"


def test_qdrant_collection_name_tenant_without_prefix() -> None:
    assert qdrant_collection_name(base="sealai-docs", prefix="", tenant_id="tenant-1") == "sealai-docs"


def test_qdrant_collection_name_prefix_without_tenant() -> None:
    assert qdrant_collection_name(base="sealai-docs", prefix="rag", tenant_id=None) == "sealai-docs"


def test_qdrant_collection_name_base_only() -> None:
    assert qdrant_collection_name(base="sealai-docs", prefix=None, tenant_id=None) == "sealai-docs"
