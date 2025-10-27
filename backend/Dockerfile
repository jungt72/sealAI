# =========================
# Builder: Wheels erzeugen
# =========================
FROM python:3.11-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 DEBIAN_FRONTEND=noninteractive
WORKDIR /opt/build

# Build-Tools nur im Builder (Runtime bleibt schlank)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev pkg-config libffi-dev rustc cargo \
 && rm -rf /var/lib/apt/lists/*

# Eine zentrale requirements.txt
COPY requirements.txt ./requirements.txt

# Stabiler Resolver + Wheels bauen (für offline-Installation im Runtime-Stage)
RUN python -m pip install --upgrade pip \
 && pip wheel --no-cache-dir --wheel-dir /opt/wheels -r requirements.txt


# =========================
# Runtime: schlank & offline
# =========================
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Nur was wirklich gebraucht wird:
# - libgomp1: OpenMP für onnxruntime (CPU)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Non-root User
RUN useradd -m -u 10001 -s /usr/sbin/nologin appuser

# Python-Deps offline aus Wheels installieren
COPY --from=builder /opt/wheels /opt/wheels
COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip \
 && pip install --no-index --find-links /opt/wheels -r /tmp/requirements.txt

# App-Code
COPY app ./app
COPY agents ./agents
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

# Rechte & Run-User
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
