# ADR-004: LLM Gateway (Phase 3)

**Status:** Accepted  
**Date:** 2026-07-13

## Context

Phase 3 extracts `src/llm_components.py` into an internal LLM Gateway microservice and wires Chat Service auto-compress when context usage exceeds the threshold.

## Decisions

### Service boundary

- LLM Gateway owns provider routing (local/Groq), retries, rate limits, and HTTP APIs.
- Pipeline role classes (`QueryRewriter`, `Orchestrator`, etc.) remain importable Python modules for the dev monolith until Phase 6 orchestrator HTTP integration.

### Internal-only in Phase 3

- `/llm/*` is **not** proxied on the public gateway (`501` to browsers).
- Chat Service calls `LLM_GATEWAY_URL` directly on the internal network — **no JWT**.
- Anon users can trigger compress via `POST /chats/{id}/messages` without login; compress runs server-side.

### Auto-compress

- **Inline synchronous** on message POST when `should_compress` and aged messages exist.
- `POST /llm/compress` returns updated JSON snapshot.
- Clears `compression_pending` on success; leaves `true` if LLM call fails.

### APIs

| Endpoint | Purpose |
|----------|---------|
| `POST /llm/compress` | Snapshot compression |
| `POST /llm/complete` | Non-streaming completion |
| `POST /llm/complete/stream` | SSE tokens (Phase 6 consumer) |

### Monolith

- Deleted `src/llm_components.py`, `src/prompt_loader.py`.
- `graph.py` and ingestion modules import `services.llm_gateway.*` in-process.

## Consequences

- Chat depends on LLM Gateway availability for compress at high context usage.
- Groq API key required when `LLM_PROVIDER=groq`.
- Phase 6 activates gateway `/llm` proxy for orchestrator if needed.
