from contextlib import asynccontextmanager

from fastapi import FastAPI

from futbot_common import CorrelationIdMiddleware
from futbot_common.models import HealthResponse
from services.observability.trace_store import init_db
from services.rag_orchestrator.routes import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="FutBot RAG Orchestrator", lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="rag-orchestrator")

    app.include_router(router)
    return app


app = create_app()
