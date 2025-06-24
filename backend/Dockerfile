# --- Build Stage ---
FROM python:3.11-slim AS builder

WORKDIR /app

# System-Abhängigkeiten FÜR BUILD (inkl. git für pip install von GitHub!)
RUN apt-get update && \
    apt-get install -y gcc libpq-dev curl git && \
    rm -rf /var/lib/apt/lists/*

# Python-Abhängigkeiten vorbereiten
COPY requirements.txt .
RUN python -m venv /venv && \
    /venv/bin/pip install --no-cache-dir --upgrade pip && \
    /venv/bin/pip install --no-cache-dir -r requirements.txt

# --- Runtime Stage ---
FROM python:3.11-slim

WORKDIR /app

# System-Abhängigkeiten zur Laufzeit (minimal, kein git mehr nötig)
RUN apt-get update && \
    apt-get install -y libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Virtuelle Umgebung übernehmen
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# App-Code übernehmen
COPY . .

# Starte FastAPI-App korrekt von main.py im Root, EIN Worker für Streaming!
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--workers", "1"]
