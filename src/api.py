from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime, timezone
import os

from src.context import ConversationContext, Message
from src.data_layer import load_csv, chunk_text
from src.graph import run_pipeline
from src.retriever import ChromaRetriever, BM25Retriever

app = FastAPI(title="FutBot API")

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
        res = ingest_data()
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
def ingest_data():
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

    all_chunk_texts: List[str] = []
    bm25_texts: List[str] = []
    all_metadatas: List[Dict[str, str]] = []

    for art in articles:
        # chunk_text returns List[str]
        chunks = chunk_text(art.body)
        date_str = art.date_published.isoformat() if art.date_published else ""
        for chunk in chunks:
            all_chunk_texts.append(chunk)
            bm25_texts.append(f"{art.title}\n{art.title}\n{art.title}\n{chunk}")
            all_metadatas.append({
                "url": art.url,
                "title": art.title,
                "source": art.source,
                "date": date_str,
            })

    chunk_ids = [f"chunk_{i}" for i in range(len(all_chunk_texts))]

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

    # 2. Build rolling context (last 10 msgs, excluding the one we just added)
    context_msgs = session.get_context_messages()
    history_for_llm = [m.model_dump() for m in context_msgs[:-1]]

    # 3. Run the full LangGraph pipeline
    try:
        reply = run_pipeline(
            query=request.message,
            context_messages=history_for_llm,
            session_id=request.session_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 4. Record assistant reply
    bot_msg = Message(
        role="assistant",
        content=reply,
        timestamp=datetime.now(timezone.utc),
    )
    session.add_message(bot_msg)

    return ChatResponse(reply=reply)


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
