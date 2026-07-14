# ADR-005: Retrieval Service (Phase 4)

**Status:** Accepted  
**Date:** 2026-07-14

## Context

Phase 4 extracts hybrid search from `src/retriever.py` into an internal Retrieval microservice. Dense vectors move from ChromaDB to Qdrant; BM25 stays in-process with pickle persistence.

## Decisions

### Storage

- **Qdrant** single collection `futbot_chunks` with `project_id` metadata filter (`__global__` for standalone KB).
- **BM25** pickle at `DATA_DIR/bm25_index.pkl` with parallel `project_id` metadata per chunk.
- **Embeddings:** client-side `all-MiniLM-L6-v2` via Chroma's `DefaultEmbeddingFunction` (reuse existing dep).

### APIs (internal `:8085`)

| Endpoint | Purpose |
|----------|---------|
| `POST /retrieve` | Hybrid search; returns citation fields |
| `POST /index/chunks` | Upsert chunks for a project/file |
| `DELETE /index/{project_id}` | Wipe project-scoped index |

### Gateway

- `/retrieve/*` stays **501** on public gateway (internal-only, no JWT).
- Orchestrator (Phase 6) and Ingestion (Phase 5) call `RETRIEVAL_SERVICE_URL` directly.

### Scoping

- `project_id: null` → global football KB only.
- `project_id` set → filter dense + sparse to that project.

### Memory vs retrieval

- **Project memory** stays in Project service (Postgres); not indexed by Retrieval in Phase 4.
- **Retrieved chunks** are document KB hits only.

### Migration

- On startup, if Qdrant is empty and legacy `data/chroma_db` exists, import vectors + BM25 pickle.

### Monolith

- Deleted `src/retriever.py`.
- `graph.py` `retrieve_node` calls retrieval HTTP (no `api.py` globals).
- Legacy monolith ingest returns `501` until Phase 5.

## Consequences

- Legacy monolith ingest/index paths intentionally broken.
- Citation metadata available for Phase 6 orchestrator attachment to assistant messages.
