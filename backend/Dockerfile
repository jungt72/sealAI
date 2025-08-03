###############################################################################
#                         ─── Build Stage (“builder”) ──                      #
###############################################################################
FROM python:3.11-slim AS builder

WORKDIR /app

# System-Abhängigkeiten
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      gcc \
      libpq-dev \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# ── requirements.txt liegt direkt im Build-Kontext (./backend) ──
COPY requirements.txt .
RUN python -m venv /venv \
 && /venv/bin/pip install --no-cache-dir --upgrade pip \
 && /venv/bin/pip install --no-cache-dir -r requirements.txt

###############################################################################
#                        ─── Runtime Stage (final) ───                         #
###############################################################################
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      libpq5 \
      curl \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# vorinstallierte Pakete aus dem Builder übernehmen
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

# ── Code kopieren (alle Pfade OHNE "backend/"-Vorsatz) ──
COPY app ./app
COPY alembic.ini .
COPY alembic ./alembic
# falls vorhanden, sonst diesen COPY-Befehl entfernen
COPY docs ./docs

# ── Start-Befehl (eine einzelne JSON-Zeile) ──
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--workers","2","--proxy-headers"]
