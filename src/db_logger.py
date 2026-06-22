import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "trace_logs.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create QueryLogs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS query_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            original_query TEXT,
            orchestrator_classification TEXT,
            total_iterations INTEGER,
            final_answer TEXT
        )
    """)
    
    # Create LoopTraces table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS loop_traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_id INTEGER,
            iteration INTEGER,
            rewritten_query TEXT,
            retrieved_chunk_ids TEXT,  -- JSON string
            judge_status TEXT,
            judge_reasoning TEXT,
            FOREIGN KEY(query_id) REFERENCES query_logs(id)
        )
    """)
    
    conn.commit()
    conn.close()

def log_pipeline_trace(
    original_query: str,
    classification: str,
    total_iterations: int,
    final_answer: str,
    loop_traces: list
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Insert main query log
    cursor.execute("""
        INSERT INTO query_logs (original_query, orchestrator_classification, total_iterations, final_answer)
        VALUES (?, ?, ?, ?)
    """, (original_query, classification, total_iterations, final_answer))
    
    query_id = cursor.lastrowid
    
    # Insert traces for each loop
    for i, trace in enumerate(loop_traces):
        cursor.execute("""
            INSERT INTO loop_traces (query_id, iteration, rewritten_query, retrieved_chunk_ids, judge_status, judge_reasoning)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            query_id,
            i + 1,
            trace.get("rewritten_query", ""),
            json.dumps(trace.get("retrieved_chunk_ids", [])),
            trace.get("judge_status", ""),
            trace.get("judge_reasoning", "")
        ))
        
    conn.commit()
    conn.close()

# Initialize on import
init_db()
