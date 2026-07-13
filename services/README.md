# FutBot microservices

## Phase 1 (active)

| Service | Port | Run |
|---------|------|-----|
| gateway | 8000 | `uvicorn services.gateway.main:app --port 8000` |
| auth | 8081 | `uvicorn services.auth.main:app --port 8081` |

```bash
pip install -e packages/futbot-common
pip install -r requirements.txt

docker compose -f docker-compose.services.yml up -d --build
alembic upgrade head
```

Gateway routes: `/auth/*` (proxy). Other prefixes return `501` until later phases.
