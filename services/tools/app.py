from fastapi import FastAPI

from futbot_common import CorrelationIdMiddleware
from futbot_common.models import HealthResponse
from services.tools.builtins.web_search import register_web_search
from services.tools.mcp.register import register_football_mcp_tools, register_pdf_tool
from services.tools.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="FutBot Tools Service")
    app.add_middleware(CorrelationIdMiddleware)

    @app.on_event("startup")
    def _startup() -> None:
        register_web_search()
        register_pdf_tool()
        register_football_mcp_tools()

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="tools")

    app.include_router(router)
    return app


app = create_app()
