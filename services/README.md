# FutBot microservices

## Phase 2 (active)

| Service | Port | Run |
|---------|------|-----|
| gateway | 8000 | `uvicorn services.gateway.main:app --port 8000` |
| auth | 8081 | `uvicorn services.auth.main:app --port 8081` |
| chat | 8082 | `uvicorn services.chat.main:app --port 8082` |
| project | 8083 | `uvicorn services.project.main:app --port 8083` |

```bash
pip install -e packages/futbot-common
pip install -r requirements.txt

docker compose -f docker-compose.services.yml up -d --build
alembic upgrade head
```

Gateway routes: `/auth/*`, `/chats/*`, `/projects/*` (proxy). Other prefixes return `501`.
