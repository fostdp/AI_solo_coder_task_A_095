# syntax=docker/dockerfile:1.6

############################
# Stage 1: Python Builder
############################
FROM python:3.12-slim-bookworm AS python-builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

############################
# Stage 2: Frontend Gzip (static compress assets)
############################
FROM alpine:3.20 AS frontend-compressor

WORKDIR /app/frontend
COPY frontend/ .

RUN apk add --no-cache gzip \
    && find . -type f \( -name "*.js" -o -name "*.css" -o -name "*.html" -o -name "*.svg" -o -name "*.json" \) \
       -exec sh -c 'gzip -k -9 "$1" && touch -r "$1" "$1.gz"' _ {} \;

############################
# Stage 3: Runtime
############################
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app \
    TZ=UTC

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=python-builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY backend/ backend/
COPY services/ services/
COPY config/ config/
COPY scripts/ scripts/
COPY --from=frontend-compressor /app/frontend frontend/

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", "backend.main:app", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--timeout", "120", \
     "--keepalive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--log-level", "info"]
