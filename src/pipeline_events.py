"""
Thread-safe per-session event bus for live pipeline status over WebSockets.

Sync graph nodes call emit_event(); the async WebSocket handler drains the queue.
"""

from __future__ import annotations

import queue
import threading
from typing import Any, Dict, Optional

_lock = threading.Lock()
_queues: Dict[str, queue.Queue] = {}


def register_session(session_id: str) -> queue.Queue:
    """Return (and create if needed) the event queue for a session."""
    with _lock:
        if session_id not in _queues:
            _queues[session_id] = queue.Queue(maxsize=500)
        return _queues[session_id]


def emit_event(session_id: str, event: Dict[str, Any]) -> None:
    """Push a pipeline status event. Auto-creates the session queue if needed."""
    if not session_id:
        return
    q = register_session(session_id)
    try:
        q.put_nowait(event)
    except queue.Full:
        pass


def clear_session_events(session_id: str) -> None:
    """Drain pending events before a new pipeline run."""
    with _lock:
        q = _queues.get(session_id)
    if q is None:
        return
    while True:
        try:
            q.get_nowait()
        except queue.Empty:
            break
