from contextlib import asynccontextmanager

from fastapi import FastAPI

from futbot_common import CorrelationIdMiddleware
from futbot_common.models import HealthResponse
from services.retrieval.migrate import run_startup_migration
from services.retrieval.routes import router


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        run_startup_migration()
        yield

    app = FastAPI(title="FutBot Retrieval Service", lifespan=lifespan)
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="retrieval")

    app.include_router(router)
    return app


app = create_app()
