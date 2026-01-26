# =========================
# Builder: Wheels erzeugen
# =========================
FROM python:3.11-slim AS builder
ARG INSTALL_DEV=false
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 DEBIAN_FRONTEND=noninteractive
WORKDIR /opt/build

# Build-Tools nur im Builder (Runtime bleibt schlank)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev pkg-config libffi-dev rustc cargo \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
COPY requirements-dev.txt ./requirements-dev.txt

# Stabiler Resolver + Wheels bauen (für offline-Installation im Runtime-Stage)
RUN mkdir -p /opt/wheels \
 && python -m pip install --upgrade pip \
 && python -m pip wheel --no-cache-dir --wheel-dir /opt/wheels -r requirements.txt \
 && if [ "$INSTALL_DEV" = "true" ]; then \
      python -m pip wheel --no-cache-dir --wheel-dir /opt/wheels -r requirements-dev.txt; \
    fi


# =========================
# Runtime: schlank & offline
# =========================
FROM python:3.11-slim

ARG INSTALL_DEV=false
ARG WARMUP_MODELS=false

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    HF_HOME=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence_transformers \
    TRANSFORMERS_CACHE=/app/.cache/huggingface \
    FASTEMBED_CACHE_PATH=/app/.cache/fastembed \
    WARMUP_MODELS=$WARMUP_MODELS

WORKDIR /app

# Runtime libs
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Non-root User
RUN useradd -m -u 10001 -s /usr/sbin/nologin appuser

# Python-Deps offline aus Wheels installieren
COPY --from=builder /opt/wheels /opt/wheels
COPY requirements.txt /tmp/requirements.txt
COPY requirements-dev.txt /tmp/requirements-dev.txt

RUN python -m pip install --upgrade pip \
 && python -m pip install --no-index --find-links /opt/wheels -r /tmp/requirements.txt \
 && if [ "$INSTALL_DEV" = "true" ]; then \
      python -m pip install --no-index --find-links /opt/wheels -r /tmp/requirements-dev.txt; \
    fi

# App-Code
COPY app ./app
COPY sitecustomize.py /usr/local/lib/python3.11/site-packages/sitecustomize.py
COPY agents ./agents
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

# Optional: Modelle beim Build warmupen (macht Image größer, braucht Internet beim Build)
# Wichtig: Kein Shell-if/fi um den Heredoc, sonst Dockerfile-Parse-Probleme.
RUN python - <<'PY'
import os
from pathlib import Path

warm = os.getenv("WARMUP_MODELS", "false").strip().lower() in {"1", "true", "yes", "on"}
hf_home = os.getenv("HF_HOME", "/app/.cache/huggingface")
st_home = os.getenv("SENTENCE_TRANSFORMERS_HOME", "/app/.cache/sentence_transformers")
fe_cache = os.getenv("FASTEMBED_CACHE_PATH", "/app/.cache/fastembed")

print("Warmup enabled?" , warm)
print("HF_HOME=", hf_home)
print("SENTENCE_TRANSFORMERS_HOME=", st_home)
print("FASTEMBED_CACHE_PATH=", fe_cache)

if not warm:
    raise SystemExit(0)

for p in (hf_home, st_home, fe_cache):
    Path(p).mkdir(parents=True, exist_ok=True)

# FastEmbed warmup (falls installiert / genutzt)
try:
    from fastembed import TextEmbedding
    TextEmbedding()  # default model; ok for prefetch
    print("fastembed warmup: OK")
except Exception as e:
    print("fastembed warmup: skipped:", e)

# SentenceTransformers warmup (falls genutzt)
try:
    from sentence_transformers import SentenceTransformer
    SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    print("sentence-transformers warmup: OK")
except Exception as e:
    print("sentence-transformers warmup: skipped:", e)
PY

# Rechte & Run-User (inkl. Cache)
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
