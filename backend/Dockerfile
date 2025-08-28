FROM python:3.11-slim

# Systemdeps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential wget curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# App
COPY app /app/app

# Health / Runtime
ENV PYTHONUNBUFFERED=1 \
    UVICORN_WORKERS=1 \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000

EXPOSE 8000

# Start FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
