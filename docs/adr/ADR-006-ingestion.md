# ADR-006: Ingestion Service (Phase 5)

**Status:** Accepted  
**Date:** 2026-07-14

## Context

Phase 5 extracts document ingestion from the legacy monolith into an internal Ingestion microservice. Upload metadata stays in the Project service; chunk vectors live in Retrieval (Qdrant + BM25).

## Decisions

### APIs (internal `:8086`)

| Endpoint | Purpose |
|----------|---------|
| `POST /ingest/jobs` | Enqueue file ingest (202) |
| `GET /ingest/jobs/{id}` | Poll job status |

### Async execution

- **FastAPI `BackgroundTasks`** + in-memory `JobStore` (no Celery in Phase 5).
- Jobs: `pending` → `processing` → `ingested` | `rejected` | `failed`.

### Integration flow

```
POST /projects/{id}/files  →  MinIO + DB status=pending
       ↓ (project auto HTTP)
POST /ingest/jobs  →  BackgroundTasks run_job
       ↓
fetch MinIO → extract → relevance → chunk → POST retrieval /index/chunks
       ↓
PATCH /projects/{id}/files/{file_id}/status  →  ingested | failed
```

### Gateway

- `/ingest/*` stays **501** on public gateway (internal-only).
- Project service calls `INGESTION_SERVICE_URL` after upload.

### Project file status

- `project_files.error_message` column (migration `004`) for P5-02 UI.
- Internal `PATCH /projects/{id}/files/{file_id}/status` (no JWT).

### Monolith

- Deleted `src/ingestion/`.
- `POST /api/ingest` returns **501**.

### Memory vs ingestion

- Project memory remains in Postgres; not indexed by ingestion in Phase 5.

## Consequences

- UI polls `GET /projects/{id}/files` until `status` is `ingested` or `failed`.
- Groq required for relevance guard and image/PDF VLM paths (`LLM_PROVIDER=groq`).
