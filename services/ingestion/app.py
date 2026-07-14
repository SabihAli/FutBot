from fastapi import FastAPI

from futbot_common import CorrelationIdMiddleware
from futbot_common.models import HealthResponse
from services.ingestion.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="FutBot Ingestion Service")
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="ingestion")

    app.include_router(router)
    return app


app = create_app()
