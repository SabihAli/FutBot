# FutBot microservices

## Phase 4 (active)

| Service | Port | Run |
|---------|------|-----|
| gateway | 8000 | `uvicorn services.gateway.main:app --port 8000` |
| auth | 8081 | `uvicorn services.auth.main:app --port 8081` |
| chat | 8082 | `uvicorn services.chat.main:app --port 8082` |
| project | 8083 | `uvicorn services.project.main:app --port 8083` |
| llm-gateway | 8087 | `uvicorn services.llm_gateway.main:app --port 8087` |
| retrieval | 8085 | `uvicorn services.retrieval.main:app --port 8085` |

```bash
pip install -e packages/futbot-common
pip install -r requirements.txt

docker compose -f docker-compose.services.yml up -d --build
alembic upgrade head
```

Gateway routes: `/auth/*`, `/chats/*`, `/projects/*` (proxy). `/llm/*` and `/retrieve/*` are **internal only** (`501` on public gateway).

Chat auto-compress: inline on `POST /chats/{id}/messages` when context ≥ 85% — calls `LLM_GATEWAY_URL/llm/compress` (no JWT, works for anon).

Retrieval: `POST /retrieve`, `POST /index/chunks`, `DELETE /index/{project_id}` on `:8085` (Qdrant dense + BM25 + RRF).
