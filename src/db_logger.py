"""Legacy shim — re-exports trace store (pipeline + ingestion SQLite logging)."""

from services.observability import trace_store as trace_store

from services.observability.trace_store import *  # noqa: F403
