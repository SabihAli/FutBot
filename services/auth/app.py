from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from starlette.middleware.sessions import SessionMiddleware

from futbot_common import CorrelationIdMiddleware
from futbot_common.errors import AuthError
from futbot_common.models import HealthResponse
from futbot_common.responses import ErrorBody, ErrorResponse
from services.auth.config import settings
from services.auth.db import init_db
from services.auth.redis_store import close_redis
from services.auth.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(settings.database_url)
    yield
    await close_redis()


@asynccontextmanager
async def _noop_lifespan(app: FastAPI):
    yield


def create_app(*, with_lifespan: bool = True) -> FastAPI:
    ls = lifespan if with_lifespan else _noop_lifespan
    app = FastAPI(title="FutBot Auth Service", lifespan=ls)
    app.add_middleware(SessionMiddleware, secret_key=settings.jwt_secret)
    app.add_middleware(CorrelationIdMiddleware)

    @app.exception_handler(AuthError)
    async def auth_error_handler(_request: Request, exc: AuthError):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=ErrorBody(code=exc.code, message=exc.message)
            ).model_dump(),
        )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="auth")

    app.include_router(router)
    return app


app = create_app()
