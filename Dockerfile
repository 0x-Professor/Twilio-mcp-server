# ── Build stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build deps
RUN pip install --no-cache-dir hatchling

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install the package and all dependencies
RUN pip install --no-cache-dir .

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy source and boot script
COPY src/ src/
COPY boot.py .

# Data directory for SQLite inbox
RUN mkdir -p /data && chown appuser:appuser /data

USER appuser

# Webhook HTTP port (configure in Twilio Console as your webhook URL)
EXPOSE 8080

# Environment defaults (override with --env-file or -e flags)
ENV TWILIO_DB_PATH=/data/inbox.db \
    WEBHOOK_PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# MCP runs on stdio; webhook runs on HTTP in background
CMD ["python", "boot.py"]
