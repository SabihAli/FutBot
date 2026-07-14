"""Thread-safe per-session event bus for live pipeline status over WebSockets."""

from __future__ import annotations

import queue
import threading
from typing import Any

_lock = threading.Lock()
_queues: dict[str, queue.Queue] = {}


def register_session(session_id: str) -> queue.Queue:
    with _lock:
        if session_id not in _queues:
            _queues[session_id] = queue.Queue(maxsize=500)
        return _queues[session_id]


def emit_event(session_id: str, event: dict[str, Any]) -> None:
    if not session_id:
        return
    q = register_session(session_id)
    try:
        q.put_nowait(event)
    except queue.Full:
        pass


def clear_session_events(session_id: str) -> None:
    with _lock:
        q = _queues.get(session_id)
    if q is None:
        return
    while True:
        try:
            q.get_nowait()
        except queue.Empty:
            break
