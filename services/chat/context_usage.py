from __future__ import annotations

from dataclasses import dataclass, field

import tiktoken

_DEFAULT_ENCODING = "cl100k_base"
_enc = tiktoken.get_encoding(_DEFAULT_ENCODING)


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_enc.encode(text))


@dataclass
class ContextInput:
    snapshot: str = ""
    hot_messages: list[dict[str, str]] = field(default_factory=list)
    current_query: str = ""
    memory_content: str = ""
    retrieved_chunks: str = ""


def compute_context_usage(
    inp: ContextInput,
    limit_tokens: int,
    compress_threshold_pct: int = 85,
) -> dict:
    snapshot_t = count_tokens(inp.snapshot)
    hot_t = sum(
        count_tokens(f"{m['role']}: {m['content']}") for m in inp.hot_messages
    )
    query_t = count_tokens(inp.current_query)
    memory_t = count_tokens(inp.memory_content)
    chunks_t = count_tokens(inp.retrieved_chunks)
    used = snapshot_t + hot_t + query_t + memory_t + chunks_t
    percent = round(used / limit_tokens * 100, 1) if limit_tokens else 0.0
    return {
        "used_tokens": used,
        "limit_tokens": limit_tokens,
        "percent_used": percent,
        "breakdown": {
            "snapshot": snapshot_t,
            "hot_messages": hot_t,
            "current_query": query_t,
            "memory": memory_t,
            "retrieved_chunks": chunks_t,
        },
        "should_compress": percent >= compress_threshold_pct,
    }
