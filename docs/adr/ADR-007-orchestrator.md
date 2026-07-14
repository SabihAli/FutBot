# ADR-007: RAG Orchestrator, WebSocket, Observability (Phase 6)

**Status:** Accepted  
**Date:** 2026-07-14

## Context

Phase 6 wires the LangGraph RAG pipeline into microservices, enables live pipeline UI over WebSocket, and migrates SQLite trace logging to the Observability service.

## Decisions

| Topic | Decision |
|-------|----------|
| Trigger | **Chat inline** — `POST /chats/{id}/messages` calls orchestrator internally |
| Streaming | **WebSocket only** — `/ws/pipeline` events (stage timeline + completion) |
| LangGraph | **`services/rag_orchestrator/graph.py`** — monolith `src/graph.py` deleted |
| Traces | **SQLite in Observability** — `GET /traces/{run_id}` on `:8090` |
| Gateway | `/traces/*` proxied; `/ws/pipeline` relayed to orchestrator; `/pipeline/*` stays **501** |

## Flow

```
POST /chats/{id}/messages (user)
  → Chat persists user message
  → HTTP POST rag-orchestrator /pipeline/run
  → LangGraph + WS stage events (session_id = chat_id)
  → Chat persists assistant message + citations_json
GET /traces/{run_id} — pipeline span tree from SQLite
```

## Consequences

- Monolith `POST /api/chat` returns **501**
- Frontend should use gateway `/chats/*` + `/ws/pipeline?session_id={chatId}`
- Token-level SSE streaming deferred; WS carries stage events + `pipeline_complete`
