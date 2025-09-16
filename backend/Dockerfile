# syntax=docker/dockerfile:1.6
FROM python:3.11-slim AS builder
WORKDIR /opt/build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc curl libpq-dev && rm -rf /var/lib/apt/lists/*
COPY requirements*.txt ./
RUN set -eux; \
    if [ -f requirements.txt ]; then pip wheel -r requirements.txt -w /opt/wheels; \
    elif [ -f requirements.prod.txt ]; then pip wheel -r requirements.prod.txt -w /opt/wheels; \
    fi

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 10001 -s /usr/sbin/nologin appuser

# Python deps
COPY --from=builder /opt/wheels /opt/wheels
COPY requirements*.txt ./
RUN set -eux; \
    if ls /opt/wheels/*.whl >/dev/null 2>&1; then pip install /opt/wheels/*; fi; \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; \
    elif [ -f requirements.prod.txt ]; then pip install -r requirements.prod.txt; fi

# App code
COPY app ./app

# Alembic config + scripts (fixes: "No 'script_location' key found")
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

USER appuser
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
