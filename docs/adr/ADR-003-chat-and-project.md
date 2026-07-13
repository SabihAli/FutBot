# ADR-003: Chat and Project Services (Phase 2)

**Status:** Accepted  
**Date:** 2026-07-13

## Context

Phase 2 extracts chat persistence and project management from the monolith. Gateway activates `/chats/*` and `/projects/*`. RAG replies remain out of scope until Phase 6.

## Decisions

### Context usage budget

Measures the **full next-turn LLM prompt**, not snapshot alone:

| Component | Included | Phase |
|-----------|----------|-------|
| Snapshot | Yes | 2 |
| Hot messages | Yes | 2 |
| Current query | Yes (when estimating a pending send) | 2 |
| Project memory | Yes (fetched from Project service) | 2 |
| Retrieved chunks | Yes (0 until orchestrator wires retrieval) | 2+ |
| System prompts | Deferred (fixed overhead, add in Phase 6) | 6 |

`CONTEXT_BUDGET_TOKENS` (default 8192) and `AUTO_COMPRESS_THRESHOLD_PCT` (default 85) are env-configurable. At threshold, chat sets `compression_pending`; LLM compress runs in Phase 3.

Response includes `breakdown` per component for UI (Phase 8).

### Chat service

- Postgres schema `chat`: `chats`, `messages`, `chat_snapshots`
- `user_id` nullable (anonymous chats); `project_id` nullable
- Hard delete
- Export: markdown + JSON
- `X-User-ID` from gateway JWT decode

### Project service

- Postgres schema `project`: `projects`, `project_files`, `project_memory`
- Files → MinIO (`status=pending` until Phase 5 ingestion)
- All routes JWT-only (`X-User-ID`)

### Gateway

- `/chats` and `/projects` proxied
- `LoginRequiredMiddleware` for list/delete/export/projects
- Anon message limit keyed by `chat_id` on `POST /chats/{id}/messages`

### Monolith

- Removed `GET /api/session/{id}` (replaced by Chat service)
- `POST /api/chat` kept for local dev only (not on gateway)

## Consequences

- Chat service calls Project service for memory when computing context usage
- Alembic chain: `001` auth → `002` chat → `003` project
- UI requirements tracked in `docs/UI_REQUIREMENTS.md`
