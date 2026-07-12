# FutBot microservices (stubs). Each exposes `GET /health`.

| Service | Uvicorn target | Default port |
|---------|----------------|--------------|
| gateway | `services.gateway.main:app` | 8080 |
| auth | `services.auth.main:app` | 8081 |
| chat | `services.chat.main:app` | 8082 |
| project | `services.project.main:app` | 8083 |
| rag-orchestrator | `services.rag_orchestrator.main:app` | 8084 |
| retrieval | `services.retrieval.main:app` | 8085 |
| ingestion | `services.ingestion.main:app` | 8086 |
| llm-gateway | `services.llm_gateway.main:app` | 8087 |
| tools | `services.tools.main:app` | 8088 |
| realtime | `services.realtime.main:app` | 8089 |
| observability | `services.observability.main:app` | 8090 |

```bash
pip install -e packages/futbot-common
uvicorn services.auth.main:app --port 8081 --reload
```

Infra (Postgres, Redis, MinIO, Qdrant):

```bash
docker compose -f docker-compose.infra.yml up -d
```
