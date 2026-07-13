import base64
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from futbot_common.responses import DataResponse
from services.llm_gateway.components import SnapshotCompressor
from services.llm_gateway.config import settings
from services.llm_gateway.provider import (
    GROQ_API_URL,
    GROQ_MODEL_MAP,
    MODEL_GENERATOR,
    invoke_llm,
    invoke_llm_stream,
)
from services.llm_gateway.schemas import (
    CompleteRequest,
    CompleteResponse,
    CompressRequest,
    CompressResponse,
)

router = APIRouter(prefix="/llm", tags=["llm"])

_rate_counts: dict[str, list[float]] = {}


def _check_rate_limit(request: Request) -> JSONResponse | None:
    key = request.headers.get("X-Correlation-ID", "default")
    import time

    now = time.time()
    window = _rate_counts.setdefault(key, [])
    window[:] = [t for t in window if now - t < 60]
    if len(window) >= settings.llm_rate_limit_rpm:
        return JSONResponse(
            status_code=429,
            content={"error": {"code": "RATE_LIMITED", "message": "LLM rate limit exceeded."}},
            headers={"Retry-After": "60"},
        )
    window.append(now)
    return None


@router.post("/compress", response_model=DataResponse[CompressResponse])
def compress(body: CompressRequest, request: Request):
    limited = _check_rate_limit(request)
    if limited:
        return limited
    compressor = SnapshotCompressor()
    snapshot = compressor.compress_incremental(
        body.existing_snapshot,
        [m.model_dump() for m in body.aged_messages],
    )
    return DataResponse(data=CompressResponse(snapshot=snapshot))


@router.post("/complete", response_model=DataResponse[CompleteResponse])
def complete(body: CompleteRequest, request: Request):
    limited = _check_rate_limit(request)
    if limited:
        return limited
    import time

    t0 = time.monotonic()
    image = base64.b64decode(body.image_b64) if body.image_b64 else None
    model_name = body.model or MODEL_GENERATOR
    content = invoke_llm(
        body.user_content,
        model_name=model_name,
        step=body.step,
        system_prompt=body.system_prompt or None,
        image=image,
    )
    latency_ms = int((time.monotonic() - t0) * 1000)
    provider = settings.llm_provider
    resolved_model = (
        GROQ_MODEL_MAP.get(body.step, settings.groq_model_main)
        if provider == "groq"
        else model_name
    )
    return DataResponse(
        data=CompleteResponse(
            content=content,
            model=resolved_model,
            latency_ms=latency_ms,
            provider=provider,
        )
    )


@router.post("/complete/stream")
def complete_stream(body: CompleteRequest, request: Request):
    limited = _check_rate_limit(request)
    if limited:
        return limited

    def event_stream():
        tokens = invoke_llm_stream(
            body.user_content,
            model_name=body.model or MODEL_GENERATOR,
            step=body.step,
            system_prompt=body.system_prompt or None,
        )
        for token in tokens:
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
