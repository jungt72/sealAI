
import sys
from qdrant_client import QdrantClient

client = QdrantClient(url="http://qdrant:6333")
try:
    info = client.get_collection("sealai_knowledge_v2")
    print(f"EXISTS: {info.status}")
    # Verify sparse config
    if info.config.params.sparse_vectors_config:
        print("SPARSE_CONFIG: OK")
    else:
        print("SPARSE_CONFIG: MISSING")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
