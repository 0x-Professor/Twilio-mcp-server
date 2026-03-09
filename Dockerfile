FROM python:3.12-slim AS builder

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

FROM python:3.12-slim AS runtime

RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

RUN mkdir -p /data \
    && chown -R appuser:appuser /data /app

USER appuser

EXPOSE 8080

ENV TWILIO_DB_PATH=/data/inbox.db \
    WEBHOOK_PORT=8080 \
    TWILIO_VALIDATE_WEBHOOK_SIGNATURES=true \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys, urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3); sys.exit(0)"

CMD ["python", "-m", "twilio_sms_mcp.boot"]
