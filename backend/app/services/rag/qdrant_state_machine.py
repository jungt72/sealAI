from qdrant_client import QdrantClient
from qdrant_client.models import (
    Filter, FieldCondition, MatchValue,
    SetPayloadOperation, SetPayload
)
from datetime import datetime, timezone
import uuid

class PublishTransitionError(Exception):
    pass

def transition_to_published_bulletproof(
    client: QdrantClient,
    collection_name: str,
    logical_document_key: str,
    new_version_id: int,
    new_qdrant_id: str,
) -> dict:
    """
    Atomares State-Update (VALIDATED -> PUBLISHED).
    Nutzt Qdrant Batch-Update, um Race-Conditions mit dem LangGraph-Agenten zu verhindern.
    """
    publish_ts = datetime.now(timezone.utc).isoformat()
    operation_id = str(uuid.uuid4())

    # 1. Verify Zustand des neuen Points
    target = client.retrieve(
        collection_name=collection_name,
        ids=[new_qdrant_id],
        with_payload=["document_meta.status"]
    )
    if not target or target[0].payload is None or target[0].payload.get("document_meta", {}).get("status") != "VALIDATED":
        raise PublishTransitionError(f"Point {new_qdrant_id} nicht gefunden oder nicht VALIDATED.")

    # 2. Hole IDs aller alten Versionen dieses Dokuments
    old_points_scroll, _ = client.scroll(
        collection_name=collection_name,
        scroll_filter=Filter(
            must=[FieldCondition(key="document_meta.logical_document_key", match=MatchValue(value=logical_document_key))],
            must_not=[FieldCondition(key="document_meta.version_id", match=MatchValue(value=new_version_id))]
        ),
        limit=1000,
        with_payload=False
    )
    old_ids = [p.id for p in old_points_scroll]

    # 3. Das gebündelte, synchrone Batch Update
    operations = []
    if old_ids:
        operations.append(
            SetPayloadOperation(
                set_payload=SetPayload(
                    payload={
                        "document_meta": {
                            "status": "DEPRECATED",
                            "deprecated_ts": publish_ts,
                            "operation_id": operation_id,
                        }
                    },
                    points=old_ids
                )
            )
        )
        
    operations.append(
        SetPayloadOperation(
            set_payload=SetPayload(
                payload={
                    "document_meta": {
                        "status": "PUBLISHED",
                        "published_ts": publish_ts,
                        "operation_id": operation_id,
                    }
                },
                points=[new_qdrant_id]
            )
        )
    )

    client.batch_update_points(collection_name=collection_name, update_operations=operations, wait=True)

    # 4. Final Verify
    verify_new = client.retrieve(collection_name=collection_name, ids=[new_qdrant_id], with_payload=["document_meta.status"])
    if not verify_new or verify_new[0].payload.get("document_meta", {}).get("status") != "PUBLISHED":
        raise PublishTransitionError("CRITICAL: Batch update failed.")

    return {
        "status": "SUCCESS",
        "operation_id": operation_id,
        "published_id": new_qdrant_id,
        "deprecated_ids": old_ids
    }
