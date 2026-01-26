
from qdrant_client import QdrantClient

client = QdrantClient(url="http://qdrant:6333")
col = "sealai_knowledge_v2"

try:
    count = client.count(col)
    print(f"COUNT: {count.count}")
    
    if count.count > 0:
        points = client.scroll(col, limit=1)[0]
        print(f"SAMPLE PAYLOAD: {points[0].payload}")
except Exception as e:
    print(f"ERROR: {e}")
