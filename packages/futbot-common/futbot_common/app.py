from fastapi import FastAPI

from futbot_common.middleware import CorrelationIdMiddleware
from futbot_common.models import HealthResponse


def create_stub_app(service_name: str) -> FastAPI:
    app = FastAPI(title=f"FutBot {service_name}")
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service=service_name)

    return app
