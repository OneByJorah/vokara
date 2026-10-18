# Phase 2 ARCHITECT — Architecture Report

**Repository:** `OneByJorah/vokara`
**Date:** 2026-07-05
**Analyst:** J1-PIPELINE ARCHITECT

---

## Architecture Overview

vokara implements a **streaming audio pipeline** for real-time AI-powered voice conversations over telephone (SIP/RTP). The architecture follows a clean **transport-agnostic core** pattern with thin transport adapters.

### High-Level Architecture

```
Caller (SIP phone)
    │
    ▼
┌─────────────────────────────────────────────────────┐
│                  PBX Layer                           │
│  FreeSWITCH (bundled) / Asterisk / 3CX              │
│  └─ SIP termination, call routing, media forking    │
└─────────────────────┬───────────────────────────────┘
                      │ WebSocket (FreeSWITCH) or RTP (Asterisk)
                      ▼
┌─────────────────────────────────────────────────────┐
│              Transport Layer                         │
│  server.py (FreeSWITCH WS) / server_asterisk.py (ARI)│
│  └─ Thin adapters — audio in/out only               │
└─────────────────────┬───────────────────────────────┘
                      │ PCM16 bytes
                      ▼
┌─────────────────────────────────────────────────────┐
│              Brain Core (vokara_brain.py)             │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐ │
│  │   VAD   │→ │   STT    │→ │   LLM    │→ │ TTS  │ │
│  │(Silero/ │  │(faster-  │  │(Ollama/  │  │(Piper│ │
│  │Amplitude│  │ whisper) │  │llamacpp/ │  │ONNX) │ │
│  └─────────┘  └──────────┘  │ API)     │  └──────┘ │
│                             └──────────┘            │
└─────────────────────────────────────────────────────┘
```

---

## Architectural Strengths

### 1. Transport-Agnostic Brain (Score: 95/100)
`vokara_brain.py` is a pure module that accepts PCM16 bytes and returns text/audio. It has zero knowledge of telephony transports. `server.py` (FreeSWITCH WebSocket) and `server_asterisk.py` (Asterisk ARI) are thin adapters. Adding a new transport (WebRTC, SIP directly) requires no changes to the STT/LLM/TTS logic.

### 2. Factory Pattern for VAD (Score: 90/100)
`vad.py` uses a factory function `create_vad()` that tries Silero VAD (deep learning) and falls back to amplitude-threshold VAD. Both implement the same interface (`is_speech()`, `process_stream()`, `reset()`), making them swappable without changing callers.

### 3. Multiple LLM Backends (Score: 85/100)
The brain supports Ollama, llama.cpp, and hosted API (Anthropic, OpenAI, OpenRouter) via a simple `ask_llm()` dispatcher. Each backend is a separate function with the same signature.

### 4. Clean Module Boundaries (Score: 90/100)
- `vokara_brain.py` — STT/LLM/TTS logic
- `vad.py` — Voice Activity Detection
- `server.py` — FreeSWITCH transport
- `server_asterisk.py` — Asterisk transport
- `persona.txt` — System prompt (externalized)

---

## Architectural Concerns

### 1. No Persistent Memory (Score: 60/100 — DEGRADED)
Each call starts with a fresh conversation history. There is no mechanism for cross-call memory, no vector store integration, and no call history persistence. The roadmap acknowledges this but it's a significant limitation for a voice assistant.

**Recommendation:** Add an optional memory backend (Qdrant, Honcho, or simple SQLite) that stores call transcripts and can be queried on subsequent calls.

### 2. No Barge-In Support (Score: 50/100 — DEGRADED)
The caller cannot interrupt the AI mid-response. The pipeline processes one utterance at a time and waits for the full TTS response before listening again. This is a documented limitation but significantly impacts user experience.

**Recommendation:** Implement barge-in by monitoring the audio stream during TTS playback and interrupting on speech detection.

### 3. Host Networking Mode (Score: 40/100 — DEGRADED)
Both services use `network_mode: host` in Docker Compose. While this is the simplest approach for SIP/RTP NAT behavior, it sacrifices Docker network isolation, portability, and makes multi-host deployments impossible.

**Recommendation:** Investigate macvlan or dedicated Docker networks with proper port mapping for SIP/RTP.

### 4. No Health Checks (Score: 30/100 — CRITICAL)
Neither the `freeswitch` nor `bot` service defines a `healthcheck` directive. Docker Compose cannot detect service failures, and orchestration tools have no way to verify service health.

**Recommendation:** Add health checks to both services.

### 5. No Graceful Degradation (Score: 40/100 — DEGRADED)
If STT, LLM, or TTS fails mid-call, the system stops producing audio rather than recovering gracefully. There is no retry logic, fallback model, or error message to the caller.

**Recommendation:** Add try/except blocks around each pipeline stage with fallback behavior (e.g., "I'm sorry, I'm having trouble processing that" for LLM failures).

### 6. Simplified RTP in Asterisk Transport (Score: 50/100 — DEGRADED)
The Asterisk transport (`server_asterisk.py`) strips the RTP header (12 bytes) to get raw PCM but does not track RTP sequence numbers or timestamps. The code explicitly acknowledges this as simplified.

**Recommendation:** Implement proper RTP depacketization with sequence number tracking.

### 7. No Rate Limiting (Score: 30/100 — CRITICAL)
The WebSocket server (`server.py`) has no rate limiting. A misbehaving client or attacker could open unlimited connections and consume all system resources (GPU for STT, CPU for TTS, LLM inference).

**Recommendation:** Add connection limits and per-IP rate limiting to the WebSocket server.

### 8. No Monitoring or Observability (Score: 20/100 — CRITICAL)
All logging is via `print()` statements. There are no metrics, no structured logging, no tracing, and no health endpoint. Operators have no visibility into system behavior.

**Recommendation:** Replace `print()` with structured logging (structlog or standard logging), add a health endpoint, and expose Prometheus metrics.

---

## Architecture Score Breakdown

| Sub-Category | Score | Status |
|-------------|-------|--------|
| Module Separation | 90 | OPERATIONAL |
| Transport Abstraction | 95 | OPERATIONAL |
| VAD Factory Pattern | 90 | OPERATIONAL |
| LLM Backend Abstraction | 85 | OPERATIONAL |
| Persistent Memory | 60 | DEGRADED |
| Barge-In Support | 50 | DEGRADED |
| Docker Networking | 40 | DEGRADED |
| Health Checks | 30 | CRITICAL |
| Graceful Degradation | 40 | DEGRADED |
| RTP Handling (Asterisk) | 50 | DEGRADED |
| Rate Limiting | 30 | CRITICAL |
| Observability | 20 | CRITICAL |

**Overall Architecture Score: 57/100 — DEGRADED**

---

## Recommendations (Not to be auto-fixed — for human review)

1. **Add persistent memory** — Qdrant or Honcho integration for cross-call context
2. **Implement barge-in** — Monitor audio during TTS playback
3. **Move to bridge networking** — Investigate macvlan for SIP/RTP
4. **Add graceful degradation** — Error recovery at each pipeline stage
5. **Implement proper RTP handling** — Sequence number tracking in Asterisk transport
6. **Add observability** — Structured logging, metrics, health endpoint
7. **Consider WebRTC transport** — Browser-based calling (on roadmap)
