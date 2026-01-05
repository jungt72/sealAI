#!/bin/bash

set -e

cd backend/

echo "📁 Lege neue Struktur an..."
mkdir -p app/{models,services/{auth,ragg,prompt,streaming,memory,utils},api/v1,config,tests,schemas}

echo "📦 Verschiebe Modelle..."
mv app/models/chat_message*.py app/models/chat.py || true
mv app/models/chat.py app/models/chat.py || true

echo "🧠 Services aufteilen..."
mv app/services/ai_service.py app/services/rag/rag_service.py || true
mv app/services/chat_db_service.py app/services/memory/memory_service.py || true
mv app/services/prompt/* app/services/prompt/ || true
mv app/services/streaming/* app/services/streaming/ || true
mv app/services/keycloak_service.py app/services/auth/keycloak_service.py || true
mv app/services/auth_service.py app/services/auth/auth_service.py || true
mv app/services/redis_service.py app/services/utils/redis_service.py || true
mv app/services/helpers.py app/services/utils/helpers.py || true
mv app/services/auth.py app/services/utils/auth.py || true

echo "🧪 Testdateien verschieben..."
mkdir -p app/tests/
mv app/test_langchain.py app/tests/test_langchain.py || true
mv app/api/test_redis.py app/tests/test_redis.py || true

echo "🧹 Entferne veraltete Dateien..."
rm -rf venv sealai_venv
rm -f app/services/keycloak_auth_deprecated.py || true

echo "📁 API bereinigen..."
mv app/api/schemas.py app/schemas/schemas.py || true
mv app/api/v1/* app/api/v1/ || true
rm -f app/api/requirements.txt || true

echo "✅ Migration abgeschlossen."
tree -L 3 app/
