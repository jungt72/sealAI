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

# Eine zentrale requirements.txt
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
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Nur was wirklich gebraucht wird:
# - libgomp1: OpenMP für onnxruntime (CPU)
# - curl: healthchecks
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 curl \
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
COPY agents ./agents
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY prompts ./prompts

# Rechte & Run-User
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health >/dev/null || exit 1

CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
