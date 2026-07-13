import os
from typing import Callable

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from futbot_common import CorrelationIdMiddleware
from futbot_common.context import CORRELATION_ID_HEADER
from futbot_common.models import HealthResponse
from futbot_common.responses import ErrorBody, ErrorResponse
from services.gateway.config import settings
from services.gateway.middleware import (
    AnonMessageLimitMiddleware,
    LoginRequiredMiddleware,
    optional_user_id_from_jwt,
)
from services.gateway.routing import (
    ACTIVE_PREFIXES,
    FRONTEND_DIR,
    NOT_IMPLEMENTED_PREFIXES,
    SERVICE_ROUTES,
)

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=60.0)
    return _client


def _match_prefix(path: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in prefixes:
        if path == prefix or path.startswith(prefix + "/"):
            return prefix
    return None


async def _proxy(request: Request, upstream_base: str) -> Response:
    client = _get_client()
    url = upstream_base.rstrip("/") + request.url.path
    if request.url.query:
        url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)
    correlation_id = request.headers.get(CORRELATION_ID_HEADER)
    if correlation_id:
        headers[CORRELATION_ID_HEADER] = correlation_id
    user_id = optional_user_id_from_jwt(request)
    if user_id:
        headers["X-User-ID"] = user_id

    body = await request.body()
    upstream = await client.request(
        request.method,
        url,
        headers=headers,
        content=body,
    )
    response_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
    }
    if correlation_id:
        response_headers[CORRELATION_ID_HEADER] = correlation_id

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        background=BackgroundTask(upstream.aclose),
    )


def create_app() -> FastAPI:
    app = FastAPI(title="FutBot Gateway")
    app.add_middleware(AnonMessageLimitMiddleware)
    app.add_middleware(LoginRequiredMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    static_dir = FRONTEND_DIR / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="gateway")

    @app.api_route(
        "/{full_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )
    async def route_all(request: Request, full_path: str = "") -> Response:
        path = "/" + full_path

        not_impl = _match_prefix(path, NOT_IMPLEMENTED_PREFIXES)
        if not_impl:
            return JSONResponse(
                status_code=501,
                content=ErrorResponse(
                    error=ErrorBody(
                        code="NOT_IMPLEMENTED",
                        message=f"Route {not_impl} is not available yet.",
                    )
                ).model_dump(),
            )

        active = _match_prefix(path, ACTIVE_PREFIXES)
        if active:
            return await _proxy(request, SERVICE_ROUTES[active])

        if path == "/" or path == "/index.html":
            index = FRONTEND_DIR / "index.html"
            if index.is_file():
                return Response(content=index.read_bytes(), media_type="text/html")
            return JSONResponse(status_code=404, content={"error": "frontend not found"})

        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                error=ErrorBody(code="NOT_FOUND", message="Route not found")
            ).model_dump(),
        )

    return app


app = create_app()
