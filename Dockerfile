# =============================================================================
# Vokara — Self-hosted voice assistant call stack
# JorahOne
#
# STT (faster-whisper) -> LLM (Ollama/llama.cpp/API) -> TTS (Piper)
# =============================================================================
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 git build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 vokara

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY bot/ /app/bot/
COPY dashboard/ /app/dashboard/
COPY .env.example /app/.env.example

USER vokara

EXPOSE 8765 8766

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${BOT_HTTP_PORT:-8766}/healthz" || exit 1

CMD ["python3", "bot/server.py"]
