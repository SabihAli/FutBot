from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, UploadFile, File, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict
from datetime import datetime, timezone
import asyncio
import os
import queue

from src.context import ConversationContext, Message
from src.pipeline_events import register_session, emit_event, clear_session_events
from src.db_logger import get_ingestion_event
from futbot_common import CorrelationIdMiddleware

app = FastAPI(title="FutBot API")
app.add_middleware(CorrelationIdMiddleware)

sessions_db: Dict[str, ConversationContext] = {}


def get_session(session_id: str) -> ConversationContext:
    if session_id not in sessions_db:
        sessions_db[session_id] = ConversationContext(session_id=session_id)
    return sessions_db[session_id]


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.post("/api/ingest")
async def ingest_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(None),
):
    raise HTTPException(
        status_code=501,
        detail="Ingestion moved to ingestion microservice (Phase 5).",
    )


@app.get("/api/ingest/status/{event_id}")
def ingest_status(event_id: int):
    event = get_ingestion_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Ingestion event not found")
    return dict(event)


def _run_pipeline(**kwargs):
    from src.graph import run_pipeline

    return run_pipeline(**kwargs)


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    session = get_session(request.session_id)

    user_msg = Message(
        role="user",
        content=request.message,
        timestamp=datetime.now(timezone.utc),
    )
    session.add_message(user_msg)

    full_history = [{"role": m.role, "content": m.content} for m in session.messages]

    register_session(request.session_id)
    clear_session_events(request.session_id)
    emit_event(request.session_id, {
        "type": "pipeline_start",
        "query": request.message,
    })

    try:
        reply, snapshot, turn_count = _run_pipeline(
            query=request.message,
            context_messages=full_history,
            session_id=request.session_id,
            snapshot=session.snapshot,
            snapshot_turn_count=session.snapshot_turn_count,
        )
    except Exception as e:
        emit_event(request.session_id, {
            "type": "pipeline_error",
            "message": str(e),
        })
        raise HTTPException(status_code=500, detail=str(e))

    session.snapshot = snapshot
    session.snapshot_turn_count = turn_count
    bot_msg = Message(
        role="assistant",
        content=reply,
        timestamp=datetime.now(timezone.utc),
    )
    session.add_message(bot_msg)

    return ChatResponse(reply=reply)


@app.websocket("/ws/pipeline")
async def pipeline_websocket(websocket: WebSocket, session_id: str = Query(...)):
    await websocket.accept()
    event_queue = register_session(session_id)
    await websocket.send_json({"type": "connected", "session_id": session_id})

    try:
        while True:
            try:
                event = await asyncio.to_thread(event_queue.get, True, 30.0)
                await websocket.send_json(event)
            except queue.Empty:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass


FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static")
