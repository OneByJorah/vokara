# Phase 0 CLASSIFIER — Project Classification

**Repository:** `OneByJorah/vokara`
**Date:** 2026-07-05
**Analyst:** J1-PIPELINE CLASSIFIER

---

## Primary Classification

**PROJECT_CLASS: Python, Docker, AI, LLM, Agent, Web**

### Class Breakdown

| Class | Rationale |
|-------|-----------|
| **Python** | Core language — all bot code is Python 3.11 (vokara_brain.py, server.py, server_asterisk.py, vad.py) |
| **Docker** | Docker Compose deployment with two services (freeswitch, bot), Dockerfile for bot |
| **AI** | Full STT → LLM → TTS AI pipeline (faster-whisper, Ollama/llama.cpp/API, Piper) |
| **LLM** | Multiple LLM backends: Ollama, llama.cpp, Anthropic, OpenAI, OpenRouter |
| **Agent** | Voice AI assistant agent with configurable persona |
| **Web** | WebSocket server for FreeSWITCH audio streaming |

### Secondary Attributes

- **Infrastructure** — Docker Compose deployment, FreeSWITCH PBX integration
- **Linux** — Deployed on Linux, Docker containers based on python:3.11-slim

### Excluded Classes

| Class | Reason |
|-------|--------|
| Docker Swarm | No swarm mode config |
| Kubernetes / K3s | No k8s manifests |
| Security | Not a security tool |
| Monitoring | No monitoring/observability |
| Dashboard | No web dashboard |
| CLI | No CLI tool |
| Go / Rust / PowerShell / Shell | No code in these languages |
| macOS / Swift | Not applicable |
| MCP | Not an MCP server |
| Cloudflare Workers | Not a CF Worker |
| TypeScript | No TS source files |

---

## Pipeline Gate Implications

- **Docker hardening checks** apply (Dockerfile, Compose)
- **AI/LLM checks** apply (prompt quality, model configuration)
- **Security checks** apply (WebSocket auth, TLS, rate limiting)
- **Documentation checks** apply (README, API docs)
- **Testing checks** apply (no test suite found — CRITICAL gap)
