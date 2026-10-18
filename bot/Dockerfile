# Vokara bot image — build from the repository root:
#   docker build -f bot/Dockerfile .
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 git build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 vokara

WORKDIR /app
COPY bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ /app/bot/
COPY dashboard/ /app/dashboard/

USER vokara

EXPOSE 8765 8766

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${BOT_HTTP_PORT:-8766}/healthz" || exit 1

CMD ["python", "bot/server.py"]
