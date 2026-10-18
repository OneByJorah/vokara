# Phase 3 GUARDIAN — Security Report

**Repository:** `OneByJorah/vokara`
**Date:** 2026-07-05
**Analyst:** J1-PIPELINE GUARDIAN

---

## Security Score Summary

| Sub-Category | Score | Status |
|-------------|-------|--------|
| Auth/AuthZ | 70 | DEGRADED |
| HTTPS/TLS | 30 | CRITICAL |
| CSP/Headers | 0 | CRITICAL |
| Docker Hardening | 40 | DEGRADED |
| Least Privilege | 30 | CRITICAL |
| Supply Chain | 80 | DEGRADED |
| Secrets | 75 | DEGRADED |
| AppArmor/SELinux | 50 | DEGRADED |
| Rate Limiting | 20 | CRITICAL |
| Firewall/Network | 50 | DEGRADED |
| Input Validation | 70 | DEGRADED |

**Overall Security Score: 47/100 — CRITICAL**

---

## Detailed Findings

### 1. Auth/AuthZ (Score: 70 — DEGRADED)

| Finding | Severity | Details |
|---------|----------|---------|
| No authentication on WebSocket server | CRITICAL | `server.py` binds to `0.0.0.0` with no auth. Anyone who can reach port 8765 can send audio to the STT/LLM/TTS pipeline. |
| ARI has basic auth but default password | DEGRADED | `server_asterisk.py` defaults to `ARI_PASS = "changeme"` — documented but easily missed |
| No API key validation | INFO | API_KEY is for the LLM provider, not for the bot server itself |

### 2. HTTPS/TLS (Score: 30 — CRITICAL)

| Finding | Severity | Details |
|---------|----------|---------|
| WebSocket server uses plain WS, not WSS | CRITICAL | `server.py` uses `websockets.serve` without TLS. Audio data flows in cleartext. |
| ARI events over plain WebSocket | CRITICAL | `server_asterisk.py` connects to ARI events via `ws://` not `wss://` |
| No TLS anywhere in the stack | CRITICAL | No TLS certificates, no HTTPS, no WSS |

### 3. CSP/Security Headers (Score: 0 — CRITICAL)

| Finding | Severity | Details |
|---------|----------|---------|
| No security headers | CRITICAL | The WebSocket server returns no HTTP headers (it's a WS server, not HTTP). No CSP, no HSTS, no X-Content-Type-Options. |
| No HTTP interface to add headers to | INFO | The bot is a WebSocket-only server; there's no web dashboard |

### 4. Docker Hardening (Score: 40 — DEGRADED)

| Finding | Severity | Details |
|---------|----------|---------|
| Container runs as root | CRITICAL | `bot/Dockerfile` has no `USER` directive — runs as root |
| Host networking mode | DEGRADED | Both services use `network_mode: host` — no network isolation |
| No health checks | DEGRADED | No healthcheck directives |
| No .dockerignore | DEGRADED | Build context includes unnecessary files |
| No read-only root filesystem | INFO | Not configured |
| No resource limits | INFO | No CPU/memory limits in compose |

### 5. Least Privilege (Score: 30 — CRITICAL)

| Finding | Severity | Details |
|---------|----------|---------|
| Container runs as root | CRITICAL | The bot process has full root access inside the container |
| No dedicated service user | CRITICAL | No non-root user created in Dockerfile |
| Host network access | DEGRADED | Host networking gives container full access to host network stack |

### 6. Supply Chain (Score: 80 — DEGRADED)

| Finding | Severity | Details |
|---------|----------|---------|
| Dependabot configured | ✅ PASS | Weekly updates for pip, docker, github-actions |
| Dependencies use `>=` specifiers | DEGRADED | Not pinned to exact versions — CI may get different versions |
| No SBOM generation | INFO | No software bill of materials |
| npm Dependabot is vestigial | DEGRADED | Configured but no JS/TS code |

### 7. Secrets (Score: 75 — DEGRADED)

| Finding | Severity | Details |
|---------|----------|---------|
| .env in .gitignore | ✅ PASS | Environment file excluded |
| API_KEY defaults to empty | ✅ PASS | No hardcoded API key |
| Email audit performed | ✅ PASS | Commit `6433101` sanitized emails |
| Default ARI password in code | DEGRADED | `ARI_PASS = "changeme"` — should be env-var-only |
| API_KEY passed in Authorization header | INFO | Standard Bearer token pattern — acceptable |

### 8. AppArmor/SELinux (Score: 50 — DEGRADED)

| Finding | Severity | Details |
|---------|----------|---------|
| No AppArmor profiles | INFO | Not configured in Docker Compose |
| No seccomp profiles | INFO | Not configured |
| No security_opt in compose | INFO | No Docker security options set |

### 9. Rate Limiting (Score: 20 — CRITICAL)

| Finding | Severity | Details |
|---------|----------|---------|
| No connection limits on WebSocket server | CRITICAL | `server.py` accepts unlimited connections |
| No per-IP rate limiting | CRITICAL | An attacker can exhaust GPU/CPU resources by opening many connections |
| No request throttling | CRITICAL | No limit on STT/LLM/TTS calls per connection |

### 10. Firewall/Network (Score: 50 — DEGRADED)

| Finding | Severity | Details |
|---------|----------|---------|
| WebSocket binds to 0.0.0.0 | DEGRADED | `server.py` listens on all interfaces — should bind to localhost or specific interface |
| Host networking exposes all ports | DEGRADED | `network_mode: host` means no port isolation |
| No firewall rules documented | INFO | No iptables/ufw recommendations in README |

### 11. Input Validation (Score: 70 — DEGRADED)

| Finding | Severity | Details |
|---------|----------|---------|
| PCM16 audio data is raw bytes | INFO | Audio data is binary, not text — limited injection surface |
| LLM prompt injection risk | DEGRADED | AI model output is rendered as speech, not executed — low risk |
| No input size limits | DEGRADED | No max message size on WebSocket (max_size=None) |

---

## CRITICAL Security Items

| # | Finding | File | Fix |
|---|---------|------|-----|
| S1 | No authentication on WebSocket server | `bot/server.py` | Add API key or token-based auth |
| S2 | No TLS/WSS on WebSocket | `bot/server.py` | Add TLS support |
| S3 | Container runs as root | `bot/Dockerfile` | Add non-root USER |
| S4 | No rate limiting on WebSocket | `bot/server.py` | Add connection limits |
| S5 | No observability/monitoring | All files | Replace print() with structured logging |

## DEGRADED Security Items

| # | Finding | File | Fix |
|---|---------|------|-----|
| S6 | Default ARI password in code | `bot/server_asterisk.py` | Add warning or make env-var-only |
| S7 | Host networking mode | `docker-compose.yml` | Consider bridge networking |
| S8 | No .dockerignore | — | Create `.dockerignore` |
| S9 | No health checks | `docker-compose.yml` | Add healthcheck directives |
| S10 | WebSocket binds to 0.0.0.0 | `bot/server.py` | Consider binding to 127.0.0.1 |

---

## Recommendations (Not to be auto-fixed — for human review)

1. **Add TLS to WebSocket** — Generate self-signed certs or use Let's Encrypt
2. **Add authentication** — Simple API key or token for WebSocket connections
3. **Add rate limiting** — Connection limits and per-IP throttling
4. **Create non-root user in Dockerfile** — Follow principle of least privilege
5. **Add structured logging** — Replace print() with proper logging
6. **Consider bridge networking** — Move away from host networking mode
7. **Add health checks** — Both services need healthcheck directives
