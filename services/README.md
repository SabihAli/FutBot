# FutBot microservices

## Phase 6 (active)

| Service | Port | Run |
|---------|------|-----|
| gateway | 8000 | `uvicorn services.gateway.main:app --port 8000` |
| auth | 8081 | `uvicorn services.auth.main:app --port 8081` |
| chat | 8082 | `uvicorn services.chat.main:app --port 8082` |
| project | 8083 | `uvicorn services.project.main:app --port 8083` |
| rag-orchestrator | 8084 | `uvicorn services.rag_orchestrator.main:app --port 8084` |
| retrieval | 8085 | `uvicorn services.retrieval.main:app --port 8085` |
| ingestion | 8086 | `uvicorn services.ingestion.main:app --port 8086` |
| observability | 8090 | `uvicorn services.observability.main:app --port 8090` |
| llm-gateway | 8087 | `uvicorn services.llm_gateway.main:app --port 8087` |

```bash
pip install -e packages/futbot-common
pip install -r requirements.txt

docker compose -f docker-compose.services.yml up -d --build
alembic upgrade head
```

Gateway routes: `/auth/*`, `/chats/*`, `/projects/*`, `/traces/*` (proxy). `/ws/pipeline` relays to orchestrator. `/llm/*`, `/retrieve/*`, `/ingest/*`, and `/pipeline/*` are **internal only** (`501` on public gateway).

Chat RAG: user `POST /chats/{id}/messages` → internal `POST /pipeline/run` on orchestrator; assistant reply + `citations_json` persisted.

Orchestrator: LangGraph pipeline, `POST /pipeline/run`, `WS /ws/pipeline` on `:8084`.

Observability: `GET /traces/{run_id}` on `:8090` (SQLite `trace_logs.db`).
