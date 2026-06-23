"""
db_logger.py
============
Normalized SQLite trace logger for the FutBot RAG pipeline.

Schema (normalized):
  pipeline_runs       – one row per /api/chat call
  llm_calls           – one row per invoke_llm call (prompt, response, latency)
  loop_iterations     – one row per rewriter→judge retry cycle
  retrieval_events    – one row per retrieve_node call
  retrieved_chunks    – one row per chunk returned in a retrieval event
"""

import sqlite3
import os
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trace_logs.db")


# ---------------------------------------------------------------------------
# Schema Initialization
# ---------------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. Top-level run — one per user message processed through the pipeline
    c.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id          TEXT,
            original_query      TEXT NOT NULL,
            classification      TEXT,           -- SIMPLE | KNOWLEDGE | UNKNOWN
            total_iterations    INTEGER DEFAULT 0,
            final_answer        TEXT,
            reached_max_retries INTEGER DEFAULT 0,  -- boolean (0/1)
            started_at          TEXT NOT NULL,
            finished_at         TEXT,
            duration_ms         INTEGER
        )
    """)

    # 2. Each call to invoke_llm — captures prompt, response, latency
    c.execute("""
        CREATE TABLE IF NOT EXISTS llm_calls (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          INTEGER NOT NULL REFERENCES pipeline_runs(id),
            iteration       INTEGER DEFAULT 0,  -- which retry loop this belongs to
            step            TEXT NOT NULL,       -- rewriter | orchestrator | drafter | judge | simple_responder
            model_name      TEXT NOT NULL,
            api_url         TEXT,
            prompt          TEXT NOT NULL,
            raw_response    TEXT,               -- before think-tag stripping
            response        TEXT,               -- after stripping
            status_code     INTEGER,
            latency_ms      INTEGER,
            called_at       TEXT NOT NULL
        )
    """)

    # 3. One row per retry loop iteration (rewrite → retrieve → draft → judge)
    c.execute("""
        CREATE TABLE IF NOT EXISTS loop_iterations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          INTEGER NOT NULL REFERENCES pipeline_runs(id),
            iteration       INTEGER NOT NULL,
            rewritten_query TEXT,
            judge_status    TEXT,               -- PASS | FAIL
            judge_reasoning TEXT,
            created_at      TEXT NOT NULL
        )
    """)

    # 4. One row per retrieve_node call
    c.execute("""
        CREATE TABLE IF NOT EXISTS retrieval_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          INTEGER NOT NULL REFERENCES pipeline_runs(id),
            iteration_id    INTEGER REFERENCES loop_iterations(id),
            iteration       INTEGER DEFAULT 0,
            query_used      TEXT NOT NULL,      -- the rewritten query
            dense_count     INTEGER DEFAULT 0,
            sparse_count    INTEGER DEFAULT 0,
            fused_count     INTEGER DEFAULT 0,
            retrieved_at    TEXT NOT NULL
        )
    """)

    # 5. Normalized individual chunks returned by retrieval
    c.execute("""
        CREATE TABLE IF NOT EXISTS retrieved_chunks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id        INTEGER NOT NULL REFERENCES retrieval_events(id),
            run_id          INTEGER NOT NULL REFERENCES pipeline_runs(id),
            rank            INTEGER NOT NULL,
            chunk_id        TEXT NOT NULL,
            document        TEXT,
            rrf_score       REAL,
            source          TEXT,
            title           TEXT,
            url             TEXT,
            date_published  TEXT
        )
    """)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Context Manager for Pipeline Runs
# ---------------------------------------------------------------------------

class PipelineRunLogger:
    """
    Tracks a single pipeline_runs row and provides helpers to log each sub-event.
    Designed to be instantiated at the start of run_pipeline() and passed down.

    Thread-safety: a fresh SQLite connection is opened and closed for every
    operation, so this object can be shared across LangGraph worker threads.

    Usage:
        with PipelineRunLogger(session_id=..., original_query=...) as run:
            run.log_llm_call(step="rewriter", ...)
            run.log_retrieval(query_used=..., chunks=...)
            run.finish(classification="KNOWLEDGE", final_answer="...", ...)
    """

    def __init__(self, original_query: str, session_id: str = ""):
        self.original_query = original_query
        self.session_id = session_id
        self.run_id: Optional[int] = None
        self._start_ms = int(time.monotonic() * 1000)

    def _connect(self) -> sqlite3.Connection:
        """Open a fresh thread-local SQLite connection."""
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def __enter__(self):
        conn = self._connect()
        try:
            c = conn.cursor()
            c.execute(
                "INSERT INTO pipeline_runs (session_id, original_query, started_at) VALUES (?, ?, ?)",
                (self.session_id, self.original_query, _now())
            )
            self.run_id = c.lastrowid
            conn.commit()
        finally:
            conn.close()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False  # do not suppress exceptions

    # ---- LLM call logging -------------------------------------------------

    def log_llm_call(
        self,
        step: str,
        model_name: str,
        prompt: str,
        raw_response: str,
        response: str,
        api_url: str = "",
        status_code: Optional[int] = None,
        latency_ms: Optional[int] = None,
        iteration: int = 0,
    ):
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO llm_calls
                   (run_id, iteration, step, model_name, api_url, prompt, raw_response,
                    response, status_code, latency_ms, called_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    self.run_id, iteration, step, model_name, api_url,
                    prompt, raw_response, response, status_code, latency_ms, _now()
                )
            )
            conn.commit()
        finally:
            conn.close()

    # ---- Retrieval logging ------------------------------------------------

    def log_retrieval(
        self,
        query_used: str,
        fused_chunks: List[Dict[str, Any]],
        dense_count: int = 0,
        sparse_count: int = 0,
        iteration: int = 0,
        iteration_id: Optional[int] = None,
    ) -> int:
        """Inserts a retrieval_events row + individual retrieved_chunks rows."""
        conn = self._connect()
        try:
            c = conn.cursor()
            c.execute(
                """INSERT INTO retrieval_events
                   (run_id, iteration_id, iteration, query_used,
                    dense_count, sparse_count, fused_count, retrieved_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    self.run_id, iteration_id, iteration, query_used,
                    dense_count, sparse_count, len(fused_chunks), _now()
                )
            )
            event_id = c.lastrowid

            for rank, chunk in enumerate(fused_chunks, start=1):
                meta = chunk.get("metadata", {})
                c.execute(
                    """INSERT INTO retrieved_chunks
                       (event_id, run_id, rank, chunk_id, document, rrf_score,
                        source, title, url, date_published)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        event_id, self.run_id, rank,
                        chunk.get("chunk_id", ""),
                        chunk.get("document", ""),
                        chunk.get("rrf_score"),
                        meta.get("source", chunk.get("source", "")),
                        meta.get("title", chunk.get("title", "")),
                        meta.get("url", chunk.get("url", "")),
                        meta.get("date", chunk.get("date_published", "")),
                    )
                )

            conn.commit()
            return event_id
        finally:
            conn.close()

    # ---- Loop iteration logging -------------------------------------------

    def log_iteration(
        self,
        iteration: int,
        rewritten_query: str = "",
        judge_status: str = "",
        judge_reasoning: str = "",
    ) -> int:
        """Insert a loop_iterations row."""
        conn = self._connect()
        try:
            c = conn.cursor()
            c.execute(
                """INSERT INTO loop_iterations
                   (run_id, iteration, rewritten_query, judge_status, judge_reasoning, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (self.run_id, iteration, rewritten_query, judge_status, judge_reasoning, _now())
            )
            conn.commit()
            return c.lastrowid
        finally:
            conn.close()

    def update_iteration(
        self,
        iteration_id: int,
        judge_status: str = "",
        judge_reasoning: str = "",
    ):
        conn = self._connect()
        try:
            conn.execute(
                """UPDATE loop_iterations
                   SET judge_status=?, judge_reasoning=?
                   WHERE id=?""",
                (judge_status, judge_reasoning, iteration_id)
            )
            conn.commit()
        finally:
            conn.close()

    # ---- Final run completion ---------------------------------------------

    def finish(
        self,
        classification: str = "UNKNOWN",
        total_iterations: int = 0,
        final_answer: str = "",
        reached_max_retries: bool = False,
    ):
        elapsed = int(time.monotonic() * 1000) - self._start_ms
        conn = self._connect()
        try:
            conn.execute(
                """UPDATE pipeline_runs
                   SET classification=?, total_iterations=?, final_answer=?,
                       reached_max_retries=?, finished_at=?, duration_ms=?
                   WHERE id=?""",
                (
                    classification, total_iterations, final_answer,
                    int(reached_max_retries), _now(), elapsed,
                    self.run_id
                )
            )
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Legacy shim — kept so existing tests don't break
# ---------------------------------------------------------------------------

def log_pipeline_trace(
    original_query: str,
    classification: str,
    total_iterations: int,
    final_answer: str,
    loop_traces: list,
    session_id: str = "",
):
    """Thin compatibility wrapper for callers that use the old API."""
    with PipelineRunLogger(original_query=original_query, session_id=session_id) as run:
        for i, trace in enumerate(loop_traces, start=1):
            iter_id = run.log_iteration(
                iteration=i,
                rewritten_query=trace.get("rewritten_query", ""),
                judge_status=trace.get("judge_status", ""),
                judge_reasoning=trace.get("judge_reasoning", ""),
            )
        run.finish(
            classification=classification,
            total_iterations=total_iterations,
            final_answer=final_answer,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Initialize schema on import
init_db()
