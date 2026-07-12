from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, UploadFile, File, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime, timezone
import asyncio
import os
import queue
import tempfile

from src.context import ConversationContext, Message
from src.data_layer import load_csv
from src.ingestion.chunking.smart_chunker import SmartChunker
from src.ingestion.indexer import chunked_to_index_payload
from src.graph import run_pipeline
from src.retriever import ChromaRetriever, BM25Retriever
from src.pipeline_events import register_session, emit_event, clear_session_events
from src.ingestion.pipeline import ingest_upload, should_process_in_background
from src.ingestion.background import run_background_ingest
from src.ingestion.extractors.pdf import count_pdf_vlm_work
from src.ingestion.extractors.registry import get_extension, get_file_type
from src.ingestion.errors import (
    FootballRelevanceError,
    UnsupportedFormatError,
    EmptyFileError,
    IngestionProviderError,
)
from src.db_logger import (
    compute_content_hash,
    find_duplicate_ingestion,
    create_ingestion_event,
    update_ingestion_event,
    get_ingestion_event,
)
from futbot_common import CorrelationIdMiddleware

app = FastAPI(title="FutBot API")
app.add_middleware(CorrelationIdMiddleware)

# ---------------------------------------------------------------------------
# Global State
# ---------------------------------------------------------------------------
sessions_db: Dict[str, ConversationContext] = {}

# Global Retrievers — initialized once, shared across all requests
global_chroma = ChromaRetriever()
global_bm25 = BM25Retriever()


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
def populate_db_on_startup():
    """Load, chunk and index all articles automatically when the server boots.
    If persistent data already exists on disk, skip ingestion entirely.
    """
    from src.retriever import BM25_PATH
    already_have_chroma = global_chroma.count() > 0
    already_have_bm25 = global_bm25.load()  # tries to load from disk

    if already_have_chroma and already_have_bm25:
        print(f"✅ Persistent index found: {global_chroma.count()} chunks in ChromaDB. Skipping ingestion.")
        return

    print("🔄 No persistent index found. Running ingestion (one-time, may take a few minutes)...")
    try:
        res = ingest_csv_bootstrap()
        n_arts = res.get("articles_ingested", 0)
        n_chunks = res.get("total_chunks_indexed", 0)
        print(f"✅ Ingestion complete: {n_arts} articles → {n_chunks} chunks indexed.")
    except Exception as e:
        print(f"⚠️  Ingestion failed on startup: {e}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_session(session_id: str) -> ConversationContext:
    if session_id not in sessions_db:
        sessions_db[session_id] = ConversationContext(session_id=session_id)
    return sessions_db[session_id]


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


class SessionResponse(BaseModel):
    session_id: str
    messages: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/ingest")
async def ingest_endpoint(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(None),
):
    """Bootstrap CSV ingestion when no file is sent; otherwise ingest an uploaded file."""
    if file is None:
        return ingest_csv_bootstrap()

    filename = file.filename or "upload"
    file_bytes = await file.read()
    content_hash = compute_content_hash(file_bytes)
    duplicate = find_duplicate_ingestion(content_hash)
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "DuplicateUploadError",
                "message": (
                    f"This file has already been uploaded as '{duplicate['filename']}' "
                    f"(ingestion #{duplicate['id']}). Duplicate uploads are not allowed."
                ),
                "filename": filename,
                "existing_ingestion_id": duplicate["id"],
                "existing_filename": duplicate["filename"],
            },
        )

    suffix = os.path.splitext(filename)[1]
    file_type = get_file_type(get_extension(filename))

    tmp_path = None
    event_id = None
    try:
        if suffix.lower() == ".pdf" and file_bytes:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            if should_process_in_background(tmp_path, filename):
                images_total = count_pdf_vlm_work(tmp_path)
                event_id = create_ingestion_event(
                    filename=filename,
                    file_type="pdf",
                    status="processing",
                    images_total=images_total,
                    images_processed=0,
                    content_hash=content_hash,
                )
                background_tasks.add_task(
                    run_background_ingest,
                    event_id,
                    tmp_path,
                    filename,
                    global_chroma,
                    global_bm25,
                    images_total,
                )
                return JSONResponse(
                    status_code=202,
                    content={
                        "status": "processing",
                        "event_id": event_id,
                        "filename": filename,
                        "file_type": "pdf",
                        "images_total": images_total,
                        "message": (
                            "Your file is being processed in the background. "
                            "You can continue chatting."
                        ),
                        "status_url": f"/api/ingest/status/{event_id}",
                    },
                )

            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
                tmp_path = None

        event_id = create_ingestion_event(
            filename=filename,
            file_type=file_type,
            status="processing",
            content_hash=content_hash,
        )
        result = ingest_upload(
            file_bytes,
            filename,
            global_chroma,
            global_bm25,
            ingestion_id=event_id,
        )
        update_ingestion_event(
            event_id,
            status="success",
            file_type=result["file_type"],
            chunk_count=result["chunks_indexed"],
            relevance_verdict=result["relevance_verdict"],
            duration_ms=result["duration_ms"],
        )
        result["event_id"] = event_id
        return result
    except FootballRelevanceError as e:
        if event_id is not None:
            update_ingestion_event(
                event_id,
                status="rejected",
                relevance_verdict="NO",
                error=str(e),
            )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "FootballRelevanceError",
                "message": str(e),
                "filename": e.filename,
            },
        )
    except UnsupportedFormatError as e:
        if event_id is not None:
            update_ingestion_event(event_id, status="failed", error=str(e))
        raise HTTPException(
            status_code=415,
            detail={
                "error": "UnsupportedFormatError",
                "message": str(e),
                "filename": e.filename,
            },
        )
    except EmptyFileError as e:
        if event_id is not None:
            update_ingestion_event(event_id, status="failed", error=str(e))
        raise HTTPException(
            status_code=400,
            detail={
                "error": "EmptyFileError",
                "message": str(e),
                "filename": e.filename,
            },
        )
    except IngestionProviderError as e:
        if event_id is not None:
            update_ingestion_event(event_id, status="failed", error=str(e))
        raise HTTPException(
            status_code=422,
            detail={
                "error": "IngestionProviderError",
                "message": str(e),
            },
        )
    except Exception as e:
        if event_id is not None:
            update_ingestion_event(event_id, status="failed", error=str(e))
        raise
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.get("/api/ingest/status/{event_id}")
def ingest_status(event_id: int):
    event = get_ingestion_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Ingestion event not found")

    payload = dict(event)
    if event["status"] == "processing":
        payload["message"] = (
            "Your file is being processed in the background. "
            "You can continue chatting."
        )
    return payload


def ingest_csv_bootstrap():
    """Load football articles from CSV, chunk them, and index into ChromaDB + BM25."""
    csv_path = os.path.join(os.path.dirname(__file__), "..", "final-articles.csv")
    articles = load_csv(csv_path)

    if not articles:
        return {
            "status": "success",
            "articles_ingested": 0,
            "total_chunks_indexed": 0,
            "message": "No new articles found.",
        }

    chunker = SmartChunker()
    all_chunk_texts: List[str] = []
    bm25_texts: List[str] = []
    all_metadatas: List[Dict[str, str]] = []
    chunk_ids: List[str] = []
    id_offset = 0

    for art in articles:
        chunks = chunker.chunk_article(art.body, art.title)
        date_str = art.date_published.isoformat() if art.date_published else ""
        texts, bm25, metas, ids = chunked_to_index_payload(
            chunks,
            source_file=art.title,
            extra_metadata={
                "url": art.url,
                "title": art.title,
                "source": art.source,
                "date": date_str,
            },
            id_prefix="chunk",
            id_offset=id_offset,
        )
        all_chunk_texts.extend(texts)
        bm25_texts.extend(bm25)
        all_metadatas.extend(metas)
        chunk_ids.extend(ids)
        id_offset += len(texts)

    # Index into ChromaDB (dense) and BM25 (sparse)
    global_chroma.add_documents(chunk_ids, all_chunk_texts, all_metadatas)
    global_bm25.build_index(bm25_texts, chunk_ids)
    global_bm25.save()  # persist BM25 to disk for future runs

    return {
        "status": "success",
        "articles_ingested": len(articles),
        "total_chunks_indexed": len(all_chunk_texts),
        "message": "Articles scraped, chunked, and fully indexed in Vector DB and BM25.",
    }


@app.get("/api/session/{session_id}", response_model=SessionResponse)
def get_session_endpoint(session_id: str):
    """Retrieve the full message history for a session (for UI history persistence)."""
    session = get_session(session_id)
    return {
        "session_id": session.session_id,
        "messages": [m.model_dump() for m in session.messages],
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """Process a user message through the full LangGraph RAG pipeline."""
    session = get_session(request.session_id)

    # 1. Record user message
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
        reply, snapshot, turn_count = run_pipeline(
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
    """Stream live pipeline stage updates for a session."""
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


# ---------------------------------------------------------------------------
# Frontend — serve the React/Vanilla JS app
# ---------------------------------------------------------------------------
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

# Mount static files LAST so API routes take priority
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")), name="static")
