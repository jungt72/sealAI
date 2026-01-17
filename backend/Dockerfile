# =========================
# Builder: Wheels erzeugen
# =========================
FROM python:3.11-slim AS builder
ARG INSTALL_DEV=false
ARG USE_REQUIREMENTS_LOCK=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 DEBIAN_FRONTEND=noninteractive
WORKDIR /opt/build

# Build-Tools nur im Builder (Runtime bleibt schlank)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev pkg-config libffi-dev rustc cargo \
 && rm -rf /var/lib/apt/lists/*

# Eine zentrale requirements.txt
COPY requirements.txt ./requirements.txt
COPY requirements-lock.txt ./requirements-lock.txt
COPY requirements-dev.txt ./requirements-dev.txt

# Stabiler Resolver + Wheels bauen (für offline-Installation im Runtime-Stage)
RUN python -m pip install --upgrade pip \
 && if [ "$USE_REQUIREMENTS_LOCK" = "1" ]; then \
      if [ -f requirements-lock.txt ]; then \
        echo "Using requirements-lock.txt for wheel build"; \
        REQ_FILE=requirements-lock.txt; \
      else \
        echo "Missing requirements-lock.txt. Run ops/gen_backend_requirements_lock.sh or set USE_REQUIREMENTS_LOCK=0"; \
        exit 1; \
      fi; \
    else \
      echo "Using requirements.txt for wheel build"; \
      REQ_FILE=requirements.txt; \
    fi \
 && python -m pip wheel --no-cache-dir --wheel-dir /opt/wheels -r "$REQ_FILE" \
 && if [ "$INSTALL_DEV" = "true" ]; then \
      python -m pip wheel --no-cache-dir --wheel-dir /opt/wheels -r requirements-dev.txt; \
    fi


# =========================
# Runtime: schlank & offline
# =========================
FROM python:3.11-slim
ARG INSTALL_DEV=false
ARG USE_REQUIREMENTS_LOCK=1
ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 DEBIAN_FRONTEND=noninteractive
WORKDIR /app
ENV PYTHONPATH=/app

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
COPY requirements-lock.txt /tmp/requirements-lock.txt
COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN python -m pip install --upgrade pip \
 && if [ "$USE_REQUIREMENTS_LOCK" = "1" ]; then \
      if [ -f /tmp/requirements-lock.txt ]; then \
        echo "Using requirements-lock.txt for install"; \
        REQ_FILE=/tmp/requirements-lock.txt; \
      else \
        echo "Missing requirements-lock.txt. Run ops/gen_backend_requirements_lock.sh or set USE_REQUIREMENTS_LOCK=0"; \
        exit 1; \
      fi; \
    else \
      echo "Using requirements.txt for install"; \
      REQ_FILE=/tmp/requirements.txt; \
    fi \
 && python -m pip install --no-index --find-links /opt/wheels -r "$REQ_FILE" \
 && if [ "$INSTALL_DEV" = "true" ]; then \
      python -m pip install --no-index --find-links /opt/wheels -r /tmp/requirements-dev.txt; \
    fi

# App-Code
COPY pytest.ini ./pytest.ini
COPY app ./app
COPY agents ./agents
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

# Rechte & Run-User
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
