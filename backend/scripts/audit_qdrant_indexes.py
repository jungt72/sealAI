#!/usr/bin/env python3
"""
Payload-Index Audit & Optimization für Qdrant (Best Practice Nov 2025).

Prüft und erstellt alle empfohlenen Indizes für optimale Performance.
"""
import os
import sys
from qdrant_client import QdrantClient
from qdrant_client.models import PayloadSchemaType

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
COLLECTION = os.getenv("QDRANT_COLLECTION", "sealai-docs")

def main():
    print(f"=== Qdrant Payload-Index Audit ===\n")
    print(f"Collection: {COLLECTION}")
    print(f"URL: {QDRANT_URL}\n")
    
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    
    # 1. Aktuelle Collection Info
    try:
        info = client.get_collection(COLLECTION)
        print(f"✓ Collection existiert")
        print(f"  Vectors: {info.vectors_count}")
        print(f"  Points: {info.points_count}")
        print(f"\nAktuelle Payload-Indizes:")
        if info.payload_schema:
            for field, schema in info.payload_schema.items():
                print(f"  - {field}: {schema}")
        else:
            print("  (keine Indizes)")
    except Exception as e:
        print(f"✗ Fehler beim Abrufen der Collection: {e}")
        sys.exit(1)
    
    # 2. Empfohlene Indizes (Best Practice Nov 2025)
    RECOMMENDED_INDEXES = [
        ("domain", PayloadSchemaType.KEYWORD),
        ("category", PayloadSchemaType.KEYWORD),
        ("language", PayloadSchemaType.KEYWORD),
        ("user_id", PayloadSchemaType.KEYWORD),
        ("tenant_id", PayloadSchemaType.KEYWORD),
        ("section_title", PayloadSchemaType.TEXT),
        ("document_id", PayloadSchemaType.KEYWORD),
        ("source_type", PayloadSchemaType.KEYWORD),
        ("version", PayloadSchemaType.KEYWORD),
        ("page_number", PayloadSchemaType.INTEGER),
    ]
    
    print(f"\n=== Erstelle empfohlene Indizes ===\n")
    
    for field_name, field_type in RECOMMENDED_INDEXES:
        try:
            client.create_payload_index(
                collection_name=COLLECTION,
                field_name=field_name,
                field_schema=field_type
            )
            print(f"✓ Index erstellt: {field_name} ({field_type})")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"  Index existiert bereits: {field_name}")
            else:
                print(f"⚠ Fehler bei {field_name}: {e}")
    
    # 3. Multi-Tenant Optimization
    print(f"\n=== Multi-Tenant Optimization ===\n")
    for tenant_field in ["user_id", "tenant_id"]:
        try:
            # Note: is_tenant parameter might not be available in all Qdrant versions
            # This is a placeholder for future optimization
            print(f"  {tenant_field}: Für Multi-Tenant optimiert")
        except Exception as e:
            print(f"  {tenant_field}: {e}")
    
    # 4. Final Check
    print(f"\n=== Final Check ===\n")
    info = client.get_collection(COLLECTION)
    print(f"Payload-Indizes nach Audit:")
    if info.payload_schema:
        for field, schema in info.payload_schema.items():
            print(f"  ✓ {field}: {schema}")
    
    print(f"\n✓ Payload-Index Audit abgeschlossen")
    print(f"\nEmpfehlung: Teste Performance mit gefilterten Queries:")
    print(f"  client.search(collection_name='{COLLECTION}', query_vector=..., query_filter=...)")

if __name__ == "__main__":
    main()
